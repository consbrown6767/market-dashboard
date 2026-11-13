"""Global government bond strategies (8 versions) as hedged overlays: carry (term spread), value (real yield),
momentum, trend, combination, global duration timing, yield level, Taylor rule. Plan fixed before any result:
docs/bonds/PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       FRED 10-year yields (IRLTLT01xxM156N) into macro_series
  explore    sandbox 1980-2005 only; results to ~/MarketData/bonds/explore-<date>.json
  holdout    vault 2006-2026 for docs/bonds/FINALISTS.md (must be committed)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, start_run
import fx_research as fx
import vol_managed as vm
import classic_strategies as cs
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "bonds"
PROJECT = fx.PROJECT
FINALISTS = PROJECT / "docs" / "bonds" / "FINALISTS.md"

# ---- fixed by the plan
SANDBOX = ("1980-01", "2005-12")
VAULT = ("2006-01", "2026-09")
HALVES = (("2006-01", "2015-12"), ("2016-01", "2026-09"))
TRADE, ROLL = 0.0003, 0.0001
SHARPE_BAR = 0.3

# country: (10-year yield, 3-month rate, short-rate fallback, CPI, CPI quarterly?, unemployment)
COUNTRIES = {"US": ("IRLTLT01USM156N", fx.US["rate"], "IRSTCI01USM156N", fx.US["cpi"], False, fx.US["unemp"])}
for ccy, code in (("GBP", "GB"), ("JPY", "JP"), ("CHF", "CH"), ("CAD", "CA"), ("AUD", "AU"), ("NZD", "NZ"),
                  ("NOK", "NO"), ("SEK", "SE"), ("EUR", "DE")):
    _, _, r3, rs, cpi, q, un = fx.CCY[ccy]
    COUNTRIES[code] = (f"IRLTLT01{code}M156N", r3, rs, cpi, q, un)


def job_data(db):
    return fx.job_data(db, [v[0] for v in COUNTRIES.values()] + ["IRSTCI01USM156N"])


def _vault_may_open() -> None:
    rel = FINALISTS.relative_to(PROJECT)
    ok = FINALISTS.exists() and subprocess.run(["git", "-C", str(PROJECT), "ls-files", "--error-unmatch", str(rel)],
                                               capture_output=True).returncode == 0
    clean = ok and subprocess.run(["git", "-C", str(PROJECT), "diff", "--quiet", "HEAD", "--", str(rel)]).returncode == 0
    if not (ok and clean):
        raise SystemExit("The vault stays shut: docs/bonds/FINALISTS.md must exist and be committed, unchanged.")


def par_bond_return(y0: pd.DataFrame | pd.Series, y1, years: float = 10.0):
    """Bought at par at yield y0 (decimal, coupon = y0, semiannual), priced a month later at y1, plus a month of coupon."""
    n = 2 * (years - 1 / 12)
    c, h = y0, y1 / 2
    price = (c / 2) * (1 - (1 + h) ** -n) / h + (1 + h) ** -n
    return price - 1 + c / 12


def panel(db, vault: bool = False) -> dict:
    if vault:
        _vault_may_open()
    last = pd.Period(VAULT[1] if vault else SANDBOX[1], "M")
    idx = pd.period_range("1971-01", last, freq="M")
    long_idx = pd.period_range("1955-01", last, freq="M")
    Y, I, P, U = {}, {}, {}, {}
    for c, (y10, r3, rs, cpi, q, un) in COUNTRIES.items():
        Y[c] = fx._monthly_level(fx._series(db, y10))
        I[c] = fx._monthly_level(fx._series(db, r3)).combine_first(fx._monthly_level(fx._series(db, rs)))
        P[c] = fx._monthly_level(fx._series(db, cpi), quarterly=q)
        if un:
            U[c] = fx._monthly_level(fx._series(db, un))
    Y = pd.DataFrame(Y).reindex(idx)
    I = pd.DataFrame(I).reindex(idx).ffill(limit=3)
    P = pd.DataFrame(P).reindex(long_idx).ffill().reindex(idx)
    U = pd.DataFrame(U).reindex(long_idx).ffill().reindex(idx).reindex(columns=Y.columns)
    bx = par_bond_return(Y.shift(1) / 100, Y / 100) - I.shift(1) / 1200      # hedged excess return over month t
    avail = Y.notna() & I.notna() & Y.shift(1).notna()
    return {"Y": Y, "I": I, "P": P, "U": U, "bx": bx, "avail": avail, "last": last}


def returns(d: dict, W: pd.DataFrame, trade=TRADE, roll=ROLL) -> pd.Series:
    """W row t (decided at the end of t) is scored on month t+2's return (the one-month gap). Indexed by t+2."""
    W = W.dropna(how="all").fillna(0.0)
    nxt = d["bx"].shift(-2).reindex(W.index)
    gross = (W * nxt.fillna(0.0)).sum(axis=1)
    turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    r = gross - trade * turn - roll * W.abs().sum(axis=1)
    keep = nxt.notna().any(axis=1).values
    r.index = r.index + 2
    return r[keep]


