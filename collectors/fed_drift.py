"""Fed-day drift (Lucca & Moench) and the Fed cycle (Cieslak, Morse & Vissing-Jorgensen) on SPY.
Plan fixed before any result: docs/fed-drift/PLAN.md. Write-up: docs/fed-drift/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  backtest   run the plan; results to ~/MarketData/fed_drift/backtest-<date>.json
Uses econ_calendar (fomc), SPY_ADJ in index_daily, and Alpaca SPY minute bars (fetched live, not stored).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ALPACA_DATA, ET, alpaca, connect, load_keys
import vol_managed as vm
import classic_strategies as cs
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "fed_drift"

# ---- fixed by the plan
ADD = ("2013-05-01", "2017-02-01", "2017-11-01", "2018-08-01", "2019-05-01")
DROP = ("2003-09-15",)
COST = 0.0001
COST_ALSO = 0.0005
A_POST, B_POST, END = "2012-01-01", "2017-01-01", "2026-10-31"
FIRST = "2002-01-01"


def meetings(db) -> list[pd.Timestamp]:
    ds = {r[0] for r in db.execute("SELECT date FROM econ_calendar WHERE event='fomc' AND date <= ?", (END,))}
    ds = (ds | set(ADD)) - set(DROP)
    return sorted(pd.Timestamp(d) for d in ds)


def frame(db) -> pd.DataFrame:
    spy = tn._daily_index(db, "SPY_ADJ")
    d_us, _ = cs.market(db, "us")
    df = pd.DataFrame({"r": spy.pct_change()})
    df["rf"] = d_us["rf"].reindex(df.index).ffill()
    df = df.loc[FIRST:END].dropna()
    days = df.index
    pos = [int(days.searchsorted(m)) for m in meetings(db) if m >= days[0]]
    assert all(days[p] == m for p, m in zip(pos, [m for m in meetings(db) if m >= days[0]])), "meeting not a trading day"
    df["day0"] = False
    df.iloc[pos, df.columns.get_loc("day0")] = True
    # cycle: k = trading days since the latest meeting, where the day before a meeting already counts as k=-1
    k = np.full(len(days), np.nan)
    ps = np.array(pos)
    for i in range(len(days)):
        nxt = ps[ps >= i]
        if len(nxt) and nxt[0] == i + 1:
            k[i] = -1
            continue
        prev = ps[ps <= i]
        if len(prev):
            k[i] = i - prev[-1]
    df["k"] = k
    df["week"] = np.floor((df["k"] + 1) / 5)
    return df.dropna(subset=["week"])


def hold(df: pd.DataFrame, on: pd.Series, cost: float) -> pd.Series:
    """Daily returns: SPY when on (decided in advance), T-bill otherwise, cost on each switch."""
    on = on.astype(float)
    sw = on.diff().abs().fillna(on.iloc[0])
    return df["rf"] + on * (df["r"] - df["rf"]) - cost * sw


def monthly(s):
    return (1 + s).groupby(s.index.to_period("M")).prod() - 1


def welch(a: np.ndarray, b: np.ndarray) -> float:
    return float((a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))


def drift_test(df, a, z) -> dict:
    s = df.loc[a:z]
    ex = s["r"] - s["rf"]
    d0, other = ex[s["day0"]].values, ex[~s["day0"]].values
    return {"meetings": len(d0), "day0_pct": round(d0.mean() * 100, 3), "other_days_pct": round(other.mean() * 100, 4),
            "t": round(welch(d0, other), 2), "share_up": round(float((d0 > 0).mean()), 2),
            "share_of_total_excess": round(float(d0.sum() / ex.sum()), 2) if ex.sum() > 0 else None}


def intraday(db) -> dict:
    """2 pm day -1 to 1:59 pm day 0, SPY minute bars (Alpaca, SIP, adjusted), 2016-2026."""
    keys = load_keys()
    df = frame(db)
    days = df.index
    out = []
    for m in [m for m in meetings(db) if m >= pd.Timestamp("2016-01-01")]:
        i = days.get_loc(m)
        prev = days[i - 1]
        px = {}
        for d in (prev, m):
            t0 = datetime(d.year, d.month, d.day, 13, 59, tzinfo=ET)
            b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols="SPY", timeframe="1Min", feed="sip", adjustment="all",
                       start=t0.isoformat(), end=(t0 + timedelta(minutes=1)).isoformat(), limit=10)
            bars = (b.get("bars") or {}).get("SPY") or []
            px[d] = bars[0]["c"] if bars else None
            time.sleep(0.35)
        if px[prev] and px[m]:
            out.append({"date": str(m.date()), "ret_pct": round((px[m] / px[prev] - 1) * 100, 3)})
    r = np.array([o["ret_pct"] for o in out])
    allex = (df.loc["2016":END, "r"].mean()) * 100
    return {"meetings": len(r), "avg_pct": round(float(r.mean()), 3), "t_vs_zero": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 2),
            "share_up": round(float((r > 0).mean()), 2), "avg_spy_day_pct_2016_2026": round(float(allex), 3), "each": out}


def job_backtest(db) -> dict:
    df = frame(db)
    rfm = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/fed-drift/PLAN.md",
           "data": [str(df.index[0].date()), str(df.index[-1].date())], "meetings": int(df["day0"].sum())}
    res["A_drift"] = {"after_2012": drift_test(df, A_POST, END), "before_2002_2011": drift_test(df, FIRST, "2011-12-31")}
    res["A_years"] = {str(y): round(float((df.loc[str(y)]["r"][df.loc[str(y)]["day0"]]).mean() * 100), 2)
                      for y in sorted(set(df.index.year))}
    even = (df["week"] % 2 == 0)
    ex = df["r"] - df["rf"]
    res["weeks"] = {}
    for a, z, name in ((FIRST, "2016-12-31", "2002_2016"), (B_POST, END, "2017_2026")):
        s = df.loc[a:z]
        e = ex.loc[a:z]
        res["weeks"][name] = {str(int(w)): {"days": int((s["week"] == w).sum()), "avg_excess_bp": round(float(e[s["week"] == w].mean()) * 1e4, 2)}
                              for w in range(0, 8)}
        res["weeks"][name]["even_minus_odd_bp"] = round(float(e[even.loc[a:z]].mean() - e[~even.loc[a:z]].mean()) * 1e4, 2)
        res["weeks"][name]["t_even_vs_odd"] = round(welch(e[even.loc[a:z]].values, e[~even.loc[a:z]].values), 2)
    m = {"B_cycle": monthly(hold(df, even, COST)), "B_cycle_cost_0.05": monthly(hold(df, even, COST_ALSO)),
         "B_cycle_no_cost": monthly(hold(df, even, 0.0)), "A_drift_days_only": monthly(hold(df, df["day0"], COST)),
         "SPY": monthly(df["r"])}
    res["in_market_share_B"] = round(float(even.mean()), 2)
    res["switches_per_year_B"] = round(float(even.astype(int).diff().abs().sum() / (len(df) / 252)), 1)
    res["stats"] = {}
    for name, a, z in (("2017_2026", B_POST, END), ("2002_2016", FIRST, "2016-12-31"), ("2002_2026", FIRST, END)):
        res["stats"][name] = {k: vm.stats(v.loc[pd.Period(a[:7], "M"):pd.Period(z[:7], "M")], rfm) for k, v in m.items()}
    res["years"] = {str(y): {k: round(float(np.prod(1 + v[v.index.year == y]) - 1) * 100, 1) for k, v in m.items()}
                    for y in sorted(set(m["SPY"].index.year))}
    res["intraday_2pm_2016_2026"] = intraday(db)
    a, s = res["A_drift"]["after_2012"], res["stats"]["2017_2026"]
    res["verdict"] = {
        "A_drift_real": a["t"] >= 2 and a["day0_pct"] > a["other_days_pct"],
        "B_beats_spy": s["B_cycle"]["10k_becomes"] > s["SPY"]["10k_becomes"] and s["B_cycle"]["sharpe"] > s["SPY"]["sharpe"],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "backtest":
        r = job_backtest(db)
        r["intraday_2pm_2016_2026"].pop("each")
        print(json.dumps(r, indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
