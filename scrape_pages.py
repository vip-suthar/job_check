#!/usr/bin/env python3
"""Polite starter scraper for public job/career pages.

It respects robots.txt, waits between requests, and leaves labels as 'unreviewed'.
A scraped page must not automatically be considered a genuine job posting.
"""
from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "JobCheckResearchBot/0.1 (educational project; contact: project team)"
FIELDS = [
    "title", "text", "source_url", "source_type", "date_collected",
    "label", "label_evidence", "labeller_1", "labeller_2", "label_1", "label_2", "notes"
]

def allowed_by_robots(url: str, session: requests.Session) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=10)
        # If robots.txt is unavailable, fail closed rather than assuming permission.
        if response.status_code != 200:
            print(f"SKIP: could not verify robots.txt for {url} (HTTP {response.status_code})")
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except requests.RequestException as exc:
        print(f"SKIP: robots.txt check failed for {url}: {exc}")
        return False

def page_text(html: str | bytes) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        element.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Keep page text bounded; listing pages can contain many unrelated elements.
    text = " ".join(soup.get_text(" ", strip=True).split())[:20000]
    return title, text

def extract_page(url: str, session: requests.Session) -> tuple[str, str]:
    response = session.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return page_text(response.text)

def main() -> None:
    parser = argparse.ArgumentParser(description="Collect permitted public career-page text.")
    parser.add_argument("--urls", default="scrapers/sources.txt", help="Text file containing one URL per line")
    parser.add_argument("--output", default="data/raw/scraped_postings.csv")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds to wait between page requests (minimum 2)")
    args = parser.parse_args()
    delay = max(2.0, args.delay)

    urls_file = Path(args.urls)
    if not urls_file.exists():
        raise SystemExit(f"URL list not found: {urls_file}")
    urls = [
        line.strip() for line in urls_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    rows = []
    for index, url in enumerate(urls):
        if urlparse(url).scheme not in {"http", "https"}:
            print(f"SKIP: unsupported URL: {url}")
            continue
        if not allowed_by_robots(url, session):
            print(f"SKIP: robots.txt disallows or permission could not be verified: {url}")
            time.sleep(delay)
            continue
        try:
            title, text = extract_page(url, session)
            rows.append({
                "title": title,
                "text": text,
                "source_url": url,
                "source_type": "career_or_recruitment_page",
                "date_collected": datetime.now(timezone.utc).date().isoformat(),
                "label": "unreviewed",
                "label_evidence": "",
                "labeller_1": "",
                "labeller_2": "",
                "notes": "Page text extracted; individual postings and source evidence require manual review."
            })
            print(f"OK: collected page text from {url}")
        except requests.RequestException as exc:
            print(f"ERROR: {url}: {exc}")
        if index < len(urls) - 1:
            time.sleep(delay)

    # Append existing rows without duplicating the header.
    exists = output.exists() and output.stat().st_size > 0
    with output.open("a" if exists else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} page-level record(s) to {output}")
    print("Reminder: these are page-level records, not verified individual job postings.")

if __name__ == "__main__":
    main()
