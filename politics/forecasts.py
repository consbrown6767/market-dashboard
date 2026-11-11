#!/usr/bin/env python3
"""Append-only forecast log and scorecard.

Three kinds of score, because one election can't validate a model on its own:
  1. Brier scores on questions that have resolved (lower is better; always saying 50% scores 0.25).
  2. "Did the market move toward me?": each logged gap between raw and market is checked
     7, 30 and 90 days later. This is a proxy, not proof of being right.
  3. Final Brier scores on nominees and the winner, which use the same code as 1.

Each log entry stores a hash of the entry before it, so editing history breaks the chain and
`verify` finds it. That gives a tamper check without needing git.

Usage: python3 forecasts.py verify
       python3 forecasts.py scorecard
       python3 forecasts.py questions
       python3 forecasts.py resolve "senate-2026/AK-dem" no "Sullivan held the seat"
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FORECASTS = DATA / "forecasts.jsonl"
RESOLUTIONS = DATA / "resolutions.jsonl"
GAPS = DATA / "gaps.jsonl"

CHECK_DAYS = (7, 30, 90)
MIN_GAP = 0.03  # smaller differences between raw and market are treated as agreement
MIN_MOVE = 0.005  # market moves smaller than this count as "no move"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def chain_append(path: Path, entry: dict) -> dict:
    """Add one entry to a hash-chained log."""
    log = read_log(path)
    entry = {**entry, "seq": len(log) + 1, "prev_hash": log[-1]["hash"] if log else ""}
    entry["hash"] = entry_hash(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def verify_log(path: Path) -> int | None:
    """Return the sequence number of the first broken entry, or None if the log is intact."""
    previous = ""
    for position, entry in enumerate(read_log(path), start=1):
        if entry["seq"] != position or entry["prev_hash"] != previous or entry_hash(entry) != entry["hash"]:
            return position
        previous = entry["hash"]
    return None


def add_forecast(question: str, prob: float, source: str, resolve_by: str, note: str = "",
                 path: Path = FORECASTS) -> dict:
    if not 0 <= prob <= 1:
        raise ValueError(f"Probability must be between 0 and 1: {prob}")
    return chain_append(path, {"made_at": now_utc(), "question": question, "prob": prob, "source": source,
                               "resolve_by": resolve_by, "note": note})


def resolve(question: str, outcome: bool, note: str = "", path: Path = RESOLUTIONS) -> dict:
    return chain_append(path, {"resolved_at": now_utc(), "question": question, "outcome": bool(outcome), "note": note})


def brier_by_source(forecasts: list[dict], resolutions: list[dict]) -> dict:
    """Average Brier score per source. Each source's latest forecast on a question counts, so a
    question repeated every turn can't outweigh the others."""
    outcomes = {r["question"]: r["outcome"] for r in resolutions}
    latest = {}
    for f in forecasts:
        if f["question"] in outcomes:
            latest[(f["source"], f["question"])] = f["prob"]
    errors = defaultdict(list)
    for (source, question), prob in latest.items():
        errors[source].append((prob - outcomes[question]) ** 2)
    return {source: {"brier": sum(e) / len(e), "questions": len(e)} for source, e in errors.items()}


def record_gap(market: str, candidate: str, raw: float, market_price: float, path: Path = GAPS) -> dict | None:
    if abs(raw - market_price) < MIN_GAP:
        return None
    return chain_append(path, {"at": now_utc(), "market": market, "candidate": candidate, "raw": raw,
                               "market_price": market_price})


def gap_results(gaps: list[dict], price_at, today: datetime | None = None) -> dict:
    """Score each gap at each checkpoint that has arrived. `price_at(market, candidate, when)`
    returns the market price at that time, or None if there's no data."""
    today = today or datetime.now(timezone.utc)
    # A gap logged twice in a day is one bet, not two. Keep the latest.
    gaps = list({(g["market"], g["candidate"], g["at"][:10]): g for g in gaps}.values())
    results = {days: {"toward": 0, "away": 0, "flat": 0, "no_data": 0} for days in CHECK_DAYS}
    for gap in gaps:
        start = datetime.fromisoformat(gap["at"])
        for days in CHECK_DAYS:
            due = start + timedelta(days=days)
            if due > today:
                continue
            later = price_at(gap["market"], gap["candidate"], due)
            if later is None:
                results[days]["no_data"] += 1
                continue
            move = later - gap["market_price"]
            if abs(move) < MIN_MOVE:
                results[days]["flat"] += 1
            elif (move > 0) == (gap["raw"] > gap["market_price"]):
                results[days]["toward"] += 1
            else:
                results[days]["away"] += 1
    return results


def scorecard(price_at=None) -> dict:
    forecasts, resolutions, gaps = read_log(FORECASTS), read_log(RESOLUTIONS), read_log(GAPS)
    return {
        "forecasts": len(forecasts),
        "open_questions": len({f["question"] for f in forecasts} - {r["question"] for r in resolutions}),
        "resolved": len(resolutions),
        "brier": brier_by_source(forecasts, resolutions),
        "gaps_logged": len(gaps),
        "gap_checks": gap_results(gaps, price_at or (lambda *_: None)),
        "tamper_check": "ok" if not any(verify_log(p) for p in (FORECASTS, RESOLUTIONS, GAPS)) else "BROKEN",
    }


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "scorecard"
    if command == "verify":
        broken = {p.name: verify_log(p) for p in (FORECASTS, RESOLUTIONS, GAPS)}
        print(json.dumps(broken, indent=2))
        return 1 if any(broken.values()) else 0
    if command == "questions":
        done = {r["question"] for r in read_log(RESOLUTIONS)}
        for question in sorted({f["question"] for f in read_log(FORECASTS)} - done):
            print(question)
        return 0
    if command == "resolve":
        question, answer = sys.argv[2], sys.argv[3].lower()
        if answer not in ("yes", "no"):
            raise SystemExit("The answer must be yes or no")
        if question not in {f["question"] for f in read_log(FORECASTS)}:
            raise SystemExit(f"No forecasts for {question}. Run: python3 forecasts.py questions")
        print(resolve(question, answer == "yes", sys.argv[4] if len(sys.argv) > 4 else ""))
        return 0
    print(json.dumps(scorecard(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
