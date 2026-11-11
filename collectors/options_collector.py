"""Options data collector: builds a forward history of open interest and option prices.

Best free source per data type (tested 2026-10-26, see README):
  open interest   OCC (official; Yahoo's numbers are identical, Alpaca's were 4 days stale)
  option prices   Alpaca indicative feed (near live, with IV and greeks; Yahoo's are ~15 min old)
  stock volume    Yahoo (live, all exchanges, regular hours); Alpaca SIP (15+ min old) as backup
  stock price     Alpaca IEX (live)

Jobs (run by launchd, see install.sh):
  daily     OCC open interest at every strike, falling back to Yahoo for any symbol OCC fails.
            Weekday mornings; open interest only changes once a day, overnight.
  snapshot  Alpaca option chain prices, IV and greeks, plus underlying prices and volume.
            Several times per trading day.
  bars      Official full-market daily bars (raw) for the watchlist into stock_bars_daily. Weekday evenings.
  backup    Compressed copy of everything that can't be re-downloaded, into the project's iCloud folder.
  status    Print recent runs and row counts.

Everything goes into ~/MarketData/options.db (SQLite, outside iCloud). Every run, including
skipped and failed ones, is recorded in the `runs` table so gaps are visible.
Research only: nothing here places orders.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # python.org Python on macOS ships without CA certificates; use the system keychain
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ET = ZoneInfo("America/New_York")
DATA_DIR = Path.home() / "MarketData"
DB_PATH = DATA_DIR / "options.db"
KEYS_PATH = Path.home() / ".config" / "market-dashboard" / "alpaca.env"
PROJECT_DIR = Path.home() / "Code" / "market-dashboard"  # the code (a git repo); moved out of iCloud on 2026-11-10
WATCHLIST_PATH = Path(os.environ.get("WATCHLIST", PROJECT_DIR / "shared" / "watchlist.json"))
# Database backups stay in iCloud (off this Mac); the code's off-Mac copy is GitHub.
BACKUP_DIR = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Vibe Coding/Market Dashboard/backups"

OCC_SERIES_URL = "https://marketdata.theocc.com/series-search"
ALPACA_TRADE = "https://paper-api.alpaca.markets"
ALPACA_DATA = "https://data.alpaca.markets"
OPTION_SYMBOL = re.compile(r"^(.+?)(\d{6})([CP])(\d{8})$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, job TEXT, started_at TEXT, finished_at TEXT,
    status TEXT, rows INTEGER, detail TEXT
);
-- OCC Series Search. OCC doesn't print an as-of date; values reflect the latest settlement
-- (normally the previous trading day's close). source is 'occ', or 'yahoo' when OCC failed
-- for that symbol (Yahoo republishes OCC's numbers; no position_limit).
CREATE TABLE IF NOT EXISTS occ_oi (
    fetch_date TEXT, product TEXT, underlying TEXT, expiration TEXT, strike REAL,
    call_oi INTEGER, put_oi INTEGER, position_limit INTEGER, run_id INTEGER, source TEXT,
    PRIMARY KEY (fetch_date, product, expiration, strike)
);
-- Collected on 2026-10-26 only: Alpaca's open interest turned out to lag OCC by days.
CREATE TABLE IF NOT EXISTS alpaca_contracts (
    fetch_date TEXT, symbol TEXT, underlying TEXT, root TEXT, expiration TEXT, type TEXT,
    strike REAL, multiplier REAL, oi INTEGER, oi_date TEXT, close_price REAL,
    close_price_date TEXT, run_id INTEGER,
    PRIMARY KEY (fetch_date, symbol)
);
-- price/bid/ask/day_* come from IEX (one exchange, real time): fine for price, but day_volume
-- is only a few percent of the market. For volume rules use yahoo_day_volume (all exchanges,
-- live, regular hours only, as of yahoo_asof), or sip_day_volume as backup (all exchanges,
-- 15+ minutes delayed, includes pre-market, as of sip_asof).
CREATE TABLE IF NOT EXISTS underlying_snap (
    run_id INTEGER, ts TEXT, symbol TEXT, price REAL, bid REAL, ask REAL,
    day_open REAL, day_high REAL, day_low REAL, day_close REAL, day_volume REAL,
    prev_close REAL, trade_ts TEXT, sip_day_volume REAL, sip_asof TEXT,
    yahoo_day_volume REAL, yahoo_asof TEXT,
    PRIMARY KEY (run_id, symbol)
);
CREATE TABLE IF NOT EXISTS option_snap (
    run_id INTEGER, ts TEXT, symbol TEXT, underlying TEXT, root TEXT, expiration TEXT,
    type TEXT, strike REAL, bid REAL, ask REAL, bid_size REAL, ask_size REAL, quote_ts TEXT,
    last REAL, last_size REAL, last_ts TEXT, day_volume REAL, day_close REAL,
    iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL,
    PRIMARY KEY (run_id, symbol)
);
-- Stock splits from Alpaca's corporate actions feed (refreshed by the daily job). A split with
-- old_rate 1 and new_rate 3 means one share became three on ex_date. Raw price tables are never
-- changed; stock_bars_split_adj applies these.
CREATE TABLE IF NOT EXISTS stock_splits (
    symbol TEXT, ex_date TEXT, old_rate REAL, new_rate REAL, source TEXT, fetched_at TEXT,
    PRIMARY KEY (symbol, ex_date)
);
CREATE INDEX IF NOT EXISTS option_snap_lookup ON option_snap (underlying, expiration, strike);
CREATE INDEX IF NOT EXISTS occ_oi_lookup ON occ_oi (underlying, fetch_date);
"""

