"""Constant leverage (Ayres & Nalebuff; Kelly): always hold a fixed multiple of the US market.
Plan fixed before any result: docs/constant-leverage/PLAN.md. Write-up: docs/constant-leverage/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       Yahoo dividend-adjusted UPRO into index_daily (UPRO_ADJ); SSO_ADJ and SPY_ADJ already stored
  backtest   run the plan; results to ~/MarketData/constant_leverage/backtest-<date>.json
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, start_run
import vol_managed as vm
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "constant_leverage"

# ---- fixed by the plan
LEVELS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
SPREAD = 0.01
COST = 0.0005
START, POST = "1927-01", "2009-01"
STRETCH20 = range(1927, 2007)
STRETCH10 = range(1927, 2017)
COHORTS = range(1927, 1987)
CRASHES = {"1929-1932": ("1929-09", "1932-06"), "2007-2009": ("2007-11", "2009-02"), "2020 Covid": ("2020-02", "2020-03")}


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    now = datetime.now(ET).isoformat(timespec="seconds")
    t = yf.download("UPRO", start="2009-01-01", progress=False, auto_adjust=True)["Close"].iloc[:, 0].dropna()
    rows = [("UPRO_ADJ", d.strftime("%Y-%m-%d"), None, None, None, float(v), "yahoo-adjusted", now) for d, v in t.items()]
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), f"UPRO {t.index[0]:%Y-%m-%d}..{t.index[-1]:%Y-%m-%d}"


def daily_reset(d: pd.DataFrame, L: float) -> pd.Series:
    Rm = d["ex"] + d["rf"]
    rp = d["rf"] + L * d["ex"] - (L - 1) * SPREAD / 252
    trade = L * (Rm - rp).abs()          # re-levering back to L after the day's move
    return rp - COST * trade


def monthly_reset(d: pd.DataFrame, L: float) -> tuple[pd.Series, bool]:
    """Set to L at each month's start, drift within the month. Returns monthly returns, wiped-out flag."""
    Rm = 1 + d["ex"] + d["rf"]
    debt_g = 1 + d["rf"] + SPREAD / 252
    out, wiped = {}, False
    for m, g in d.groupby(d.index.to_period("M")):
        if wiped:
            out[m] = 0.0
            continue
        N = L * np.cumprod(Rm.loc[g.index].values)
        D = (L - 1) * np.cumprod(debt_g.loc[g.index].values)
        V = N - D
        if (V <= 0).any():
            out[m], wiped = -1.0, True
            continue
        v_end = V[-1]
        v_end -= COST * abs(L * v_end - N[-1])     # trade back to L at the month's end
        out[m] = v_end - 1
    return pd.Series(out), wiped


