#!/usr/bin/env python3
"""Save one Polymarket snapshot straight from its public API, into data/live/.

This keeps prices fresh without touching Market Dashboard. Rows match the format of
data/dev/, so clean_markets.py can read both. Placeholder slots such as "Person AI" are
inactive, so they're skipped. So is one stale inactive listing priced at 49%.

Usage: python3 snapshot_polymarket.py           main markets
       python3 snapshot_polymarket.py states    state-by-state presidential markets
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "live"
API = "https://gamma-api.polymarket.com/events?slug="
EVENTS = ("presidential-election-winner-2028", "democratic-presidential-nominee-2028",
          "republican-presidential-nominee-2028", "which-party-wins-2028-us-presidential-election",
          "who-will-announce-presidential-run-before-2028-20260803142755224")
SYSTEM_CERTS = "/etc/ssl/cert.pem"
STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
               "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
               "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
               "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
               "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
               "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
               "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
               "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
               "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
               "WI": "Wisconsin", "WY": "Wyoming"}


def fetch_event(slug: str) -> dict:
    request = urllib.request.Request(API + slug, headers={"User-Agent": "box-of-scraps-research"})
    context = ssl.create_default_context(cafile=SYSTEM_CERTS if Path(SYSTEM_CERTS).exists() else None)
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        events = json.load(response)
    if not events:
        raise ValueError(f"No Polymarket event found for {slug}")
    return events[0]


def number(value) -> float | None:
    return None if value in (None, "") else float(value)


def parse_event(event: dict, fetched_utc: str) -> tuple[list, list]:
    markets, snapshots = [], []
    for m in event["markets"]:
        if not m.get("active") or m.get("closed"):
            continue
        price = json.loads(m.get("outcomePrices") or "[null]")[0]
        markets.append({"id": str(m["id"]), "event_id": str(event["id"]), "label": m["groupItemTitle"]})
        snapshots.append({"fetched_utc": fetched_utc, "market_id": str(m["id"]), "price": number(price),
                          "best_bid": number(m.get("bestBid")), "best_ask": number(m.get("bestAsk"))})
    return markets, snapshots


def snapshot(out: Path = OUT, fetch=fetch_event) -> dict:
    fetched_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    markets, snapshots = [], []
    for slug in EVENTS:  # all-or-nothing, so one hour can't hold a partial market
        new_markets, new_snapshots = parse_event(fetch(slug), fetched_utc)
        markets += new_markets
        snapshots += new_snapshots

    out.mkdir(parents=True, exist_ok=True)
    known = {}
    market_file = out / "poly_markets.jsonl"
    if market_file.exists():
        with open(market_file, encoding="utf-8") as f:
            known = {row["id"]: row for row in map(json.loads, f)}
    known.update({m["id"]: m for m in markets})
    part = market_file.with_suffix(".part")
    part.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in known.values()), encoding="utf-8")
    part.replace(market_file)
    with open(out / "poly_snapshots.jsonl", "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(s) + "\n" for s in snapshots))
    return {"fetched_utc": fetched_utc, "markets": len(markets)}


def state_price(event: dict) -> dict | None:
    """The Democratic price in one state's market, or None if it has no usable quote."""
    for m in event["markets"]:
        if m.get("active") and not m.get("closed") and m["groupItemTitle"].lower().startswith("dem"):
            bid, ask = number(m.get("bestBid")), number(m.get("bestAsk"))
            if bid is None or ask is None:
                return None
            return {"p_dem": (bid + ask) / 2, "spread": ask - bid}
    return None


def state_snapshot(out: Path = OUT, fetch=fetch_event) -> dict:
    states, failed = {}, []
    for code, name in STATE_NAMES.items():
        slug = f"2028-presidential-election-{name.lower().replace(' ', '-')}-winner"
        try:
            price = state_price(fetch(slug))
            if price:
                states[code] = price
            else:
                failed.append(code)
        except (OSError, ValueError, KeyError):
            failed.append(code)
        time.sleep(0.15)
    result = {"fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "states": states, "failed": failed}
    out.mkdir(parents=True, exist_ok=True)
    (out / "poly_states.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["states"]:
        data = state_snapshot()
        print(f"{len(data['states'])} states, missing {data['failed']}")
    else:
        print(json.dumps(snapshot()))
