import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import db
from app.fetch import FetchError, fetch_text, is_public_host
from app.models import Check
from tests.test_app import SCAM, client  # noqa: F401


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1",
                                  "169.254.169.254", "::1", "0.0.0.0"])
def test_internal_hosts_blocked(host):
    assert not is_public_host(host)


def test_public_ip_allowed():
    assert is_public_host("8.8.8.8")


@pytest.mark.parametrize("url", ["http://127.0.0.1:5000/", "file:///etc/passwd", "ftp://8.8.8.8/x"])
def test_fetch_refuses_unsafe_urls(url):
    with pytest.raises(FetchError):
        fetch_text(url)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/page")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write("<html><script>x()</script><main>Earn ₹500 per day</main></html>".encode())

    def log_message(self, *args):
        pass


def test_fetch_follows_only_allowed_hosts(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # pretend "localhost" is public so the real fetch path runs; 127.0.0.1 stays blocked
    monkeypatch.setattr("app.fetch.is_public_host", lambda host: host == "localhost")
    base = f"http://localhost:{server.server_port}"
    try:
        assert fetch_text(base + "/page") == "Earn ₹500 per day"
        with pytest.raises(FetchError):
            fetch_text(base + "/redirect")
    finally:
        server.shutdown()


def test_check_url_saves_fetched_text(client, monkeypatch):
    monkeypatch.setattr("app.routes.fetch_text", lambda url: "  " + SCAM + "  ")
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"Red flags found (2)" in body
    assert db.session.query(Check).one().source == "url"


def test_check_url_falls_back_to_paste(client, monkeypatch):
    def blocked(url):
        raise FetchError("blocked")
    monkeypatch.setattr("app.routes.fetch_text", blocked)
    body = client.post("/check-url", data={"url": "https://example.com/job"}, follow_redirects=True).data
    assert b"Please copy the posting text" in body
    body = client.post("/check-url", data={"url": "not a url"}, follow_redirects=True).data
    assert b"Please enter a valid web address" in body
    assert db.session.query(Check).count() == 0
