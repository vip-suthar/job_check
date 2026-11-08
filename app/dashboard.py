import base64
from datetime import date, datetime, timedelta
from io import BytesIO

from matplotlib.figure import Figure
from sqlalchemy import distinct, func, select

from app import db
from app.models import Check, Feedback, RuleHit

DAYS = 30


def png(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png")
    return base64.b64encode(buf.getvalue()).decode()


def checks_over_time():
    since = datetime.combine(date.today() - timedelta(days=DAYS - 1), datetime.min.time())
    day = func.date(Check.created_at)
    rows = db.session.execute(
        select(day, Check.indicator, func.count())
        .where(Check.created_at >= since)
        .group_by(day, Check.indicator)
    ).all()
    days = [since.date() + timedelta(days=i) for i in range(DAYS)]
    counts = {(d, ind): n for d, ind, n in rows}
    flagged = [counts.get((d.isoformat(), "red_flags"), 0) for d in days]
    clean = [counts.get((d.isoformat(), "no_flags"), 0) for d in days]

    fig = Figure(figsize=(8, 3), layout="constrained")
    ax = fig.subplots()
    ax.bar(days, flagged, color="#dc3545", label="Red flags found")
    ax.bar(days, clean, bottom=flagged, color="#adb5bd", label="No common red flags")
    ax.set_title(f"Checks per day, last {DAYS} days")
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.legend(loc="upper left")
    ax.tick_params(axis="x", labelrotation=45)
    return png(fig)


def top_flags(limit=10):
    rows = db.session.execute(
        select(RuleHit.rule_id, func.count(distinct(RuleHit.check_id)).label("n"))
        .group_by(RuleHit.rule_id)
        .order_by(func.count(distinct(RuleHit.check_id)).desc())
        .limit(limit)
    ).all()
    if not rows:
        return None
    fig = Figure(figsize=(8, 0.5 * len(rows) + 1), layout="constrained")
    ax = fig.subplots()
    ax.barh([r[0] for r in rows][::-1], [r[1] for r in rows][::-1], color="#dc3545")
    ax.set_title("Most frequent red flags (number of checks)")
    ax.xaxis.get_major_locator().set_params(integer=True)
    return png(fig)


def summary():
    total = db.session.scalar(select(func.count()).select_from(Check))
    flagged = db.session.scalar(select(func.count()).where(Check.indicator == "red_flags"))
    feedback = dict(db.session.execute(
        select(Feedback.user_says, func.count()).group_by(Feedback.user_says)
    ).all())
    return {
        "total": total,
        "flagged": flagged,
        "flagged_pct": round(100 * flagged / total) if total else 0,
        "correct": feedback.get("correct", 0),
        "incorrect": feedback.get("incorrect", 0),
    }
