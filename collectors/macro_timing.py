"""Macro timing model: each month, predict next month's stock premium from 14 economic indicators
(Goyal & Welch 2008), average the predictions (Rapach, Strauss & Zhou 2010), never below zero
(Campbell & Thompson 2008), and size the stock holding by it. Plan fixed before any result:
docs/macro-timing/PLAN.md. Write-up: docs/macro-timing/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       Goyal's monthly predictor file (1871-2025) into gw_monthly
  backtest   run the plan; results to ~/MarketData/macro_timing/backtest-<date>.json
"""

from __future__ import annotations

import io
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from options_collector import ET, connect, finish_run, http_get, start_run
from classic_strategies import nw_t
import vol_managed as vm

RESULTS_DIR = Path.home() / "MarketData" / "macro_timing"
GW_URL = "https://docs.google.com/spreadsheets/d/1qwpl2R_DNujpU5YUkk8lacP1tTeMb9iJ/export?format=csv"

# ---- fixed by the plan
FIT_FROM = "1927-01"
OOS_FROM, OOS_TO = "1947-01", "2025-12"
POST_PUB = "2006-01"
GAMMA = 3.0
VAR_MONTHS = 60
W_MIN, W_MAX = 0.0, 1.5
TRADE_COST = 0.0005
BORROW_SPREAD = 0.01
INDICATORS = ("dp", "dy", "ep", "de", "svar", "bm", "ntis", "tbl", "lty", "ltr", "tms", "dfy", "dfr", "infl")
LAGS = {"infl": 1, "ep": 3, "de": 3}          # extra months before the value was public
CRASHES = {"1973-74 bear market": ("1973-01", "1974-09"), "1987 crash": ("1987-08", "1987-12"),
           "2000-02 tech bust": ("2000-09", "2002-09"), "2008 crisis": ("2007-11", "2009-02"),
           "2020 Covid crash": ("2020-02", "2020-03"), "2020 rebound (Apr-Dec)": ("2020-04", "2020-12"),
           "2022 bear year": ("2022-01", "2022-12")}

SCHEMA = """
CREATE TABLE IF NOT EXISTS gw_monthly (
    month TEXT, series TEXT, value REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (month, series)
);
"""


