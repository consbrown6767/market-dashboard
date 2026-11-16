"""Polymarket long-shot bias test. Plan fixed first: docs/polymarket-bias/PLAN.md.
Reads the stored hourly snapshots; writes ~/MarketData/poly_bias/results-<date>.json. Research only.

    poly_bias.py            # run the plan's tests once
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DB = Path.home() / "MarketData" / "options.db"
OUT = Path.home() / "MarketData" / "poly_bias"
# ---- fixed by the plan
YES, NO = 0.98, 0.02
MIN_HOURS, MIN_VOL = 48, 1000.0
BUCKETS = [0.01, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95, 0.99]
DRAWS, SEED = 2000, 7


def load() -> tuple[pd.DataFrame, dict]:
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = """WITH span AS (SELECT market_id, MIN(fetched_at) f0, MAX(fetched_at) f1 FROM poly_snapshots GROUP BY market_id)
           SELECT m.id, m.event_id, e.grp, e.end_date AS event_end, m.end_date, s.f0, s.f1,
                  a.price p0, a.best_bid bid0, a.best_ask ask0, a.volume_24h vol0, b.price p1
           FROM span s JOIN poly_markets m ON m.id = s.market_id LEFT JOIN poly_events e ON e.id = m.event_id
           JOIN poly_snapshots a ON a.market_id = s.market_id AND a.fetched_at = s.f0
           JOIN poly_snapshots b ON b.market_id = s.market_id AND b.fetched_at = s.f1"""
    d = pd.read_sql(q, db)
    newest = db.execute("SELECT MAX(fetched_at) FROM poly_snapshots").fetchone()[0]
    counts = {"markets_stored": len(d)}
    d = d[d["f1"] < newest]                                     # no longer listed: it ended
    counts["ended"] = len(d)
    d["hours"] = (pd.to_datetime(d["f1"], utc=True) - pd.to_datetime(d["f0"], utc=True)).dt.total_seconds() / 3600
    settled = d[(d["p1"] >= YES) | (d["p1"] <= NO)]
    counts["ended_settled"] = len(settled)
    counts["ended_not_settled_left_out"] = len(d) - len(settled)
    d = settled.copy()
    d["yes"] = (d["p1"] >= YES).astype(float)
    both = d["bid0"].notna() & d["ask0"].notna() & (d["ask0"] > d["bid0"])
    d["price"] = np.where(both, (d["bid0"] + d["ask0"]) / 2, d["p0"])
    d = d[(d["hours"] >= MIN_HOURS) & (d["price"] >= 0.01) & (d["price"] <= 0.99) & (d["vol0"] >= MIN_VOL)]
    counts["in_test"] = len(d)
    counts["events_in_test"] = int(d["event_id"].nunique())
    d["grp"] = d["grp"].fillna("unknown")
    return d.reset_index(drop=True), counts


def boot(d: pd.DataFrame, col: str, by_event: bool) -> dict:
    """Mean of `col` with a 95% range from resampling whole events."""
    g = d.groupby("event_id")[col].agg(["sum", "count", "mean"])
    sums, ns, means = g["sum"].values, g["count"].values, g["mean"].values
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), size=(DRAWS, len(g)))
    draws = means[idx].mean(axis=1) if by_event else sums[idx].sum(axis=1) / ns[idx].sum(axis=1)
    point = float(means.mean() if by_event else sums.sum() / ns.sum())
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"mean": round(point, 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4), "n": int(ns.sum()), "events": int(len(g))}


def rule(d: pd.DataFrame, name: str) -> dict:
    if name == "sell_long_shots":            # buy No at 1 - Yes bid, pays 1 if No
        t = d[(d["price"] <= 0.10) & d["bid0"].notna() & (d["bid0"] > 0)].copy()
        cost = 1 - t["bid0"]
        t["ret"] = (1 - t["yes"]) / cost - 1
    else:                                    # buy Yes at the ask
        t = d[(d["price"] >= 0.90) & d["ask0"].notna() & (d["ask0"] < 1)].copy()
        t["ret"] = t["yes"] / t["ask0"] - 1
    if t["event_id"].nunique() < 20:
        return {"n": len(t), "note": "too few events"}
    ends = pd.to_datetime(t["f1"], utc=True)
    cut = t.groupby("event_id")["f1"].max().pipe(pd.to_datetime, utc=True).median()
    biggest = t["grp"].value_counts().idxmax()
    out = {"per_market": boot(t, "ret", False), "per_event": boot(t, "ret", True),
           "first_half": boot(t[ends <= cut], "ret", False), "second_half": boot(t[ends > cut], "ret", False),
           "biggest_group": biggest, "without_biggest_group": boot(t[t["grp"] != biggest], "ret", False),
           "win_rate": round(float((t["ret"] > 0).mean()), 4), "worst": round(float(t["ret"].min()), 3),
           "by_group": {g: {"n": len(x), "mean": round(float(x["ret"].mean()), 4)} for g, x in t.groupby("grp")}}
    out["passes"] = {"1_per_market": out["per_market"]["lo"] > 0, "2_per_event": out["per_event"]["lo"] > 0,
                     "3_both_halves": out["first_half"]["mean"] > 0 and out["second_half"]["mean"] > 0,
                     "4_without_biggest": out["without_biggest_group"]["mean"] > 0}
    out["pass"] = all(out["passes"].values())
    return out


def main() -> int:
    d, counts = load()
    d["bucket"] = pd.cut(d["price"], BUCKETS, include_lowest=True)
    d["gap"] = d["yes"] - d["price"]          # positive = happened more often than priced
    calib = []
    for b, x in d.groupby("bucket", observed=True):
        if x["event_id"].nunique() < 5:
            continue
        g = boot(x, "gap", False)
        calib.append({"bucket": f"{b.left * 100:.0f}-{b.right * 100:.0f}%", "n": len(x), "events": int(x["event_id"].nunique()),
                      "avg_price": round(float(x["price"].mean()), 4), "share_yes": round(float(x["yes"].mean()), 4),
                      "gap": g["mean"], "gap_lo": g["lo"], "gap_hi": g["hi"]})
    res = {"made": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"), "plan": "docs/polymarket-bias/PLAN.md",
           "counts": counts, "by_group": d["grp"].value_counts().to_dict(),
           "first_seen": [d["f0"].min(), d["f0"].max()], "calibration": calib,
           "sell_long_shots": rule(d, "sell_long_shots"), "buy_favourites": rule(d, "buy_favourites")}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"results-{datetime.now().date()}.json"
    path.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
