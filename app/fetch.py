import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

from scrape_pages import USER_AGENT, page_text

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5


class FetchError(Exception):
    pass


def is_public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    return all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def fetch_text(url):
    """Fetch a public web page and return its visible text.

    Every redirect target is checked as well, so a link cannot make the server
    request its own network (localhost, private ranges, cloud metadata).
    """
    # ponytail: requests resolves the host again, so DNS rebinding is not covered; pin the checked IP before any public deployment
    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or not is_public_host(parsed.hostname):
            raise FetchError("only public http(s) addresses can be fetched")
        with requests.get(url, timeout=10, stream=True, allow_redirects=False,
                          headers={"User-Agent": USER_AGENT}) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", ""):
                raise FetchError("not a web page")
            body = response.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(body) > MAX_BYTES:
            raise FetchError("page too large")
        return page_text(body)[1]
    raise FetchError("too many redirects")