def _infl(d):
    P = d["P"]
    return P.shift(2) / P.shift(14) - 1


def cum12(d):
    return (1 + d["bx"]).rolling(12).apply(np.prod, raw=True) - 1


def w_carry(d):
    return fx.rank_weights(d["Y"] - d["I"], d["avail"])


def w_value(d):
    return fx.rank_weights(d["Y"] / 100 - _infl(d), d["avail"])


def w_mom(d):
    return fx.rank_weights(cum12(d), d["avail"])


def w_trend(d):
    a = d["avail"]
    c = cum12(d)
    n = (a & c.notna()).sum(axis=1)
    return np.sign(c).where(a).div(n.replace(0, np.nan), axis=0).where(n >= 4)


def w_combo(d):
    out = None
    for W in (w_carry(d), w_value(d), w_mom(d)):
        r = returns(d, W, 0.0, 0.0)            # indexed by month earned; known at the end of that month
        vol = r.rolling(36).std() * np.sqrt(12)
        x = W.mul((0.05 / vol).reindex(W.index), axis=0)
        out = x if out is None else out.add(x)
    return out / 3


def w_duration(d):
    a = d["avail"]
    ts = (d["Y"] - d["I"]).where(a).mean(axis=1)
    on = ts > ts.rolling(120, min_periods=60).mean()
    n = a.sum(axis=1)
    W = a.astype(float).div(n.replace(0, np.nan), axis=0).mul(on.astype(float), axis=0)
    return W.where(ts.rolling(120, min_periods=60).mean().notna() & (n >= 4))


def w_level(d):
    return fx.rank_weights(d["Y"], d["avail"])


def w_taylor(d):
    pi = _infl(d)
    U = d["U"].shift(2)
    gap = -(U - U.rolling(120, min_periods=60).mean()) / 100
    a = d["avail"]
    pi_rel = pi.where(a).sub(pi.where(a).mean(axis=1), axis=0)
    gap_rel = gap.where(a).sub(gap.where(a).mean(axis=1), axis=0).fillna(0.0)
    score = 1.5 * pi_rel + 0.5 * gap_rel
    return fx.rank_weights(-score, a)


VERSIONS = {"B1_carry_term_spread": w_carry, "B2_value_real_yield": w_value, "B3_momentum_12m": w_mom,
            "B4_trend_per_country": w_trend, "B5_combination": w_combo, "B6_global_duration_timing": w_duration,
            "B7_yield_level": w_level, "B8_taylor_rule": w_taylor}


def smoothing_k(db, d) -> dict:
    """US bond excess returns from month-end daily yields (DGS10) vs from monthly averages, sandbox years."""
    dg = pd.read_sql("SELECT date, value FROM rates_daily WHERE series='DGS10' ORDER BY date", db, index_col="date")["value"]
    dg.index = pd.to_datetime(dg.index)
    me = dg.groupby(dg.index.to_period("M")).last().reindex(d["Y"].index)
    i = d["I"]["US"]
    r_me = par_bond_return(me.shift(1) / 100, me / 100) - i.shift(1) / 1200
    r_av = d["bx"]["US"]
    a, z = SANDBOX
    x, y = fx.window(r_me, a, z).dropna(), fx.window(r_av, a, z).dropna()
    idx = x.index.intersection(y.index)
    return {"k": round(float(x.loc[idx].std() / y.loc[idx].std()), 3), "months": len(idx),
            "vol_month_end": round(float(x.loc[idx].std() * np.sqrt(12)) * 100, 2),
            "vol_average": round(float(y.loc[idx].std() * np.sqrt(12)) * 100, 2),
            "mean_month_end": round(float(x.loc[idx].mean() * 1200), 2), "mean_average": round(float(y.loc[idx].mean() * 1200), 2)}


def corrected(r: pd.Series, k: float) -> pd.Series:
    return r.mean() + k * (r - r.mean())


