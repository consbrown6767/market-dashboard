#!/usr/bin/env python3
"""Turn raw Polymarket and Kalshi snapshots into comparable odds, then check them.

Cleaning rules:
  * One price per candidate: the midpoint of bid and ask. Polymarket's own price is used when
    a long shot has no bid.
  * One snapshot per hour: the last one in that hour.
  * A market over 100% is scaled down, since real probabilities can't exceed 100%.
  * A market under 100% is NOT scaled up. The gap is kept as "unlisted", because it may be
    people not listed yet or a discount for money tied up until 2028. Spreading it across
    named candidates would inflate them by an amount nobody can justify.

Any name missing from candidates.json is reported, never silently dropped.

Usage: python3 clean_markets.py
"""

from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLYMARKET_DIR = HERE / "data" / "dev"
LIVE_DIR = HERE / "data" / "live"  # fresher rows from snapshot_polymarket.py, same format
KALSHI_HISTORY = HERE / "data" / "history" / "kalshi_hourly.jsonl"  # from backfill_history.py
KALSHI_DIR = Path(os.environ.get("PGM_DATA_DIR", HERE)) / "kalshi"

POLYMARKET_EVENTS = {"31552": "winner", "30829": "nominee_d", "31875": "nominee_r", "33228": "party"}
KALSHI_EVENTS = {"KXPRESPERSON-28": "winner", "KXPRESNOMD-28": "nominee_d",
                 "KXPRESNOMR-28": "nominee_r", "KXPRESPARTY-2028": "party"}
PARTY_LABELS = {"Democratic": "D", "Democratic party": "D", "Republican": "R", "Republican party": "R"}

MIN_NOMINEE_PRICE = 0.03  # below this, win / nominee is mostly rounding noise
MAX_HOURS_APART = 2  # venues further apart than this aren't compared as if simultaneous


def load_candidates(path: Path = HERE / "candidates.json") -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def name_lookup(candidates: list[dict], venue: str) -> dict:
    lookup = {label: c["id"] for c in candidates for label in c[venue]}
    lookup.update(PARTY_LABELS)
    return lookup


def midpoint(bid: float | None, ask: float | None, fallback: float | None = None) -> float | None:
    if bid is None or ask is None:
        return fallback
    return (bid + ask) / 2


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def add_quote(book: dict, market: str, timestamp: str, candidate: str, bid, ask, mid) -> None:
    # The first 13 characters of a UTC timestamp identify its hour. Rows arrive in time order,
    # so a later snapshot in the same hour replaces an earlier one.
    book[market][timestamp[:13]][candidate] = {"bid": bid, "ask": ask, "mid": mid}


def polymarket_rows(data_dir: Path, name: str, live_dir: Path | None = None) -> list[dict]:
    """Rows from the backup pull, then any live rows, so newer data wins within an hour."""
    rows = read_jsonl(data_dir / name)
    if live_dir and (live_dir / name).exists():
        rows += read_jsonl(live_dir / name)
    return rows


def load_polymarket(data_dir: Path, lookup: dict, live_dir: Path | None = None) -> tuple[dict, set]:
    labels = {}
    for market in polymarket_rows(data_dir, "poly_markets.jsonl", live_dir):
        if market["event_id"] in POLYMARKET_EVENTS:
            labels[market["id"]] = (POLYMARKET_EVENTS[market["event_id"]], market["label"])
    book, unmapped = defaultdict(lambda: defaultdict(dict)), set()
    for row in polymarket_rows(data_dir, "poly_snapshots.jsonl", live_dir):
        if row["market_id"] not in labels:
            continue
        market, label = labels[row["market_id"]]
        if label not in lookup:
            unmapped.add(label)
            continue
        mid = midpoint(row["best_bid"], row["best_ask"], fallback=row["price"])
        add_quote(book, market, row["fetched_utc"], lookup[label], row["best_bid"], row["best_ask"], mid)
    return book, unmapped


def load_kalshi(data_dir: Path, lookup: dict, history: Path | None = None) -> tuple[dict, set]:
    book, unmapped = defaultdict(lambda: defaultdict(dict)), set()
    # History first, so live snapshots win when both cover the same hour.
    paths = ([history] if history and history.exists() else []) + [Path(p) for p in sorted(glob.glob(str(data_dir / "snapshots-*.jsonl")))]
    for path in paths:
        for row in read_jsonl(path):
            if row["label"] not in lookup:
                unmapped.add(row["label"])
                continue
            add_quote(book, KALSHI_EVENTS[row["event_ticker"]], row["fetched_at"], lookup[row["label"]],
                      row["yes_bid"], row["yes_ask"], midpoint(row["yes_bid"], row["yes_ask"]))
    return book, unmapped


