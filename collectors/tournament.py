"""Round 4 strategies (leveraged trend, dual momentum, four-factor mix, trend-filtered near misses,
CBOE option strategies) and the tournament of every strategy tested on 2026-11-12, on one common
window against SPY. Plan fixed before any result: docs/tournament/PLAN.md. Write-up:
docs/tournament/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       CBOE PUT, BXM, PPUT, CLL daily history and the S&P 500 total return (Yahoo ^SP500TR)
             into index_daily
  backtest   round 4 verdicts and the tournament; results to ~/MarketData/tournament/backtest-<date>.json
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
import vol_managed as vm
import classic_strategies as cs
import risk_budget as rb
import macro_timing as mt
import pairs_model as pm

RESULTS_DIR = Path.home() / "MarketData" / "tournament"
CBOE = {"PUT": "Put-selling (CBOE PUT)", "BXM": "Covered calls (CBOE BXM)", "PPUT": "Protective puts (CBOE PPUT)",
        "CLL": "Collar (CBOE CLL)"}

# ---- fixed by the plan
SWITCH_COST = 0.0005
BORROW_SPREAD = 0.01
FUND_FEE = 0.0040          # a year, option-strategy funds
SPY_FEE = 0.0009
COMMON = ("2006-01", "2025-09")
MIN_TRIALS = 25
NEW = {   # name: (label, source, after-publication start or None, yardstick)
    "lev_trend": ("Leveraged trend (2x above 200-day average)", "Gayed & Bilello (2016)", "2016-01", "market"),
    "dual_mom": ("Dual momentum (US / intl / bonds)", "Antonacci (2012/2014)", "2012-01", "market"),
    "four_factor": ("Four-factor mix", "Asness, Moskowitz & Pedersen (2013)", "2012-01", "market"),
    "indmom_trend": ("Industry momentum with trend (my idea)", "none", "2006-01", "market"),
    "smallvalue_trend": ("Small value with trend (my idea)", "none", "2006-01", "market"),
    "PUT": (CBOE["PUT"], "Whaley (2002); Israelov & Nielsen (2014)", "2007-07", "sp500"),
    "BXM": (CBOE["BXM"], "Whaley (2002)", "2002-05", "sp500"),
    "PPUT": (CBOE["PPUT"], "Israelov (2017)", "2008-01", "sp500"),
    "CLL": (CBOE["CLL"], "CBOE", None, "sp500"),
}
AFTER_SEEING = ("indmom_trend", "smallvalue_trend")


# ---------------------------------------------------------------- data

def job_data(db) -> tuple[str, int, str]:
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows, notes = [], []
    for sym in CBOE:
        text = http_get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv").decode()
        df = pd.read_csv(io.StringIO(text))
        df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
        rows += [(sym, d, None, None, None, float(v), "cboe", now) for d, v in zip(df["DATE"], df[sym]) if pd.notna(v)]
        notes.append(f"{sym} {df['DATE'].iloc[0]}..{df['DATE'].iloc[-1]}")
    import yfinance as yf
    t = yf.download("^SP500TR", start="1988-01-01", progress=False, auto_adjust=False)["Close"].iloc[:, 0].dropna()
    rows += [("SP500TR", d.strftime("%Y-%m-%d"), None, None, None, float(v), "yahoo", now) for d, v in t.items()]
    notes.append(f"SP500TR {t.index[0]:%Y-%m-%d}..{t.index[-1]:%Y-%m-%d}")
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), "; ".join(notes)


def index_monthly(db, sym: str) -> pd.Series:
    s = pd.read_sql("SELECT date, close FROM index_daily WHERE symbol=? ORDER BY date", db, params=(sym,),
                    index_col="date")["close"]
    s.index = pd.to_datetime(s.index)
    last = s.groupby(s.index.to_period("M")).last()
    full = pd.period_range(last.index[0], last.index[-1], freq="M")
    last = last.reindex(full)
    r = last.pct_change(fill_method=None)      # a month after a gap gets no return (not a multi-month jump)
    this_month = pd.Period(date.today().strftime("%Y-%m"), "M")
    return r.loc[:this_month - 1].dropna()


# ---------------------------------------------------------------- round 4 strategies

def lev_trend(daily: pd.DataFrame, lev: float = 2.0) -> pd.Series:
    lvl = (1 + daily["ex"] + daily["rf"]).cumprod()
    ma = lvl.rolling(200).mean()
    w = (lvl > ma).astype(float).where(ma.notna()) * lev
    w = w.shift(1).dropna()           # decided at the close, held the next day
    d = daily.loc[w.index]
    r = d["rf"] + w * d["ex"] - (w - 1).clip(lower=0) * BORROW_SPREAD / 252 - SWITCH_COST * w.diff().abs().fillna(0)
    return ((1 + r).groupby(r.index.to_period("M")).prod() - 1).iloc[1:]


def dual_mom(us: pd.DataFrame, intl: pd.DataFrame, bonds: pd.Series) -> pd.Series:
    df = pd.DataFrame({"us": us["R"], "intl": intl["R"], "rf": us["rf"], "bonds": bonds}).dropna()
    m12 = (1 + df).rolling(12).apply(np.prod, raw=True) - 1
    out, prev = {}, None
    for i in range(12, len(df)):
        t, past = df.index[i], m12.iloc[i - 1]
        pick = "us" if past["us"] >= past["intl"] else "intl"
        if past[pick] < past["rf"]:
            pick = "bonds"
        r = df.at[t, pick]
        if prev is not None and pick != prev:
            r -= 2 * SWITCH_COST
        out[t] = r
        prev = pick
    return pd.Series(out)


def four_factor(db) -> pd.Series:
    parts = [cs.strategy_series(db, n, None, None)[0] for n in ("smallvalue", "mom", "profit", "lowvar")]
    return pd.concat(parts, axis=1).dropna().mean(axis=1)


def with_trend(r: pd.Series, mo: pd.DataFrame) -> pd.Series:
    lvl = (1 + mo["R"]).cumprod()
    on = (lvl > lvl.rolling(10).mean()).astype(float).where(lvl.rolling(10).count() == 10).shift(1)
    on = on.reindex(r.index).dropna()
    rr = r.loc[on.index]
    out = on * rr + (1 - on) * mo["rf"].reindex(on.index) - SWITCH_COST * on.diff().abs().fillna(0)
    return out


def all_series(db) -> tuple[dict, dict]:
    """Every strategy tested on 2026-11-12, monthly returns after its own costs. Returns (series, labels)."""
    daily, mo = cs.market(db, "us")
    s, lab = {}, {}
    vmo = vm.monthly(daily)
    for cap_name, cap in vm.CAPS.items():
        s[f"vm_{cap_name}"] = vm.run_strategy(vmo, vm.weights(vmo, cap))
        lab[f"vm_{cap_name}"] = f"Volatility-managed, {cap_name.replace('_', ' ')}"
    for n, meta in cs.STRATS.items():
        r, _ = cs.strategy_series(db, n, daily, mo)
        s[n], lab[n] = r, meta[0]
    rbm = rb.monthly_frame(db)
    for lv in (0.10, 0.15):
        k = f"risk_budget_{int(lv * 100)}"
        s[k], lab[k] = rb.run(rbm, rb.weights(rbm, "model", lv)), f"Risk budget model, {int(lv * 100)}% risk"
    x = mt.frame(db)
    s["macro"], lab["macro"] = mt.evaluate(x, mt.forecasts(x))["model"], "Macro timing"
    px = pm.load_prices(db)
    ex, _ = pm.strategy(px, pm.history())
    s["pairs"], lab["pairs"] = pm.monthly_rf(db).reindex(ex.index) + ex, "Pairs trading"
    # round 4
    s["lev_trend"] = lev_trend(daily)
    _, intl = cs.market(db, "dev_ex_us")
    s["dual_mom"] = dual_mom(mo, intl, rb.bond_returns(db))
    s["four_factor"] = four_factor(db)
    s["indmom_trend"] = with_trend(s["indmom"], mo)
    s["smallvalue_trend"] = with_trend(s["smallvalue"], mo)
    for sym in CBOE:
        s[sym] = index_monthly(db, sym) - FUND_FEE / 12
    for k, v in NEW.items():
        lab[k] = v[0]
    return s, lab


# ---------------------------------------------------------------- scoring

def rf_monthly(db) -> pd.Series:
    rf = vm.monthly(vm.load(db, "us"))["rf"]
    full = pd.period_range(rf.index[0], pd.Period(date.today().strftime("%Y-%m"), "M"), freq="M")
    return rf.reindex(full).ffill()


def window(s, a, z=None):
    return s.loc[pd.Period(a, "M"):(pd.Period(z, "M") if z else None)]


def judge(name: str, r: pd.Series, yard: pd.Series, rf: pd.Series) -> dict:
    r = r.dropna()
    b = yard.reindex(r.index).dropna()
    r = r.loc[b.index]
    pub = NEW[name][2]
    full = {"strategy": vm.stats(r, rf), "yardstick": vm.stats(b, rf), "from": str(r.index[0]), "to": str(r.index[-1]),
            "t_gap": round(cs.nw_t((r - b).values), 2)}
    out = {"full": full}
    if pub:
        rp, bp = window(r, pub), window(b, pub)
        out["after"] = {"strategy": vm.stats(rp, rf), "yardstick": vm.stats(bp, rf), "from": pub}
    else:
        out["after"] = {"strategy": full["strategy"], "yardstick": full["yardstick"], "from": full["from"]}
    a, f = out["after"], out["full"]
    beats = (a["strategy"]["10k_becomes"] > a["yardstick"]["10k_becomes"] and a["strategy"]["sharpe"] > a["yardstick"]["sharpe"]
             and f["t_gap"] >= 3)
    safer = all(p["strategy"]["sharpe"] > p["yardstick"]["sharpe"] and p["strategy"]["worst_drop"] > p["yardstick"]["worst_drop"]
                for p in (a, f))
    out["verdict"] = {"beats_market": beats, "safer_not_better": safer}
    cr = {}
    for n, (x0, x1) in mt.CRASHES.items():
        sr = window(r, x0, x1)
        if len(sr):
            cr[n] = [round(float(np.prod(1 + sr) - 1) * 100, 1), round(float(np.prod(1 + b.loc[sr.index]) - 1) * 100, 1)]
    out["crashes"] = cr
    return out


def deflated(gap: np.ndarray, trial_srs: list[float], n_trials: int) -> dict:
    sr = gap.mean() / gap.std(ddof=1)
    g3, g4 = float(pd.Series(gap).skew()), float(pd.Series(gap).kurt()) + 3
    V = float(np.var(trial_srs, ddof=1))
    em = 0.5772156649
    sr0 = math.sqrt(V) * ((1 - em) * norm.ppf(1 - 1 / n_trials) + em * norm.ppf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(len(gap) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return {"monthly_sharpe_of_gap": round(float(sr), 3), "luck_hurdle": round(float(sr0), 3),
            "trials": n_trials, "prob_real": round(float(norm.cdf(z)), 3)}


def own_verdicts(db) -> dict:
    """Each earlier strategy's verdict from its own committed results file."""
    out = {}
    vmr = json.loads(max((Path.home() / "MarketData" / "vol_managed").glob("backtest-*.json")).read_text())
    out["vm_up_to_1.5x"] = "fail"
    out["vm_never_borrow"] = "fail"       # failed its own "safer" rule (README)
    csr = json.loads(max((Path.home() / "MarketData" / "classic_strategies").glob("backtest-*.json")).read_text())
    for n, v in csr["strategies"].items():
        out[n] = "beats" if v["verdict"]["beats_market"] else ("safer" if v["verdict"].get("safer_not_better") else "fail")
    out["risk_budget_10"] = out["risk_budget_15"] = "fail"
    out["macro"] = "fail"
    out["pairs"] = "fail"
    return out