def job_data(db) -> tuple[str, int, str]:
    df = pd.read_csv(io.BytesIO(http_get(GW_URL)), thousands=",", na_values=["NaN"])
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows = []
    for _, r in df.iterrows():
        m = str(int(r["yyyymm"]))
        month = f"{m[:4]}-{m[4:]}"
        for c in df.columns[1:]:
            if pd.notna(r[c]):
                rows.append((month, c, float(r[c]), "goyal", now))
    db.executemany("INSERT OR REPLACE INTO gw_monthly VALUES (?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), f"{len(df)} months {df['yyyymm'].iloc[0]}..{df['yyyymm'].iloc[-1]}"


def frame(db, lags: bool = True) -> pd.DataFrame:
    d = pd.read_sql("SELECT month, series, value FROM gw_monthly", db).pivot(index="month", columns="series", values="value")
    d.index = pd.PeriodIndex(d.index, freq="M")
    x = pd.DataFrame(index=d.index)
    x["dp"] = np.log(d["D12"]) - np.log(d["Index"])
    x["dy"] = np.log(d["D12"]) - np.log(d["Index"].shift(1))
    x["ep"] = np.log(d["E12"]) - np.log(d["Index"])
    x["de"] = np.log(d["D12"]) - np.log(d["E12"])
    x["svar"] = d["svar"]
    x["bm"] = d["b/m"]
    x["ntis"] = d["ntis"]
    x["tbl"] = d["tbl"]
    x["lty"] = d["lty"]
    x["ltr"] = d["ltr"]
    x["tms"] = d["lty"] - d["tbl"]
    x["dfy"] = d["BAA"] - d["AAA"]
    x["dfr"] = d["corpr"] - d["ltr"]
    x["infl"] = d["infl"]
    if lags:
        for k, n in LAGS.items():
            x[k] = x[k].shift(n)
    x["R"] = d["CRSP_SPvw"]
    x["rf"] = d["Rfree"]
    x["eq"] = d["CRSP_SPvw"] - d["Rfree"]
    return x


# ---------------------------------------------------------------- forecasts (each made at month-end t for t+1)

def forecasts(x: pd.DataFrame) -> pd.DataFrame:
    idx = x.index
    start = idx.get_loc(pd.Period(OOS_FROM, "M"))
    fit0 = idx.get_loc(pd.Period(FIT_FROM, "M"))
    out = {}
    for j in range(start, len(idx)):
        # forecast for month idx[j], made at the end of idx[j-1]: data pairs (x_s, eq_{s+1}) with s+1 <= j-1
        t = j - 1
        row = {}
        y = x["eq"].iloc[fit0 + 1:t + 1].values
        for k in INDICATORS:
            xs = x[k].iloc[fit0:t].values
            ok = ~(np.isnan(xs) | np.isnan(y))
            if ok.sum() < 60 or np.isnan(x[k].iloc[t]):
                continue
            b, a = np.polyfit(xs[ok], y[ok], 1)
            row[k] = a + b * x[k].iloc[t]
        row["hist"] = float(np.nanmean(y))
        row["var60"] = float(np.nanvar(x["eq"].iloc[t - VAR_MONTHS + 1:t + 1].values))
        out[idx[j]] = row
    f = pd.DataFrame(out).T
    f["combo_raw"] = f[list(INDICATORS)].mean(axis=1)
    f["combo"] = f["combo_raw"].clip(lower=0)
    return f


def weight(pred: pd.Series, var: pd.Series, gamma: float = GAMMA, lo: float = W_MIN, hi: float = W_MAX) -> pd.Series:
    return (pred / (gamma * var)).clip(lo, hi)


def run(x: pd.DataFrame, w: pd.Series, delay: int = 0) -> pd.Series:
    w = w.shift(delay).dropna() if delay else w.dropna()
    out, held = {}, None
    for t, wt in w.items():
        R, rf = x.at[t, "R"], x.at[t, "rf"]
        if np.isnan(R):
            continue
        prev = wt if held is None else held
        r = rf + wt * (R - rf) - max(wt - 1, 0) * BORROW_SPREAD / 12 - TRADE_COST * abs(wt - prev)
        out[t] = r
        held = wt * (1 + R) / (1 + r)
    return pd.Series(out)


def r2_os(eq: pd.Series, f: pd.Series, fbar: pd.Series) -> dict:
    e1, e0 = (eq - f) ** 2, (eq - fbar) ** 2
    r2 = 1 - e1.sum() / e0.sum()
    cw = e0 - (e1 - (fbar - f) ** 2)            # Clark & West (2007)
    t = nw_t(cw.values, lags=0)
    return {"r2_pct": round(float(r2) * 100, 2), "clark_west_t": round(t, 2), "p_one_sided": round(float(1 - norm.cdf(t)), 3)}


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    e = r - rf.reindex(r.index)
    return float(e.mean() / e.std() * np.sqrt(12))


def window(s, a, z):
    return s.loc[pd.Period(a, "M"):pd.Period(z, "M")]


def evaluate(x: pd.DataFrame, f: pd.DataFrame, gamma=GAMMA, lo=W_MIN, hi=W_MAX, delay=0) -> dict:
    model = run(x, weight(f["combo"], f["var60"], gamma, lo, hi), delay)
    hist = run(x, weight(f["hist"], f["var60"], gamma, lo, hi), delay)
    bh = x["R"].loc[model.index]
    return {"model": model, "hist": hist, "buy_hold": bh}


def job_backtest(db) -> dict:
    x = frame(db)
    f = forecasts(x)
    eq = x["eq"].reindex(f.index)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/macro-timing/PLAN.md"}
    s = evaluate(x, f)
    rf = x["rf"]
    for name, (a, z) in {"oos": (OOS_FROM, OOS_TO), "post_pub": (POST_PUB, OOS_TO), "pre_pub": (OOS_FROM, "2005-12")}.items():
        res[name] = {k: vm.stats(window(v, a, z), rf) for k, v in s.items()}
        ff = window(f, a, z)
        res[name]["accuracy"] = r2_os(window(eq, a, z), ff["combo"], ff["hist"])
        res[name]["accuracy_untruncated"] = r2_os(window(eq, a, z), ff["combo_raw"], ff["hist"])
    dec = {}
    for d0 in range(1950, 2030, 10):
        z = f"{d0 + 9}-12" if d0 < 2020 else OOS_TO
        dec[f"{d0}s"] = {k: round(sharpe(window(v, f"{d0}-01", z), rf), 3) for k, v in s.items()}
    res["decades"] = dec
    w = weight(f["combo"], f["var60"])
    res["model_amount"] = {"avg": round(float(w.mean()), 2), "share_zero": round(float((w <= 0).mean()), 3),
                           "share_max": round(float((w >= W_MAX).mean()), 3),
                           "avg_post_pub": round(float(window(w, POST_PUB, OOS_TO).mean()), 2),
                           "last_12": {str(k): round(float(v), 2) for k, v in w.iloc[-12:].items()}}
    res["crashes"] = {n: {k: round(float(np.prod(1 + window(v, a, z)) - 1) * 100, 1) for k, v in s.items()}
                      for n, (a, z) in CRASHES.items()}
    res["years"] = {str(y): {k: round(float(np.prod(1 + v[v.index.year == y]) - 1) * 100, 1) for k, v in s.items()}
                    for y in sorted(set(s["model"].index.year))}
    single = {}
    for k in INDICATORS:
        fk = f[k].dropna()
        row = {}
        for name, (a, z) in {"oos": (OOS_FROM, OOS_TO), "post_pub": (POST_PUB, OOS_TO), "pre_pub": (OOS_FROM, "2005-12")}.items():
            fw = window(fk, a, z)
            row[name] = r2_os(window(eq, a, z).reindex(fw.index), fw, window(f["hist"], a, z).reindex(fw.index))["r2_pct"]
        r = run(x, weight(f[k].clip(lower=0), f["var60"]).dropna())
        row["sharpe_oos"] = round(sharpe(window(r, OOS_FROM, OOS_TO), rf), 3)
        row["sharpe_post_pub"] = round(sharpe(window(r, POST_PUB, OOS_TO), rf), 3)
        single[k] = row
    res["single_indicators"] = single
    sens = {}
    xl = frame(db, lags=False)
    fl = forecasts(xl)
    cases = {"no real-time lags": evaluate(xl, fl)["model"], "risk aversion 2": evaluate(x, f, gamma=2)["model"],
             "risk aversion 5": evaluate(x, f, gamma=5)["model"], "limits 0 to 1": evaluate(x, f, hi=1.0)["model"],
             "one-month delay": evaluate(x, f, delay=1)["model"]}
    for k, v in cases.items():
        sens[k] = {"oos": vm.stats(window(v, OOS_FROM, OOS_TO), rf), "post_pub": vm.stats(window(v, POST_PUB, OOS_TO), rf)}
    sens["accuracy no lags"] = {"oos": r2_os(eq.reindex(fl.index), fl["combo"], fl["hist"]),
                                "post_pub": r2_os(window(eq, POST_PUB, OOS_TO), window(fl, POST_PUB, OOS_TO)["combo"],
                                                  window(fl, POST_PUB, OOS_TO)["hist"])}
    res["sensitivity"] = sens
    o, p = res["oos"], res["post_pub"]
    res["verdict"] = {
        "1_post_pub_more_money_and_sharpe": p["model"]["10k_becomes"] > p["buy_hold"]["10k_becomes"] and p["model"]["sharpe"] > p["buy_hold"]["sharpe"],
        "2_oos_accuracy_and_sharpe": o["accuracy"]["r2_pct"] > 0 and o["accuracy"]["p_one_sided"] < 0.05
        and o["model"]["sharpe"] > max(o["buy_hold"]["sharpe"], o["hist"]["sharpe"]),
        "3_post_pub_r2_above_0": p["accuracy"]["r2_pct"] > 0,
        "4_decades_5_of_8": sum(v["model"] > v["buy_hold"] for v in dec.values()) >= 5,
    }
    res["verdict"]["passes"] = all(res["verdict"].values())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    db.executescript(SCHEMA)
    if cmd == "data":
        run_id = start_run(db, "macro-data")
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
