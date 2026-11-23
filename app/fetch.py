import html
import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from app.forms import clean_whitespace
from scrapers.scrape_pages import USER_AGENT

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
MAX_POSTINGS = 10      # how many postings we open from one listing page
MIN_LISTING_LINKS = 3  # a page with fewer posting links is treated as one posting
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"}

# tags that never have posting text in them
JUNK_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "aside", "form", "iframe", "button"]
# tags that start a new line
BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "table", "tr", "section", "article", "main", "br",
              "h1", "h2", "h3", "h4", "h5", "h6"]
# words that show up in links to postings, like /jobs/12345 or /internship/detail/...
JOB_WORDS = ["job", "jobs", "career", "careers", "vacancy", "vacancies", "opening", "openings",
             "position", "positions", "posting", "postings", "internship", "internships"]


class FetchError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status  # http status code, if the site answered


def is_public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    return all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def download(url):
    #Downloads a public url and returns (final url, content type, body).
    
    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or not is_public_host(parsed.hostname):
            raise FetchError("only public http(s) addresses can be fetched")
        try:
            with requests.get(url, timeout=10, stream=True, allow_redirects=False, headers=HEADERS, verify=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    continue
                status = response.status_code
                if status in (401, 403, 429):
                    raise FetchError(f"the site blocked automated access (HTTP {status})", status)
                if status in (404, 410):
                    raise FetchError(f"the page was not found (HTTP {status}), the posting may have been removed",
                                     status)
                if status >= 400:
                    raise FetchError(f"the site returned an error (HTTP {status})", status)
                content_type = response.headers.get("Content-Type", "")
                # read the page in pieces so we can stop as soon as it gets too big
                body = b""
                for chunk in response.iter_content(64 * 1024):
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise FetchError("the page is too large")
        except requests.Timeout:
            raise FetchError("the site took too long to respond")
        except requests.RequestException:
            raise FetchError("could not connect to the site")
        return url, content_type, body
    raise FetchError("too many redirects")


def get_page(url):
    """Returns (final url, parsed page)."""
    url, content_type, body = download(url)
    if "html" not in content_type:
        raise FetchError("the link is not a web page")
    return url, BeautifulSoup(body, "html.parser")


def html_to_text(node):
    """Gets the text of an html element with a line break after each block tag (p, li, h2...).

    get_text("\\n") would also break the line at inline tags like <b> and <a>, which cuts
    sentences in half (and the negation check in detector/rules.py works per sentence).
    So we put a [BR] mark after each block, squash all the other whitespace from the html,
    and then turn the marks into line breaks.
    """
    for tag in node.find_all(BLOCK_TAGS):
        tag.insert_after(" [BR] ")
    text = " ".join(node.get_text().split())
    return clean_whitespace(text.replace("[BR]", "\n"))


def read_json_ld(soup):
    """Returns the objects in the page's JSON-LD blocks.

    Job sites put the posting in <script type="application/ld+json"> so Google Jobs can show it.
    It is usually there even when the rest of the page is made with JavaScript.
    """
    items = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "", strict=False)  # strict=False allows raw newlines in the text
        except ValueError:
            continue
        if isinstance(data, dict) and "@graph" in data:  # some sites put everything inside "@graph"
            data = data["@graph"]
        if not isinstance(data, list):
            data = [data]
        for item in data:
            if isinstance(item, dict):
                items.append(item)
    return items


def is_type(item, name):
    # "@type" can be one string or a list of strings
    t = item.get("@type")
    if isinstance(t, list):
        return name in t
    return t == name


def job_posting_text(job):
    company = job.get("hiringOrganization")
    if isinstance(company, dict):
        company = company.get("name")
    description = str(job.get("description") or "")
    if "&lt;" in description:  # some sites escape the html twice
        description = html.unescape(description)
    lines = [str(job.get("title") or "")]
    if company:
        lines.append(f"Company: {company}")
    lines.append(html_to_text(BeautifulSoup(description, "html.parser")))
    return clean_whitespace("\n".join(lines))


def posting_text(soup):
    """Text of the posting on a page. Uses the JobPosting data if the page has it, else the page text."""
    jobs = [i for i in read_json_ld(soup) if is_type(i, "JobPosting")]
    data_text = ""
    if len(jobs) == 1:
        data_text = job_posting_text(jobs[0])
        if len(data_text) >= 200:
            return data_text

    # no data, or the description in it is very short, so read the page itself
    main = soup.find("main") or soup.find("article")
    junk = JUNK_TAGS
    if main is None or len(main.get_text(strip=True)) < 200:
        main = soup.body or soup
        # only remove <header> here, inside <main> the header is usually the job title
        junk = JUNK_TAGS + ["header"]
    for tag in main.find_all(junk):
        tag.decompose()
    page_text = html_to_text(main)

    if len(data_text) > len(page_text):
        return data_text
    return page_text


def looks_like_posting(url, page_url):
    """Guesses if a link goes to one job posting.

    The link has to be on the same site as the page, and
    - have a job word in its path (/jobs/12345) or be under the page's own path (/acme -> /acme/8f2c...)
    - end with something that has a number in it. Posting links almost always end in an id,
      category links like /jobs/python-jobs/ don't.
    """
    link = urlparse(url)
    page = urlparse(page_url)
    if link.hostname != page.hostname:
        return False
    path = link.path.rstrip("/")
    page_path = page.path.rstrip("/")
    if path == page_path:
        return False

    last = path.split("/")[-1]
    if not any(ch.isdigit() for ch in last):
        return False
    if last.isdigit() and len(last) < 4:  # /page/2 is the next page of the list, not a posting
        return False

    has_job_word = any(part.lower() in JOB_WORDS for part in path.split("/"))
    under_page = page_path != "" and path.startswith(page_path + "/")
    return has_job_word or under_page


def posting_links(soup, page_url):
    """If the page lists several postings, returns {link: title} for each of them.
    Returns {} when the page is a single posting."""
    items = read_json_ld(soup)
    jobs = [i for i in items if is_type(i, "JobPosting")]
    if len(jobs) == 1:
        return {}  # the page itself says it is one posting

    found = []  # (link, title)
    for job in jobs:
        found.append((job.get("url"), job.get("title")))
    for item_list in [i for i in items if is_type(i, "ItemList")]:
        for element in item_list.get("itemListElement", []):
            if isinstance(element, dict):
                found.append((element.get("url"), element.get("name")))
    for a in soup.find_all("a", href=True):
        # links in menus go to categories, not postings
        if a.find_parent(["nav", "header", "footer"]) is None:
            found.append((a["href"], a.get_text(" ", strip=True)))

    links = {}
    for link, title in found:
        if not isinstance(link, str):
            continue
        link = urljoin(page_url, link).split("#")[0]
        title = " ".join(str(title or "").split())[:150]
        if looks_like_posting(link, page_url):
            # the same posting is often linked twice ("Apply" and the job title), keep the longer text
            if len(title) >= len(links.get(link, "")):
                links[link] = title

    if len(links) < MIN_LISTING_LINKS:
        return {}
    return links


def get_robots(page_url):
    """Reads the site's robots.txt, to know which links we may open on our own."""
    parsed = urlparse(page_url)
    try:
        body = download(f"{parsed.scheme}://{parsed.netloc}/robots.txt")[2]
        lines = body.decode("utf-8", "replace").splitlines()
    except FetchError as e:
        if e.status is not None and e.status < 500:
            lines = []  # the site has no robots.txt, so everything is allowed
        else:
            lines = ["User-agent: *", "Disallow: /"]  # the site is down or broken, so leave it alone
    robots = RobotFileParser()
    robots.parse(lines)
    return robots