def job_backtest(db) -> dict:
    series, labels = all_series(db)
    rf = rf_monthly(db)
    _, mo = cs.market(db, "us")
    sp = index_monthly(db, "SP500TR")
    yard = {"market": mo["R"], "sp500": sp}
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/tournament/PLAN.md", "round4": {}}
    verdicts = own_verdicts(db)
    for name in NEW:
        j = judge(name, series[name], yard[NEW[name][3]], rf)
        j["label"], j["source"] = NEW[name][0], NEW[name][1]
        res["round4"][name] = j
        v = j["verdict"]
        verdicts[name] = "beats" if v["beats_market"] else ("safer" if v["safer_not_better"] else "fail")
    # info: 1x trend daily
    daily, _ = cs.market(db, "us")
    res["info_trend_200d_1x"] = {"full": vm.stats(lev_trend(daily, 1.0).loc[pd.Period("1928-01", "M"):], rf),
                                 "after_2016": vm.stats(window(lev_trend(daily, 1.0), "2016-01"), rf)}
    # tournament
    spy = sp - SPY_FEE / 12
    a, z = COMMON
    spyw = window(spy, a, z)
    table, gaps = {}, {}
    for name, r in series.items():
        rw = window(r.dropna(), a, z)
        if name in ("pairs", "CLL"):
            rw2 = rw
            note = f"short window {rw2.index[0]}..{rw2.index[-1]}"
        else:
            note = ""
            if len(rw) < len(spyw):
                note = f"has {len(rw)} of {len(spyw)} months"
        b = spyw.reindex(rw.index)
        st, bs = vm.stats(rw, rf), vm.stats(b, rf)
        table[name] = {"label": labels[name], "own_verdict": verdicts.get(name, "?"), **st,
                       "spy_same_months": {k: bs[k] for k in ("per_year", "sharpe", "worst_drop", "10k_becomes")},
                       "gap_per_year": round(float((rw - b).mean()) * 1200, 2), "note": note}
        if not note:
            gaps[name] = (rw - b).values
    res["tournament"] = {"window": COMMON, "spy": vm.stats(spyw, rf), "rows": table}
    srs = {k: float(g.mean() / g.std(ddof=1)) for k, g in gaps.items()}
    ntr = max(len(srs), MIN_TRIALS)
    t1 = [k for k, v in table.items() if not v["note"] and k not in AFTER_SEEING and verdicts.get(k) == "beats"
          and v["10k_becomes"] > v["spy_same_months"]["10k_becomes"] and v["sharpe"] > v["spy_same_months"]["sharpe"]]
    t2 = [k for k, v in table.items() if not v["note"] and k not in AFTER_SEEING and verdicts.get(k) in ("beats", "safer")
          and v["worst_drop"] > v["spy_same_months"]["worst_drop"]]
    win1 = max(t1, key=lambda k: table[k]["10k_becomes"]) if t1 else None
    win2 = max(t2, key=lambda k: table[k]["sharpe"]) if t2 else None
    res["winners"] = {
        "T1_best_for_beating_spy": win1 or "SPY itself", "T1_candidates": t1,
        "T2_best_risk_adjusted": win2, "T2_candidates": t2,
        "T4_luck": {k: deflated(gaps[k], list(srs.values()), ntr) for k in {win1, win2} if k},
        "best_gap_sharpe_any": max(srs, key=srs.get), "best_gap_luck": deflated(gaps[max(srs, key=srs.get)], list(srs.values()), ntr),
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
        run_id = start_run(db, "tournament-data")
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
