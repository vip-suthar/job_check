import numpy as np
import pandas as pd

from app.models import Check
from detector import model, verdict
from tests.test_app import GENUINE as POSTING, client, submit  # noqa: F401

SCAMS = ["Earn daily from home, pay registration fee on WhatsApp",
         "Pay registration fee and earn daily on WhatsApp",
         "WhatsApp us, small registration fee, earn daily"]
GENUINE = ["Backend engineer role in our Bengaluru office, apply on careers page",
           "Our Bengaluru office is hiring an engineer, apply through the careers page",
           "Apply on our careers page for the engineer role in Bengaluru office"]


class FakeModel:
    def __init__(self, p):
        self.p = p

    def predict_proba(self, texts):
        return np.array([[1 - self.p, self.p] for _ in texts])


def test_posting_text_joins_text_fields_only():
    df = pd.DataFrame({"title": ["Clerk"], "company_profile": [None], "description": ["Files"],
                       "requirements": ["Typing"], "benefits": [None], "has_company_logo": [1]})
    assert list(model.posting_text(df)) == ["Clerk  Files Typing "]


def test_trained_model_ranks_scam_text_higher():
    clf = model.train(SCAMS + GENUINE, [1, 1, 1, 0, 0, 0])
    scam, genuine = clf.predict_proba(["Pay the registration fee on WhatsApp",
                                       "Engineer role at our Bengaluru office"])[:, 1]
    assert scam > 0.5 > genuine


def test_flagged_uses_either_threshold():
    assert verdict.flagged(5, None, 1, 0.5)
    assert verdict.flagged(0, 0.7, 1, 0.5)
    assert not verdict.flagged(0, 0.3, 1, 0.5)
    assert not verdict.flagged(0, None, 1, 0.5)


def test_verdict_without_model_is_rules_only():
    result = verdict.check(GENUINE[0])
    assert (result["probability"], result["indicator"], result["hits"]) == (None, "no_flags", [])


def test_verdict_model_can_flag_without_rule_hits(monkeypatch):
    monkeypatch.setattr(model, "load", lambda: FakeModel(0.9))
    result = verdict.check(GENUINE[0])
    assert (result["probability"], result["indicator"], result["hits"]) == (0.9, "red_flags", [])


def test_app_stores_model_probability(client, monkeypatch):
    monkeypatch.setattr(model, "load", lambda: FakeModel(0.2))
    submit(client, POSTING)
    record = Check.query.one()
    assert (record.model_probability, record.indicator) == (0.2, "no_flags")
