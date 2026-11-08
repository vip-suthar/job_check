from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from marshmallow import ValidationError
from sqlalchemy import select
from werkzeug.exceptions import HTTPException

from app import dashboard, db
from app.forms import CheckForm, FeedbackForm
from app.models import Check, Feedback, RuleHit
from app.schemas import CheckRequestSchema, CheckSchema
from detector.rules import EXPLANATIONS, check, highlight

bp = Blueprint("main", __name__)


def save_check(text, source):
    result = check(text)
    record = Check(
        source=source,
        text=text,
        rule_score=result["score"],
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
    return render_template("index.html", form=form)


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
