"""Options fear premium (VRP, exploration finalist 4b): confirmation tests on S&P 500 declines, four fresh markets
and time periods. Plan fixed before any test was run: docs/exploration/VRP_CONFIRM_PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       fear indexes and markets into index_daily: VXN, VXD, NDX, DJI, RUT (Yahoo), RVX (Cboe),
             V2TX (STOXX), QQQ_ADJ, DIA_ADJ, IWM_ADJ (Yahoo, dividend-adjusted)
  backtest   run the plan; results to ~/MarketData/exploration/vrp-confirm-<date>.json
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, http_get, start_run
import vol_managed as vm
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "exploration"

# ---- fixed by the plan (the rule is finalist 4b, unchanged)
GAMMA, CAP, MIN_PAIRS, VAR_MONTHS = 3.0, 1.5, 36, 120
COST = 0.0005
DECLINE = 0.10
PERIODS = (("1993", "1999"), ("2000", "2005"), ("2006", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026"))
END = "2026-10"


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows, notes = [], []
    for sym, name, adj in (("^VXN", "VXN", False), ("^VXD", "VXD", False), ("^NDX", "NDX", False), ("^DJI", "DJI", False),
                           ("^RUT", "RUT", False), ("QQQ", "QQQ_ADJ", True), ("DIA", "DIA_ADJ", True), ("IWM", "IWM_ADJ", True)):
        t = yf.download(sym, start="1985-01-01", progress=False, auto_adjust=adj)["Close"].iloc[:, 0].dropna()
        rows += [(name, d.strftime("%Y-%m-%d"), None, None, None, float(v), "yahoo-adjusted" if adj else "yahoo", now) for d, v in t.items()]
        notes.append(f"{name} {t.index[0]:%Y-%m-%d}..{t.index[-1]:%Y-%m-%d}")
    text = http_get("https://cdn.cboe.com/api/global/us_indices/daily_prices/RVX_History.csv").decode()
    n0 = len(rows)
    for ln in text.splitlines()[1:]:
        p = ln.split(",")
        if len(p) >= 5 and p[4]:
            m, d, y = p[0].split("/")
            rows.append(("RVX", f"{y}-{m}-{d}", None, None, None, float(p[4]), "cboe", now))
    notes.append(f"RVX {rows[n0][1]}..{rows[-1][1]}")
    text = http_get("https://www.stoxx.com/document/Indices/Current/HistoricalData/h_v2tx.txt").decode()
    n0 = len(rows)
    for ln in text.splitlines()[1:]:
        p = ln.split(";")
        if len(p) >= 3 and p[2].strip():
            d, m, y = p[0].split(".")
            rows.append(("V2TX", f"{y}-{m}-{d}", None, None, None, float(p[2]), "stoxx", now))
    notes.append(f"V2TX {rows[n0][1]}..{rows[-1][1]}")
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return "ok", len(rows), "; ".join(notes)


# ---------------------------------------------------------------- the rule

def weights(fear: pd.Series, idx_ret: pd.Series, ex_m: pd.Series, gamma=GAMMA, cap=CAP, window: int | None = None) -> pd.Series:
    """Monthly weights keyed by the month they're held. fear: daily fear index; idx_ret: daily returns of the
    market (for realized variance); ex_m: the held market's monthly excess returns."""
    lr = np.log1p(idx_ret.dropna())
    rv = (lr ** 2).groupby(lr.index.to_period("M")).sum()
    fe = fear.dropna().groupby(fear.dropna().index.to_period("M")).last()
    v = ((fe / 100) ** 2 / 12 - rv).dropna()
    w = {}
    for i in range(MIN_PAIRS, len(v)):
        t = v.index[i]
        X = v.iloc[:i].values
        y = ex_m.reindex(v.index[1:i + 1]).values
        ok = ~np.isnan(y)
        X, y = X[ok], y[ok]
        if window:
            X, y = X[-window:], y[-window:]
        if len(X) < MIN_PAIRS:
            continue
        b = np.polyfit(X, y, 1)
        f = b[0] * v.iloc[i] + b[1]
        var = np.nanvar(ex_m.loc[:t].values[-VAR_MONTHS:])
        w[t + 1] = float(np.clip(f / (gamma * var), 0, cap))
    return pd.Series(w)


