"""Emerging-market currency strategies (9 versions), reusing the mechanics of fx_research.py.
Plan fixed before any EM data was loaded: docs/fx/EM_PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       FRED and Yahoo spot rates, OECD rates and CPI into macro_series (Yahoo series named "YF:USDxxx=X")
  explore    sandbox 2004-2013 only; results to ~/MarketData/fx/em-explore-<date>.json
  holdout    vault 2014-2026 for docs/fx/EM_FINALISTS.md (must be committed)
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, start_run
import fx_research as fx
import vol_managed as vm
import classic_strategies as cs
import tournament as tn

PROJECT = fx.PROJECT
FINALISTS = PROJECT / "docs" / "fx" / "EM_FINALISTS.md"

# ---- fixed by the plan
SANDBOX = ("2004-01", "2013-12")
VAULT = ("2014-01", "2026-10")
HALVES = (("2014-01", "2019-12"), ("2020-01", "2026-10"))
TRADE, ROLL = 0.0010, 0.0002
SHARPE_BAR = 0.3
RUB_LAST = "2022-02"

# currency: (spot series, 3-month rate or None, call-money rate, CPI)
EM = {
    "MXN": ("DEXMXUS", "IR3TIB01MXM156N", "IRSTCI01MXM156N", "MEXCPIALLMINMEI"),
    "KRW": ("DEXKOUS", "IR3TIB01KRM156N", "IRSTCI01KRM156N", "KORCPIALLMINMEI"),
    "ZAR": ("DEXSFUS", "IR3TIB01ZAM156N", "IRSTCI01ZAM156N", "ZAFCPIALLMINMEI"),
    "BRL": ("DEXBZUS", None, "IRSTCI01BRM156N", "BRACPIALLMINMEI"),
    "INR": ("DEXINUS", None, "IRSTCI01INM156N", "INDCPIALLMINMEI"),
    "HUF": ("YF:USDHUF=X", "IR3TIB01HUM156N", "IRSTCI01HUM156N", "HUNCPIALLMINMEI"),
    "PLN": ("YF:USDPLN=X", "IR3TIB01PLM156N", "IRSTCI01PLM156N", "POLCPIALLMINMEI"),
    "CZK": ("YF:USDCZK=X", "IR3TIB01CZM156N", "IRSTCI01CZM156N", "CZECPIALLMINMEI"),
    "ILS": ("YF:USDILS=X", "IR3TIB01ILM156N", "IRSTCI01ILM156N", "ISRCPIALLMINMEI"),
    "CLP": ("YF:USDCLP=X", "IR3TIB01CLM156N", "IRSTCI01CLM156N", "CHLCPIALLMINMEI"),
    "IDR": ("YF:USDIDR=X", "IR3TIB01IDM156N", "IRSTCI01IDM156N", "IDNCPIALLMINMEI"),
    "RUB": ("YF:USDRUB=X", "IR3TIB01RUM156N", "IRSTCI01RUM156N", "RUSCPIALLMINMEI"),
    "TRY": ("YF:USDTRY=X", None, "IRSTCI01TRM156N", "TURCPIALLMINMEI"),
}


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    db.execute(fx.SCHEMA)
    now = datetime.now(ET).isoformat(timespec="seconds")
    n, notes, missing = 0, [], []
    for spot, r3, rs, cpi in EM.values():
        for sid in (spot, r3, rs, cpi):
            if not sid:
                continue
            if sid.startswith("YF:"):
                t = yf.download(sid[3:], start="2003-01-01", progress=False, auto_adjust=True)["Close"].iloc[:, 0].dropna()
                rows = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in t.items()]
                src = "yahoo"
            else:
                try:
                    rows, src = fx.fred(sid), "fred"
                except urllib.error.HTTPError:
                    missing.append(sid)
                    continue
            db.executemany("INSERT OR REPLACE INTO macro_series VALUES (?,?,?,?,?)", [(sid, d, v, src, now) for d, v in rows])
            n += len(rows)
            notes.append(f"{sid} {rows[0][0]}..{rows[-1][0]}")
    db.commit()
    return "ok", n, "; ".join(notes) + (f"; not on FRED: {' '.join(missing)}" if missing else "")


def _has(db, sid) -> bool:
    return sid is not None and db.execute("SELECT 1 FROM macro_series WHERE series=? LIMIT 1", (sid,)).fetchone() is not None


def _vault_may_open() -> None:
    rel = FINALISTS.relative_to(PROJECT)
    ok = FINALISTS.exists() and subprocess.run(["git", "-C", str(PROJECT), "ls-files", "--error-unmatch", str(rel)],
                                               capture_output=True).returncode == 0
    clean = ok and subprocess.run(["git", "-C", str(PROJECT), "diff", "--quiet", "HEAD", "--", str(rel)]).returncode == 0
    if not (ok and clean):
        raise SystemExit("The vault stays shut: docs/fx/EM_FINALISTS.md must exist and be committed, unchanged.")


def panel(db, vault: bool = False) -> dict:
    if vault:
        _vault_may_open()
    last = pd.Period(VAULT[1] if vault else SANDBOX[1], "M")
    idx = pd.period_range("2003-01", last, freq="M")
    long_idx = pd.period_range("1955-01", last, freq="M")
    S, I, P = {}, {}, {}
    for c, (spot, r3, rs, cpi) in EM.items():
        raw = fx._series(db, spot)
        if spot.startswith("YF:"):   # Yahoo has occasional bad prints: drop days >8% off the 11-day centred median
            med = raw.rolling(11, center=True, min_periods=5).median()
            raw = raw[(raw / med - 1).abs() <= 0.08]
        S[c] = 1 / fx._monthly_level(raw)           # all quoted as local currency per dollar
        rate = fx._monthly_level(fx._series(db, rs))
        if _has(db, r3):
            rate = fx._monthly_level(fx._series(db, r3)).combine_first(rate)
        I[c] = rate
        if _has(db, cpi):
            P[c] = fx._monthly_level(fx._series(db, cpi))
    S = pd.DataFrame(S).reindex(idx)
    S.loc[pd.Period(RUB_LAST, "M") + 1:, "RUB"] = np.nan
    I = pd.DataFrame(I).reindex(idx).ffill(limit=3)
    P = pd.DataFrame(P).reindex(long_idx).ffill().reindex(idx).reindex(columns=S.columns)
    i_us = fx._monthly_level(fx._series(db, fx.US["rate"])).reindex(idx).ffill(limit=3)
    p_us = fx._monthly_level(fx._series(db, fx.US["cpi"])).reindex(long_idx).ffill().reindex(idx)
    rx = S / S.shift(1) * (1 + I.shift(1) / 1200) - (1 + i_us.shift(1).values[:, None] / 1200)
    avail = S.notna() & I.notna() & S.shift(1).notna()
    return {"S": S, "I": I, "P": P, "U": None, "i_us": i_us, "p_us": p_us, "u_us": None, "rx": rx, "avail": avail}


def w_long_carry(d):
    a = d["avail"]
    diff = d["I"].sub(d["i_us"], axis=0).where(a)
    W = pd.DataFrame(0.0, index=diff.index, columns=diff.columns)
    for t in diff.index:
        s = diff.loc[t].dropna()
        if len(s) < 4:
            W.loc[t] = np.nan
            continue
        k = len(s) // 2
        W.loc[t, s.sort_values().index[-k:]] = 1 / k
    return W


def w_vix(W, db):
    v = fx._vix_month_end(db, W.index[-1])
    calm = (v <= v.rolling(12).mean()).reindex(W.index)
    return W.mul(calm.astype(float), axis=0).where(calm.notna())


def w_combo(d):
    parts = [fx.w_carry(d), fx.w_mom(d, 12), fx.w_value(d)]
    out = None
    for W in parts:
        r = fx.returns(d, W, 0.0, 0.0)
        vol = r.rolling(36).std() * np.sqrt(12)
        x = W.mul((0.08 / vol).reindex(W.index), axis=0)
        out = x if out is None else out.add(x)
    return out / 3


VERSIONS = {
    "E1_carry": lambda d, db: fx.w_carry(d),
    "E2_em_carry_long_only": lambda d, db: w_long_carry(d),
    "E3_all_em_vs_dollar": lambda d, db: fx.w_dollar(d),
    "E4_trend_per_currency": lambda d, db: fx.w_ts_trend(d),
    "E5_momentum_12m": lambda d, db: fx.w_mom(d, 12),
    "E6_value_ppp": lambda d, db: fx.w_value(d),
    "E7_carry_vix_filter": lambda d, db: w_vix(fx.w_carry(d), db),
    "E8_em_carry_long_only_vix": lambda d, db: w_vix(w_long_carry(d), db),
    "E9_combination": lambda d, db: w_combo(d),
}


def run(d, db, name) -> pd.Series:
    return fx.returns(d, VERSIONS[name](d, db), TRADE, ROLL)


def job_explore(db) -> dict:
    d = panel(db, vault=False)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/fx/EM_PLAN.md", "sandbox": SANDBOX,
           "currencies": {str(y): list(d["avail"].columns[d["avail"].loc[pd.Period(f"{y}-06", "M")]]) for y in (2004, 2008, 2013)},
           "value_currencies": list(d["P"].columns[d["P"].notna().any()]), "versions": {}}
    mkt = vm.monthly(vm.load(db, "us"))
    series = {}
    for name in VERSIONS:
        r = fx.window(run(d, db, name), *SANDBOX).dropna()
        series[name] = r
        st = fx.overlay_stats(r)
        m = mkt["R"].reindex(r.index)
        st["corr_with_us_stocks"] = round(float(np.corrcoef(r, m)[0, 1]), 2)
        st["us_stocks_plus_overlay"] = vm.stats(m + r, mkt["rf"])
        st["us_stocks"] = vm.stats(m, mkt["rf"])
        st["2008-09_to_2009-02"] = round(float(np.prod(1 + fx.window(r, "2008-09", "2009-02")) - 1) * 100, 1)
        res["versions"][name] = st
        print(name, st["per_year"], st["sharpe"], st["t"], st["worst_drop"], flush=True)
    ranked = sorted(res["versions"], key=lambda k: res["versions"][k]["sharpe"], reverse=True)
    srs = [res["versions"][k]["sharpe"] / np.sqrt(12) for k in ranked]
    for k in ranked:
        res["versions"][k]["deflated_prob"] = cs.deflated_sharpe(series[k].values, srs)["prob_real"]
    res["ranked_by_sharpe"] = [(k, res["versions"][k]["sharpe"]) for k in ranked]
    res["finalists_by_rule"] = [k for k in ranked if res["versions"][k]["sharpe"] >= SHARPE_BAR][:3]
    fx.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = fx.RESULTS_DIR / f"em-explore-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def job_holdout(db) -> dict:
    d = panel(db, vault=True)
    names = [ln.split(":", 1)[1].strip() for ln in FINALISTS.read_text().splitlines() if ln.startswith("- finalist:")]
    if not names or len(names) > 3 or any(n not in VERSIONS for n in names):
        raise SystemExit(f"EM_FINALISTS.md must list 1 to 3 known versions; got {names}")
    spy = tn._daily_index(db, "SPY_ADJ")
    spym = fx.window(spy.groupby(spy.index.to_period("M")).last().pct_change(), *VAULT)
    rfm = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "window": VAULT,
           "commit": subprocess.run(["git", "-C", str(PROJECT), "log", "-1", "--format=%h", "--", str(FINALISTS.relative_to(PROJECT))],
                                    capture_output=True, text=True).stdout.strip(),
           "spy": vm.stats(spym, rfm), "finalists": {}}
    for name in names:
        r = fx.window(run(d, db, name), *VAULT).dropna()
        idx = r.index.intersection(spym.index)
        r, s = r.loc[idx], spym.loc[idx]
        combo = s + r
        cst, sst = vm.stats(combo, rfm), vm.stats(s, rfm)
        halves = {f"{a[:4]}-{z[:4]}": fx.overlay_stats(fx.window(r, a, z)) for a, z in HALVES}
        p1 = cst["10k_becomes"] > sst["10k_becomes"] and cst["sharpe"] > sst["sharpe"]
        p2 = all(h["per_year"] > 0 for h in halves.values())
        res["finalists"][name] = {
            "overlay": fx.overlay_stats(r), "halves": halves, "spy_plus_overlay": cst, "spy": sst,
            "corr_with_spy": round(float(np.corrcoef(r, s)[0, 1]), 2),
            "bootstrap_sharpe_gap": vm.bootstrap_gap((combo - rfm.reindex(idx)).values, (s - rfm.reindex(idx)).values),
            "crashes": {"2020-02 to 2020-03": round(float(np.prod(1 + fx.window(r, "2020-02", "2020-03")) - 1) * 100, 1),
                        "2022": round(float(np.prod(1 + r[r.index.year == 2022]) - 1) * 100, 1)},
            "years": {str(y): round(float(np.prod(1 + r[r.index.year == y]) - 1) * 100, 1) for y in sorted(set(r.index.year))},
            "pass_1": p1, "pass_2": p2, "worth_live_testing": p1 and p2}
    path = fx.RESULTS_DIR / f"em-holdout-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "fx-em-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "explore":
        r = job_explore(db)
        print(json.dumps({k: r[k] for k in ("currencies", "value_currencies", "ranked_by_sharpe", "finalists_by_rule", "_path")}, indent=1))
    elif cmd == "holdout":
        print(json.dumps(job_holdout(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
