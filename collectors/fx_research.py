"""Currency (FX) strategies from international monetary theory: carry, dollar carry, momentum, value (PPP), Taylor
rule, real carry, crash-filtered and trend-filtered carry, per-currency trend, and a combination. Monthly, as
overlays. Plan fixed before any result: docs/fx/PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       FRED spot rates (daily), interest rates, CPI, unemployment into macro_series
  explore    the sandbox (1980-2005 only); results to ~/MarketData/fx/explore-<date>.json
  holdout    opens the vault (2006-2026) for the finalists in docs/fx/FINALISTS.md (must be committed)
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, start_run
import vol_managed as vm
import classic_strategies as cs
import tournament as tn

RESULTS_DIR = Path.home() / "MarketData" / "fx"
PROJECT = Path(__file__).resolve().parent.parent
FINALISTS = PROJECT / "docs" / "fx" / "FINALISTS.md"

# ---- fixed by the plan
SANDBOX = ("1980-01", "2005-12")
VIX_FROM = "1991-01"
VAULT = ("2006-01", "2026-10")
HALVES = (("2006-01", "2015-12"), ("2016-01", "2026-10"))
TRADE_COST, ROLL_COST = 0.0005, 0.0001
SHARPE_BAR = 0.3

# currency: (FRED spot id, quoted as USD per unit?, 3-month rate, fallback short rate, CPI id, CPI quarterly?, unemployment id)
CCY = {
    "GBP": ("DEXUSUK", True, "IR3TIB01GBM156N", "IRSTCI01GBM156N", "GBRCPIALLMINMEI", False, "LRHUTTTTGBM156S"),
    "JPY": ("DEXJPUS", False, "IR3TIB01JPM156N", "IRSTCI01JPM156N", "JPNCPIALLMINMEI", False, "LRHUTTTTJPM156S"),
    "CHF": ("DEXSZUS", False, "IR3TIB01CHM156N", "IRSTCI01CHM156N", "CHECPIALLMINMEI", False, None),
    "CAD": ("DEXCAUS", False, "IR3TIB01CAM156N", "IRSTCI01CAM156N", "CANCPIALLMINMEI", False, "LRHUTTTTCAM156S"),
    "AUD": ("DEXUSAL", True, "IR3TIB01AUM156N", "IRSTCI01AUM156N", "AUSCPIALLQINMEI", True, "LRHUTTTTAUM156S"),
    "NZD": ("DEXUSNZ", True, "IR3TIB01NZM156N", "IRSTCI01NZM156N", "NZLCPIALLQINMEI", True, None),
    "NOK": ("DEXNOUS", False, "IR3TIB01NOM156N", "IRSTCI01NOM156N", "NORCPIALLMINMEI", False, "LRHUTTTTNOM156S"),
    "SEK": ("DEXSDUS", False, "IR3TIB01SEM156N", "IRSTCI01SEM156N", "SWECPIALLMINMEI", False, "LRHUTTTTSEM156S"),
    "EUR": ("DEXUSEU", True, "IR3TIB01DEM156N", "IRSTCI01DEM156N", "DEUCPIALLMINMEI", False, "LRHUTTTTDEM156S"),
}
US = {"rate": "IR3TIB01USM156N", "cpi": "USACPIALLMINMEI", "unemp": "LRHUTTTTUSM156S"}


# ---------------------------------------------------------------- data

SCHEMA = """CREATE TABLE IF NOT EXISTS macro_series (
    series TEXT, date TEXT, value REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (series, date))"""


def fred(series_id: str) -> list[tuple[str, float]]:
    # FRED answers Python's standard user agent (see risk_budget.job_data).
    with urllib.request.urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=90) as r:
        text = r.read().decode()
    out = []
    for ln in text.splitlines()[1:]:
        d, v = ln.split(",")[:2]
        if v not in ("", "."):
            out.append((d, float(v)))
    return out


def all_series() -> list[str]:
    ids = [US["rate"], US["cpi"], US["unemp"]]
    for spot, _, r3, rs, cpi, _, un in CCY.values():
        ids += [spot, r3, rs, cpi] + ([un] if un else [])
    return ids


def job_data(db, ids: list[str] | None = None) -> tuple[str, int, str]:
    db.execute(SCHEMA)
    now = datetime.now(ET).isoformat(timespec="seconds")
    n, notes = 0, []
    for sid in ids or all_series():
        rows = fred(sid)
        db.executemany("INSERT OR REPLACE INTO macro_series VALUES (?,?,?,?,?)", [(sid, d, v, "fred", now) for d, v in rows])
        n += len(rows)
        notes.append(f"{sid} {rows[0][0]}..{rows[-1][0]}")
    db.commit()
    return "ok", n, "; ".join(notes)


# ---------------------------------------------------------------- monthly panel, with the vault lock

def _vault_may_open() -> None:
    rel = FINALISTS.relative_to(PROJECT)
    ok = FINALISTS.exists() and subprocess.run(["git", "-C", str(PROJECT), "ls-files", "--error-unmatch", str(rel)],
                                               capture_output=True).returncode == 0
    clean = ok and subprocess.run(["git", "-C", str(PROJECT), "diff", "--quiet", "HEAD", "--", str(rel)]).returncode == 0
    if not (ok and clean):
        raise SystemExit("The vault stays shut: docs/fx/FINALISTS.md must exist and be committed, unchanged.")


def _series(db, sid: str) -> pd.Series:
    s = pd.read_sql("SELECT date, value FROM macro_series WHERE series=? ORDER BY date", db, params=(sid,), index_col="date")["value"]
    s.index = pd.to_datetime(s.index)
    return s


def _monthly_level(s: pd.Series, quarterly=False) -> pd.Series:
    m = s.groupby(s.index.to_period("M")).last()
    if quarterly:   # quarter dated at its first month: spread over the quarter's three months
        full = pd.period_range(m.index[0], m.index[-1] + 2, freq="M")
        m = m.reindex(full).ffill(limit=2)
    return m


def panel(db, vault: bool = False) -> dict:
    if vault:
        _vault_may_open()
    last = pd.Period(VAULT[1] if vault else SANDBOX[1], "M")
    S, I, P, U = {}, {}, {}, {}
    for c, (spot, usd_per, r3, rs, cpi, q, un) in CCY.items():
        x = _monthly_level(_series(db, spot))
        S[c] = x if usd_per else 1 / x
        a, b = _monthly_level(_series(db, r3)), _monthly_level(_series(db, rs))
        I[c] = a.combine_first(b)
        P[c] = _monthly_level(_series(db, cpi), quarterly=q)
        U[c] = _monthly_level(_series(db, un)) if un else None
    i_us = _monthly_level(_series(db, US["rate"]))
    p_us = _monthly_level(_series(db, US["cpi"]))
    u_us = _monthly_level(_series(db, US["unemp"]))
    idx = pd.period_range("1971-01", last, freq="M")
    S = pd.DataFrame(S).reindex(idx)
    I = pd.DataFrame(I).reindex(idx)
    # rates and CPI: carry the last value forward a little (published series that end early)
    I = I.ffill(limit=3)
    P = pd.DataFrame({c: v for c, v in P.items()}).reindex(pd.period_range("1955-01", last, freq="M")).ffill().reindex(idx)
    U = pd.DataFrame({c: v for c, v in U.items() if v is not None}).reindex(pd.period_range("1955-01", last, freq="M")).ffill().reindex(idx)
    i_us = i_us.reindex(idx).ffill(limit=3)
    p_us = p_us.reindex(pd.period_range("1955-01", last, freq="M")).ffill().reindex(idx)
    u_us = u_us.reindex(pd.period_range("1955-01", last, freq="M")).ffill().reindex(idx)
    # excess return of a long position over month t (from end t-1 to end t)
    rx = S / S.shift(1) * (1 + I.shift(1) / 1200) - (1 + i_us.shift(1).values[:, None] / 1200)
    avail = S.notna() & I.notna()
    if not vault:
        assert idx[-1] <= pd.Period(SANDBOX[1], "M")
    return {"S": S, "I": I, "P": P, "U": U, "i_us": i_us, "p_us": p_us, "u_us": u_us, "rx": rx, "avail": avail}


# ---------------------------------------------------------------- signals -> weights (row t = held during t+1)

def rank_weights(sig: pd.DataFrame, avail: pd.DataFrame) -> pd.DataFrame:
    W = pd.DataFrame(0.0, index=sig.index, columns=sig.columns)
    for t in sig.index:
        s = sig.loc[t][avail.loc[t] & sig.loc[t].notna()]
        n = len(s)
        if n < 4:
            W.loc[t] = np.nan
            continue
        k = max(2, n // 3)
        o = s.sort_values()
        W.loc[t, o.index[-k:]] = 1 / k
        W.loc[t, o.index[:k]] = -1 / k
    return W


def returns(d: dict, W: pd.DataFrame, trade=TRADE_COST, roll=ROLL_COST) -> pd.Series:
    """W row t = weights held over month t+1. Monthly overlay returns after costs, indexed by t+1."""
    W = W.dropna(how="all").fillna(0.0)
    rxn = d["rx"].shift(-1).reindex(W.index)
    gross = (W * rxn.fillna(0.0)).sum(axis=1)
    turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    r = gross - trade * turn - roll * W.abs().sum(axis=1)
    r.index = r.index + 1
    return r[rxn.notna().any(axis=1).values]


def infl(d: dict):
    """12-month inflation known at t (CPI two months old)."""
    P, p = d["P"], d["p_us"]
    return P.shift(2) / P.shift(14) - 1, p.shift(2) / p.shift(14) - 1


def w_carry(d):
    return rank_weights(d["I"].sub(d["i_us"], axis=0), d["avail"])


def w_dollar(d):
    a = d["avail"]
    diff = d["I"].sub(d["i_us"], axis=0).where(a).mean(axis=1)
    n = a.sum(axis=1)
    W = a.astype(float).div(n.replace(0, np.nan), axis=0).mul(np.sign(diff), axis=0)
    return W.where(n >= 4)


def w_mom(d, k):
    cum = (1 + d["rx"]).rolling(k).apply(np.prod, raw=True) - 1
    return rank_weights(cum, d["avail"])


def w_value(d):
    q = np.log(d["S"]) + np.log(d["P"].shift(2)) - np.log(d["p_us"].shift(2)).values[:, None]
    return rank_weights(-(q - q.shift(60)), d["avail"])


def w_taylor(d):
    pi, pi_us = infl(d)
    U, u_us = d["U"].shift(2), d["u_us"].shift(2)
    gap = -(U - U.rolling(120, min_periods=60).mean())
    gap_us = -(u_us - u_us.rolling(120, min_periods=60).mean())
    gdiff = gap.sub(gap_us, axis=0).reindex(columns=pi.columns).fillna(0.0)
    score = 1.5 * pi.sub(pi_us, axis=0) + 0.5 * gdiff / 100     # gap is in percentage points
    return rank_weights(score, d["avail"])


def w_real_carry(d):
    pi, pi_us = infl(d)
    real = d["I"] / 100 - pi
    return rank_weights(real.sub(d["i_us"] / 100 - pi_us, axis=0), d["avail"])


def _vix_month_end(db, last) -> pd.Series:
    v = tn._daily_index(db, "VIX")
    m = v.groupby(v.index.to_period("M")).last()
    return m.loc[:last]


def w_carry_vix(d, db):
    W = w_carry(d)
    v = _vix_month_end(db, W.index[-1])
    calm = (v <= v.rolling(12).mean()).reindex(W.index)
    W = W.mul(calm.astype(float), axis=0)
    return W.where(calm.notna())


def w_carry_trend(d):
    W = w_carry(d)
    r = returns(d, W, 0.0, 0.0)               # carry's own gross monthly returns (indexed by month earned)
    trail = (1 + r).rolling(12).apply(np.prod, raw=True) - 1
    on = (trail > 0).reindex(W.index)         # at end of t, carry's last 12 months up to t
    return W.mul(on.astype(float), axis=0).where(trail.reindex(W.index).notna())


def w_ts_trend(d):
    a = d["avail"]
    cum = (1 + d["rx"]).rolling(12).apply(np.prod, raw=True) - 1
    n = (a & cum.notna()).sum(axis=1)
    W = np.sign(cum).where(a).div(n.replace(0, np.nan), axis=0)
    return W.where(n >= 4)


def w_combo(d):
    parts = [w_carry(d), w_mom(d, 12), w_value(d)]
    out = None
    for W in parts:
        r = returns(d, W, 0.0, 0.0)
        vol = r.rolling(36).std() * np.sqrt(12)
        scale = (0.08 / vol).reindex(W.index)    # r is indexed by the month earned: vol at t uses returns up to t
        x = W.mul(scale, axis=0)
        out = x if out is None else out.add(x, fill_value=np.nan)
    return out / 3


VERSIONS = {
    "1_carry": lambda d, db: w_carry(d),
    "2_dollar_carry": lambda d, db: w_dollar(d),
    "3_momentum_1m": lambda d, db: w_mom(d, 1),
    "4_momentum_12m": lambda d, db: w_mom(d, 12),
    "5_value_ppp": lambda d, db: w_value(d),
    "6_taylor_rule": lambda d, db: w_taylor(d),
    "7_real_carry": lambda d, db: w_real_carry(d),
    "8_carry_vix_filter": lambda d, db: w_carry_vix(d, db),
    "9_carry_trend_filter": lambda d, db: w_carry_trend(d),
    "10_trend_per_currency": lambda d, db: w_ts_trend(d),
    "11_combination": lambda d, db: w_combo(d),
}


# ---------------------------------------------------------------- scoring

def overlay_stats(r: pd.Series) -> dict:
    r = r.dropna()
    w = (1 + r).cumprod()
    return {"months": len(r), "per_year": round(float(w.iloc[-1] ** (12 / len(r)) - 1) * 100, 2),
            "vol": round(float(r.std() * np.sqrt(12)) * 100, 2),
            "sharpe": round(float(r.mean() / r.std() * np.sqrt(12)), 3),
            "t": round(cs.nw_t(r.values), 2), "worst_drop": round(float((w / w.cummax() - 1).min()) * 100, 1),
            "worst_month": round(float(r.min()) * 100, 1)}


def window(s, a, z):
    return s.loc[pd.Period(a, "M"):pd.Period(z, "M")]


def job_explore(db) -> dict:
    d = panel(db, vault=False)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/fx/PLAN.md",
           "sandbox": SANDBOX, "currencies_by_year": {}, "versions": {}}
    for y in (1980, 1985, 1990, 1999, 2005):
        res["currencies_by_year"][str(y)] = list(d["avail"].columns[d["avail"].loc[pd.Period(f"{y}-06", "M")]])
    mkt = vm.monthly(vm.load(db, "us"))
    rfm = mkt["rf"]
    for name, fn in VERSIONS.items():
        W = fn(d, db)
        r = returns(d, W)
        a = VIX_FROM if name.startswith("8_") else SANDBOX[0]
        r = window(r, a, SANDBOX[1]).dropna()
        st = overlay_stats(r)
        m = mkt["R"].reindex(r.index)
        st["corr_with_us_stocks"] = round(float(np.corrcoef(r, m)[0, 1]), 2)
        st["us_stocks_plus_overlay"] = vm.stats(m + r, rfm)
        st["us_stocks"] = vm.stats(m, rfm)
        st["decades"] = {f"{y}s": round(float(np.prod(1 + r[(r.index.year >= y) & (r.index.year < y + 10)]) - 1) * 100, 1)
                         for y in (1980, 1990, 2000)}
        res["versions"][name] = st
        print(name, st["per_year"], st["sharpe"], st["t"], st["worst_drop"], flush=True)
    ranked = sorted(res["versions"], key=lambda k: res["versions"][k]["sharpe"], reverse=True)
    res["ranked_by_sharpe"] = [(k, res["versions"][k]["sharpe"]) for k in ranked]
    res["finalists_by_rule"] = [k for k in ranked if res["versions"][k]["sharpe"] >= SHARPE_BAR][:3]
    srs = [res["versions"][k]["sharpe"] for k in ranked]
    for k in ranked:   # deflated chance the Sharpe is real, given 11 tries
        r = returns(d, VERSIONS[k](d, db))
        r = window(r, VIX_FROM if k.startswith("8_") else SANDBOX[0], SANDBOX[1]).dropna()
        res["versions"][k]["deflated_prob"] = cs.deflated_sharpe(r.values, [s / np.sqrt(12) for s in srs])["prob_real"]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"explore-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def finalists() -> list[str]:
    names = [ln.split(":", 1)[1].strip() for ln in FINALISTS.read_text().splitlines() if ln.startswith("- finalist:")]
    if not names or len(names) > 3 or any(n not in VERSIONS for n in names):
        raise SystemExit(f"FINALISTS.md must list 1 to 3 known versions; got {names}")
    return names


def job_holdout(db) -> dict:
    d = panel(db, vault=True)
    names = finalists()
    spy = tn._daily_index(db, "SPY_ADJ")
    spym = (spy.groupby(spy.index.to_period("M")).last().pct_change())
    spym = window(spym, *VAULT)
    rfm = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "window": VAULT,
           "commit": subprocess.run(["git", "-C", str(PROJECT), "log", "-1", "--format=%h", "--", str(FINALISTS.relative_to(PROJECT))],
                                    capture_output=True, text=True).stdout.strip(),
           "spy": vm.stats(spym, rfm), "finalists": {}}
    for name in names:
        r = window(returns(d, VERSIONS[name](d, db)), *VAULT).dropna()
        idx = r.index.intersection(spym.index)
        r, s = r.loc[idx], spym.loc[idx]
        combo = s + r
        cst, sst = vm.stats(combo, rfm), vm.stats(s, rfm)
        halves = {f"{a[:4]}-{z[:4]}": overlay_stats(window(r, a, z)) for a, z in HALVES}
        p1 = cst["10k_becomes"] > sst["10k_becomes"] and cst["sharpe"] > sst["sharpe"]
        p2 = all(h["per_year"] > 0 for h in halves.values())
        res["finalists"][name] = {
            "overlay": overlay_stats(r), "halves": halves, "spy_plus_overlay": cst, "spy": sst,
            "corr_with_spy": round(float(np.corrcoef(r, s)[0, 1]), 2),
            "bootstrap_sharpe_gap": vm.bootstrap_gap((combo - rfm.reindex(idx)).values, (s - rfm.reindex(idx)).values),
            "crashes": {"2008-09 to 2009-02": round(float(np.prod(1 + window(r, "2008-09", "2009-02")) - 1) * 100, 1),
                        "2020-02 to 2020-03": round(float(np.prod(1 + window(r, "2020-02", "2020-03")) - 1) * 100, 1)},
            "years": {str(y): round(float(np.prod(1 + r[r.index.year == y]) - 1) * 100, 1) for y in sorted(set(r.index.year))},
            "pass_1_spy_plus_overlay_beats_spy": p1, "pass_2_both_halves": p2,
            "pass_3_fresh_currencies": "run separately (fx_research.py confirm), only if 1 and 2 pass"}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"holdout-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "fx-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "explore":
        r = job_explore(db)
        print(json.dumps({k: r[k] for k in ("currencies_by_year", "ranked_by_sharpe", "finalists_by_rule", "_path")}, indent=1))
    elif cmd == "holdout":
        print(json.dumps(job_holdout(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
