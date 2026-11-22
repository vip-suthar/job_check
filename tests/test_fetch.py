import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from bs4 import BeautifulSoup

from app import create_app, db
from app.fetch import (USER_AGENT, FetchError, get_page, get_robots, is_public_host, looks_like_posting,
                       posting_links, posting_text)
from app.models import Check
from detector.rules import check
from tests.test_app import GENUINE, SCAM, client  # noqa: F401


def soup(html):
    return BeautifulSoup(html, "html.parser")


def job_ld(title, description, url=None):
    data = {"@context": "https://schema.org", "@type": "JobPosting", "title": title, "description": description,
            "hiringOrganization": {"@type": "Organization", "name": "Acme"}}
    if url:
        data["url"] = url
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1",
                                  "169.254.169.254", "::1", "0.0.0.0"])
def test_internal_hosts_blocked(host):
    assert not is_public_host(host)


def test_public_ip_allowed():
    assert is_public_host("8.8.8.8")


@pytest.mark.parametrize("url", ["http://127.0.0.1:5000/", "file:///etc/passwd", "ftp://8.8.8.8/x"])
def test_fetch_refuses_unsafe_urls(url):
    with pytest.raises(FetchError):
        get_page(url)


def test_inline_tags_do_not_break_sentences():
    text = posting_text(soup("<html><body><h1>Data entry</h1><p>We <b>never</b> charge a "
                             "<a href='#'>registration fee</a>.</p><p>Apply   on our\n site.</p></body></html>"))
    assert text == "Data entry\nWe never charge a registration fee.\nApply on our site."
    assert check(text)["score"] == 0  # negation still works


def test_json_ld_posting_is_used():
    description = "<p>Pay the <b>registration fee</b> of Rs 500.</p>" + "<p>Details of the job.</p>" * 20
    page = soup("<html><head>" + job_ld("Data Entry Operator", description) + "</head>"
                "<body><nav>Home Jobs</nav><p>Loading...</p></body></html>")
    text = posting_text(page)
    assert text.startswith("Data Entry Operator\nCompany: Acme\nPay the registration fee of Rs 500.\n")
    assert "Loading" not in text


def test_page_text_without_json_ld():
    page = soup("<html><body><header>Site menu</header><main><header><h1>Backend engineer</h1></header>"
                + "<p>Write Python code.</p>" * 20 + "<aside>Similar jobs</aside></main><footer>(c)</footer></body></html>")
    text = posting_text(page)
    assert text.startswith("Backend engineer\nWrite Python code.")
    assert "Similar jobs" not in text and "Site menu" not in text


@pytest.mark.parametrize("url, expected", [
    ("https://acme.com/jobs/12345", True),
    ("https://acme.com/job/data-analyst-987", True),
    ("https://acme.com/internship/detail/web-dev-in-pune1793088722", True),
    ("https://acme.com/openings/7f3a2c1e-4b5d", True),            # under the listing page
    ("https://acme.com/jobs/python-jobs/", False),                # category, no id
    ("https://acme.com/openings/page/2", False),                  # pagination
    ("https://acme.com/blog/2024-hiring-tips", False),            # not a job link
    ("https://other.com/jobs/12345", False),                      # another site
    ("https://jobs.acme.com/jobs/12345", False),                  # another host name
    ("https://acme.com/openings?page=3", False),                  # the listing itself
])
def test_looks_like_posting(url, expected):
    assert looks_like_posting(url, "https://acme.com/openings") == expected


def test_posting_links_on_listing_page():
    page = soup("""<html><body>
        <nav><a href="/jobs/python-jobs/">Python jobs</a><a href="/jobs/4444">Featured</a></nav>
        <div><a href="/jobs/1001">Apply</a><a href="/jobs/1001">Data entry operator</a></div>
        <div><a href="/jobs/1002">Backend engineer</a></div>
        <div><a href="https://acme.com/jobs/1003#top">Sales intern</a></div>
        <a href="/jobs/page/2">Next</a></body></html>""")
    assert posting_links(page, "https://acme.com/openings") == {
        "https://acme.com/jobs/1001": "Data entry operator",
        "https://acme.com/jobs/1002": "Backend engineer",
        "https://acme.com/jobs/1003": "Sales intern",
    }


def test_posting_links_from_json_ld_item_list():
    items = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": f"Job {n}", "url": f"https://acme.com/internship/detail/x{n}00"}
        for n in range(1, 4)]}
    page = soup(f'<script type="application/ld+json">{json.dumps(items)}</script>')
    assert list(posting_links(page, "https://acme.com/internships/").values()) == ["Job 1", "Job 2", "Job 3"]


def test_single_posting_is_not_a_listing():
    similar = "".join(f'<a href="/jobs/{n}">Similar job {n}</a>' for n in range(1001, 1006))
    assert posting_links(soup(job_ld("Engineer", "x") + similar), "https://acme.com/jobs/1000") == {}
    assert posting_links(soup('<a href="/jobs/1001">One</a><a href="/jobs/1002">Two</a>'),
                         "https://acme.com/jobs") == {}


