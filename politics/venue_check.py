#!/usr/bin/env python3
"""When Polymarket and Kalshi disagree, which one moves to close the gap?

Uses data/history/daily.json. For every candidate and day with both prices, take the gap
(Kalshi minus Polymarket) and see how each venue moved over the next week. If a venue is the one
that gets corrected, its price moves toward the other. If gaps are noise, they just fade.

Candidates are all counted together and days overlap, so the samples aren't independent. Read
this as a rough description of the past year, not a tested trading signal.

Usage: python3 venue_check.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAILY = HERE / "data" / "history" / "daily.json"
HORIZON_DAYS = 7
MIN_GAP = 0.01  # smaller gaps are mostly rounding


def paired_days(markets: dict) -> list:
    """(polymarket today, kalshi today, polymarket later, kalshi later) for each usable day."""
    rows = []
    for people in markets.values():
        for venues in people.values():
            poly, kalshi = venues.get("polymarket", {}), venues.get("kalshi", {})
            days = sorted(set(poly) & set(kalshi))
            for start, end in zip(days, days[HORIZON_DAYS:]):
                rows.append((poly[start], kalshi[start], poly[end], kalshi[end]))
    return rows


def slope(xs: list, ys: list) -> float:
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sum((x - mean_x) ** 2 for x in xs)


def summarize(rows: list) -> dict:
    wide = [r for r in rows if abs(r[1] - r[0]) >= MIN_GAP]
    gaps = [k - p for p, k, _, _ in wide]
    poly_moves = [later - p for p, _, later, _ in wide]
    kalshi_moves = [later - k for _, k, _, later in wide]
    later_gaps = [lk - lp for _, _, lp, lk in wide]
    return {
        "days": len(rows), "gap_days": len(wide),
        "average_gap": sum(abs(g) for g in gaps) / len(gaps),
        # Share of a gap that each venue closes in a week. A positive Polymarket number means it
        # moves up when Kalshi is higher. A negative Kalshi number means it moves down.
        "polymarket_follows": slope(gaps, poly_moves),
        "kalshi_follows": -slope(gaps, kalshi_moves),
        "gap_left_after": slope(gaps, later_gaps),
    }


def check(path: Path = DAILY) -> dict:
    if not path.exists():
        return {}
    return summarize(paired_days(json.loads(path.read_text(encoding="utf-8"))["markets"]))


if __name__ == "__main__":
    result = check()
    print(f"{result['gap_days']:,} candidate-days with a gap of at least {MIN_GAP:.0%} (average {result['average_gap']:.1%})")
    print(f"After {HORIZON_DAYS} days: Polymarket closes {result['polymarket_follows']:.0%} of the gap, "
          f"Kalshi closes {result['kalshi_follows']:.0%}, and {result['gap_left_after']:.0%} is left")
