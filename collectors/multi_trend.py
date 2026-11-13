"""Trend across many markets: Faber's five-asset trend rule (long-only) and Moskowitz-Ooi-Pedersen time-series
momentum (long/short), on real funds. Plan fixed before any result: docs/multi-trend/PLAN.md. Write-up:
docs/multi-trend/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       dividend-adjusted daily closes of SPY, EFA, IEF, VNQ, DBC from Yahoo into index_daily (<SYM>_ADJ)
  backtest   run the plan; results to ~/MarketData/multi_trend/backtest-<date>.json
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
import classic_strategies as cs
import risk_budget as rb
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "multi_trend"
FUNDS = ("SPY", "EFA", "IEF", "VNQ", "DBC")

# ---- fixed by the plan
START, END = "2007-03", "2026-10"
POST_MOP = "2013-01"
COST = 0.0005
BORROW = 0.005
MF_FEE = 0.0085
TARGET_VOL = 0.40
MAX_W = 2.0
VOL_DAYS = 126


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows, notes = [], []
    for sym in FUNDS:
        t = yf.download(sym, start="2000-01-01", progress=False, auto_adjust=True)["Close"].iloc[:, 0].dropna()
        rows += [(f"{sym}_ADJ", d.strftime("%Y-%m-%d"), None, None, None, float(v), "yahoo-adjusted", now) for d, v in t.items()]
        notes.append(f"{sym} {t.index[0]:%Y-%m-%d}..{t.index[-1]:%Y-%m-%d}")
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), "; ".join(notes)


def prices(db) -> pd.DataFrame:
    px = pd.concat({s: tn._daily_index(db, f"{s}_ADJ") for s in FUNDS}, axis=1).dropna()
    return px


def daily_rf(db, index) -> pd.Series:
    d, _ = cs.market(db, "us")
    return d["rf"].reindex(index).ffill()


def simulate(px: pd.DataFrame, rf: pd.Series, targets: dict, fee: float = 0.0) -> pd.Series:
    """targets: {month-end date: pd.Series of signed weights}. New weights take effect at the next day's
    close. Notionals drift with prices between rebalances; cash earns the T-bill. Returns daily returns."""
    r = px.pct_change()
    days = px.index
    eff = {}
    for d0, w in targets.items():
        i = days.get_loc(d0)
        if i + 1 < len(days):
            eff[days[i + 1]] = w
    V, n = 1.0, None
    out = {}
    started = False
    for k in range(1, len(days)):
        d = days[k]
        if n is not None:
            ret = r.iloc[k].fillna(0)
            pnl = float((n * (ret - rf.iloc[k])).sum())
            short = float(-n[n < 0].sum())
            newV = V * (1 + rf.iloc[k]) + pnl - BORROW / 252 * short - fee / 252 * V
            n = n * (1 + ret)
            out[d] = newV / V - 1
            V = newV
        if d in eff:
            target = eff[d] * V
            prev = n if n is not None else target * 0
            V -= COST * float((target - prev).abs().sum())
            n = target.copy()
            started = True
    return pd.Series(out)


def month_ends(px: pd.DataFrame) -> list:
    s = pd.Series(px.index, index=px.index)
    return list(s.groupby(px.index.to_period("M")).last())


def targets_A(px: pd.DataFrame) -> dict:
    me = month_ends(px)
    mpx = px.loc[me]
    out = {}
    for i in range(9, len(me)):
        avg = mpx.iloc[i - 9:i + 1].mean()
        on = (mpx.iloc[i] > avg).astype(float)
        out[me[i]] = on * 0.20
    return out


def targets_B(px: pd.DataFrame, rf: pd.Series) -> dict:
    me = month_ends(px)
    r = px.pct_change()
    out = {}
    for i in range(12, len(me)):
        d, d12 = me[i], me[i - 12]
        ret12 = px.loc[d] / px.loc[d12] - 1
        rf12 = float(np.prod(1 + rf.loc[d12:d].iloc[1:]) - 1)
        sign = np.where(ret12 > rf12, 1.0, -1.0)
        k = px.index.get_loc(d)
        vol = r.iloc[k - VOL_DAYS + 1:k + 1].std() * np.sqrt(252)
        w = pd.Series(sign, index=px.columns) * TARGET_VOL / vol / len(FUNDS)
        out[d] = w.clip(-MAX_W, MAX_W)
    return out


def targets_fixed(px: pd.DataFrame, weights: dict) -> dict:
    w = pd.Series({s: weights.get(s, 0.0) for s in px.columns})
    return {d: w for d in month_ends(px)}


def monthly(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def window(s, a, z=None):
    return s.loc[pd.Period(a, "M"):(pd.Period(z, "M") if z else None)]


def long_check(db) -> dict:
    """1994-2026 on French data: US stocks, Developed ex US stocks, 10-year Treasury (from yields). Monthly."""
    _, us = cs.market(db, "us")
    _, intl = cs.market(db, "dev_ex_us")
    df = pd.DataFrame({"us": us["R"], "intl": intl["R"], "bond": rb.bond_returns(db), "rf": us["rf"]}).dropna()
    A, B = {}, {}
    lvl = (1 + df[["us", "intl", "bond"]]).cumprod()
    for i in range(12, len(df)):
        t = df.index[i]
        past = lvl.iloc[i - 10:i]
        on = (lvl.iloc[i - 1] > past.mean()).astype(float)
        A[t] = float(df.at[t, "rf"] + (on * (df.loc[t, ["us", "intl", "bond"]] - df.at[t, "rf"])).sum() / 3)
        r12 = lvl.iloc[i - 1] / lvl.iloc[i - 13] - 1 if i >= 13 else None
        if r12 is None:
            continue
        rf12 = float(np.prod(1 + df["rf"].iloc[i - 12:i]) - 1)
        vol = (df[["us", "intl", "bond"]].iloc[i - 12:i]).std() * np.sqrt(12)
        w = (np.sign(r12 - rf12) * TARGET_VOL / vol / 3).clip(-MAX_W, MAX_W)
        B[t] = float(df.at[t, "rf"] + (w * (df.loc[t, ["us", "intl", "bond"]] - df.at[t, "rf"])).sum() - MF_FEE / 12)
    A, B = pd.Series(A), pd.Series(B)
    rf = df["rf"]
    out = {}
    for name, s in (("A_trend", A), ("B_long_short", B), ("C_half_us_half_B", 0.5 * df["us"].reindex(B.index) + 0.5 * B),
                    ("US stocks", df["us"])):
        out[name] = vm.stats(window(s.dropna(), "1994-01", "2026-09"), rf)
    return out


def job_backtest(db) -> dict:
    px = prices(db)
    rf = daily_rf(db, px.index)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/multi-trend/PLAN.md",
           "data": [str(px.index[0].date()), str(px.index[-1].date())]}
    sims = {
        "A_trend_five": simulate(px, rf, targets_A(px)),
        "B_long_short_trend": simulate(px, rf, targets_B(px, rf), fee=MF_FEE),
        "five_funds_20pct": simulate(px, rf, targets_fixed(px, {s: 0.2 for s in FUNDS})),
        "60_40": simulate(px, rf, targets_fixed(px, {"SPY": 0.6, "IEF": 0.4})),
    }
    m = {k: monthly(v) for k, v in sims.items()}
    m["SPY"] = monthly(px["SPY"].pct_change().dropna())
    m["C_half_spy_half_B"] = 0.5 * m["SPY"] + 0.5 * m["B_long_short_trend"]
    this_month = pd.Period(date.today().strftime("%Y-%m"), "M")
    m = {k: window(v.loc[:this_month - 1], START, END) for k, v in m.items()}
    rfm = tn.rf_monthly(db)
    res["whole"] = {k: vm.stats(v, rfm) for k, v in m.items()}
    res["since_2013"] = {k: vm.stats(window(v, POST_MOP), rfm) for k, v in m.items()}
    res["years"] = {str(y): {k: round(float(np.prod(1 + v[v.index.year == y]) - 1) * 100, 1) for k, v in m.items()}
                    for y in sorted(set(m["SPY"].index.year))}
    crashes = {"2008 crisis": ("2007-11", "2009-02"), "2020 Covid crash": ("2020-02", "2020-03"), "2022": ("2022-01", "2022-12")}
    res["crashes"] = {n: {k: round(float(np.prod(1 + window(v, a, z)) - 1) * 100, 1) for k, v in m.items()} for n, (a, z) in crashes.items()}
    exB = (m["B_long_short_trend"] - rfm.reindex(m["B_long_short_trend"].index)).values
    res["B_excess_per_year"] = round(float(exB.mean()) * 1200, 2)
    res["B_t"] = round(cs.nw_t(exB), 2)
    # how often A and B changed positions
    tA, tB = targets_A(px), targets_B(px, rf)
    ka = sorted(tA)
    res["A_changes_per_year"] = round(sum(int((tA[ka[i]] != tA[ka[i - 1]]).sum()) for i in range(1, len(ka))) / (len(ka) / 12), 1)
    kb = sorted(tB)
    res["B_sign_flips_per_year"] = round(sum(int((np.sign(tB[kb[i]]) != np.sign(tB[kb[i - 1]])).sum()) for i in range(1, len(kb))) / (len(kb) / 12), 1)
    res["B_last_weights"] = {str(kb[-1].date()): {k: round(float(v), 2) for k, v in tB[kb[-1]].items()}}
    res["long_check_1994_2026"] = long_check(db)
    w, s13 = res["whole"], res["since_2013"]

    def beats(k):
        return w[k]["10k_becomes"] > w["SPY"]["10k_becomes"] and w[k]["sharpe"] > w["SPY"]["sharpe"]

    def safer(k):
        return all(p[k]["sharpe"] > p["SPY"]["sharpe"] and p[k]["worst_drop"] > p["SPY"]["worst_drop"] for p in (w, s13))

    res["verdict"] = {
        "A_beats_spy": beats("A_trend_five"), "A_safer": safer("A_trend_five"),
        "B_works": res["B_t"] >= 2 and res["B_excess_per_year"] > 0 and res["years"]["2008"]["B_long_short_trend"] > 0
        and res["years"]["2022"]["B_long_short_trend"] > 0,
        "C_beats_spy": beats("C_half_spy_half_B"), "C_safer": safer("C_half_spy_half_B"),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "multitrend-data")
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