@pytest.mark.parametrize("status, allowed", [(404, True), (403, True), (500, False), (None, False)])
def test_robots_txt_missing_or_down(monkeypatch, status, allowed):
    def no_robots(url):
        raise FetchError("failed", status)
    monkeypatch.setattr("app.fetch.download", no_robots)
    assert get_robots("https://acme.com/jobs").can_fetch(USER_AGENT, "https://acme.com/jobs/1") == allowed


# a small site for the tests below: a listing page, its postings and a robots.txt
PAGES = {
    "/page": "<html><script>x()</script><main>Earn ₹500 per day</main></html>",
    "/jobs": "<html><body><h1>Openings</h1><p>Pick a job below to see the details.</p>" + "".join(
        f'<a href="/jobs/{n}">Job {n}</a>' for n in (1001, 1002, 1003, 1004)) + "</body></html>",
    "/jobs/1001": "<html><head>" + job_ld("Data entry", "<p>" + SCAM + "</p>") + "</head></html>",
    "/jobs/1002": f"<html><body><main><h1>Backend engineer</h1><p>{GENUINE}</p></main></body></html>",
    "/jobs/1003": f"<html><body><p>{SCAM}</p></body></html>",
}
ROBOTS = "User-agent: *\nDisallow: /jobs/1003\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/page")
            self.end_headers()
            return
        if self.path == "/robots.txt":
            status, kind, body = 200, "text/plain", ROBOTS
        elif self.path == "/file.pdf":
            status, kind, body = 200, "application/pdf", "%PDF"
        elif self.path in PAGES:
            status, kind, body = 200, "text/html", PAGES[self.path]
        else:
            status, kind, body = 404, "text/html", "not found"
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def site(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # pretend 127.0.0.1 is public so the real fetch path runs; "localhost" stays blocked.
    # (an ip is used because the url form does not accept "localhost", it has no domain ending)
    monkeypatch.setattr("app.fetch.is_public_host", lambda host: host == "127.0.0.1")
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_fetch_follows_only_allowed_hosts(site):
    url, page = get_page(site + "/page")
    assert posting_text(page) == "Earn ₹500 per day"
    with pytest.raises(FetchError):
        get_page(site + "/redirect")


@pytest.mark.parametrize("path, message", [("/missing", "page was not found"), ("/file.pdf", "not a web page")])
def test_fetch_error_messages(site, path, message):
    with pytest.raises(FetchError, match=message):
        get_page(site + path)


def test_listing_page_postings_checked_one_by_one(client, site):
    body = client.post("/check-url", data={"url": site + "/jobs"}).data
    assert b"This page lists 4 postings" in body
    assert b"Red flags found (2)" in body and b"No common red flags found" in body
    assert b"robots.txt does not allow it" in body  # /jobs/1003
    assert b"Could not open: the page was not found" in body  # /jobs/1004
    checks = db.session.query(Check).order_by(Check.id).all()
    assert [c.source_url for c in checks] == [site + "/jobs/1001", site + "/jobs/1002"]
    assert checks[0].text.startswith("Data entry\nCompany: Acme\nWork from home")


def test_listing_page_checked_as_one_posting_when_asked(client, site):
    body = client.post("/check-url", data={"url": site + "/jobs", "single": "y"}, follow_redirects=True).data
    assert b"Text read from" in body
    assert db.session.query(Check).one().text.startswith("Openings\nPick a job below to see the details.\nJob 1001")


def test_check_url_saves_fetched_text(client, monkeypatch):
    monkeypatch.setattr("app.routes.get_page", lambda url: (url, soup(f"<p>  {SCAM}  </p>")))
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"Red flags found (2)" in body
    assert b"https://example.com/job" in body
    record = db.session.query(Check).one()
    assert (record.source, record.source_url, record.text) == ("url", "https://example.com/job", SCAM)


def test_long_page_is_cut(client, monkeypatch):
    monkeypatch.setattr("app.routes.get_page", lambda url: (url, soup("<p>" + GENUINE * 100 + "</p>")))
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"only the first 10,000 were checked" in body
    assert len(db.session.query(Check).one().text) == 10_000


def test_check_url_falls_back_to_paste(client, monkeypatch):
    def blocked(url):
        raise FetchError("the site blocked automated access (HTTP 403)")
    monkeypatch.setattr("app.routes.get_page", blocked)
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"blocked automated access (HTTP 403). Please copy the posting text" in body
    monkeypatch.setattr("app.routes.get_page", lambda url: (url, soup("<div id='app'></div>")))
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"may need JavaScript" in body
    body = client.post("/check-url", data={"url": "not a url"}, follow_redirects=True).data
    assert b"Please enter a valid web address" in body
    assert db.session.query(Check).count() == 0


def test_old_database_gets_source_url_column(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE checks (id INTEGER PRIMARY KEY, created_at DATETIME NOT NULL, "
                     "source VARCHAR(10) NOT NULL, text TEXT NOT NULL, rule_score INTEGER NOT NULL, "
                     "model_probability FLOAT, indicator VARCHAR(20) NOT NULL)")
        conn.execute("INSERT INTO checks VALUES (1, '2026-11-01 10:00:00', 'form', 'old text', 0, NULL, 'no_flags')")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})
    with app.app_context():
        record = db.session.get(Check, 1)
        assert (record.text, record.source_url) == ("old text", None)
