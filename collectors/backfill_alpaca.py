"""One-off backfill: daily option bars from Alpaca, Feb 2024 to today, into ~/MarketData/options.db.

Scope (keeps it to the part of the chain where walls and setups form):
  - expirations: the last expiration of each week (the Friday weekly/monthly, or Thursday when
    Friday is a holiday); SPY/QQQ daily expirations are skipped
  - window: the 45 calendar days before each expiration (and on/after 2024-02-01)
  - strikes: within 10% of the stock's range during that window (raw, unadjusted prices, so
    pre-split strikes such as NVDA's $880 in early 2024 line up)
  - standard contracts only (root == underlying; split-adjusted roots like 1NVDA skipped)

What the bars are: open/high/low/close/volume/VWAP/trade count of actual trades that day. A
contract that didn't trade on a day has no bar. No bid/ask, IV, greeks or open interest: Alpaca
doesn't provide those historically. Prices come from the free "indicative" feed.

Resumable: finished (symbol, expiration) pairs are recorded in backfill_progress, so re-running
continues where it stopped.

Usage: python backfill_alpaca.py [SYMBOL ...]        (default: whole watchlist)
       python backfill_alpaca.py --dry-run [SYMBOL ...]
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta

from options_collector import (ALPACA_DATA, ALPACA_TRADE, ET, alpaca, connect, finish_run, load_keys,
                               num, parse_option_symbol, start_run, watchlist)

START = date(2024, 2, 1)
WINDOW_DAYS = 45
STRIKE_MARGIN = 0.10
BATCH = 100  # option symbols per bars request

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_bars_daily (
    symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, vwap REAL,
    trades INTEGER, PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS option_bars_daily (
    symbol TEXT, date TEXT, underlying TEXT, expiration TEXT, type TEXT, strike REAL,
    open REAL, high REAL, low REAL, close REAL, volume REAL, vwap REAL, trades INTEGER,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS option_bars_daily_lookup ON option_bars_daily (underlying, date, expiration, strike);
CREATE TABLE IF NOT EXISTS backfill_progress (
    underlying TEXT, expiration TEXT, contracts INTEGER, bars INTEGER, finished_at TEXT,
    PRIMARY KEY (underlying, expiration)
);
"""

_last_call = 0.0


def call(base, path, keys, **params):
    """Alpaca's free plan allows 200 requests a minute; stay a little under it."""
    global _last_call
    wait = 0.32 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()
    return alpaca(base, path, keys, **params)


