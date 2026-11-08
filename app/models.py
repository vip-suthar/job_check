from datetime import datetime

from app import db


class Check(db.Model):
    __tablename__ = "checks"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    source = db.Column(db.String(10), nullable=False)  # form, bulk, api, url
    text = db.Column(db.Text, nullable=False)
    rule_score = db.Column(db.Integer, nullable=False)
    model_probability = db.Column(db.Float)  # TODO: filled by the ML model
    indicator = db.Column(db.String(20), nullable=False)  # red_flags or no_flags
    hits = db.relationship("RuleHit", backref="check", cascade="all, delete-orphan")

    @property
    def flag_count(self):
        return len({h.rule_id for h in self.hits})

    @property
    def label(self):
        if self.indicator == "red_flags":
            return f"Red flags found ({self.flag_count})"
        return "No common red flags found"


class RuleHit(db.Model):
    __tablename__ = "rule_hits"

    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey("checks.id"), nullable=False, index=True)
    rule_id = db.Column(db.String(40), nullable=False, index=True)
    matched_text = db.Column(db.Text, nullable=False)
    # character offsets in checks.text, stored so old results still highlight
    # correctly after the rules change
    span_start = db.Column(db.Integer, nullable=False)
    span_end = db.Column(db.Integer, nullable=False)


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey("checks.id"), nullable=False, index=True)
    user_says = db.Column(db.String(10), nullable=False)  # correct or incorrect
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