# The official layer. Dashboards, scoring and backtests read ONLY these views: one value per
# field, chosen by a fixed rule. A backup source fills in only when the primary is missing
# (never averaged, never chosen because it "looks better") and is flagged when used.
# To change which source is official, change it here and everything downstream follows.
VIEWS = """
DROP VIEW IF EXISTS stock_snapshots;
CREATE VIEW stock_snapshots AS
SELECT run_id, ts, symbol, price, bid, ask, prev_close,
       COALESCE(yahoo_day_volume, sip_day_volume) AS volume,
       CASE WHEN yahoo_day_volume IS NOT NULL THEN yahoo_asof ELSE sip_asof END AS volume_asof,
       CASE WHEN yahoo_day_volume IS NOT NULL THEN 'yahoo'
            WHEN sip_day_volume IS NOT NULL THEN 'alpaca_sip' END AS volume_source,
       (yahoo_day_volume IS NULL AND sip_day_volume IS NOT NULL) AS volume_from_backup,
       -- Health check only, never used to pick a value: after 11:00 (when pre-market volume,
       -- which only the SIP number includes, is a small share) the sources should agree within 10%.
       (yahoo_day_volume IS NOT NULL AND sip_day_volume IS NOT NULL AND substr(ts, 12, 5) >= '11:00'
        AND abs(sip_day_volume - yahoo_day_volume) > 0.10 * yahoo_day_volume) AS volume_check
FROM underlying_snap;

-- stock_bars_daily is kept raw so prices line up with the option strikes of the time. For a price
-- series across a split (returns, drawdowns, volatility), use this view: every bar before a split
-- is put in today's share terms (prices times split_factor, volume divided by it).
DROP VIEW IF EXISTS stock_bars_split_adj;
CREATE VIEW stock_bars_split_adj AS
SELECT symbol, date, open * f AS open, high * f AS high, low * f AS low, close * f AS close,
       volume / f AS volume, vwap * f AS vwap, trades, f AS split_factor
FROM (SELECT b.*, COALESCE((SELECT exp(sum(ln(s.old_rate / s.new_rate))) FROM stock_splits s
                            WHERE s.symbol = b.symbol AND s.ex_date > b.date), 1.0) AS f
      FROM stock_bars_daily b);

DROP VIEW IF EXISTS open_interest;
CREATE VIEW open_interest AS
SELECT fetch_date AS date, underlying, product, expiration, strike, call_oi, put_oi,
       COALESCE(source, 'occ') AS source, (COALESCE(source, 'occ') = 'yahoo') AS from_backup
FROM occ_oi;

DROP VIEW IF EXISTS option_quotes;
CREATE VIEW option_quotes AS
SELECT run_id, ts, symbol, underlying, root, expiration, type, strike, bid, ask,
       CASE WHEN bid > 0 AND ask > 0 THEN (bid + ask) / 2 END AS mid,
       last, day_volume AS volume, iv, delta, gamma, theta, vega, quote_ts
FROM option_snap;
"""


# ---------- plumbing