def clean_market(quotes: dict) -> dict:
    """Apply the over/under 100% rule to one market at one hour."""
    raw_sum = sum(q["mid"] for q in quotes.values())
    scale = 1 / raw_sum if raw_sum > 1 else 1
    return {
        "raw_sum": raw_sum,
        "unlisted": max(0.0, 1 - raw_sum),
        "odds": {candidate: q["mid"] * scale for candidate, q in quotes.items()},
    }


def latest_view(book: dict) -> dict:
    """The most recent hour of each market, cleaned."""
    view = {}
    for market, hours in book.items():
        hour = max(hours)
        view[market] = {"hour": hour, **clean_market(hours[hour])}
    return view


def hours_apart(first: str, second: str) -> float:
    a, b = (datetime.fromisoformat(h + ":00:00") for h in (first, second))
    return abs((a - b).total_seconds()) / 3600


def win_if_nominated(view: dict) -> dict:
    """Implied chance of winning if nominated: P(win) / P(nominated)."""
    implied = {}
    for market in ("nominee_d", "nominee_r"):
        for candidate, nominee in view.get(market, {}).get("odds", {}).items():
            win = view.get("winner", {}).get("odds", {}).get(candidate)
            if win is not None and nominee >= MIN_NOMINEE_PRICE:
                implied[candidate] = win / nominee
    return implied


def party_check(view: dict, parties: dict) -> dict:
    """Candidate win odds added up by party, next to the party market itself."""
    sums = {"D": 0.0, "R": 0.0, "unassigned": 0.0}
    for candidate, odds in view.get("winner", {}).get("odds", {}).items():
        sums[parties.get(candidate) or "unassigned"] += odds
    return {"candidates": sums, "party_market": view.get("party", {}).get("odds", {})}


def percent(value: float | None) -> str:
    return "   --" if value is None else f"{value * 100:5.1f}"


def report() -> int:
    candidates = load_candidates()
    names = {c["id"]: c["name"] for c in candidates}
    parties = {c["id"]: c["party"] for c in candidates}
    polymarket, poly_unmapped = load_polymarket(POLYMARKET_DIR, name_lookup(candidates, "polymarket"), LIVE_DIR)
    kalshi, kalshi_unmapped = load_kalshi(KALSHI_DIR, name_lookup(candidates, "kalshi"), KALSHI_HISTORY)
    views = {"Polymarket": latest_view(polymarket), "Kalshi": latest_view(kalshi)}

    if poly_unmapped or kalshi_unmapped:
        print("NAMES MISSING FROM candidates.json (left out below):")
        print(f"  Polymarket: {sorted(poly_unmapped)}\n  Kalshi: {sorted(kalshi_unmapped)}\n")

    gap = hours_apart(views["Polymarket"]["winner"]["hour"], views["Kalshi"]["winner"]["hour"])
    for venue, view in views.items():
        print(f"{venue}: latest hour {view['winner']['hour']}:00 UTC")
    if gap > MAX_HOURS_APART:
        print(f"WARNING: venues are {gap:.0f} hours apart, so differences may just be timing.")

    print("\nMarket totals (raw sum, and the gap kept as unlisted)")
    for market in ("winner", "nominee_d", "nominee_r", "party"):
        cells = [f"{venue} {percent(v[market]['raw_sum'])} / {percent(v[market]['unlisted'])}"
                 for venue, v in views.items()]
        print(f"  {market:10} " + "   ".join(cells))

    print("\nWin odds and implied win-if-nominated (%)")
    print(f"  {'':26}{'Poly win':>9}{'Kalshi':>8}{'Poly if nom':>13}{'Kalshi':>8}")
    implied = {venue: win_if_nominated(view) for venue, view in views.items()}
    wins = {venue: view["winner"]["odds"] for venue, view in views.items()}
    top = sorted(set(wins["Polymarket"]) | set(wins["Kalshi"]),
                 key=lambda c: -max(wins["Polymarket"].get(c, 0), wins["Kalshi"].get(c, 0)))[:12]
    for c in top:
        print(f"  {names[c]:26}{percent(wins['Polymarket'].get(c)):>9}{percent(wins['Kalshi'].get(c)):>8}"
              f"{percent(implied['Polymarket'].get(c)):>13}{percent(implied['Kalshi'].get(c)):>8}")

    print("\nParty check (%): candidate win odds added up, against the party market")
    for venue, view in views.items():
        check = party_check(view, parties)
        sums, market = check["candidates"], check["party_market"]
        print(f"  {venue:11} D {percent(sums['D'])} vs {percent(market.get('D'))}   "
              f"R {percent(sums['R'])} vs {percent(market.get('R'))}   unassigned {percent(sums['unassigned'])}")
    return 1 if poly_unmapped or kalshi_unmapped else 0


if __name__ == "__main__":
    raise SystemExit(report())
