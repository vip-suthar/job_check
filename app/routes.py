from io import BytesIO

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from marshmallow import ValidationError
from sqlalchemy import select
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from app import dashboard, db
from app.excel import check_workbook, read_workbook
from app.fetch import MAX_POSTINGS, USER_AGENT, FetchError, get_page, get_robots, posting_links, posting_text
from app.forms import MAX_LENGTH, MIN_LENGTH, BulkForm, CheckForm, FeedbackForm, UrlForm
from app.models import Check, Feedback, RuleHit
from app.schemas import CheckRequestSchema, CheckSchema
from detector.rules import EXPLANATIONS, highlight
from detector.verdict import check

bp = Blueprint("main", __name__)


def save_check(text, source, source_url=None):
    result = check(text)
    record = Check(
        source=source,
        source_url=source_url,
        text=text,
        rule_score=result["score"],
        model_probability=result["probability"],
        indicator=result["indicator"],
        hits=[
            RuleHit(rule_id=h["rule_id"], matched_text=h["matched_text"],
                    span_start=h["start"], span_end=h["end"])
            for h in result["hits"]
        ],
    )
    db.session.add(record)
    db.session.commit()
    # posting text is never logged
    current_app.logger.info(
        "check id=%d source=%s score=%d indicator=%s flags=%d",
        record.id, source, record.rule_score, record.indicator, record.flag_count,
    )
    return record


@bp.route("/", methods=["GET", "POST"])
def index():
    form = CheckForm()
    if form.validate_on_submit():
        record = save_check(form.text.data, "form")
        return redirect(url_for("main.result", check_id=record.id))
    return render_template("index.html", form=form, url_form=UrlForm())


def cannot_read(reason):
    current_app.logger.info("url fetch failed: %s", reason)
    flash(f"Could not read a posting from that link: {reason}. "
          "Please copy the posting text and paste it below.", "warning")
    return redirect(url_for("main.index"))


@bp.route("/check-url", methods=["POST"])
def check_url():
    form = UrlForm()
    if not form.validate_on_submit():
        flash("Please enter a valid web address, starting with http:// or https://.", "warning")
        return redirect(url_for("main.index"))
    try:
        page_url, soup = get_page(form.url.data)
    except FetchError as e:
        return cannot_read(e)

    links = {} if form.single.data else posting_links(soup, page_url)
    if links:
        return check_listing(page_url, links)

    text = posting_text(soup)
    if len(text) < MIN_LENGTH:
        return cannot_read("the page has almost no text, it may need JavaScript or a login to show the posting")
    if len(text) > MAX_LENGTH:
        flash(f"The page was longer than {MAX_LENGTH:,} characters, so only the first {MAX_LENGTH:,} were checked.",
              "info")
    record = save_check(text[:MAX_LENGTH], "url", page_url)
    return redirect(url_for("main.result", check_id=record.id))


def check_listing(page_url, links):
    """The link was a page listing several postings, so open each one and check it on its own."""
    robots = get_robots(page_url)
    items = []
    opened = 0
    # big job boards can link hundreds of postings, only list the first 50
    for url, title in list(links.items())[:50]:
        item = {"url": url, "title": title, "check": None, "note": ""}
        items.append(item)
        if opened == MAX_POSTINGS:
            item["note"] = f"Not opened, only the first {MAX_POSTINGS} postings are checked at once."
            continue
        if not robots.can_fetch(USER_AGENT, url):
            item["note"] = "Not opened, the site's robots.txt does not allow it."
            continue
        opened += 1
        try:
            posting_url, posting_page = get_page(url)
        except FetchError as e:
            item["note"] = f"Could not open: {e}."
            continue
        text = posting_text(posting_page)
        if len(text) < MIN_LENGTH:
            item["note"] = "Could not find the posting text on that page."
            continue
        item["check"] = save_check(text[:MAX_LENGTH], "url", posting_url)
        if not item["title"]:
            item["title"] = text.split("\n")[0][:150]

    checked = [item["check"] for item in items if item["check"]]
    flagged = len([c for c in checked if c.indicator == "red_flags"])
    current_app.logger.info("listing links=%d checked=%d red_flags=%d", len(links), len(checked), flagged)
    return render_template("listing.html", page_url=page_url, total=len(links), items=items,
                           checked=len(checked), flagged=flagged, url_form=UrlForm())


@bp.route("/bulk", methods=["GET", "POST"])
def bulk():
    form = BulkForm()
    if form.validate_on_submit():
        upload = form.file.data
        try:
            wb = read_workbook(upload)
        except ValueError as e:
            form.file.errors.append(str(e))
        else:
            counts = check_workbook(wb, save_check)
            current_app.logger.info("bulk red_flags=%d no_flags=%d skipped=%d",
                                    counts["red_flags"], counts["no_flags"], counts["skipped"])
            out = BytesIO()
            wb.save(out)
            out.seek(0)
            name = secure_filename(upload.filename).rsplit(".", 1)[0] or "postings"
            return send_file(out, as_attachment=True, download_name=f"{name}_jobcheck.xlsx",
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return render_template("bulk.html", form=form)


@bp.route("/check/<int:check_id>")
def result(check_id):
    record = db.get_or_404(Check, check_id)
    flags = {}
    for h in record.hits:
        flags.setdefault(h.rule_id, []).append(h.matched_text)
    highlighted = highlight(record.text, [(h.span_start, h.span_end) for h in record.hits])
    return render_template("result.html", check=record, flags=flags, explanations=EXPLANATIONS,
                           highlighted=highlighted, feedback_form=FeedbackForm())


@bp.route("/check/<int:check_id>/feedback", methods=["POST"])
def feedback(check_id):
    db.get_or_404(Check, check_id)
    form = FeedbackForm()
    if form.validate_on_submit():
        db.session.add(Feedback(check_id=check_id, user_says=form.user_says.data,
                                comment=form.comment.data or None))
        db.session.commit()
        current_app.logger.info("feedback check id=%d user_says=%s", check_id, form.user_says.data)
        flash("Thank you for your feedback.", "success")
    else:
        flash("Your feedback could not be saved. Please try again.", "warning")
    return redirect(url_for("main.result", check_id=check_id))


@bp.route("/history")
def history():
    page = db.paginate(select(Check).order_by(Check.id.desc()), per_page=20)
    return render_template("history.html", page=page)


@bp.route("/dashboard")
def dashboard_view():
    stats = dashboard.summary()
    charts = [dashboard.checks_over_time(), dashboard.top_flags()] if stats["total"] else []
    return render_template("dashboard.html", stats=stats, charts=[c for c in charts if c])


@bp.route("/api/check", methods=["POST"])
def api_check():
    try:
        data = CheckRequestSchema().load(request.get_json(silent=True))
    except ValidationError as e:
        return {"errors": e.messages}, 400
    record = save_check(data["text"], "api")
    return CheckSchema().dump(record), 201


@bp.app_errorhandler(HTTPException)
def http_error(e):
    if request.path.startswith("/api/"):
        return {"errors": {"_request": [e.name]}}, e.code
    return render_template("error.html", error=e), e.code
