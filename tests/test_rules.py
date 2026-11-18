import pytest

from detector.rules import RULES, check, highlight

GENUINE = ("We are hiring a backend engineer with three years of Python experience "
           "to join our Bengaluru office. Apply through our careers page.")


def flags(text, **kwargs):
    return {h["rule_id"] for h in check(text, **kwargs)["hits"]}


@pytest.mark.parametrize("rule_id, text", [
    ("payment_fee", "Pay a refundable security deposit to confirm"),
    ("upfront_payment", "Just pay a small amount to activate your ID"),
    ("upfront_payment", "Deposit Rs. 2,000 to start"),
    ("off_platform_contact", "Message us on t.me/jobs_now"),
    ("unrealistic_pay", "Earn ₹5000 per day from your phone"),
    ("unrealistic_pay", "Rs.300/task, daily payout"),
    ("get_rich_quick", "Be your own boss with unlimited income"),
    ("id_documents", "Send your Aadhaar and PAN card photos"),
    ("bank_details", "Share your bank account number and IFSC"),
    ("otp_request", "Tell us the OTP you receive"),
    ("free_email", "Send your CV to hr.infosys.jobs@gmail.com"),
    ("urgency", "Limited seats, join today"),
    ("task_scam", "Like YouTube videos and rate products"),
    ("task_scam", "Earn by liking videos and rating hotels"),
    ("no_interview", "Direct joining, no interview"),
    ("no_experience", "No experience required"),
    ("typing_jobs", "Home based copy paste work and form filling"),
    ("money_transfer", "Receive payments on behalf of our clients via Western Union"),
    ("guaranteed_job", "100% job guarantee after training"),
    ("wallet_recharge", "Recharge your wallet to withdraw your commission"),
    ("unnamed_employer", "Hiring for a reputed MNC, company name will be disclosed later"),
])
def test_rule_fires(rule_id, text):
    assert rule_id in flags(text)


def test_rule_ids_unique_and_count_in_plan_range():
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids))
    assert 15 <= len(ids) <= 20


def test_genuine_posting_has_no_flags():
    assert check(GENUINE) == {"score": 0, "indicator": "no_flags", "hits": []}


def test_score_counts_each_rule_once():
    result = check("Pay the registration fee. Then pay the joining fee. Contact on WhatsApp.")
    assert len(result["hits"]) == 3
    assert result["score"] == 5
    assert result["indicator"] == "red_flags"


@pytest.mark.parametrize("text", [
    "We never charge any registration fee.",
    "There is no registration fee.",
    "We do not ask for your bank account details.",
    "Don't share your OTP with anyone.",
])
def test_negation_suppresses_match(text):
    assert flags(text) == set()
    assert flags(text, handle_negation=False)


def test_negation_limited_to_same_sentence_and_window():
    assert flags("No calls please. Pay the registration fee now.") == {"payment_fee"}
    assert flags("We never said that you would have to pay the registration fee.") == {"payment_fee"}


def test_rules_containing_no_are_not_negated():
    assert flags("Direct joining. No interview, no experience required.") == {"no_interview", "no_experience"}


def test_highlight_escapes_and_merges_overlapping_spans():
    text = "pay <b>fee</b> now"
    # spans (4, 10) and (8, 14) overlap and should become one <mark>
    assert str(highlight(text, [(8, 14), (4, 10)])) == "pay <mark>&lt;b&gt;fee&lt;/b&gt;</mark> now"


def test_highlight_without_spans_only_escapes():
    assert str(highlight("a < b", [])) == "a &lt; b"
