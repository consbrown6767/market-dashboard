"""Country stock-market rotation with real iShares country funds: momentum, reversal, value (dividend yield), low
volatility, value + momentum, trend, filtered momentum. Plan fixed before any data: docs/countries/PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       Yahoo adjusted and raw closes (<T>_ADJ, <T>_RAW in index_daily) and dividends for the country funds
  explore    sandbox 1997-04 to 2010-12 only; results to ~/MarketData/countries/explore-<date>.json
  holdout    vault 2011-2026 for docs/countries/FINALISTS.md (must be committed)
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

RESULTS_DIR = Path.home() / "MarketData" / "countries"
PROJECT = fx.PROJECT
FINALISTS = PROJECT / "docs" / "countries" / "FINALISTS.md"

# ---- fixed by the plan
FUNDS = ["EWA", "EWC", "EWD", "EWG", "EWH", "EWI", "EWJ", "EWK", "EWL", "EWM", "EWN", "EWO", "EWP", "EWQ", "EWS",
         "EWU", "EWW", "SPY", "EWY", "EWT", "EWZ", "EZA"]
SANDBOX = ("1997-04", "2010-12")
VAULT = ("2011-01", "2026-10")
HALVES = (("2011-01", "2018-12"), ("2019-01", "2026-10"))
TRADE, BORROW = 0.0010, 0.005
SHARPE_BAR = 0.3


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows, divs, notes = [], [], []
    for t in FUNDS:
        x = yf.download(t, start="1993-01-01" if t == "SPY" else "1996-01-01", progress=False, auto_adjust=False, actions=True)
        x.columns = [c[0] for c in x.columns]
        x = x.dropna(subset=["Close", "Adj Close"])
        # whole history replaced at once: Yahoo rescales adjusted prices after each dividend
        rows += [(f"{t}_ADJ", d.strftime("%Y-%m-%d"), None, None, None, float(r["Adj Close"]), "yahoo-adjusted", now) for d, r in x.iterrows()]
        if t == "SPY":
            notes.append(f"SPY_ADJ {x.index[0]:%Y-%m-%d}..{x.index[-1]:%Y-%m-%d} (SPY_RAW and dividends already stored)")
            continue
        rows += [(f"{t}_RAW", d.strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), "yahoo-raw", now)
                 for d, r in x.iterrows()]
        dv = x["Dividends"][x["Dividends"] > 0]
        divs += [(t, d.strftime("%Y-%m-%d"), float(v), "yahoo", now) for d, v in dv.items()]
        notes.append(f"{t} {x.index[0]:%Y-%m-%d}..{x.index[-1]:%Y-%m-%d} div={len(dv)}")
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT OR IGNORE INTO dividends VALUES (?,?,?,?,?)", divs)
    db.commit()
    return "ok", len(rows), "; ".join(notes)


def _vault_may_open() -> None:
    rel = FINALISTS.relative_to(PROJECT)
    ok = FINALISTS.exists() and subprocess.run(["git", "-C", str(PROJECT), "ls-files", "--error-unmatch", str(rel)],
                                               capture_output=True).returncode == 0
    clean = ok and subprocess.run(["git", "-C", str(PROJECT), "diff", "--quiet", "HEAD", "--", str(rel)]).returncode == 0
    if not (ok and clean):
        raise SystemExit("The vault stays shut: docs/countries/FINALISTS.md must exist and be committed, unchanged.")


def panel(db, vault: bool = False) -> dict:
    if vault:
        _vault_may_open()
    end = pd.Period(VAULT[1] if vault else SANDBOX[1], "M")
    adj = pd.concat({t: tn._daily_index(db, f"{t}_ADJ") for t in FUNDS}, axis=1)
    raw = pd.concat({t: tn._daily_index(db, f"{t}_RAW") for t in FUNDS}, axis=1)
    adj = adj[adj.index.to_period("M") <= end]
    raw = raw[raw.index.to_period("M") <= end]
    dv = pd.read_sql("SELECT symbol, ex_date, amount FROM dividends WHERE symbol IN (%s)" % ",".join("?" * len(FUNDS)), db,
                     params=FUNDS)
    dv["ex_date"] = pd.to_datetime(dv["ex_date"])
    dv = dv[dv["ex_date"].dt.to_period("M") <= end]
    dv = dv.drop_duplicates(["symbol", "ex_date"]).pivot_table(index="ex_date", columns="symbol", values="amount", aggfunc="sum")
    me_adj = adj.groupby(adj.index.to_period("M")).last()
    me_raw = raw.groupby(raw.index.to_period("M")).last()
    R = me_adj.pct_change(fill_method=None)
    dm = dv.groupby(dv.index.to_period("M")).sum().reindex(me_adj.index).fillna(0.0).reindex(columns=FUNDS, fill_value=0.0)
    dy = dm.rolling(12).sum() / me_raw
    first = me_adj.apply(lambda s: s.first_valid_index())
    for t in FUNDS:   # a fund needs 12 months of dividends history before its yield counts
        if first[t] is not None:
            dy.loc[: first[t] + 12, t] = np.nan
    dret = adj.pct_change(fill_method=None)
    vol = dret.rolling(252, min_periods=200).std().groupby(dret.index.to_period("M")).last()
    avail = R.notna() & R.shift(1).notna()
    rf = tn.rf_monthly(db).reindex(R.index)
    return {"R": R, "dy": dy, "vol": vol, "avail": avail, "rf": rf, "level": me_adj}


def overlay_returns(d: dict, W: pd.DataFrame) -> pd.Series:
    W = W.dropna(how="all").fillna(0.0)
    nxt = d["R"].shift(-1).reindex(W.index)
    gross = (W * nxt.fillna(0.0)).sum(axis=1)
    turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    r = gross - TRADE * turn - BORROW / 12 * (-W.clip(upper=0)).sum(axis=1)
    keep = nxt.notna().any(axis=1).values
    r.index = r.index + 1
    return r[keep]


def cum(R, a, b):
    """Return over months t-a .. t-b (inclusive), known at the end of t."""
    return (1 + R).shift(b).rolling(a - b + 1).apply(np.prod, raw=True) - 1


def pct_rank(sig, avail):
    return sig.where(avail).rank(axis=1, pct=True)


def w_mom12(d):
    return fx.rank_weights(cum(d["R"], 11, 1), d["avail"])


def w_mom6(d):
    return fx.rank_weights(cum(d["R"], 5, 0), d["avail"])


def w_reversal(d):
    return fx.rank_weights(-d["R"], d["avail"])


def w_value(d):
    return fx.rank_weights(d["dy"], d["avail"])


def w_lowvol(d):
    return fx.rank_weights(-d["vol"], d["avail"])


def w_valmom(d):
    a = d["avail"]
    s = (pct_rank(cum(d["R"], 11, 1), a) + pct_rank(d["dy"], a)) / 2
    return fx.rank_weights(s, a)


def ew_level(d):
    ew = d["R"].where(d["avail"]).mean(axis=1).fillna(0.0)
    return (1 + ew).cumprod()


def w_trend_long(d):
    lvl = d["level"]
    above = (lvl > lvl.rolling(10).mean()) & lvl.rolling(10).count().eq(10) & d["avail"]
    n = d["avail"].sum(axis=1)
    return above.astype(float).div(n.replace(0, np.nan), axis=0)


def w_mom_filtered(d):
    W = w_mom12(d)
    lv = ew_level(d)
    on = (lv > lv.rolling(10).mean()).reindex(W.index)
    return W.mul(on.astype(float), axis=0).where(lv.rolling(10).mean().reindex(W.index).notna())


VERSIONS = {"C1_momentum_12_1": w_mom12, "C2_momentum_6m": w_mom6, "C3_reversal_1m": w_reversal, "C4_value_dividend_yield": w_value,
            "C5_low_volatility": w_lowvol, "C6_value_plus_momentum": w_valmom, "C7_trend_long_only": w_trend_long,
            "C8_momentum_market_filter": w_mom_filtered}


def long_only_returns(d, W):
    W = W.dropna(how="all").fillna(0.0)
    nxt = d["R"].shift(-1).reindex(W.index)
    rf = d["rf"].shift(-1).reindex(W.index)
    gross = rf + (W * (nxt.fillna(0.0).sub(rf, axis=0))).sum(axis=1)
    turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    r = gross - TRADE * turn
    r.index = r.index + 1
    return r[nxt.notna().any(axis=1).values]


def strategy(d, name):
    W = VERSIONS[name](d)
    return long_only_returns(d, W) if name.startswith("C7") else overlay_returns(d, W)


def _spy(d):
    return d["R"]["SPY"]


def job_explore(db) -> dict:
    d = panel(db, vault=False)
    rfm = tn.rf_monthly(db)
    spy = fx.window(_spy(d), *SANDBOX)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/countries/PLAN.md", "sandbox": SANDBOX,
           "funds_by_year": {str(y): int(d["avail"].loc[pd.Period(f"{y}-06", "M")].sum()) for y in (1997, 2001, 2004, 2010)},
           "spy": vm.stats(spy, rfm), "versions": {}}
    series = {}
    for name in VERSIONS:
        r = fx.window(strategy(d, name), *SANDBOX).dropna()
        series[name] = r
        if name.startswith("C7"):
            st = vm.stats(r, rfm)
            st["sharpe_for_ranking"] = st["sharpe"]
        else:
            st = fx.overlay_stats(r)
            s = spy.reindex(r.index)
            st["spy_plus_overlay"] = vm.stats(s + r, rfm)
            st["corr_with_spy"] = round(float(np.corrcoef(r, s)[0, 1]), 2)
            st["sharpe_for_ranking"] = st["sharpe"]
        res["versions"][name] = st
        print(name, st, flush=True)
    ranked = sorted(res["versions"], key=lambda k: res["versions"][k]["sharpe_for_ranking"], reverse=True)
    res["ranked"] = [(k, res["versions"][k]["sharpe_for_ranking"]) for k in ranked]
    res["finalists_by_rule"] = [k for k in ranked if res["versions"][k]["sharpe_for_ranking"] >= SHARPE_BAR][:3]
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
    rfm = tn.rf_monthly(db)
    spy = fx.window(_spy(d), *VAULT)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "window": VAULT, "spy": vm.stats(spy, rfm),
           "commit": subprocess.run(["git", "-C", str(PROJECT), "log", "-1", "--format=%h", "--", str(FINALISTS.relative_to(PROJECT))],
                                    capture_output=True, text=True).stdout.strip(), "finalists": {}}
    for name in names:
        r = fx.window(strategy(d, name), *VAULT).dropna()
        idx = r.index.intersection(spy.index)
        r, s = r.loc[idx], spy.loc[idx]
        if name.startswith("C7"):
            st, sp = vm.stats(r, rfm), vm.stats(s, rfm)
            halves = {f"{a[:4]}-{z[:4]}": {"rule": vm.stats(fx.window(r, a, z), rfm), "spy": vm.stats(fx.window(s, a, z), rfm)} for a, z in HALVES}
            better = lambda x, y: x["10k_becomes"] > y["10k_becomes"] and x["sharpe"] > y["sharpe"]
            safer = lambda x, y: x["sharpe"] > y["sharpe"] and x["worst_drop"] > y["worst_drop"]
            ok = (better(st, sp) and all(better(h["rule"], h["spy"]) for h in halves.values())) or \
                 (safer(st, sp) and all(safer(h["rule"], h["spy"]) for h in halves.values()))
            res["finalists"][name] = {"rule": st, "spy": sp, "halves": halves, "worth_live_testing": ok,
                                      "bootstrap_sharpe_gap": vm.bootstrap_gap((r - rfm.reindex(idx)).values, (s - rfm.reindex(idx)).values)}
        else:
            combo = s + r
            cst, sst = vm.stats(combo, rfm), vm.stats(s, rfm)
            halves = {f"{a[:4]}-{z[:4]}": fx.overlay_stats(fx.window(r, a, z)) for a, z in HALVES}
            p1 = cst["10k_becomes"] > sst["10k_becomes"] and cst["sharpe"] > sst["sharpe"]
            p2 = all(h["per_year"] > 0 for h in halves.values())
            res["finalists"][name] = {"overlay": fx.overlay_stats(r), "halves": halves, "spy_plus_overlay": cst, "spy": sst,
                                      "corr_with_spy": round(float(np.corrcoef(r, s)[0, 1]), 2), "pass_1": p1, "pass_2": p2,
                                      "worth_live_testing": p1 and p2,
                                      "bootstrap_sharpe_gap": vm.bootstrap_gap((combo - rfm.reindex(idx)).values, (s - rfm.reindex(idx)).values)}
        res["finalists"][name]["years"] = {str(y): round(float(np.prod(1 + r[r.index.year == y]) - 1) * 100, 1) for y in sorted(set(r.index.year))}
    path = RESULTS_DIR / f"holdout-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "countries-data")
        status, n, detail = job_data(db)
        finish_run(db, run_id, status, n, detail)
        print(detail)
    elif cmd == "explore":
        r = job_explore(db)
        print(json.dumps({k: r[k] for k in ("funds_by_year", "spy", "ranked", "finalists_by_rule", "_path")}, indent=1))
    elif cmd == "holdout":
        print(json.dumps(job_holdout(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