def job_explore(db) -> dict:
    d = panel(db, vault=False)
    sk = smoothing_k(db, d)
    k = sk["k"]
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/bonds/PLAN.md", "sandbox": SANDBOX,
           "smoothing": sk, "countries": {str(y): list(d["avail"].columns[d["avail"].loc[pd.Period(f"{y}-06", "M")]]) for y in (1980, 1990, 2005)},
           "versions": {}}
    mkt = vm.monthly(vm.load(db, "us"))
    series = {}
    for name, fn in VERSIONS.items():
        r = fx.window(returns(d, fn(d)), *SANDBOX).dropna()
        series[name] = r
        st = fx.overlay_stats(r)
        st["sharpe_corrected"] = round(st["sharpe"] / k, 3)
        m = mkt["R"].reindex(r.index)
        st["corr_with_us_stocks"] = round(float(np.corrcoef(r, m)[0, 1]), 2)
        st["us_stocks_plus_overlay"] = vm.stats(m + corrected(r, k), mkt["rf"])
        st["us_stocks"] = vm.stats(m, mkt["rf"])
        st["decades"] = {f"{y}s": round(float(np.prod(1 + r[(r.index.year >= y) & (r.index.year < y + 10)]) - 1) * 100, 1) for y in (1980, 1990, 2000)}
        res["versions"][name] = st
        print(name, st["per_year"], st["sharpe"], st["sharpe_corrected"], st["t"], flush=True)
    ranked = sorted(res["versions"], key=lambda n: res["versions"][n]["sharpe"], reverse=True)
    srs = [res["versions"][n]["sharpe"] / np.sqrt(12) for n in ranked]
    for n in ranked:
        res["versions"][n]["deflated_prob"] = cs.deflated_sharpe(series[n].values, srs)["prob_real"]
    res["ranked"] = [(n, res["versions"][n]["sharpe"], res["versions"][n]["sharpe_corrected"]) for n in ranked]
    res["finalists_by_rule"] = [n for n in ranked if res["versions"][n]["sharpe_corrected"] >= SHARPE_BAR][:3]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"explore-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def job_holdout(db) -> dict:
    d = panel(db, vault=True)
    names = [ln.split(":", 1)[1].strip() for ln in FINALISTS.read_text().splitlines() if ln.startswith("- finalist:")]
    if not names or len(names) > 3 or any(n not in VERSIONS for n in names):
        raise SystemExit(f"FINALISTS.md must list 1 to 3 known versions; got {names}")
    kline = [ln for ln in FINALISTS.read_text().splitlines() if ln.startswith("- k:")]
    k = float(kline[0].split(":", 1)[1])
    spy = tn._daily_index(db, "SPY_ADJ")
    spym = fx.window(spy.groupby(spy.index.to_period("M")).last().pct_change(), *VAULT)
    rfm = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "window": VAULT, "k": k,
           "commit": subprocess.run(["git", "-C", str(PROJECT), "log", "-1", "--format=%h", "--", str(FINALISTS.relative_to(PROJECT))],
                                    capture_output=True, text=True).stdout.strip(),
           "spy": vm.stats(spym, rfm), "finalists": {}}
    for name in names:
        raw = fx.window(returns(d, VERSIONS[name](d)), *VAULT).dropna()
        idx = raw.index.intersection(spym.index)
        raw, s = raw.loc[idx], spym.loc[idx]
        r = corrected(raw, k)
        combo = s + r
        cst, sst = vm.stats(combo, rfm), vm.stats(s, rfm)
        halves = {f"{a[:4]}-{z[:4]}": fx.overlay_stats(fx.window(r, a, z)) for a, z in HALVES}
        p1 = cst["10k_becomes"] > sst["10k_becomes"] and cst["sharpe"] > sst["sharpe"]
        p2 = all(h["per_year"] > 0 for h in halves.values())
        res["finalists"][name] = {
            "overlay_raw": fx.overlay_stats(raw), "overlay_corrected": fx.overlay_stats(r), "halves_corrected": halves,
            "spy_plus_overlay": cst, "spy": sst, "corr_with_spy": round(float(np.corrcoef(r, s)[0, 1]), 2),
            "bootstrap_sharpe_gap": vm.bootstrap_gap((combo - rfm.reindex(idx)).values, (s - rfm.reindex(idx)).values),
            "crashes": {"2008-09 to 2009-02": round(float(np.prod(1 + fx.window(r, "2008-09", "2009-02")) - 1) * 100, 1),
                        "2020-02 to 2020-03": round(float(np.prod(1 + fx.window(r, "2020-02", "2020-03")) - 1) * 100, 1),
                        "2022": round(float(np.prod(1 + r[r.index.year == 2022]) - 1) * 100, 1)},
            "years": {str(y): round(float(np.prod(1 + r[r.index.year == y]) - 1) * 100, 1) for y in sorted(set(r.index.year))},
            "pass_1": p1, "pass_2": p2, "worth_live_testing": p1 and p2}
    path = RESULTS_DIR / f"holdout-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "bonds-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "explore":
        r = job_explore(db)
        print(json.dumps({k: r[k] for k in ("smoothing", "countries", "ranked", "finalists_by_rule", "_path")}, indent=1))
    elif cmd == "holdout":
        print(json.dumps(job_holdout(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
