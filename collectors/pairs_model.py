"""Pairs trading model (Gatev, Goetzmann & Rouwenhorst 2006, distance method) on S&P 500 members at
the time. Plan fixed before any result: docs/pairs/PLAN.md. Write-up: docs/pairs/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  members    S&P 500 members and sectors at each year-end 2014-2025, from Wikipedia's edit history,
             into shared/sp500_history.json
  prices     Alpaca split- and dividend-adjusted daily bars (2016 on) for every past member, into daily_bars_adj
  backtest   run the plan; results to ~/MarketData/pairs/backtest-<date>.json
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ALPACA_DATA, ET, PROJECT_DIR, alpaca, connect, finish_run, http_get, load_keys, start_run
from classic_strategies import nw_t
import vol_managed as vm

HISTORY = PROJECT_DIR / "shared" / "sp500_history.json"
RESULTS_DIR = Path.home() / "MarketData" / "pairs"
PRICE_START = "2016-01-01"
SECTORS = ["Information Technology", "Health Care", "Financials", "Consumer Discretionary", "Consumer Staples",
           "Industrials", "Energy", "Utilities", "Materials", "Real Estate", "Communication Services",
           "Telecommunication Services", "Telecommunications Services"]

# ---- fixed by the plan
FORM_DAYS, TRADE_DAYS = 252, 126
N_PAIRS = 20
OPEN_SD = 2.0
COST = 0.0005            # per dollar traded, each leg
BORROW = 0.005           # a year on the short leg while open
FIRST_START, LAST_MONTH = "2017-01", "2026-10"


# ---------------------------------------------------------------- members

def _clean(cell: str) -> str:
    cell = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", cell)
    return re.sub(r"<[^>]+>|'''?", "", cell).strip()


def job_members() -> dict:
    out = {"source": "Wikipedia 'List of S&P 500 companies', last revision before each Jan 1 (edit history)",
           "years": {}}
    for y in range(2015, 2027):
        q = urllib.parse.urlencode({"action": "query", "prop": "revisions", "titles": "List of S&P 500 companies",
                                    "rvlimit": 1, "rvstart": f"{y}-01-01T00:00:00Z", "rvdir": "older",
                                    "rvprop": "ids|timestamp|content", "rvslots": "main", "format": "json",
                                    "formatversion": 2})
        time.sleep(5)      # Wikipedia's API asks for a gentle pace
        rev = json.loads(http_get("https://en.wikipedia.org/w/api.php?" + q))["query"]["pages"][0]["revisions"][0]
        text = rev["slots"]["main"]["content"]
        start = text.index("{|")
        table = text[start:text.index("|}", start)]
        members = {}
        for row in table.split("|-")[2:]:
            m = (re.search(r"\{\{\s*(?:NyseSymbol|NasdaqSymbol|nyse|nasdaq|NYSE|NASDAQ|NYSE link|Nasdaq symbol|NYSE symbol)"
                           r"\s*\|\s*([A-Za-z.\-]+)", row)
                 or re.search(r"\[https?://\S+\s+([A-Z][A-Z.\-]*)\]", row))
            if not m:
                continue
            cells = [_clean(c) for c in re.split(r"\|\||\n\|", row)]
            sector = next((c for c in cells if c in SECTORS), None)
            if sector and sector.startswith("Telecommunication"):
                sector = "Communication Services"      # GICS renamed it in 2018
            members[m.group(1).upper().replace("-", ".")] = sector
        out["years"][str(y)] = {"revision": rev["revid"], "as_of": rev["timestamp"], "members": members}
    HISTORY.write_text(json.dumps(out, indent=1, sort_keys=True))
    return {y: len(v["members"]) for y, v in out["years"].items()}


def history() -> dict:
    return json.loads(HISTORY.read_text())["years"]


def all_members() -> list[str]:
    return sorted(set().union(*[set(v["members"]) for v in history().values()]))


# ---------------------------------------------------------------- prices

def job_prices(db) -> tuple[str, int, str]:
    keys = load_keys()
    now = datetime.now(ET)
    end = (now - timedelta(minutes=16)).isoformat()
    symbols = all_members()
    total, got = 0, set()
    for i in range(0, len(symbols), 50):
        group = symbols[i:i + 50]
        token = None
        while True:
            try:
                b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(group), timeframe="1Day", feed="sip",
                           adjustment="all", start=PRICE_START, end=end, limit=10000, page_token=token)
            except RuntimeError as ex:
                bad = re.search(r"invalid symbol: ([A-Za-z.\-]+)", str(ex))
                if not bad or bad.group(1) not in group:
                    raise
                group = [g for g in group if g != bad.group(1)]
                token = None
                continue
            rows = [(sym, x["t"][:10], x["o"], x["h"], x["l"], x["c"], x["v"], x.get("vw"), x.get("n"),
                     now.isoformat(timespec="seconds")) for sym, xs in (b.get("bars") or {}).items() for x in xs]
            got |= {r[0] for r in rows}
            db.executemany("INSERT OR REPLACE INTO daily_bars_adj VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            total += len(rows)
            token = b.get("next_page_token")
            if not token:
                break
        db.commit()
    missing = sorted(set(symbols) - got)
    return "ok", total, f"symbols={len(symbols)} with_data={len(got)} bars={total} missing={len(missing)}: {' '.join(missing)}"


# ---------------------------------------------------------------- backtest

def load_prices(db) -> pd.DataFrame:
    px = pd.read_sql("SELECT symbol, date, close FROM daily_bars_adj WHERE date >= ?", db, params=(PRICE_START,))
    px = px.pivot(index="date", columns="symbol", values="close")
    px.index = pd.to_datetime(px.index)
    return px.sort_index()


def choose_pairs(form: pd.DataFrame, sectors: dict, n: int, same_sector: bool) -> list[tuple]:
    norm = form / form.iloc[0]
    cands = []
    groups = {}
    for s in norm.columns:
        sec = sectors.get(s)
        if sec is None:
            continue
        groups.setdefault(sec if same_sector else "all", []).append(s)
    for g, syms in groups.items():
        if len(syms) < 2:
            continue
        m = norm[syms].values
        sq = (m ** 2).sum(axis=0)
        ssd = sq[:, None] + sq[None, :] - 2 * m.T @ m
        iu = np.triu_indices(len(syms), 1)
        vals = ssd[iu]
        top = np.argsort(vals)[:n]
        for t in top:
            a, b = syms[iu[0][t]], syms[iu[1][t]]
            cands.append((float(vals[t]), a, b))
    cands.sort()
    out = []
    for v, a, b in cands[:n]:
        sd = float((norm[a] - norm[b]).std())
        out.append((a, b, sd))
    return out


def trade_pair(p_a: np.ndarray, p_b: np.ndarray, sd: float, cost: float, borrow: float) -> tuple[np.ndarray, list]:
    """Daily P&L (in $, $1 a side) of one pair over the trading period. p_* are prices from the last
    formation day (index 0) through the trading days; NaN after a delisting."""
    n = len(p_a)
    a = pd.Series(p_a).ffill().values
    b = pd.Series(p_b).ffill().values
    # A stock "ends" at its first missing day: anything after a gap may be a different security
    # that later reused the ticker.
    def first_gap(p):
        gaps = np.where(np.isnan(p))[0]
        return (gaps[0] - 1) if len(gaps) else n - 1
    end = min(first_gap(p_a), first_gap(p_b))
    na, nb = a / a[0], b / b[0]
    pnl = np.zeros(n)
    trades = []
    pos = 0            # +1: long a, short b; -1: short a, long b
    pending = None     # ("open", side) or ("close",) to act at the next day's close
    ea = eb = None
    for d in range(1, end + 1):
        if pos != 0:   # mark to market: long leg value minus short leg value
            la, lb = a[d] / ea, b[d] / eb
            pa_, pb_ = a[d - 1] / ea, b[d - 1] / eb
            pnl[d] += pos * ((la - pa_) - (lb - pb_))
            pnl[d] -= borrow / 252 * (lb if pos == 1 else la)
        if pending is not None:
            if pending[0] == "open" and pos == 0:
                pos = pending[1]
                ea, eb = a[d], b[d]
                pnl[d] -= 2 * cost
                trades.append({"open": d, "side": pos})
            elif pending[0] == "close" and pos != 0:
                la, lb = a[d] / ea, b[d] / eb
                pnl[d] -= cost * (la + lb)
                trades[-1]["close"], trades[-1]["converged"] = d, True
                pos = 0
            pending = None
        spread = na[d] - nb[d]
        if pos == 0 and abs(spread) > OPEN_SD * sd:
            pending = ("open", -1 if spread > 0 else 1)     # a ran ahead: short a, long b
        elif pos != 0 and (spread * -pos) <= 0:              # crossed back
            pending = ("close",)
    if pos != 0:       # last day (or delisting): close
        la, lb = a[end] / ea, b[end] / eb
        pnl[end] -= cost * (la + lb)
        trades[-1]["close"], trades[-1]["converged"] = end, False
    return pnl, trades


def portfolio(px: pd.DataFrame, start: pd.Timestamp, members: dict, n_pairs: int, same_sector: bool,
              cost: float, borrow: float) -> tuple[pd.Series, dict]:
    days = px.index
    i0 = days.searchsorted(start)
    if i0 < FORM_DAYS:
        return pd.Series(dtype=float), {}
    form = px.iloc[i0 - FORM_DAYS:i0]
    cols = [s for s in members if s in px.columns and form[s].notna().all()]
    form = form[cols]
    pairs = choose_pairs(form, {s: members[s] for s in cols}, n_pairs, same_sector)
    span = px.iloc[i0 - 1:i0 + TRADE_DAYS]     # last formation day + trading days
    total = np.zeros(len(span))
    info = {"pairs": len(pairs), "universe": len(cols), "trades": 0, "converged": 0}
    for a, b, sd in pairs:
        pnl, tr = trade_pair(span[a].values, span[b].values, sd, cost, borrow)
        total += pnl
        info["trades"] += len(tr)
        info["converged"] += sum(t.get("converged", False) for t in tr)
    daily = pd.Series(total[1:] / n_pairs, index=span.index[1:])
    return daily, info


def strategy(px, hist, n_pairs=N_PAIRS, same_sector=True, cost=COST, borrow=BORROW) -> tuple[pd.Series, dict]:
    months = pd.period_range(FIRST_START, LAST_MONTH, freq="M")
    by_month: dict = {}
    agg = {"portfolios": 0, "trades": 0, "converged": 0, "universe": []}
    for m in months:
        start = m.start_time
        members = {s: sec for s, sec in hist[str(m.year)]["members"].items() if sec}
        daily, info = portfolio(px, start, members, n_pairs, same_sector, cost, borrow)
        if daily.empty:
            continue
        agg["portfolios"] += 1
        agg["trades"] += info["trades"]
        agg["converged"] += info["converged"]
        agg["universe"].append(info["universe"])
        mret = daily.groupby(daily.index.to_period("M")).sum()
        for mm, v in mret.items():
            if mm <= pd.Period(LAST_MONTH, "M"):
                by_month.setdefault(mm, []).append(v)
    ex = pd.Series({k: float(np.mean(v)) for k, v in sorted(by_month.items())})
    agg["avg_universe"] = round(float(np.mean(agg.pop("universe"))), 1)
    agg["share_converged"] = round(agg["converged"] / max(agg["trades"], 1), 3)
    return ex, agg


def monthly_rf(db) -> pd.Series:
    mo = vm.monthly(vm.load(db, "us"))["rf"]
    full = pd.period_range(mo.index[0], LAST_MONTH, freq="M")
    return mo.reindex(full).ffill()


def job_backtest(db) -> dict:
    px = load_prices(db)
    hist = history()
    rf = monthly_rf(db)
    spy_px = px["SPY"]
    spy = spy_px.groupby(spy_px.index.to_period("M")).last().pct_change()
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/pairs/PLAN.md"}
    members = all_members()
    res["coverage"] = {"past_members": len(members), "with_prices": int(sum(s in px.columns for s in members)),
                       "missing": sorted(s for s in members if s not in px.columns)}

    def score(ex: pd.Series) -> dict:
        r = rf.reindex(ex.index) + ex
        s = spy.reindex(ex.index)
        yrs = {str(y): round(float(np.prod(1 + g) - np.prod(1 + rf.reindex(g.index))) * 100, 2)
               for y, g in r.groupby(r.index.year)}
        beta = float(np.cov(ex.values, (s - rf.reindex(s.index)).values)[0, 1] / np.var((s - rf.reindex(s.index)).values, ddof=1))
        return {"strategy": vm.stats(r, rf), "spy": vm.stats(s, rf), "excess_per_year": round(float(ex.mean()) * 1200, 2),
                "t_excess": round(nw_t(ex.values), 2), "beta_to_spy": round(beta, 3),
                "years_above_tbill": f"{sum(v > 0 for v in yrs.values())} of {len(yrs)}", "excess_by_year": yrs}

    ex, agg = strategy(px, hist)
    res["plan_version"] = score(ex) | {"activity": agg}
    v = res["plan_version"]
    res["verdict"] = {"1_makes_money_t_at_least_2": v["t_excess"] >= 2 and v["excess_per_year"] > 0,
                      "2_sharpe_above_spy": v["strategy"]["sharpe"] > v["spy"]["sharpe"],
                      "3_years_6_of_10": int(v["years_above_tbill"].split(" of ")[0]) >= 6}
    res["verdict"]["passes"] = all(res["verdict"].values())
    variants = {"no costs": dict(cost=0, borrow=0), "any sector (Gatev original)": dict(same_sector=False),
                "10 pairs": dict(n_pairs=10), "50 pairs": dict(n_pairs=50)}
    res["variants"] = {}
    for name, kw in variants.items():
        e2, a2 = strategy(px, hist, **kw)
        sc = score(e2)
        res["variants"][name] = {k: sc[k] for k in ("excess_per_year", "t_excess", "years_above_tbill")} | {
            "sharpe": sc["strategy"]["sharpe"], "share_converged": a2["share_converged"]}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "members":
        print(job_members())
        return 0
    db = connect()
    if cmd == "prices":
        run = start_run(db, "pairs-prices")
        status, n, detail = job_prices(db)
        finish_run(db, run, status, n, detail)
        print(detail)
    elif cmd == "backtest":
        print(json.dumps(job_backtest(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
