"""Daily bars for every leg of the pairs in shared/pairs.json (RSP/SPY, KO/PEP, CVX/XOM, ...).

  daily_bars_adj   Full-market (SIP) daily bars from Alpaca, adjusted for splits AND dividends
                   (adjustment=all), 2016 onward. Total-return adjusted so a ratio of two legs
                   isn't distorted by one paying bigger dividends. Today's bar is partial and
                   ~16 minutes old (the free plan's limit), refreshed on every run.

Separate from stock_bars_daily (raw prices, for lining up option strikes). The first run per
symbol loads from 2016; later runs re-read the last 10 days (adjusted history can shift
slightly when a new dividend is paid, so a full reload happens on Saturdays).

Usage: python spreads_collector.py [--full]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from options_collector import ALPACA_DATA, ET, PROJECT_DIR, alpaca, connect, finish_run, load_keys, start_run

PAIRS_PATH = Path(os.environ.get("PAIRS", PROJECT_DIR / "shared" / "pairs.json"))
HISTORY_START = "2016-01-01"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bars_adj (
    symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, vwap REAL,
    trades INTEGER, fetched_at TEXT, PRIMARY KEY (symbol, date)
);
"""


def legs() -> list[str]:
    pairs = json.loads(PAIRS_PATH.read_text())["pairs"]
    return sorted({p["long"] for p in pairs} | {p["short"] for p in pairs})


def main() -> int:
    full = "--full" in sys.argv or datetime.now(ET).weekday() == 5
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "spreads")
    keys = load_keys()
    now = datetime.now(ET)
    end = (now - timedelta(minutes=16)).isoformat()
    symbols = legs()
    have = {r[0] for r in db.execute("SELECT DISTINCT symbol FROM daily_bars_adj")}
    try:
        total = 0
        for start, group in ((HISTORY_START, [s for s in symbols if full or s not in have]),
                             ((date.today() - timedelta(days=10)).isoformat(),
                              [s for s in symbols if not full and s in have])):
            if not group:
                continue
            token = None
            while True:
                b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(group), timeframe="1Day",
                           feed="sip", adjustment="all", start=start, end=end, limit=10000, page_token=token)
                rows = [(sym, x["t"][:10], x["o"], x["h"], x["l"], x["c"], x["v"], x.get("vw"), x.get("n"),
                         now.isoformat(timespec="seconds"))
                        for sym, xs in (b.get("bars") or {}).items() for x in xs]
                db.executemany("INSERT OR REPLACE INTO daily_bars_adj VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                total += len(rows)
                token = b.get("next_page_token")
                if not token:
                    break
        db.commit()
        status, detail = "ok", f"symbols={','.join(symbols)} bars={total}{' (full reload)' if full else ''}"
    except Exception as e:
        db.rollback()
        status, total, detail = "failed", 0, str(e)
    finish_run(db, run_id, status, total, detail)
    print(f"[{now:%Y-%m-%d %H:%M:%S}] spreads run {run_id}: {status} {detail[:300]}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
