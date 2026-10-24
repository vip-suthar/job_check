#!/usr/bin/env python3
"""Polite starter scraper for public official careers pages.

Before running, edit scrapers/sources.json with a real URL and selectors.
Check the site's terms and robots.txt. This script skips URLs that robots.txt
disallows or whose robots.txt cannot be checked.
"""
import json
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "scrapers" / "sources.json"
OUTPUT_FILE = ROOT / "data" / "processed" / "genuine_postings_template.csv"
USER_AGENT = "JobCheckResearchBot/1.0 (academic project; replace-with-contact-email)"
DELAY_SECONDS = 3
TIMEOUT_SECONDS = 15


def robots_allows(url):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        print(f"Skipping {url}: unable to verify robots.txt")
        return False


def main():
    if not SOURCES_FILE.exists():
        raise SystemExit(f"Missing configuration: {SOURCES_FILE}")

    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    rows = []

    for source in sources:
        start_url = source["url"]
        if "example.com" in start_url or "add-real-url" in start_url:
            print(f"Edit placeholder URL in {SOURCES_FILE}: {start_url}")
            continue

        if not robots_allows(start_url):
            print(f"Skipping (disallowed or robots.txt unavailable): {start_url}")
            continue

        try:
            response = session.get(start_url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Request failed for {start_url}: {exc}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        title_selector = source.get("title_selector", "h1")
        description_selector = source.get("description_selector", "main")
        card_selector = source.get("card_selector")
        cards = soup.select(card_selector) if card_selector else [soup]

        for card in cards:
            title_node = card.select_one(title_selector)
            desc_node = card.select_one(description_selector)
            if title_node is None or desc_node is None:
                continue
            link_node = card.select_one("a[href]")
            posting_url = urljoin(start_url, link_node["href"]) if link_node else start_url
            rows.append({
                "title": title_node.get_text(" ", strip=True),
                "description": desc_node.get_text(" ", strip=True),
                "label": 0,
                "source_url": posting_url,
                "source_type": "official_careers_page",
                "collection_date": pd.Timestamp.now(tz="UTC").date().isoformat(),
                "labeler_1": "",
                "labeler_2": "",
            })

        time.sleep(DELAY_SECONDS)

    columns = [
        "title", "description", "label", "source_url", "source_type",
        "collection_date", "labeler_1", "labeler_2"
    ]
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    output = pd.DataFrame(rows, columns=columns).drop_duplicates(
        subset=["source_url", "title"]
    )
    output.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(output)} records to {OUTPUT_FILE}")
    print("Review source evidence and labels manually before evaluation.")


if __name__ == "__main__":
    main()
