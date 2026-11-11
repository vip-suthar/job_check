from collections import Counter
from datetime import date, datetime, timedelta

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import distinct, func, select

from app import db
from app.forms import MAX_LENGTH, MIN_LENGTH, clean_whitespace
from app.models import Check, Feedback, RuleHit
from detector.rules import EXPLANATIONS

MAX_ROWS = 500
TEXT_HEADERS = {"text", "posting", "job posting", "description", "message"}
DISCLAIMER = ("JobCheck is a screening aid, not a verdict. "
              "'No common red flags found' does not mean a posting is safe.")
BOLD = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="DEE2E6")
RED_FILL = PatternFill("solid", fgColor="F8D7DA")


def style_header(ws, widths, row=1):
    for cell in ws[row]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


def read_workbook(stream):
    try:
        wb = load_workbook(stream)
    except Exception:  # openpyxl raises many different errors for non-xlsx or corrupt files
        raise ValueError("Could not read this file as an Excel workbook.") from None
    if wb.worksheets[0].max_row - 1 > MAX_ROWS:
        raise ValueError(f"The first sheet has more than {MAX_ROWS} postings. Split it into smaller files.")
    return wb


def check_workbook(wb, save):
    """Check each posting on the first sheet, add result columns and a summary sheet."""
    ws = wb.worksheets[0]
    headers = [str(c.value or "").strip().lower() for c in ws[1]]
    text_col = next((i for i, h in enumerate(headers) if h in TEXT_HEADERS), 0) + 1
    first = ws.max_column + 1
    for offset, title in enumerate(("JobCheck result", "Score", "Red flags")):
        ws.cell(row=1, column=first + offset, value=title)

    counts, flag_counts = Counter(), Counter()
    for r in range(2, ws.max_row + 1):
        value = ws.cell(row=r, column=text_col).value
        text = clean_whitespace(str(value)) if value is not None else ""
        if not text:
            continue
        if not MIN_LENGTH <= len(text) <= MAX_LENGTH:
            ws.cell(row=r, column=first, value=f"Skipped: text must be {MIN_LENGTH} to {MAX_LENGTH:,} characters")
            counts["skipped"] += 1
            continue
        record = save(text, "bulk")
        flags = list(dict.fromkeys(h.rule_id for h in record.hits))
        ws.cell(row=r, column=first, value=record.label)
        ws.cell(row=r, column=first + 1, value=record.rule_score)
        ws.cell(row=r, column=first + 2, value="; ".join(EXPLANATIONS.get(f, f) for f in flags))
        if record.indicator == "red_flags":
            for c in range(1, first + 3):
                ws.cell(row=r, column=c).fill = RED_FILL
        counts[record.indicator] += 1
        flag_counts.update(flags)

    style_header(ws, {get_column_letter(first): 28, get_column_letter(first + 2): 60})
    ws.freeze_panes = "A2"

    summary = wb.create_sheet("JobCheck summary")
    summary.append(["Result", "Postings"])
    summary.append(["Red flags found", counts["red_flags"]])
    summary.append(["No common red flags found", counts["no_flags"]])
    summary.append(["Skipped (too short or too long)", counts["skipped"]])
    summary.append([])
    summary.append(["Red flag", "Postings"])
    for rule_id, n in flag_counts.most_common():
        summary.append([EXPLANATIONS.get(rule_id, rule_id), n])
    summary.append([])
    summary.append([DISCLAIMER])
    style_header(summary, {"A": 60, "B": 12})
    style_header(summary, {}, row=6)
    return counts


def month_bounds(year, month):
    return datetime(year, month, 1), datetime(year + month // 12, month % 12 + 1, 1)


def monthly_report(year, month):
    start, end = month_bounds(year, month)
    in_month = (Check.created_at >= start) & (Check.created_at < end)
    total = db.session.scalar(select(func.count()).where(in_month))
    flagged = db.session.scalar(select(func.count()).where(in_month, Check.indicator == "red_flags"))
    sources = db.session.execute(
        select(Check.source, func.count()).where(in_month).group_by(Check.source).order_by(Check.source)
    ).all()
    feedback = dict(db.session.execute(
        select(Feedback.user_says, func.count()).join(Check, Feedback.check_id == Check.id)
        .where(in_month).group_by(Feedback.user_says)
    ).all())

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Measure", "Value"])
    summary.append(["Month", start.strftime("%B %Y")])
    summary.append(["Checks", total])
    summary.append(["Red flags found", flagged])
    summary.append(["Share flagged (%)", round(100 * flagged / total, 1) if total else 0])
    for source, n in sources:
        summary.append([f"Checks from {source}", n])
    summary.append(["Feedback: result right", feedback.get("correct", 0)])
    summary.append(["Feedback: result wrong", feedback.get("incorrect", 0)])
    style_header(summary, {"A": 26, "B": 16})

    day = func.date(Check.created_at)
    rows = db.session.execute(
        select(day, Check.indicator, func.count()).where(in_month).group_by(day, Check.indicator)
    ).all()
    per_day = {(d, ind): n for d, ind, n in rows}
    daily = wb.create_sheet("Daily")
    daily.append(["Date", "Red flags found", "No common red flags"])
    d = start.date()
    while d < end.date():
        key = d.isoformat()
        daily.append([d, per_day.get((key, "red_flags"), 0), per_day.get((key, "no_flags"), 0)])
        d += timedelta(days=1)
    for cell in daily["A"][1:]:
        cell.number_format = "DD MMM"
    style_header(daily, {"A": 12, "B": 16, "C": 20})
    daily.freeze_panes = "A2"

    chart = BarChart()
    chart.type, chart.grouping, chart.overlap = "col", "stacked", 100
    chart.title = "Checks per day"
    chart.y_axis.title = "Checks"
    chart.add_data(Reference(daily, min_col=2, max_col=3, min_row=1, max_row=daily.max_row), titles_from_data=True)
    chart.set_categories(Reference(daily, min_col=1, min_row=2, max_row=daily.max_row))
    chart.width, chart.height = 24, 9
    summary.add_chart(chart, "D2")

    flags = wb.create_sheet("Red flags")
    flags.append(["Rule", "Explanation", "Checks"])
    for rule_id, n in db.session.execute(
        select(RuleHit.rule_id, func.count(distinct(RuleHit.check_id)).label("n"))
        .join(Check, RuleHit.check_id == Check.id).where(in_month)
        .group_by(RuleHit.rule_id).order_by(func.count(distinct(RuleHit.check_id)).desc())
    ):
        flags.append([rule_id, EXPLANATIONS.get(rule_id, rule_id), n])
    style_header(flags, {"A": 24, "B": 60, "C": 10})
    flags.freeze_panes = "A2"
    return wb
