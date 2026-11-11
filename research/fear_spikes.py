"""Fear-spike study: what happened to the S&P 500 after days like 2026-11-05.

  spike      the VIX closes >= 30% above the day before AND above the 3-month VIX (near-term fear
             higher than longer-term fear). Only the first day of an episode counts: a spike within
             20 trading days of the previous one is skipped.
  measured   SPY over the next 5 / 20 / 60 trading days, from the spike day's close, against the
             same horizons from every day since 2007 (the baseline).
  splits     credit = HYG / IEF (junk bonds vs Treasuries). "Beforehand" (its last 20 days) and
             "VIX back to normal within 5 days" are known in real time; "credit in the next 5 days"
             is hindsight and labelled so: it explains outcomes, it can't be traded on the day.

Data: Yahoo daily history (dividend-adjusted closes), fetched fresh on every run and not stored.
Starts 2007-05 (HYG and the 3-month VIX begin then). Small sample (~20 spikes): read it as clues.

Usage: ~/MarketData/.venv/bin/python research/fear_spikes.py
"""

from __future__ import annotations

import json
import statistics as st
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collectors"))
from options_collector import http_get  # noqa: E402  (retries; truststore for certificates)

SYMBOLS = ["^VIX", "^VIX3M", "SPY", "QQQ", "RSP", "HYG", "IEF"]
START = "2007-05-01"
JUMP = 0.30
GAP = 20


def history(sym: str) -> dict[str, float]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1=946684800&period2=9999999999&interval=1d&events=div,split")
    m = json.loads(http_get(url, {"User-Agent": "Mozilla/5.0"}))["chart"]["result"][0]
    ind = m["indicators"]
    closes = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    off = timedelta(seconds=m["meta"].get("gmtoffset", 0))
    return {(datetime.fromtimestamp(t, timezone.utc) + off).date().isoformat(): c
            for t, c in zip(m["timestamp"], closes) if c}


def pct(x) -> str:
    return "     -" if x is None else f"{x:+6.1f}"


def summary(name: str, values: list) -> str:
    v = [x for x in values if x is not None]
    if not v:
        return f"  {name:40} none"
    return (f"  {name:40} n={len(v):2}  median {st.median(v):+5.1f}%  avg {st.mean(v):+5.1f}%  "
            f"up {100 * sum(x > 0 for x in v) / len(v):3.0f}%")


def main() -> int:
    H = {s: history(s) for s in SYMBOLS}
    D = [d for d in sorted(set.intersection(*(set(h) for h in H.values()))) if d >= START]
    g = lambda s, i: H[s][D[i]]
    credit = lambda i: g("HYG", i) / g("IEF", i)
    fwd = lambda s, i, n: (g(s, i + n) / g(s, i) - 1) * 100 if i + n < len(D) else None

    spikes, last = [], -GAP - 1
    for i in range(GAP + 1, len(D)):
        if g("^VIX", i) / g("^VIX", i - 1) - 1 >= JUMP and g("^VIX", i) > g("^VIX3M", i):
            if i - last > GAP:
                spikes.append(i)
            last = i

    rows = []
    for i in spikes:
        normal = next((k for k in range(1, 6) if i + k < len(D) and g("^VIX", i + k) < g("^VIX3M", i + k)), None)
        rows.append(dict(
            date=D[i], vix=g("^VIX", i), jump=(g("^VIX", i) / g("^VIX", i - 1) - 1) * 100, spy=fwd("SPY", i - 1, 1),
            credit_before=(credit(i) / credit(i - GAP) - 1) * 100,
            credit_after=(credit(i + 5) / credit(i) - 1) * 100 if i + 5 < len(D) else None,
            normal=normal, f5=fwd("SPY", i, 5), f20=fwd("SPY", i, 20), f60=fwd("SPY", i, 60),
            from5=fwd("SPY", i + 5, 55) if i + 5 < len(D) else None,
            worst20=min((g("SPY", i + k) / g("SPY", i) - 1) * 100 for k in range(1, 21)) if i + 20 < len(D) else None,
            qqq20=fwd("QQQ", i, 20), rsp20=fwd("RSP", i, 20)))

    print(f"Fear spikes since {D[0]} (data to {D[-1]}): {len(rows)}\n")
    print("date        VIX   jump  SPY day | credit 20d before | SPY next 5d  20d  60d  worst 20d "
          "| VIX normal by day | credit next 5d")
    for r in rows:
        print(f"{r['date']}  {r['vix']:5.1f} {r['jump']:+5.0f}%  {r['spy']:+5.1f}% |      {r['credit_before']:+5.1f}%      "
              f"|  {pct(r['f5'])}{pct(r['f20'])}{pct(r['f60'])}  {pct(r['worst20'])}   "
              f"| {r['normal'] or ('not yet' if r['credit_after'] is None else 'no'):>9} | {pct(r['credit_after'])}")

    base = {n: [fwd("SPY", i, n) for i in range(len(D) - n)] for n in (5, 20, 60)}
    for key, n in (("f5", 5), ("f20", 20), ("f60", 60)):
        print(f"\nSPY over the next {n} days")
        print(summary("any day (baseline)", base[n]))
        print(summary("after a spike", [r[key] for r in rows]))
        print(summary("credit steady beforehand (> -1%)", [r[key] for r in rows if r["credit_before"] > -1]))
        print(summary("credit sliding beforehand (<= -1%)", [r[key] for r in rows if r["credit_before"] <= -1]))
        print(summary("[hindsight] credit held next 5 days", [r[key] for r in rows if (r["credit_after"] or 0) >= -1]))
        print(summary("[hindsight] credit fell >1% next 5 days", [r[key] for r in rows if (r["credit_after"] or 0) < -1]))

    print("\nKnown by day 5: SPY from day 5 to day 60")
    print(summary("VIX back below 3-month VIX within 5 days", [r["from5"] for r in rows if r["normal"]]))
    print(summary("VIX still above it after 5 days", [r["from5"] for r in rows if not r["normal"]]))
    print(f"\nMedian worst dip in the 20 days after: {st.median(r['worst20'] for r in rows if r['worst20'] is not None):+.1f}%")
    print(f"Median 20-day bounce: QQQ {st.median(r['qqq20'] for r in rows if r['qqq20'] is not None):+.1f}%, "
          f"RSP {st.median(r['rsp20'] for r in rows if r['rsp20'] is not None):+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
