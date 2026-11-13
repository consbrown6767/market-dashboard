"""Earnings-week premium: hold S&P 500 stocks only around their earnings announcements.
Plan fixed before any result: docs/earnings-premium/PLAN.md. Write-up: docs/earnings-premium/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  backtest   run the plan; results to ~/MarketData/earnings_premium/backtest-<date>.json
Uses earnings_dates, daily_bars_adj, shared/sp500_history.json and SPY_ADJ (already stored).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect
import vol_managed as vm
import classic_strategies as cs
import pairs_model as pm
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "earnings_premium"

# ---- fixed by the plan
START, END = "2016-01-05", "2026-10-31"
COST = 0.0005
WIN_A = (-1, 0, 1)
WIN_B = (-5, -4, -3, -2, -1)
PRED_HALF = 5                 # 11 days centred on the predicted date
HALVES = (("2016-01-01", "2020-12-31"), ("2021-01-01", "2026-10-31"))


def load(db):
    px = pd.read_sql("SELECT symbol, date, close FROM daily_bars_adj WHERE date >= '2015-06-01'", db)
    px = px.pivot(index="date", columns="symbol", values="close")
    px.index = pd.to_datetime(px.index)
    px = px.sort_index()
    ev = pd.read_sql("SELECT symbol, ts, timing FROM earnings_dates", db)
    ev["d"] = pd.to_datetime(ev["ts"].str[:10])
    return px, ev


def universe(px: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """True where the stock was an S&P 500 member that year and has announcement dates."""
    hist = pm.history()
    has = set(ev["symbol"])
    U = pd.DataFrame(False, index=px.index, columns=px.columns)
    for y in sorted(set(px.index.year)):
        mem = hist.get(str(y), {}).get("members", {})
        cols = [s for s in px.columns if s in mem and s in has]
        U.loc[U.index.year == y, cols] = True
    return U


def reaction_pos(days: pd.DatetimeIndex, d: pd.Timestamp, timing: str) -> int:
    """Position of the reaction day E in days."""
    if timing == "amc":
        return int(days.searchsorted(d, side="right"))
    return int(days.searchsorted(d, side="left"))


def window_mask(days, cols, events, offsets) -> pd.DataFrame:
    """events: iterable of (symbol, position of the centre day). Marks centre+offset days."""
    M = np.zeros((len(days), len(cols)), bool)
    ci = {c: i for i, c in enumerate(cols)}
    for sym, p in events:
        if sym not in ci:
            continue
        for o in offsets:
            q = p + o
            if 0 <= q < len(days):
                M[q, ci[sym]] = True
    return pd.DataFrame(M, index=days, columns=cols)


def actual_events(px, ev):
    days = px.index
    return [(r.symbol, reaction_pos(days, r.d, r.timing)) for r in ev.itertuples()]


def predicted_events(px, ev):
    """Date of the same quarter a year earlier + 364 days (needs only past information)."""
    days = px.index
    out = []
    for sym, g in ev.groupby("symbol"):
        ds = sorted(g["d"])
        for d in ds:
            target = d - pd.Timedelta(days=364)
            prior = [x for x in ds if abs((x - target).days) <= 45 and x < d - pd.Timedelta(days=200)]
            if not prior:
                continue
            pd_ = min(prior, key=lambda x: abs((x - target).days)) + pd.Timedelta(days=364)
            out.append((sym, int(days.searchsorted(pd_, side="left"))))
    return out


def premium(r: pd.DataFrame, U: pd.DataFrame, W: pd.DataFrame) -> pd.Series:
    """Daily: mean return of in-window stocks minus mean of the whole universe, days with both."""
    inw = r.where(W & U)
    ew = r.where(U)
    p = inw.mean(axis=1) - ew.mean(axis=1)
    return p[inw.count(axis=1) > 0].dropna()


def portfolio(r: pd.DataFrame, H: pd.DataFrame, rf_d: pd.Series, cost: float) -> tuple[pd.Series, float]:
    """Equal weight in held stocks each day (H = holdings for that day's return). T-bills if none.
    Returns daily returns after costs and turnover per year (one-way, share of the portfolio)."""
    rr = r.fillna(0.0)
    n = H.sum(axis=1)
    w = H.div(n.replace(0, np.nan), axis=0).fillna(0.0)
    gross = (w * rr).sum(axis=1)
    gross = gross.where(n > 0, rf_d.reindex(gross.index).fillna(0.0))
    drift = (w * (1 + rr)).div((1 + gross).where(n > 0, 1.0), axis=0)     # end-of-day weights
    trade = (w - drift.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = (1 + gross) * (1 - cost * trade) - 1
    return net, float(trade.mean() * 252 / 2)


def monthly(s: pd.Series) -> pd.Series:
    m = (1 + s).groupby(s.index.to_period("M")).prod() - 1
    return m.loc[pd.Period(START[:7], "M"):pd.Period(END[:7], "M")]


def tstat(p: pd.Series) -> dict:
    return {"days": len(p), "bp_per_day": round(float(p.mean()) * 1e4, 2), "t": round(cs.nw_t(p.values, 10), 2)}


def job_backtest(db) -> dict:
    px, ev = load(db)
    px = px.loc[:END]
    r = px.pct_change()
    U = universe(px, ev)
    days, cols = px.index, px.columns
    act = actual_events(px, ev)
    WA = window_mask(days, cols, act, WIN_A) & U
    WB = window_mask(days, cols, act, WIN_B) & U
    WP = window_mask(days, cols, predicted_events(px, ev), range(-PRED_HALF, PRED_HALF + 1)) & U
    sl = slice(START, END)
    r, U, WA, WB, WP = r.loc[sl], U.loc[sl], WA.loc[sl], WB.loc[sl], WP.loc[sl]
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/earnings-premium/PLAN.md",
           "data": [str(r.index[0].date()), str(r.index[-1].date())],
           "universe_avg": round(float(U.sum(axis=1).mean()), 1),
           "in_window_A_avg": round(float(WA.sum(axis=1).mean()), 1),
           "days_with_nobody_in_A": int((WA.sum(axis=1) == 0).sum())}
    pA = premium(r, U, WA)
    res["premium_A"] = {"whole": tstat(pA), **{f"{a[:4]}-{z[:4]}": tstat(pA.loc[a:z]) for a, z in HALVES}}
    res["premium_A_years"] = {str(y): tstat(pA[pA.index.year == y]) for y in sorted(set(pA.index.year))}
    res["premium_B_pre"] = tstat(premium(r, U, WB))
    res["premium_predicted_dates"] = tstat(premium(r, U, WP))
    # by timing and day of the window
    Ufull = universe(px, ev)
    timing = list(ev["timing"])
    for kind in ("bmo", "amc"):
        sub = [e for e, t in zip(act, timing) if (t == "amc") == (kind == "amc")]
        res[f"premium_A_{kind}"] = tstat(premium(r, U, (window_mask(days, cols, sub, WIN_A) & Ufull).loc[sl]))
    for o in (-1, 0, 1):
        res[f"premium_day_{o:+d}"] = tstat(premium(r, U, (window_mask(days, cols, act, (o,)) & Ufull).loc[sl]))
    # sectors (that year's sector label)
    hist = pm.history()
    sec = {}
    for s in cols:
        for y in sorted(hist):
            if s in hist[y]["members"]:
                sec[s] = hist[y]["members"][s]
    by_sec = {}
    for name in sorted(set(sec.values())):
        cs_ = [c for c in cols if sec.get(c) == name]
        by_sec[name] = tstat(premium(r[cs_], U[cs_], WA[cs_]))
    res["premium_A_by_sector"] = by_sec
    # portfolios
    d_us, _ = cs.market(db, "us")
    rf_d = d_us["rf"].reindex(r.index).ffill()
    A, turnA = portfolio(r, WA, rf_d, COST)
    A0, _ = portfolio(r, WA, rf_d, 0.0)
    EW, _ = portfolio(r, U, rf_d, 0.0)
    spy = tn._daily_index(db, "SPY_ADJ").pct_change().reindex(r.index)
    rfm = tn.rf_monthly(db)
    m = {"A_after_costs": monthly(A), "A_no_cost": monthly(A0), "EW_same_stocks": monthly(EW), "SPY": monthly(spy)}
    res["turnover_A_per_year"] = round(turnA, 1)
    res["stats"] = {k: vm.stats(v, rfm) for k, v in m.items()}
    res["years"] = {str(y): {k: round(float(np.prod(1 + v[v.index.year == y]) - 1) * 100, 1) for k, v in m.items()}
                    for y in sorted(set(m["SPY"].index.year))}
    # break-even cost: where A after costs ends with EW's money
    lo, hi = 0.0, 0.01
    target = res["stats"]["EW_same_stocks"]["10k_becomes"]
    for _ in range(40):
        mid = (lo + hi) / 2
        v = vm.stats(monthly(portfolio(r, WA, rf_d, mid)[0]), rfm)["10k_becomes"]
        lo, hi = (mid, hi) if v > target else (lo, mid)
    res["break_even_cost_pct_vs_EW"] = round(lo * 100, 4)
    st = res["stats"]
    halves_pos = all(res["premium_A"][f"{a[:4]}-{z[:4]}"]["bp_per_day"] > 0 for a, z in HALVES)
    res["verdict"] = {
        "premium_real": res["premium_A"]["whole"]["t"] >= 2 and res["premium_A"]["whole"]["bp_per_day"] > 0 and halves_pos,
        "A_beats_spy_and_ew": all(st["A_after_costs"]["10k_becomes"] > st[k]["10k_becomes"]
                                  and st["A_after_costs"]["sharpe"] > st[k]["sharpe"] for k in ("SPY", "EW_same_stocks")),
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
        print(json.dumps(job_backtest(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
