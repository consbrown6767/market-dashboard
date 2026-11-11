#!/usr/bin/env python3
"""Pull recent headlines about the leading candidates into data/news/latest.json.

This only suggests things to look at. It never changes any odds: you decide whether a headline
deserves a turn. Headlines are outside text, so the page escapes them and nothing here acts on them.

Usage: python3 news_scan.py
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "news" / "latest.json"
RSS = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
SYSTEM_CERTS = "/etc/ssl/cert.pem"
MAX_ITEMS = 40
SEARCHES = 16  # the leading candidates; more would mostly add noise

# Words that suggest a change in who's in the race. First match wins.
KINDS = (
    ("exit", r"won'?t run|not running|rules out|drops? out|ending (his|her|their) (bid|campaign)|withdraw"),
    ("entry", r"announces?\b.*\b(run|bid|campaign)|launch(es)? (a )?(bid|campaign)|exploratory|enters? the race|running for president"),
    ("endorsement", r"endorse"),
    ("poll", r"\bpoll\b|survey shows"),
    ("money", r"fundrais|raised \$|donors?"),
)


def classify(title: str) -> str:
    for kind, pattern in KINDS:
        if re.search(pattern, title, re.IGNORECASE):
            return kind
    return "other"


def parse_feed(xml_text: str, name_patterns: dict) -> list:
    items = []
    for item in ET.fromstring(xml_text).iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published = item.findtext("pubDate")
        source = item.findtext("source") or ""
        if not title or not link.startswith("https://"):
            continue
        items.append({
            "title": title, "link": link, "source": source, "kind": classify(title),
            "published": parsedate_to_datetime(published).astimezone(timezone.utc).isoformat(timespec="minutes") if published else "",
            "candidates": [cid for cid, pattern in name_patterns.items() if re.search(pattern, title, re.IGNORECASE)],
        })
    return items


def fetch(query: str) -> str:
    url = RSS + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={"User-Agent": "box-of-scraps-research"})
    context = ssl.create_default_context(cafile=SYSTEM_CERTS if Path(SYSTEM_CERTS).exists() else None)
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def rank(items: list) -> list:
    """Drop repeats. Race-changing kinds go first, then the newest."""
    seen, unique = set(), []
    for item in sorted(items, key=lambda i: i["published"], reverse=True):
        key = re.sub(r"\W+", "", item["title"].lower())[:60]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    order = {"exit": 0, "entry": 1, "endorsement": 2, "poll": 3, "money": 4, "other": 5}
    return sorted(unique, key=lambda i: order[i["kind"]])[:MAX_ITEMS]


def scan() -> dict:
    ratings = json.loads((HERE / "ratings.json").read_text(encoding="utf-8"))["candidates"]
    names = {c["id"]: c["name"] for c in json.loads((HERE / "candidates.json").read_text(encoding="utf-8"))}
    leaders = sorted((c for c in ratings if not c["id"].startswith("field")), key=lambda c: -c["poll"] * c["p_run"])[:SEARCHES]
    # Last names catch most headlines. A few are too common to match alone, so skip the risk.
    patterns = {c["id"]: rf"\b{re.escape(names[c['id']].split()[-1])}\b" for c in leaders}
    items, failed = [], []
    for candidate in leaders:
        try:
            items += parse_feed(fetch(f'"{names[candidate["id"]]}" 2028 when:2d'), patterns)
        except Exception as error:
            failed.append(f"{candidate['id']}: {error!r}"[:100])
        time.sleep(0.3)
    result = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": rank(items), "failed": failed}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    data = scan()
    print(f"{len(data['items'])} headlines, {len(data['failed'])} failed searches")
    for item in data["items"][:10]:
        print(f"  [{item['kind']}] {item['title'][:100]}")
