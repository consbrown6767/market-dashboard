"""Overnight-only investing: hold SPY (and QQQ, IWM) from each close to the next open, cash during the day.
Plan fixed before any result: docs/overnight/PLAN.md. Write-up: docs/overnight/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       Yahoo daily open/close (split-adjusted, not dividend-adjusted) into index_daily as <SYM>_RAW,
             and dividends into dividends (source yahoo; existing Alpaca rows kept)
  backtest   run the plan; results to ~/MarketData/overnight/backtest-<date>.json
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

RESULTS_DIR = Path.home() / "MarketData" / "overnight"
FUNDS = ("SPY", "QQQ", "IWM")

# ---- fixed by the plan
COST = 0.0001                # per dollar traded, each trade
COSTS_ALSO = (0.0, 0.00005, 0.0002)
POST_PUB = "2009-01"
END = "2026-10"


def job_data(db) -> tuple[str, int, str]:
    import yfinance as yf
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows, divs, notes = [], [], []
    for sym in FUNDS:
        t = yf.download(sym, start="1993-01-01", progress=False, auto_adjust=False, actions=True)
        t.columns = [c[0] for c in t.columns]
        t = t.dropna(subset=["Open", "Close"])
        rows += [(f"{sym}_RAW", d.strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]), float(r["Low"]),
                  float(r["Close"]), "yahoo-raw", now) for d, r in t.iterrows()]
        dv = t["Dividends"][t["Dividends"] > 0]
        divs += [(sym, d.strftime("%Y-%m-%d"), float(v), "yahoo", now) for d, v in dv.items()]
        notes.append(f"{sym} {t.index[0]:%Y-%m-%d}..{t.index[-1]:%Y-%m-%d} dividends={len(dv)}")
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT OR IGNORE INTO dividends VALUES (?,?,?,?,?)", divs)
    db.commit()
    return "ok", len(rows), "; ".join(notes)


def pieces(db, sym: str) -> pd.DataFrame:
    px = pd.read_sql("SELECT date, open, close FROM index_daily WHERE symbol=? ORDER BY date", db,
                     params=(f"{sym}_RAW",), index_col="date")
    px.index = pd.to_datetime(px.index)
    dv = pd.read_sql("SELECT ex_date, amount FROM dividends WHERE symbol=?", db, params=(sym,), index_col="ex_date")["amount"]
    dv.index = pd.to_datetime(dv.index)
    div = dv.groupby(level=0).sum().reindex(px.index).fillna(0.0)
    prev = px["close"].shift(1)
    out = pd.DataFrame({"night": (px["open"] + div) / prev - 1, "day": px["close"] / px["open"] - 1,
                        "hold": (px["close"] + div) / prev - 1}).dropna()
    return out


def monthly(r: pd.Series) -> pd.Series:
    m = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    return m.loc[:pd.Period(END, "M")]


def run(p: pd.DataFrame, cost: float) -> dict:
    night = (1 + p["night"]) * (1 - cost) ** 2 - 1
    day = (1 + p["day"]) * (1 - cost) ** 2 - 1
    return {"overnight": monthly(night), "daytime": monthly(day), "buy_hold": monthly(p["hold"])}


def break_even(p: pd.DataFrame, a: str) -> float:
    """Cost per trade at which overnight ends with the same money as buy and hold."""
    s = p.loc[a:]
    target = float(np.log1p(s["hold"]).sum())
    gross = float(np.log1p(s["night"]).sum())
    n = len(s)
    return round((1 - np.exp((target - gross) / (2 * n))) * 100, 4)     # percent per trade


def job_backtest(db) -> dict:
    rf = tn.rf_monthly(db)
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/overnight/PLAN.md", "funds": {}}
    for sym in FUNDS:
        p = pieces(db, sym)
        f = {"from": str(p.index[0].date()), "to": END}
        main = run(p, COST)
        for name, a in (("whole", str(p.index[0])[:7]), ("after_2009", POST_PUB)):
            f[name] = {k: vm.stats(v.loc[pd.Period(a, "M"):], rf) for k, v in main.items()}
        f["other_costs"] = {f"{c * 100:.3f}%": {"whole": vm.stats(run(p, c)["overnight"], rf),
                                                "after_2009": vm.stats(run(p, c)["overnight"].loc[pd.Period(POST_PUB, "M"):], rf)}
                            for c in COSTS_ALSO}
        f["break_even_cost_pct_per_trade"] = {"whole": break_even(p, str(p.index[0].date())), "after_2009": break_even(p, "2009-01-01")}
        f["gross_share_of_gain_overnight"] = round(float(np.log1p(p["night"]).sum() / np.log1p(p["hold"]).sum()), 2)
        yrs = {}
        for y in sorted(set(p.index.year)):
            q = p[p.index.year == y]
            yrs[str(y)] = {"overnight_no_cost": round(float(np.prod(1 + q["night"]) - 1) * 100, 1),
                           "daytime_no_cost": round(float(np.prod(1 + q["day"]) - 1) * 100, 1),
                           "buy_hold": round(float(np.prod(1 + q["hold"]) - 1) * 100, 1)}
        f["years"] = yrs
        res["funds"][sym] = f
    s = res["funds"]["SPY"]

    def wins(block, sym=None):
        b = (res["funds"][sym] if sym else s)[block]
        return b["overnight"]["10k_becomes"] > b["buy_hold"]["10k_becomes"]

    res["verdict"] = {
        "1_spy_whole_money_and_sharpe": wins("whole") and s["whole"]["overnight"]["sharpe"] > s["whole"]["buy_hold"]["sharpe"],
        "2_spy_after_2009_money_and_sharpe": wins("after_2009") and s["after_2009"]["overnight"]["sharpe"] > s["after_2009"]["buy_hold"]["sharpe"],
        "3_qqq_iwm_after_2009_money": wins("after_2009", "QQQ") and wins("after_2009", "IWM"),
    }
    res["verdict"]["beats_buy_hold"] = all(res["verdict"].values())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "data":
        run_id = start_run(db, "overnight-data")
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
