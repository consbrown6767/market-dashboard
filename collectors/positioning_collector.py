"""Market-wide positioning: S&P 500 dealer gamma (SqueezeMetrics) and futures positioning (CFTC).

Index-level context, not single-stock walls: useful as a regime filter ("is market gamma low?")
and a dashboard backdrop. Both sources are free and carry their full history, so every run
re-reads recent history and upserts; the first run loads everything.

  market_gamma   SqueezeMetrics daily S&P 500 GEX and DIX, May 2011 onward. A row for date D
                 is computed after D's close, so a backtest trading on day D should use D-1.
  cftc_tff       CFTC Traders in Financial Futures, weekly. Positions are as of Tuesday
                 (report_date) and published the following Friday afternoon (available_date);
                 a backtest must not use a row before its available_date.
  cftc_net       View: net long positions and % of open interest per trader group.

Usage: python positioning_collector.py      (run by launchd as job "positioning", see install.sh)
"""

from __future__ import annotations

import csv
import io
import json
import sys
import traceback
import urllib.parse
from datetime import date, datetime, timedelta

from options_collector import ET, connect, finish_run, http_get, start_run

SQUEEZE_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
CFTC_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CFTC_START = "2010-06-15"  # consolidated index contracts begin here
# Codes are stable; CFTC has renamed some markets over the years.
CFTC_CONTRACTS = {
    "13874+": "S&P 500 (consolidated)",
    "20974+": "Nasdaq-100 (consolidated)",
    "239742": "Russell 2000 E-mini",
    "12460+": "Dow (consolidated)",
    "1170E1": "VIX futures",
    "042601": "2-year Treasury note",
    "044601": "5-year Treasury note",
    "043602": "10-year Treasury note",
    "020601": "Treasury bond",
}
GROUPS = {  # our column prefix -> CFTC field stems (long, short, spread)
    "dealer": ("dealer_positions_long_all", "dealer_positions_short_all", "dealer_positions_spread_all"),
    "asset_mgr": ("asset_mgr_positions_long", "asset_mgr_positions_short", "asset_mgr_positions_spread"),
    "lev_money": ("lev_money_positions_long", "lev_money_positions_short", "lev_money_positions_spread"),
    "other": ("other_rept_positions_long", "other_rept_positions_short", "other_rept_positions_spread"),
    "nonrept": ("nonrept_positions_long_all", "nonrept_positions_short_all", None),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_gamma (
    date TEXT PRIMARY KEY, spx REAL, dix REAL, gex REAL, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS cftc_tff (
    report_date TEXT, available_date TEXT, code TEXT, contract TEXT, market_name TEXT,
    open_interest REAL,
    dealer_long REAL, dealer_short REAL, dealer_spread REAL,
    asset_mgr_long REAL, asset_mgr_short REAL, asset_mgr_spread REAL,
    lev_money_long REAL, lev_money_short REAL, lev_money_spread REAL,
    other_long REAL, other_short REAL, other_spread REAL,
    nonrept_long REAL, nonrept_short REAL,
    fetched_at TEXT,
    PRIMARY KEY (report_date, code)
);
DROP VIEW IF EXISTS cftc_net;
CREATE VIEW cftc_net AS
SELECT report_date, available_date, code, contract, open_interest,
       dealer_long - dealer_short AS dealer_net,
       asset_mgr_long - asset_mgr_short AS asset_mgr_net,
       lev_money_long - lev_money_short AS lev_money_net,
       other_long - other_short AS other_net,
       nonrept_long - nonrept_short AS nonrept_net,
       ROUND(100.0 * (dealer_long - dealer_short) / open_interest, 1) AS dealer_net_pct_oi,
       ROUND(100.0 * (asset_mgr_long - asset_mgr_short) / open_interest, 1) AS asset_mgr_net_pct_oi,
       ROUND(100.0 * (lev_money_long - lev_money_short) / open_interest, 1) AS lev_money_net_pct_oi
FROM cftc_tff;
"""


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_squeeze(db, now: str) -> int:
    text = http_get(SQUEEZE_URL).decode("utf-8")
    rows = [(r["date"], num(r["price"]), num(r["dix"]), num(r["gex"]), now)
            for r in csv.DictReader(io.StringIO(text)) if r.get("date")]
    if len(rows) < 1000:
        raise RuntimeError(f"only {len(rows)} rows; format may have changed")
    db.executemany("INSERT OR REPLACE INTO market_gamma VALUES (?,?,?,?,?)", rows)
    return len(rows)


def load_cftc(db, now: str) -> int:
    last = db.execute("SELECT MAX(report_date) FROM cftc_tff").fetchone()[0]
    since = (date.fromisoformat(last) - timedelta(weeks=8)).isoformat() if last else CFTC_START
    codes = ",".join(f"'{c}'" for c in CFTC_CONTRACTS)
    total, offset = 0, 0
    while True:
        q = {"$where": f"cftc_contract_market_code in ({codes}) AND report_date_as_yyyy_mm_dd >= '{since}'",
             "$order": "report_date_as_yyyy_mm_dd, cftc_contract_market_code", "$limit": 5000, "$offset": offset}
        batch = json.loads(http_get(f"{CFTC_URL}?{urllib.parse.urlencode(q)}"))
        rows = []
        for r in batch:
            rd = r["report_date_as_yyyy_mm_dd"][:10]
            vals = []
            for long_f, short_f, spread_f in GROUPS.values():
                vals += [num(r.get(long_f)), num(r.get(short_f))] + ([num(r.get(spread_f))] if spread_f else [])
            rows.append((rd, (date.fromisoformat(rd) + timedelta(days=3)).isoformat(), r["cftc_contract_market_code"],
                         CFTC_CONTRACTS.get(r["cftc_contract_market_code"]), r["market_and_exchange_names"],
                         num(r.get("open_interest_all")), *vals, now))
        db.executemany(f"INSERT OR REPLACE INTO cftc_tff VALUES ({','.join('?' * 21)})", rows)
        total += len(rows)
        if len(batch) < 5000:
            return total
        offset += 5000


def main() -> int:
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "positioning")
    now = datetime.now(ET).isoformat(timespec="seconds")
    counts, failures = {}, []
    for name, loader in (("market_gamma", load_squeeze), ("cftc_tff", load_cftc)):
        try:
            counts[name] = loader(db, now)
            db.commit()
        except Exception as e:
            db.rollback()
            failures.append(f"{name}: {e} {traceback.format_exc()[-300:]}")
    detail = " ".join(f"{k}={v}" for k, v in counts.items()) + ("; " + " | ".join(failures) if failures else "")
    status = "ok" if not failures else "partial" if counts else "failed"
    finish_run(db, run_id, status, sum(counts.values()), detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] positioning run {run_id}: {status} {detail[:400]}")
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