def stock_bars(db, keys, sym: str) -> dict[str, tuple[float, float]]:
    """Raw daily bars for the underlying; returns {date: (low, high)}."""
    rows, token = [], None
    while True:
        b = call(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=sym, timeframe="1Day", feed="sip",
                 adjustment="raw", start=(START - timedelta(days=WINDOW_DAYS)).isoformat(),
                 end=(datetime.now(ET) - timedelta(minutes=16)).isoformat(), limit=10000, page_token=token)
        rows += [(sym, x["t"][:10], x["o"], x["h"], x["l"], x["c"], x["v"], x.get("vw"), x.get("n"))
                 for x in (b.get("bars") or {}).get(sym, [])]
        token = b.get("next_page_token")
        if not token:
            break
    db.executemany("INSERT OR REPLACE INTO stock_bars_daily VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return {r[1]: (r[4], r[3]) for r in rows}


def contracts(keys, sym: str) -> dict[str, list[dict]]:
    """All standard contracts expiring from START to today+WINDOW, grouped by expiration."""
    out: dict[str, list[dict]] = {}
    last = (date.today() + timedelta(days=WINDOW_DAYS)).isoformat()
    for status in ("inactive", "active"):
        token = None
        while True:
            b = call(ALPACA_TRADE, "/v2/options/contracts", keys, underlying_symbols=sym, status=status,
                     expiration_date_gte=START.isoformat(), expiration_date_lte=last, limit=10000, page_token=token)
            for c in b.get("option_contracts", []):
                # standard root only; a class share like BRK.B trades options under BRKB
                if c.get("root_symbol") in (sym, sym.replace(".", "")):
                    out.setdefault(c["expiration_date"], []).append(c)
            token = b.get("next_page_token")
            if not token:
                break
    return out


def week_end_expirations(exps) -> list[str]:
    last_of_week: dict[tuple, str] = {}
    for e in exps:
        y, w, _ = date.fromisoformat(e).isocalendar()
        last_of_week[(y, w)] = max(last_of_week.get((y, w), e), e)
    return sorted(last_of_week.values())


def backfill_symbol(db, keys, sym: str, dry_run: bool) -> tuple[int, int, int]:
    ranges = stock_bars(db, keys, sym)
    by_exp = contracts(keys, sym)
    done = {r[0] for r in db.execute("SELECT expiration FROM backfill_progress WHERE underlying=?", (sym,))}
    today = date.today()
    # The free plan rejects option bar requests reaching into the last 15 minutes ("OPRA agreement
    # is not signed"), so every request ends at least 16 minutes ago.
    latest = datetime.now(ET) - timedelta(minutes=16)
    n_exp = n_contracts = n_bars = 0

    for exp in week_end_expirations(by_exp):
        exp_d = date.fromisoformat(exp)
        start = max(START, exp_d - timedelta(days=WINDOW_DAYS))
        end = min(exp_d, today)
        if exp in done or start > end:
            continue
        window = [v for d, v in ranges.items() if start.isoformat() <= d <= end.isoformat()]
        if not window:
            continue
        lo = min(v[0] for v in window) * (1 - STRIKE_MARGIN)
        hi = max(v[1] for v in window) * (1 + STRIKE_MARGIN)
        picked = [c["symbol"] for c in by_exp[exp] if lo <= float(c["strike_price"]) <= hi]
        n_exp += 1
        n_contracts += len(picked)
        if dry_run:
            continue

        req_end = min(datetime.combine(end + timedelta(days=1), datetime.min.time(), ET), latest).isoformat()
        bars = 0
        try:
            for i in range(0, len(picked), BATCH):
                token = None
                while True:
                    b = call(ALPACA_DATA, "/v1beta1/options/bars", keys, symbols=",".join(picked[i:i + BATCH]),
                             timeframe="1Day", start=start.isoformat(), end=req_end, limit=10000, page_token=token)
                    rows = []
                    for osym, xs in (b.get("bars") or {}).items():
                        _, e, typ, strike = parse_option_symbol(osym)
                        rows += [(osym, x["t"][:10], sym, e, typ, strike, num(x.get("o")), num(x.get("h")),
                                  num(x.get("l")), num(x.get("c")), num(x.get("v")), num(x.get("vw")), x.get("n"))
                                 for x in xs]
                    db.executemany("INSERT OR REPLACE INTO option_bars_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                    bars += len(rows)
                    token = b.get("next_page_token")
                    if not token:
                        break
        except Exception as e:  # not marked done, so the next run retries this expiration
            db.commit()
            print(f"  {sym} {exp}: {e}", flush=True)
            continue
        # An expiration still in the future gets re-pulled next run, so its newest days fill in.
        if exp_d < today:
            db.execute("INSERT OR REPLACE INTO backfill_progress VALUES (?,?,?,?,?)",
                       (sym, exp, len(picked), bars, datetime.now(ET).isoformat(timespec="seconds")))
        db.commit()
        n_bars += bars
    return n_exp, n_contracts, n_bars


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    symbols = [a.upper() for a in args if not a.startswith("--")] or watchlist()["symbols"]
    db = connect()
    db.executescript(SCHEMA)
    keys = load_keys()
    run_id = None if dry_run else start_run(db, "backfill")
    totals, failures = [0, 0, 0], []
    for sym in symbols:
        t0 = time.time()
        try:
            res = backfill_symbol(db, keys, sym, dry_run)
            totals = [a + b for a, b in zip(totals, res)]
            print(f"{sym:5} expirations {res[0]:4}  contracts {res[1]:7,}  bars {res[2]:9,}  ({time.time() - t0:.0f}s)", flush=True)
        except Exception as e:
            failures.append(f"{sym}: {e}")
            print(f"{sym:5} FAILED: {e}", flush=True)
    print(f"TOTAL expirations {totals[0]:,}  contracts {totals[1]:,}  bars {totals[2]:,}", flush=True)
    if run_id:
        detail = f"expirations={totals[0]} contracts={totals[1]} bars={totals[2]}" + (
            "; " + " | ".join(failures) if failures else "")
        finish_run(db, run_id, "ok" if not failures else "partial", totals[2], detail)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