def daily_path(w: pd.Series, R: pd.Series, rf: pd.Series) -> pd.Series:
    """Daily returns: the month's weight applied to each day; cost on the first day of a month when it changes."""
    R = R.dropna()
    per = R.index.to_period("M")
    wd = pd.Series(w.reindex(per).values, index=R.index)
    keep = wd.notna()
    R, wd, f = R[keep], wd[keep], rf.reindex(R.index).ffill()[keep]
    first = ~R.index.to_period("M").duplicated()
    dw = wd.diff().abs().fillna(wd.abs())
    return f + wd * (R - f) - COST * dw.where(first, 0.0)


def monthly(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def _px(db, sym) -> pd.Series:
    return tn._daily_index(db, sym)


def rf_daily(db) -> pd.Series:
    return vm.load(db, "us")["rf"]


# ---------------------------------------------------------------- tests

def declines(level: pd.Series, start: pd.Timestamp) -> list[dict]:
    """Peak -> lowest close before the old peak is regained, at least DECLINE down."""
    out, peak_t, peak = [], level.index[0], level.iloc[0]
    trough_t, trough = peak_t, peak
    for t, x in level.items():
        if x >= peak:
            if trough / peak - 1 <= -DECLINE:
                out.append({"peak": peak_t, "trough": trough_t, "recovered": t})
            peak_t, peak, trough_t, trough = t, x, t, x
        elif x < trough:
            trough_t, trough = t, x
    if trough / peak - 1 <= -DECLINE:
        out.append({"peak": peak_t, "trough": trough_t, "recovered": None})
    return [e for e in out if e["peak"] >= start]


def growth(r: pd.Series, a, z) -> float:
    s = r.loc[(r.index > a) & (r.index <= z)]
    return float(np.prod(1 + s) - 1)


def job_backtest(db) -> dict:
    rfd = rf_daily(db)
    rfm = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/exploration/VRP_CONFIRM_PLAN.md"}

    # S&P 500 (tests 1 and 3)
    tr = _px(db, "SP500TR")
    R = tr.pct_change().dropna()
    exm = monthly(R) - rfm.reindex(monthly(R).index)
    w = weights(_px(db, "VIX"), _px(db, "SPX").pct_change(), exm)
    strat = daily_path(w, R, rfd)
    mk = R.reindex(strat.index)
    res["sp500_from"] = str(strat.index[0].date())

    # test 1: declines
    eps = []
    for e in declines(tr, strat.index[0]):
        a, z = e["peak"], e["trough"]
        z12 = z + pd.DateOffset(months=12)
        row = {"peak": str(a.date()), "bottom": str(z.date()), "recovered": str(e["recovered"].date()) if e["recovered"] is not None else None,
               "market_peak_to_bottom": round(growth(mk, a, z) * 100, 1), "vrp_peak_to_bottom": round(growth(strat, a, z) * 100, 1),
               "market_peak_to_12m_after": round(growth(mk, a, z12) * 100, 1), "vrp_peak_to_12m_after": round(growth(strat, a, z12) * 100, 1),
               "avg_weight_during": round(float(w.reindex(pd.period_range(a.to_period("M"), z.to_period("M"))).mean()), 2),
               "is_2008": a.year == 2007}
        row["vrp_lost_less"] = row["vrp_peak_to_bottom"] > row["market_peak_to_bottom"]
        row["vrp_ahead_12m_after"] = row["vrp_peak_to_12m_after"] > row["market_peak_to_12m_after"]
        eps.append(row)
    other = [e for e in eps if not e["is_2008"]]
    res["declines"] = eps
    res["test1"] = {"declines_excluding_2008": len(other), "vrp_lost_less": sum(e["vrp_lost_less"] for e in other),
                    "vrp_ahead_12m_after": sum(e["vrp_ahead_12m_after"] for e in other)}
    res["test1"]["pass"] = (res["test1"]["vrp_lost_less"] >= 2 / 3 * len(other)) and (res["test1"]["vrp_ahead_12m_after"] >= 0.5 * len(other))

    # test 3: periods
    sm, mm = monthly(strat).loc[:pd.Period(END, "M")], monthly(mk).loc[:pd.Period(END, "M")]
    per = {}
    for a, z in PERIODS:
        s, m = sm.loc[a:z], mm.loc[a:z]
        per[f"{a}-{z}"] = {"vrp": vm.stats(s, rfm), "market": vm.stats(m, rfm)}
        per[f"{a}-{z}"]["vrp_better_sharpe"] = per[f"{a}-{z}"]["vrp"]["sharpe"] > per[f"{a}-{z}"]["market"]["sharpe"]
    res["periods"] = per
    res["whole_sp500"] = {"vrp": vm.stats(sm, rfm), "market": vm.stats(mm, rfm)}
    res["test3"] = {"better_sharpe": sum(p["vrp_better_sharpe"] for p in per.values()), "of": len(per)}
    res["test3"]["pass"] = res["test3"]["better_sharpe"] >= 4

    # test 2: fresh markets
    fresh = {}
    eur = vm.load(db, "europe")
    eurR = eur["ex"] + eur["rf"]
    specs = {"Nasdaq-100": ("VXN", _px(db, "NDX").pct_change(), _px(db, "QQQ_ADJ").pct_change()),
             "Dow Jones": ("VXD", _px(db, "DJI").pct_change(), _px(db, "DIA_ADJ").pct_change()),
             "Russell 2000": ("RVX", _px(db, "RUT").pct_change(), _px(db, "IWM_ADJ").pct_change()),
             "Europe": ("V2TX", eurR, eurR)}
    for name, (fear, idx_r, held) in specs.items():
        held = held.dropna()
        hm = monthly(held)
        ex = hm - rfm.reindex(hm.index)
        ww = weights(_px(db, fear), idx_r, ex)
        s = daily_path(ww, held, rfd)
        smo = monthly(s).loc[:pd.Period(END, "M")]
        bmo = hm.reindex(smo.index)
        st, bh = vm.stats(smo, rfm), vm.stats(bmo, rfm)
        fresh[name] = {"from": str(smo.index[0]), "to": str(smo.index[-1]), "vrp": st, "buy_hold": bh,
                       "avg_weight": round(float(ww.loc[smo.index[0]:].mean()), 2),
                       "bootstrap_sharpe_gap": vm.bootstrap_gap((smo - rfm.reindex(smo.index)).values, (bmo - rfm.reindex(smo.index)).values),
                       "sharpe_at_least_as_high": st["sharpe"] >= bh["sharpe"],
                       "worst_years": {str(y): [round(float(np.prod(1 + smo[smo.index.year == y]) - 1) * 100, 1),
                                                round(float(np.prod(1 + bmo[bmo.index.year == y]) - 1) * 100, 1)]
                                       for y in sorted(set(smo.index.year))}}
    res["fresh_markets"] = fresh
    res["test2"] = {"sharpe_at_least_as_high": sum(f["sharpe_at_least_as_high"] for f in fresh.values()), "of": len(fresh)}
    res["test2"]["pass"] = res["test2"]["sharpe_at_least_as_high"] >= 3

    # information: rolling 5 years, sensitivity
    roll = []
    for i in range(0, len(sm) - 59):
        s, m = sm.iloc[i:i + 60], mm.iloc[i:i + 60]
        roll.append((np.prod(1 + s) > np.prod(1 + m), vm.sharpe((s - rfm.reindex(s.index)).values) > vm.sharpe((m - rfm.reindex(m.index)).values)))
    res["rolling_5y"] = {"windows": len(roll), "more_money": round(float(np.mean([r[0] for r in roll])), 2),
                         "better_sharpe": round(float(np.mean([r[1] for r in roll])), 2)}
    sens = {}
    for label, kw in (("gamma 2", {"gamma": 2}), ("gamma 5", {"gamma": 5}), ("cap 1.0", {"cap": 1.0}), ("cap 2.0", {"cap": 2.0}),
                      ("rolling 10-year regression", {"window": 120})):
        ws = weights(_px(db, "VIX"), _px(db, "SPX").pct_change(), exm, **kw)
        x = monthly(daily_path(ws, R, rfd)).loc[sm.index[0]:pd.Period(END, "M")]
        sens[label] = vm.stats(x, rfm)
    sens["rule as fixed"] = res["whole_sp500"]["vrp"]
    sens["market"] = res["whole_sp500"]["market"]
    res["sensitivity"] = sens
    res["verdict"] = "confirmed" if res["test1"]["pass"] and res["test2"]["pass"] and res["test3"]["pass"] else "not confirmed"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"vrp-confirm-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "vrp-data")
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
