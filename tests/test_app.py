import pytest

from app import create_app, db
from app.models import Check, Feedback

SCAM = ("Work from home and earn daily. Pay the registration fee of Rs 500 and "
        "message us on wa.me/919999999999 to start today.")
GENUINE = ("We are hiring a backend engineer with three years of Python experience "
           "to join our Bengaluru office. Apply through our careers page.")


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.test_client() as client, app.app_context():
        yield client


def submit(client, text):
    return client.post("/", data={"text": text}, follow_redirects=True)


def test_home_page_loads(client):
    assert b"Check a job posting" in client.get("/").data


@pytest.mark.parametrize("text", ["", "   ", "too short", "x" * 10_001])
def test_invalid_input_rejected_and_not_stored(client, text):
    response = submit(client, text)
    assert b"is-invalid" in response.data
    assert db.session.query(Check).count() == 0


def test_scam_posting_flagged_with_highlights(client):
    body = submit(client, SCAM).data
    assert b"Red flags found (2)" in body
    assert b"<mark>registration fee</mark>" in body
    assert b"1930" in body  # safety checklist shown


def test_clean_posting_has_disclaimer(client):
    body = submit(client, GENUINE).data
    assert b"No common red flags found" in body
    assert b"This does not mean the posting is safe." in body


def test_pasted_html_is_escaped(client):
    body = submit(client, "<script>alert(1)</script> " + SCAM).data
    assert b"<script>alert(1)" not in body
    assert b"&lt;script&gt;alert(1)" in body


def test_history_lists_checks_newest_first(client):
    submit(client, GENUINE)
    submit(client, SCAM)
    body = client.get("/history").data
    assert body.index(b"Red flags found (2)") < body.index(b"No common red flags found")


def test_unknown_check_returns_404(client):
    assert client.get("/check/999").status_code == 404


def test_whitespace_collapsed_before_validation():
    from app.forms import clean_whitespace
    assert clean_whitespace("  a \t  b \r\n\r\n\r\n\n  c  ") == "a b\n\nc"


def test_feedback_stored(client):
    submit(client, SCAM)
    body = client.post("/check/1/feedback", data={"user_says": "incorrect", "comment": " wrong "},
                       follow_redirects=True).data
    assert b"Thank you for your feedback." in body
    fb = db.session.query(Feedback).one()
    assert (fb.check_id, fb.user_says, fb.comment) == (1, "incorrect", "wrong")


def test_invalid_feedback_rejected(client):
    submit(client, SCAM)
    body = client.post("/check/1/feedback", data={"user_says": "maybe"}, follow_redirects=True).data
    assert b"could not be saved" in body
    assert db.session.query(Feedback).count() == 0
    assert client.post("/check/999/feedback", data={"user_says": "correct"}).status_code == 404


def test_api_check(client):
    response = client.post("/api/check", json={"text": SCAM})
    assert response.status_code == 201
    data = response.get_json()
    assert data["indicator"] == "red_flags"
    assert data["label"] == "Red flags found (2)"
    assert {"rule_id": "payment_fee", "explanation": "Asks for a fee or deposit.",
            "matched_text": "registration fee", "start": 39, "end": 55} in data["hits"]
    assert db.session.get(Check, data["id"]).source == "api"


@pytest.mark.parametrize("payload", [None, [], {}, {"text": 5}, {"text": "too short"},
                                     {"text": SCAM, "extra": 1}])
def test_api_rejects_bad_input(client, payload):
    response = client.post("/api/check", json=payload)
    assert response.status_code == 400
    assert "errors" in response.get_json()
    assert db.session.query(Check).count() == 0


def test_api_errors_are_json(client):
    response = client.get("/api/check")
    assert response.status_code == 405
    assert response.get_json() == {"errors": {"_request": ["Method Not Allowed"]}}


def test_dashboard(client):
    assert b"No checks yet" in client.get("/dashboard").data
    submit(client, SCAM)
    submit(client, GENUINE)
    body = client.get("/dashboard").data
    assert b"50%" in body
    assert body.count(b"data:image/png;base64,") == 2


def test_error_page(client):
    body = client.get("/no-such-page").data
    assert b"404 Not Found" in body