def load_keys() -> dict[str, str]:
    env = {}
    for line in KEYS_PATH.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return {"APCA-API-KEY-ID": env["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": env["APCA_API_SECRET_KEY"]}


def http_get(url: str, headers: dict | None = None, attempts: int = 4) -> bytes:
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "market-dashboard/1.0", **(headers or {})})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(5 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code} for {url.split('?')[0]}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if i < attempts - 1:
                time.sleep(5 * (i + 1))
                continue
            raise RuntimeError(f"network error for {url.split('?')[0]}: {e}") from e
    raise AssertionError("unreachable")


def alpaca(base: str, path: str, keys: dict, **params) -> dict:
    params = {k: v for k, v in params.items() if v is not None}
    return json.loads(http_get(f"{base}{path}?{urllib.parse.urlencode(params)}", keys))


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    added_later = {"underlying_snap": (("sip_day_volume", "REAL"), ("sip_asof", "TEXT"),
                                       ("yahoo_day_volume", "REAL"), ("yahoo_asof", "TEXT")),
                   "occ_oi": (("source", "TEXT"),)}
    for table, columns in added_later.items():
        existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for col, typ in columns:
            if col not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    # One transaction, so jobs that start in the same second (spreads and events both run at :05)
    # don't interleave their DROP/CREATE VIEW and crash with "view ... already exists".
    # BEGIN IMMEDIATE takes the write lock up front; the other job waits (up to the 60s timeout).
    db.executescript(f"BEGIN IMMEDIATE;\n{VIEWS}\nCOMMIT;")
    return db


def start_run(db, job: str) -> int:
    cur = db.execute("INSERT INTO runs (job, started_at, status) VALUES (?, ?, 'running')",
                     (job, datetime.now(ET).isoformat(timespec="seconds")))
    db.commit()
    return cur.lastrowid


def finish_run(db, run_id: int, status: str, rows: int = 0, detail: str = "") -> None:
    db.execute("UPDATE runs SET finished_at=?, status=?, rows=?, detail=? WHERE id=?",
               (datetime.now(ET).isoformat(timespec="seconds"), status, rows, detail[:4000], run_id))
    db.commit()


def watchlist() -> dict:
    return json.loads(WATCHLIST_PATH.read_text())


def parse_option_symbol(sym: str):
    m = OPTION_SYMBOL.match(sym)
    if not m:
        return None
    root, ymd, cp, strike = m.groups()
    exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:])).isoformat()
    return root, exp, "call" if cp == "C" else "put", int(strike) / 1000


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------- daily: OCC open interest (Yahoo fallback)

def parse_occ(text: str, underlying: str) -> list[tuple]:
    """Rows look like: NVDA  2026 10 30 220 000 C P 47889 9401 250000000.
    Product can differ from the underlying for adjusted contracts (e.g. 2NVDA after a split)."""
    rows = []
    for line in text.splitlines():
        f = line.split()
        if len(f) < 11 or not all(x.isdigit() for x in f[1:6]) or f[6:8] != ["C", "P"]:
            continue
        try:
            exp = date(int(f[1]), int(f[2]), int(f[3])).isoformat()
            strike = int(f[4]) + int(f[5]) / 1000
            rows.append((f[0], underlying, exp, strike, int(f[8]), int(f[9]), int(f[10])))
        except ValueError:
            continue
    return rows


def yahoo_oi(underlying: str) -> list[tuple]:
    """Open interest by strike from Yahoo, all expirations. Same shape as parse_occ rows."""
    import yfinance as yf
    t = yf.Ticker(underlying)
    rows = []
    for exp in t.options:
        ch = t.option_chain(exp)
        by_strike: dict[float, list[int]] = {}
        for i, df in enumerate((ch.calls, ch.puts)):
            for strike, oi in zip(df["strike"], df["openInterest"]):
                by_strike.setdefault(float(strike), [0, 0])[i] = int(oi) if oi == oi else 0  # NaN -> 0
        rows += [(underlying, underlying, exp, k, c, p, None) for k, (c, p) in sorted(by_strike.items())]
        time.sleep(0.3)
    return rows


SPLITS_START = "2016-01-01"


