"""Risk budget model: pick a risk level, the model aims for the most return at that risk, using US
stocks, 10-year Treasuries and T-bills. Equal risk (Asness, Frazzini & Pedersen 2012) + trend filter
(Faber 2007) + scaling to the chosen volatility (Harvey et al. 2018). No return forecasts.
Plan fixed before any result: docs/risk-budget/PLAN.md. Write-up: docs/risk-budget/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       10-year Treasury yields (FRED DGS10) into rates_daily (stocks: vol_managed.py data)
  bondcheck  yearly 10-year Treasury returns from the yields, to check against known years
  backtest   run the plan; results to ~/MarketData/risk_budget/backtest-<date>.json
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, start_run
import vol_managed as vm
from classic_strategies import nw_t

RESULTS_DIR = Path.home() / "MarketData" / "risk_budget"

# ---- fixed by the plan
LEVELS = (0.05, 0.10, 0.15, 0.20)
JUDGED = (0.10, 0.15)
VOL_WINDOW = 36
TREND_WINDOW = 10
CAP = 2.0
TRADE_COST = 0.0005
BORROW_SPREAD = 0.01
START, END = "1965-07", "2026-09"
POST_PUB = "2011-01"
RISING = (("1965-07", "1981-09"), ("2021-01", "2023-10"))
FALLING = (("1981-10", "2020-12"),)
CRASHES = {"1973-74 bear market": ("1973-01", "1974-09"), "1987 crash": ("1987-08", "1987-12"),
           "2000-02 tech bust": ("2000-09", "2002-09"), "2008 crisis": ("2007-11", "2009-02"),
           "2020 Covid crash": ("2020-02", "2020-03"), "2022 stocks and bonds fall": ("2022-01", "2022-12")}
ASSETS = ("stocks", "bonds")


# ---------------------------------------------------------------- data

def job_data(db) -> tuple[str, int, str]:
    # FRED answers Python's standard user agent (see stock_direction.job_data).
    with urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", timeout=60) as r:
        text = r.read().decode()
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows = []
    for line in text.splitlines()[1:]:
        d, v = line.split(",")
        if v not in ("", "."):
            rows.append(("DGS10", d, float(v), "fred", now))
    db.executemany("INSERT OR REPLACE INTO rates_daily VALUES (?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), f"DGS10 {rows[0][1]}..{rows[-1][1]} ({len(rows)} days)"


def bond_returns(db) -> pd.Series:
    """Monthly total return of a 10-year Treasury from month-end yields: a par bond bought at last
    month's yield (coupon = that yield, paid twice a year), priced a month later at this month's
    yield, plus a month of coupon."""
    y = pd.read_sql("SELECT date, value FROM rates_daily WHERE series='DGS10' ORDER BY date", db,
                    index_col="date")["value"] / 100
    y.index = pd.to_datetime(y.index)
    ym = y.groupby(y.index.to_period("M")).last()
    n = 2 * (10 - 1 / 12)
    c, y1 = ym.shift(1), ym
    price = (c / 2) * (1 - (1 + y1 / 2) ** -n) / (y1 / 2) + (1 + y1 / 2) ** -n
    return (price - 1 + c / 12).dropna()


def monthly_frame(db) -> pd.DataFrame:
    mo = vm.monthly(vm.load(db, "us"))[["R", "rf"]].rename(columns={"R": "stocks"})
    mo["bonds"] = bond_returns(db)
    return mo


# ---------------------------------------------------------------- weights (each decided at month-end t-1)

def _past(df: pd.DataFrame, i: int, n: int) -> pd.DataFrame:
    return df.iloc[max(0, i - n):i]


def weights(mo: pd.DataFrame, kind: str, level: float, vol_window: int = VOL_WINDOW,
            trend_window: int = TREND_WINDOW, cap: float = CAP) -> pd.DataFrame:
    x = pd.DataFrame({a: mo[a] - mo["rf"] for a in ASSETS})
    lvl = (1 + mo[list(ASSETS)].fillna(0)).cumprod()
    out = {}
    for i in range(1, len(mo)):
        t = mo.index[i]
        if t < pd.Period(START, "M"):
            continue
        w = {"stocks": 0.0, "bonds": 0.0}
        if kind == "spy":
            w["stocks"] = 1.0
        elif kind == "A":          # stocks + T-bills, fixed by the market's volatility over all past years
            sd = x["stocks"].iloc[:i].std() * np.sqrt(12)
            w["stocks"] = min(level / sd, cap)
        elif kind == "B":          # 60/40 scaled by its volatility over all past years with bond data
            mix = (0.6 * x["stocks"] + 0.4 * x["bonds"]).iloc[:i].dropna()
            k = min(level / (mix.std() * np.sqrt(12)), cap / 1.0)
            w["stocks"], w["bonds"] = 0.6 * k, 0.4 * k
        else:
            past = _past(x, i, vol_window)
            if past.dropna().shape[0] < vol_window:
                continue
            keep = {a: True for a in ASSETS}
            if kind in ("model", "stocks_trend"):
                for a in ASSETS:
                    lv = lvl[a].iloc[max(0, i - trend_window):i]
                    keep[a] = bool(lv.iloc[-1] > lv.mean())
            use = ["stocks"] if kind == "stocks_trend" else list(ASSETS)
            raw = {a: 1 / past[a].std() for a in use}
            tot = sum(raw.values())
            base = {a: (raw[a] / tot if keep[a] else 0.0) for a in use}
            vec = np.array([base.get(a, 0.0) for a in ASSETS])
            if vec.sum() > 0:
                cov = past[list(ASSETS)].cov().values * 12
                pv = float(np.sqrt(vec @ cov @ vec))
                vec = vec * level / pv
                if vec.sum() > cap:
                    vec = vec * cap / vec.sum()
            w = dict(zip(ASSETS, vec))
        out[t] = w
    return pd.DataFrame(out).T


def run(mo: pd.DataFrame, w: pd.DataFrame, cost: float = TRADE_COST, spread: float = BORROW_SPREAD,
        delay: int = 0) -> pd.Series:
    w = w.shift(delay).dropna() if delay else w
    res, held = {}, None
    for t, wt in w.iterrows():
        row = mo.loc[t]
        R = {a: (row[a] if not np.isnan(row[a]) else row["rf"]) for a in ASSETS}
        gross = wt.sum()
        r = row["rf"] + sum(wt[a] * (R[a] - row["rf"]) for a in ASSETS) - max(gross - 1, 0) * spread / 12
        prev = held if held is not None else wt
        r -= cost * float(np.abs(wt - prev).sum())
        res[t] = r
        held = pd.Series({a: wt[a] * (1 + R[a]) / (1 + r) for a in ASSETS})
    return pd.Series(res)


# ---------------------------------------------------------------- scoring

def window(s: pd.Series, a: str, z: str) -> pd.Series:
    return s.loc[pd.Period(a, "M"):pd.Period(z, "M")]


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    e = r - rf.reindex(r.index)
    return float(e.mean() / e.std() * np.sqrt(12))


def summary(series: dict, mo, a=START, z=END) -> dict:
    return {k: vm.stats(window(v, a, z), mo["rf"]) for k, v in series.items()}


def level_test(mo: pd.DataFrame, level: float) -> dict:
    series = {k: run(mo, weights(mo, k, level)) for k in ("model", "A", "B", "stocks_trend", "rp_notrend")}
    series["spy"] = run(mo, weights(mo, "spy", level))
    for k in series:
        series[k] = window(series[k], START, END)
    m, A, B = series["model"], series["A"], series["B"]
    rf = mo["rf"]
    out = {"full": summary(series, mo), "post_pub": summary(series, mo, POST_PUB, END)}
    out["rising"] = [{k: round(sharpe(window(series[k], a, z), rf), 3) for k in ("model", "A", "B")} | {"period": f"{a}..{z}"}
                     for a, z in RISING]
    out["falling"] = [{k: round(sharpe(window(series[k], a, z), rf), 3) for k in ("model", "A", "B")} | {"period": f"{a}..{z}"}
                      for a, z in FALLING]
    dec = {}
    for d0 in (1970, 1980, 1990, 2000, 2010, 2020):
        z = f"{d0 + 9}-12" if d0 < 2020 else END
        dec[f"{d0}s"] = {k: round(sharpe(window(series[k], f"{d0}-01", z), rf), 3) for k in ("model", "A", "B")}
    out["decades"] = dec
    gap = (m - A.reindex(m.index)).dropna().values
    out["t_gap_vs_A"] = round(nw_t(gap), 2)
    out["boot_sharpe_gap_vs_A"] = vm.bootstrap_gap((m - rf.loc[m.index]).values, (A - rf.loc[A.index]).values)
    roll, wins = 0, 0
    for i in range(0, len(m) - 120 + 1, 12):
        sm, sa = m.iloc[i:i + 120], A.iloc[i:i + 120]
        roll += 1
        wins += np.prod(1 + sm) > np.prod(1 + sa)
    out["rolling_10y_more_money_than_A"] = f"{wins} of {roll}"
    cr = {}
    for name, (a, z) in CRASHES.items():
        cr[name] = {k: round(float(np.prod(1 + window(series[k], a, z)) - 1) * 100, 1) for k in ("model", "A", "B", "spy")}
    out["crashes"] = cr
    out["years"] = {str(y): {k: round(float(np.prod(1 + g) - 1) * 100, 1) for k, g in
                             ((k, series[k][series[k].index.year == y]) for k in ("model", "A", "B", "spy"))}
                    for y in sorted(set(m.index.year))}
    wm = weights(mo, "model", level)
    wm = window(wm.sum(axis=1), START, END)
    out["model_exposure"] = {"avg_stocks": round(float(window(weights(mo, "model", level)["stocks"], START, END).mean()), 2),
                             "avg_bonds": round(float(window(weights(mo, "model", level)["bonds"], START, END).mean()), 2),
                             "avg_total": round(float(wm.mean()), 2), "share_at_cap": round(float((wm >= CAP - 1e-9).mean()), 3),
                             "share_all_cash": round(float((wm <= 1e-9).mean()), 3)}
    # verdict pieces
    f, p = out["full"], out["post_pub"]
    out["verdict"] = {
        "1_full_sharpe_money_vs_A_B_and_drop_vs_A": f["model"]["sharpe"] > max(f["A"]["sharpe"], f["B"]["sharpe"])
        and f["model"]["10k_becomes"] > max(f["A"]["10k_becomes"], f["B"]["10k_becomes"]) and f["model"]["worst_drop"] > f["A"]["worst_drop"],
        "2_post_pub_sharpe_money_vs_A_B": p["model"]["sharpe"] > max(p["A"]["sharpe"], p["B"]["sharpe"])
        and p["model"]["10k_becomes"] > max(p["A"]["10k_becomes"], p["B"]["10k_becomes"]),
        "3_t_at_least_3": out["t_gap_vs_A"] >= 3,
        "4_rising_rates_both": all(r["model"] > r["A"] for r in out["rising"]),
        "5_decades_4_of_6": sum(v["model"] > v["A"] for v in dec.values()) >= 4,
        "6_risk_within_3_points": abs(f["model"]["vol"] - level * 100) <= 3,
    }
    out["verdict"]["passes"] = all(out["verdict"].values())
    return out


def sensitivity(mo: pd.DataFrame, level: float) -> dict:
    A = window(run(mo, weights(mo, "A", level)), START, END)
    base = {"A (to beat)": A}
    cases = {
        "model (plan)": dict(), "vol window 12": dict(vol_window=12), "vol window 24": dict(vol_window=24),
        "vol window 60": dict(vol_window=60), "trend 6": dict(trend_window=6), "trend 12": dict(trend_window=12),
        "cap 1.5x": dict(cap=1.5), "cap 3x": dict(cap=3.0),
    }
    out = {}
    for name, kw in cases.items():
        s = window(run(mo, weights(mo, "model", level, **kw)), START, END)
        out[name] = {"full": vm.stats(s, mo["rf"]), "post_pub": vm.stats(window(s, POST_PUB, END), mo["rf"])}
    wm = weights(mo, "model", level)
    for name, kw in {"double costs": dict(cost=2 * TRADE_COST), "borrow T-bill + 2%": dict(spread=0.02),
                     "one-month delay": dict(delay=1)}.items():
        s = window(run(mo, wm, **kw), START, END)
        out[name] = {"full": vm.stats(s, mo["rf"]), "post_pub": vm.stats(window(s, POST_PUB, END), mo["rf"])}
    out["A (to beat)"] = {"full": vm.stats(A, mo["rf"]), "post_pub": vm.stats(window(A, POST_PUB, END), mo["rf"])}
    return out


def bondcheck(db) -> dict:
    b = bond_returns(db)
    return {str(y): round(float(np.prod(1 + g) - 1) * 100, 2) for y, g in b.groupby(b.index.year)}


def job_backtest(db) -> dict:
    mo = monthly_frame(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/risk-budget/PLAN.md",
           "data": [START, END], "levels": {}}
    for lv in LEVELS:
        res["levels"][f"{int(lv * 100)}%"] = level_test(mo, lv)
    res["passes_at_10_and_15"] = all(res["levels"][f"{int(l * 100)}%"]["verdict"]["passes"] for l in JUDGED)
    res["sensitivity_15%"] = sensitivity(mo, 0.15)
    res["bond_years"] = bondcheck(db)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "riskbudget-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "bondcheck":
        print(json.dumps(bondcheck(db), indent=0))
    elif cmd == "backtest":
        print(json.dumps(job_backtest(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