def monthly(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def stretches(a: pd.Series, b: pd.Series, years: range, n: int) -> dict:
    ratios = []
    for y in years:
        s = slice(pd.Period(f"{y}-01", "M"), pd.Period(f"{y + n - 1}-12", "M"))
        ratios.append(float(np.prod(1 + a.loc[s]) / np.prod(1 + b.loc[s])))
    r = np.array(ratios)
    return {"share_ahead": round(float((r > 1).mean()), 2), "worst_ratio": round(float(r.min()), 2),
            "worst_start": int(list(years)[int(r.argmin())]), "median_ratio": round(float(np.median(r)), 2)}


def saver(rs: list[pd.Series], y: int) -> float:
    """$1 at the start of every month for 40 years; rs gives the return series for years 1-20 and 21-40."""
    months = pd.period_range(f"{y}-01", f"{y + 39}-12", freq="M")
    W = 0.0
    for i, m in enumerate(months):
        r = rs[0] if i < 240 else rs[1]
        W = (W + 1) * (1 + float(r.get(m, 0.0)))
    return W


def job_backtest(db) -> dict:
    d = vm.load(db, "us")
    rfm = tn.rf_monthly(db)
    mkt = monthly(d["ex"] + d["rf"]).loc[pd.Period(START, "M"):]
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/constant-leverage/PLAN.md",
           "data": [str(d.index[0].date()), str(d.index[-1].date())], "levels": {}}
    series = {}
    for L in LEVELS:
        dr = monthly(daily_reset(d, L)).loc[pd.Period(START, "M"):]
        mr, wiped = monthly_reset(d, L)
        mr = mr.loc[pd.Period(START, "M"):]
        series[L] = {"daily": dr, "monthly": mr}
        lv = {}
        for kind, s in (("daily", dr), ("monthly", mr)):
            whole, post = vm.stats(s, rfm), vm.stats(s.loc[pd.Period(POST, "M"):], rfm)
            lv[kind] = {"whole": whole, "after_2009": post,
                        "wiped_out": bool(wiped) if kind == "monthly" else bool((s <= -1).any()),
                        "stretch20": stretches(s, mkt, STRETCH20, 20), "stretch10": stretches(s, mkt, STRETCH10, 10),
                        "crashes": {n: round(float(np.prod(1 + s.loc[pd.Period(a, "M"):pd.Period(z, "M")]) - 1) * 100, 1)
                                    for n, (a, z) in CRASHES.items()},
                        "worst_year": min(((str(y), round(float(np.prod(1 + s[s.index.year == y]) - 1) * 100, 1))
                                           for y in sorted(set(s.index.year))), key=lambda x: x[1])}
        res["levels"][str(L)] = lv
    # Kelly from past data only (expanding window of monthly excess returns), read at each decade's start
    ex = mkt - rfm.reindex(mkt.index)
    res["kelly_from_past"] = {str(y): round(float(ex.loc[:pd.Period(f"{y - 1}-12", "M")].mean() / ex.loc[:pd.Period(f"{y - 1}-12", "M")].var()), 2)
                              for y in (1937, 1950, 1970, 1990, 2010, 2026)}
    res["kelly_whole"] = round(float(ex.mean() / ex.var()), 2)
    best = max(LEVELS, key=lambda L: res["levels"][str(L)]["monthly"]["whole"]["10k_becomes"])
    res["best_L_hindsight_monthly"] = best
    # saver
    one, two = series[1.0]["monthly"], series[2.0]["monthly"]
    sv = {"1x": [], "2x": [], "2x_then_1x": []}
    for y in COHORTS:
        sv["1x"].append(saver([one, one], y))
        sv["2x"].append(saver([two, two], y))
        sv["2x_then_1x"].append(saver([two, one], y))
    a = {k: np.array(v) for k, v in sv.items()}
    res["saver"] = {
        "cohorts": len(COHORTS),
        "median_end_per_dollar_saved": {k: round(float(np.median(v) / 480), 2) for k, v in a.items()},
        "worst_end_per_dollar_saved": {k: round(float(v.min() / 480), 2) for k, v in a.items()},
        "share_beating_1x": {k: round(float((v > a["1x"]).mean()), 2) for k, v in a.items() if k != "1x"},
        "worst_ratio_to_1x": {k: round(float((v / a["1x"]).min()), 2) for k, v in a.items() if k != "1x"},
    }
    # real funds
    px = pd.concat({s: tn._daily_index(db, f"{s}_ADJ") for s in ("SPY", "SSO", "UPRO")}, axis=1)
    this_month = pd.Period(date.today().strftime("%Y-%m"), "M")
    real = {}
    for fund, start in (("SSO", "2006-07"), ("UPRO", "2009-07")):
        p = px[[fund, "SPY"]].dropna()
        m = {k: monthly(p[k].pct_change().dropna()).loc[pd.Period(start, "M"):this_month - 1] for k in (fund, "SPY")}
        real[fund] = {k: vm.stats(v, rfm) for k, v in m.items()}
        real[fund]["crash_2020"] = {k: round(float(np.prod(1 + v.loc[pd.Period("2020-02", "M"):pd.Period("2020-03", "M")]) - 1) * 100, 1) for k, v in m.items()}
        real[fund]["year_2022"] = {k: round(float(np.prod(1 + v[v.index.year == 2022]) - 1) * 100, 1) for k, v in m.items()}
        if fund == "SSO":
            real[fund]["crash_2008"] = {k: round(float(np.prod(1 + v.loc[pd.Period("2007-11", "M"):pd.Period("2009-02", "M")]) - 1) * 100, 1) for k, v in m.items()}
    res["real_funds"] = real
    two_m = res["levels"]["2.0"]["monthly"]
    one_m = res["levels"]["1.0"]["monthly"]
    res["verdict"] = {
        "1_more_money_whole_and_after_2009": two_m["whole"]["10k_becomes"] > one_m["whole"]["10k_becomes"]
        and two_m["after_2009"]["10k_becomes"] > one_m["after_2009"]["10k_becomes"],
        "2_ahead_in_80pct_of_20yr": two_m["stretch20"]["share_ahead"] >= 0.80,
        "3_never_wiped_and_worst_drop_above_-80": (not two_m["wiped_out"]) and two_m["whole"]["worst_drop"] > -80,
    }
    res["verdict"]["2x_worth_holding"] = all(res["verdict"].values())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "leverage-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "backtest":
        print(json.dumps(job_backtest(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
