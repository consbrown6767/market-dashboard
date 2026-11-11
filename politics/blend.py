#!/usr/bin/env python3
"""Combine raw model odds with market odds. This is the only place the two ever meet.

Blending happens in log-odds, which behaves better than a plain average near 0% and 100%:
    logit(blend) = w * logit(raw) + (1 - w) * logit(market), then rescaled to 100%

w starts low because the market should be assumed better until the scorecard shows otherwise.

Market odds need one extra step to line up with the model. Named people the model doesn't
rate, and any "unlisted" gap, all go into the party's "field" bucket.
"""

from __future__ import annotations

import math

import clean_markets as cm

BLEND_WEIGHT = 0.25
FLOOR = 0.001  # log-odds can't handle exactly 0%
RAW_MARKETS = ("winner", "nominee_d", "nominee_r")


def logit(p: float) -> float:
    p = min(max(p, FLOOR), 1 - FLOOR)
    return math.log(p / (1 - p))


def inverse_logit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def blend_odds(raw: dict, market: dict, weight: float = BLEND_WEIGHT) -> dict:
    names = set(raw) | set(market)
    pooled = {n: inverse_logit(weight * logit(raw.get(n, 0)) + (1 - weight) * logit(market.get(n, 0))) for n in names}
    total = sum(pooled.values())
    return {n: p / total for n, p in pooled.items()}


def align_to_model(view: dict, market: str, modelled: set, parties: dict) -> dict:
    """One venue's market on the model's list of names, summing to 100%."""
    aligned = {}
    side = {"nominee_d": "D", "nominee_r": "R"}.get(market)

    def field_for(candidate):
        return f"field-{(side or parties.get(candidate) or 'D').lower()}"

    for candidate, odds in view[market]["odds"].items():
        key = candidate if candidate in modelled else field_for(candidate)
        aligned[key] = aligned.get(key, 0) + odds
    gap = view[market]["unlisted"]
    if side:
        aligned[f"field-{side.lower()}"] = aligned.get(f"field-{side.lower()}", 0) + gap
    else:
        for key in ("field-d", "field-r"):
            aligned[key] = aligned.get(key, 0) + gap / 2
    return aligned


def average(venues: list) -> dict:
    names = set().union(*venues)
    return {n: sum(v.get(n, 0) for v in venues) / len(venues) for n in names}


def market_views() -> dict:
    candidates = cm.load_candidates()
    polymarket, _ = cm.load_polymarket(cm.POLYMARKET_DIR, cm.name_lookup(candidates, "polymarket"), cm.LIVE_DIR)
    kalshi, _ = cm.load_kalshi(cm.KALSHI_DIR, cm.name_lookup(candidates, "kalshi"), cm.KALSHI_HISTORY)
    return {"polymarket": cm.latest_view(polymarket), "kalshi": cm.latest_view(kalshi),
            "parties": {c["id"]: c["party"] for c in candidates},
            "books": {"polymarket": polymarket, "kalshi": kalshi}}


def build_tables(raw: dict, views: dict, weight: float = BLEND_WEIGHT) -> dict:
    """Rows of raw, venue, market and blended odds for each market."""
    parties = views["parties"]
    tables = {}
    for market in RAW_MARKETS:
        modelled = set(raw[market])
        poly = align_to_model(views["polymarket"], market, modelled, parties)
        kalshi = align_to_model(views["kalshi"], market, modelled, parties)
        consensus = average([poly, kalshi])
        blended = blend_odds(raw[market], consensus, weight)
        tables[market] = {n: {"raw": raw[market].get(n, 0), "polymarket": poly.get(n, 0), "kalshi": kalshi.get(n, 0),
                              "market": consensus.get(n, 0), "blend": blended[n]} for n in blended}
    party_markets = [views[v]["party"]["odds"] for v in ("polymarket", "kalshi")]
    consensus = average(party_markets)
    total = sum(consensus.values())
    consensus = {k: v / total for k, v in consensus.items()}
    blended = blend_odds(raw["party"], consensus, weight)
    tables["party"] = {n: {"raw": raw["party"][n], "polymarket": party_markets[0].get(n, 0), "kalshi": party_markets[1].get(n, 0),
                           "market": consensus[n], "blend": blended[n]} for n in ("D", "R")}
    return tables