def refresh_splits(db) -> int:
    """Record every split with an ex-date up to today for the watchlist and anything in stock_bars_daily.
    Future ex-dates are left out on purpose: adjusting before a split happens would be wrong."""
    keys = load_keys()
    today = datetime.now(ET).date().isoformat()
    symbols = sorted(set(watchlist()["symbols"]) | {r[0] for r in db.execute("SELECT DISTINCT symbol FROM stock_bars_daily")})
    found = []
    for i in range(0, len(symbols), 50):
        token = None
        while True:
            r = alpaca(ALPACA_DATA, "/v1/corporate-actions", keys, symbols=",".join(symbols[i:i + 50]),
                       types="forward_split,reverse_split", start=SPLITS_START, end=today, limit=1000, page_token=token)
            actions = r.get("corporate_actions", {})
            found += [s for kind in ("forward_splits", "reverse_splits") for s in actions.get(kind, [])]
            token = r.get("next_page_token")
            if not token:
                break
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows = [(s["symbol"], s["ex_date"], float(s["old_rate"]), float(s["new_rate"]), "alpaca", now)
            for s in found if s.get("ex_date") and s["ex_date"] <= today and s.get("old_rate") and s.get("new_rate")]
    db.executemany("INSERT OR REPLACE INTO stock_splits VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    return len(rows)


def job_daily(db, run_id: int) -> tuple[str, int, str]:
    today = datetime.now(ET).date().isoformat()
    failures, fallbacks, total = [], [], 0
    insert = ("INSERT OR REPLACE INTO occ_oi (fetch_date, product, underlying, expiration, strike, "
              "call_oi, put_oi, position_limit, run_id, source) VALUES (?,?,?,?,?,?,?,?,?,?)")

    for sym in watchlist()["symbols"]:
        # The 09:15 retry only fills gaps: never let a later run replace OCC data with Yahoo's.
        if db.execute("SELECT 1 FROM occ_oi WHERE fetch_date=? AND underlying=? AND COALESCE(source,'occ')='occ' LIMIT 1",
                      (today, sym)).fetchone():
            continue
        try:
            text = http_get(f"{OCC_SERIES_URL}?{urllib.parse.urlencode({'symbolType': 'U', 'symbol': sym})}").decode("utf-8", "replace")
            rows, source = parse_occ(text, sym), "occ"
            if not rows:
                raise RuntimeError("no rows parsed")
        except Exception as occ_error:
            try:
                rows, source = yahoo_oi(sym), "yahoo"
                if not rows:
                    raise RuntimeError("no rows")
                fallbacks.append(f"{sym} (OCC: {occ_error})")
            except Exception as yahoo_error:
                failures.append(f"{sym}: OCC {occ_error}; Yahoo {yahoo_error}")
                continue
        # One source per symbol per day: drop an earlier Yahoo fallback before writing OCC rows.
        db.execute("DELETE FROM occ_oi WHERE fetch_date=? AND underlying=?", (today, sym))
        db.executemany(insert, [(today, *r, run_id, source) for r in rows])
        db.commit()
        total += len(rows)
        time.sleep(0.5)

    try:
        splits = refresh_splits(db)
    except Exception as e:
        splits = None
        failures.append(f"splits: {e}")

    detail = f"oi_rows={total}" + (f"; splits={splits}" if splits is not None else "")
    if fallbacks:
        detail += "; Yahoo fallback: " + " | ".join(fallbacks)
    if failures:
        detail += "; failed: " + " | ".join(failures)
    return ("ok" if not failures else "partial" if total else "failed"), total, detail


# ---------- snapshot: Alpaca chain + underlying

def job_snapshot(db, run_id: int) -> tuple[str, int, str]:
    keys = load_keys()
    clock = alpaca(ALPACA_TRADE, "/v2/clock", keys)
    if not clock.get("is_open") and os.environ.get("FORCE") != "1":
        return "skipped", 0, f"market closed (next open {clock.get('next_open')})"

    wl = watchlist()
    symbols, cfg = wl["symbols"], wl["hourly_snapshot"]
    ts = datetime.now(ET).isoformat(timespec="seconds")
    failures, total = [], 0

    snaps = alpaca(ALPACA_DATA, "/v2/stocks/snapshots", keys, symbols=",".join(symbols), feed="iex")

    # Full-market volume: the free plan only serves SIP data older than 15 minutes.
    sip_asof = datetime.now(ET) - timedelta(minutes=16)
    sip_vol = {}
    try:
        b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(symbols), timeframe="1Day", feed="sip",
                   start=(sip_asof - timedelta(days=5)).isoformat(), end=sip_asof.isoformat(), limit=1000)
        for sym, bars in (b.get("bars") or {}).items():
            if bars and bars[-1]["t"][:10] == sip_asof.date().isoformat():
                sip_vol[sym] = num(bars[-1]["v"])
    except Exception as e:
        failures.append(f"SIP volume: {e}")

    # Live full-market volume (regular hours) from Yahoo. Unofficial, so failures are tolerated.
    yahoo_vol = {}
    try:
        import yfinance as yf
        for sym in symbols:
            try:
                info = yf.Ticker(sym).info
                if info.get("regularMarketVolume") is not None:
                    yahoo_vol[sym] = (num(info["regularMarketVolume"]),
                                      datetime.fromtimestamp(info["regularMarketTime"], ET).isoformat(timespec="seconds")
                                      if info.get("regularMarketTime") else None)
            except Exception as e:
                failures.append(f"Yahoo volume {sym}: {e}")
    except ImportError as e:
        failures.append(f"Yahoo volume: {e}")

    spot = {}
    for sym, s in snaps.items():
        t, q, d, p = (s.get(k) or {} for k in ("latestTrade", "latestQuote", "dailyBar", "prevDailyBar"))
        spot[sym] = num(t.get("p")) or num(d.get("c"))
        yv, y_asof = yahoo_vol.get(sym, (None, None))
        db.execute("INSERT OR REPLACE INTO underlying_snap VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (run_id, ts, sym, spot[sym], num(q.get("bp")), num(q.get("ap")), num(d.get("o")), num(d.get("h")),
                    num(d.get("l")), num(d.get("c")), num(d.get("v")), num(p.get("c")), t.get("t"),
                    sip_vol.get(sym), sip_asof.isoformat(timespec="seconds") if sym in sip_vol else None, yv, y_asof))
    db.commit()

    max_exp = (datetime.now(ET).date() + timedelta(days=cfg["max_days_to_expiry"])).isoformat()
    pct = cfg["strike_range_pct"] / 100
    for sym in symbols:
        px = spot.get(sym)
        if not px:
            failures.append(f"{sym}: no underlying price")
            continue
        try:
            token, n = None, 0
            while True:
                b = alpaca(ALPACA_DATA, f"/v1beta1/options/snapshots/{sym}", keys, feed="indicative", limit=1000,
                           expiration_date_lte=max_exp, strike_price_gte=round(px * (1 - pct), 2),
                           strike_price_lte=round(px * (1 + pct), 2), page_token=token)
                batch = []
                for osym, s in (b.get("snapshots") or {}).items():
                    parsed = parse_option_symbol(osym)
                    if not parsed:
                        continue
                    root, exp, typ, strike = parsed
                    q, t, d, g = (s.get(k) or {} for k in ("latestQuote", "latestTrade", "dailyBar", "greeks"))
                    batch.append((run_id, ts, osym, sym, root, exp, typ, strike,
                                  num(q.get("bp")), num(q.get("ap")), num(q.get("bs")), num(q.get("as")), q.get("t"),
                                  num(t.get("p")), num(t.get("s")), t.get("t"), num(d.get("v")), num(d.get("c")),
                                  num(s.get("impliedVolatility")), num(g.get("delta")), num(g.get("gamma")),
                                  num(g.get("theta")), num(g.get("vega"))))
                db.executemany("INSERT OR REPLACE INTO option_snap VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                n += len(batch)
                token = b.get("next_page_token")
                if not token:
                    break
            db.commit()
            if not n:
                raise RuntimeError("no option snapshots returned")
            total += n
        except Exception as e:
            failures.append(f"{sym}: {e}")

    detail = f"option_rows={total}" + ("; " + " | ".join(failures) if failures else "")
    return ("ok" if not failures else "partial" if total else "failed"), total, detail


# ---------- backup / status

# Tables the nightly backup leaves out because they can be rebuilt for free by re-running
# collectors/backfill_alpaca.py (Alpaca option bars, Feb 2024 onward). backfill_progress is left out
# with them so a restored database knows the backfill still has to be redone.
# Every other table, including ones added later, is backed up: opt OUT here, never opt in.
# The news search index (news_fts and its shadow tables) is rebuilt from news_items by news_collector.py.
BACKUP_EXCLUDE = {"option_bars_daily", "backfill_progress", "strategy_bars_5m",
                  "news_fts", "news_fts_data", "news_fts_idx", "news_fts_docsize", "news_fts_config"}


# Big append-only tables are backed up one calendar month per file, split on this date column.
# A month's file is rewritten nightly while the month is open and for MONTH_GRACE_DAYS after it ends
# (to catch late rows), then never touched again, so iCloud only re-uploads the current month.
# Every other backed-up table (small, or updated in place) goes in options-core.db.gz each night.
BACKUP_MONTHLY = {"option_snap": "ts", "underlying_snap": "ts", "occ_oi": "fetch_date",
                  "alpaca_contracts": "fetch_date", "poly_snapshots": "fetched_at", "runs": "started_at",
                  # A story stops changing 36 hours after it first appears, well inside the grace days.
                  "news_items": "first_seen", "news_stories": "first_seen"}
MONTH_GRACE_DAYS = 3


def _write_backup_file(name: str, objects, where: dict) -> tuple[int, int]:
    """Export tables (schema + rows matching where[table], or all rows) and views into
    backups/<name>.db.gz in one read transaction. Returns (rows, gz bytes)."""
    tmp = DATA_DIR / f"backup-tmp-{name}.db"
    tmp.unlink(missing_ok=True)
    dest = sqlite3.connect(tmp)
    dest.execute("ATTACH DATABASE ? AS src", (str(DB_PATH),))
    rows = 0
    dest.execute("BEGIN")
    for typ, tname, sql in objects:
        dest.execute(sql)
        if typ == "table" and tname in where:
            cond = f" WHERE {where[tname]}" if where[tname] else ""
            dest.execute(f'INSERT INTO main."{tname}" SELECT * FROM src."{tname}"{cond}')
            rows += dest.execute(f'SELECT COUNT(*) FROM main."{tname}"').fetchone()[0]
    dest.execute("COMMIT")
    dest.execute("DETACH DATABASE src")
    dest.execute("VACUUM")
    dest.close()
    out, part = BACKUP_DIR / f"{name}.db.gz", BACKUP_DIR / f"{name}.db.gz.partial"
    with open(tmp, "rb") as src, gzip.open(part, "wb", compresslevel=6) as gz:
        shutil.copyfileobj(src, gz, 1 << 20)
    part.replace(out)  # the previous copy stays intact until the new one is complete
    tmp.unlink()
    return rows, out.stat().st_size


def _backup_politics() -> int:
    """The political game machine's own logs and price snapshots, into backups/politics-data.tar.gz.
    Its forecast and turn logs can't be recreated, and Kalshi only offers 14 days of past hours.
    data/dev and data/history are left out: they're rebuilt from options.db and the public APIs."""
    home = DATA_DIR / "politics"
    if not home.exists():
        return 0
    out, part = BACKUP_DIR / "politics-data.tar.gz", BACKUP_DIR / "politics-data.tar.gz.partial"
    with tarfile.open(part, "w:gz") as tar:
        for path in sorted((home / "data").glob("*.jsonl")):
            tar.add(path, arcname=f"data/{path.name}")
        for folder in ("data/senate", "data/news", "kalshi"):
            if (home / folder).exists():
                tar.add(home / folder, arcname=folder)
    part.replace(out)
    return out.stat().st_size


def job_backup(db, run_id: int) -> tuple[str, int, str]:
    """Back up everything that can't be re-downloaded (everything except BACKUP_EXCLUDE):
      options-core.db.gz       every non-monthly table in full, plus all table schemas and views
      options-YYYY-MM.db.gz    that month's rows of each BACKUP_MONTHLY table
    Indexes are skipped (collectors recreate them). Restore with collectors/restore_backup.py."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    objects = [o for o in db.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('table', 'view') "
                                     "AND name NOT LIKE 'sqlite_%' ORDER BY type = 'view', name")
               if o[1] not in BACKUP_EXCLUDE]
    tables = [o for o in objects if o[0] == "table"]
    monthly = [o for o in tables if o[1] in BACKUP_MONTHLY]

    core_rows, core_size = _write_backup_file(
        "options-core", objects, {t[1]: None for t in tables if t[1] not in BACKUP_MONTHLY})

    months = sorted({r[0] for t in monthly for r in db.execute(
        f'SELECT DISTINCT substr("{BACKUP_MONTHLY[t[1]]}", 1, 7) FROM "{t[1]}"') if r[0]})
    today = datetime.now(ET).date()
    written, skipped, total_rows, total_size = [], [], core_rows, core_size
    for m in months:
        y, mo = int(m[:4]), int(m[5:7])
        month_end = date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)
        if (BACKUP_DIR / f"options-{m}.db.gz").exists() and (today - month_end).days > MONTH_GRACE_DAYS:
            skipped.append(m)  # closed month already backed up: leave the file alone
            continue
        rows, size = _write_backup_file(f"options-{m}", monthly,
                                        {t[1]: f"substr(\"{BACKUP_MONTHLY[t[1]]}\", 1, 7) = '{m}'" for t in monthly})
        written.append(f"{m} ({rows:,} rows, {size / 1e6:.1f} MB)")
        total_rows += rows
    politics = _backup_politics()
    return "ok", total_rows, (f"core {core_rows:,} rows {core_size / 1e6:.1f} MB; months written: {', '.join(written) or 'none'}; "
                              f"months unchanged: {', '.join(skipped) or 'none'}; left out (re-downloadable): "
                              f"{', '.join(sorted(BACKUP_EXCLUDE))}; politics {politics / 1e6:.1f} MB")


def status(db) -> None:
    print(f"database: {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.1f} MB)")
    for t in ("occ_oi", "alpaca_contracts", "underlying_snap", "option_snap"):
        print(f"  {t:17} {db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>10,} rows")
    print("recent runs:")
    for r in db.execute("SELECT id, job, started_at, status, rows, substr(detail,1,160) FROM runs ORDER BY id DESC LIMIT 12"):
        print("  ", *r)


# ---------- bars: official full-market daily bars, kept current after the one-time backfill

BARS_REREAD_DAYS = 5  # re-read the last few days, in case Alpaca corrected a bar
BARS_BATCH = 20


def job_bars(db, run_id: int) -> tuple[str, int, str]:
    """Append raw SIP daily bars to stock_bars_daily for every watchlist symbol, from a few days before
    each symbol's last stored bar up to now. Free plan: bars must end 16+ minutes ago."""
    keys = load_keys()
    symbols = watchlist()["symbols"]
    last = dict(db.execute("SELECT symbol, MAX(date) FROM stock_bars_daily GROUP BY symbol").fetchall())
    start = min((date.fromisoformat(last[s]) for s in symbols if s in last), default=date(2023, 12, 18))
    start -= timedelta(days=BARS_REREAD_DAYS)
    end = (datetime.now(ET) - timedelta(minutes=16)).isoformat()
    total, failures = 0, []
    for i in range(0, len(symbols), BARS_BATCH):
        batch, token, rows = symbols[i:i + BARS_BATCH], None, []
        try:
            while True:
                b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(batch), timeframe="1Day", feed="sip",
                           adjustment="raw", start=start.isoformat(), end=end, limit=10000, page_token=token)
                for sym, bars in (b.get("bars") or {}).items():
                    rows += [(sym, x["t"][:10], x["o"], x["h"], x["l"], x["c"], x["v"], x.get("vw"), x.get("n")) for x in bars]
                token = b.get("next_page_token")
                if not token:
                    break
        except Exception as e:
            failures.append(f"{batch[0]}..{batch[-1]}: {e}")
            continue
        db.executemany("INSERT OR REPLACE INTO stock_bars_daily VALUES (?,?,?,?,?,?,?,?,?)", rows)
        db.commit()
        total += len(rows)
    newest = db.execute("SELECT MIN(d), MAX(d) FROM (SELECT MAX(date) d FROM stock_bars_daily GROUP BY symbol)").fetchone()
    detail = f"bars={total} from {start}; latest bar per symbol {newest[0]}..{newest[1]}"
    if failures:
        detail += "; failed: " + " | ".join(failures)
    return ("ok" if not failures else "partial" if total else "failed"), total, detail


JOBS = {"daily": job_daily, "snapshot": job_snapshot, "backup": job_backup, "bars": job_bars}


def main() -> int:
    job = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if job == "status":
        status(db)
        return 0
    if job not in JOBS:
        print(__doc__)
        return 2
    run_id = start_run(db, job)
    try:
        result = JOBS[job](db, run_id)
    except Exception as e:
        result = ("failed", 0, f"{e}\n{traceback.format_exc()[-1500:]}")
    finish_run(db, run_id, *result)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] {job} run {run_id}: {result[0]} rows={result[1]} {result[2][:500]}")
    return 0 if result[0] in ("ok", "skipped", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
