from datetime import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app import db
from app.excel import RED_FILL, monthly_report
from app.models import Check, Feedback
from tests.test_app import GENUINE, SCAM, client, submit  # noqa: F401


def upload(client, wb, name="postings.xlsx"):
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return client.post("/bulk", data={"file": (buf, name)}, content_type="multipart/form-data")


def test_bulk_adds_results_and_summary(client):
    wb = Workbook()
    wb.active.append(["id", "Posting"])
    for i, text in enumerate([SCAM, "", "too short", GENUINE], start=1):
        wb.active.append([i, text])
    response = upload(client, wb)
    assert response.status_code == 200
    assert "postings_jobcheck.xlsx" in response.headers["Content-Disposition"]

    out = load_workbook(BytesIO(response.data))
    ws = out.worksheets[0]
    assert [c.value for c in ws[1]] == ["id", "Posting", "JobCheck result", "Score", "Red flags"]
    assert ws["C2"].value == "Red flags found (2)"
    assert "Asks for a fee or deposit." in ws["E2"].value
    assert ws["A2"].fill.fgColor.rgb == RED_FILL.fgColor.rgb
    assert ws["C3"].value is None
    assert ws["C4"].value.startswith("Skipped")
    assert ws["C5"].value == "No common red flags found"
    summary = out["JobCheck summary"]
    assert [summary["B2"].value, summary["B3"].value, summary["B4"].value] == [1, 1, 1]
    assert [c.source for c in db.session.query(Check)] == ["bulk", "bulk"]


def test_bulk_rejects_bad_files(client):
    response = client.post("/bulk", data={"file": (BytesIO(b"not excel"), "x.xlsx")},
                           content_type="multipart/form-data")
    assert b"Could not read this file" in response.data
    response = client.post("/bulk", data={"file": (BytesIO(b"a,b"), "x.csv")},
                           content_type="multipart/form-data")
    assert b"Upload an .xlsx file." in response.data
    wb = Workbook()
    for _ in range(502):
        wb.active.append([SCAM])
    assert b"more than 500 postings" in upload(client, wb).data
    assert db.session.query(Check).count() == 0


def test_monthly_report(client):
    submit(client, SCAM)
    submit(client, GENUINE)
    old = Check(source="api", text=GENUINE, rule_score=0, indicator="no_flags",
                created_at=datetime(2020, 1, 15))
    db.session.add_all([old, Feedback(check_id=1, user_says="correct")])
    db.session.commit()
    now = datetime.now()

    wb = monthly_report(now.year, now.month)
    summary = {row[0]: row[1] for row in wb["Summary"].iter_rows(min_row=2, values_only=True)}
    assert summary["Checks"] == 2
    assert summary["Red flags found"] == 1
    assert summary["Share flagged (%)"] == 50.0
    assert summary["Checks from form"] == 2
    assert summary["Feedback: result right"] == 1
    assert len(wb["Summary"]._charts) == 1
    assert wb["Daily"].max_row - 1 >= 28
    assert {r[0] for r in wb["Red flags"].iter_rows(min_row=2, values_only=True)} == {
        "payment_fee", "off_platform_contact"}

    january = {row[0]: row[1] for row in monthly_report(2020, 1)["Summary"].iter_rows(min_row=2, values_only=True)}
    assert january["Checks"] == 1
    assert monthly_report(2020, 12)["Daily"].max_row == 32
