"""Gamma breakout tracker: runs the rules in scoring.py against live data and keeps score.

The idea under test: when a liquid large-cap stock breaks above its options call wall and holds,
dealer hedging pushes it further up. This makes predictions and checks them. It never trades.
Rules: scoring.py and docs/gamma-strategy/. Stocks and their sector ETFs: shared/strategy.json.

Each run (every 5 minutes in market hours, see install.sh):
  1. Levels for the day, once: call wall, put wall and gamma flip. They use only what was known
     before the open: this morning's OCC file (yesterday's closing open interest) and the last
     option snapshot before today.
  2. New 5-minute bars. SIP (full market, needed for the volume rule), so about 16 minutes behind
     on the free plan: fine for checking predictions, not for trading.
  3. The rules over each stock's day. Every finished breakout is logged, including failures:
     they're the comparison group.
  4. Grades at the three checkpoints: that day's close, the next close, three closes later.

Tables: strategy_levels, strategy_events, strategy_grades, strategy_state, strategy_bars_5m.
Events are written once and never changed. mode is 'live' for days the job ran on, and 'replay'
for past days run afterwards with `replay` (same rules, same point-in-time inputs, but not a
forward test, so the Gamma tab keeps them apart).

Usage: python strategy_collector.py            normal run
       python strategy_collector.py replay [YYYY-MM-DD]   rerun past days (default: first day possible)
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import scoring
from options_collector import ALPACA_DATA, ALPACA_TRADE, ET, PROJECT_DIR, alpaca, connect, finish_run, load_keys, start_run

CONFIG_PATH = Path(os.environ.get("STRATEGY", Path(__file__).with_name("strategy.json")))
if not CONFIG_PATH.exists():
    CONFIG_PATH = PROJECT_DIR / "shared" / "strategy.json"
FREE_PLAN_DELAY = timedelta(minutes=16)  # SIP bars must end at least this long ago
BAR = timedelta(minutes=5)
MIN_BASELINE_DAYS = 10  # fewer days than this and the volume rule has no baseline
FLIP_RANGE, FLIP_STEP = 0.30, 0.005  # gamma flip is searched for within ±30% of the price
CHECKPOINTS = (("eod", 0), ("next_day", 1), ("three_days", 3))  # name, trading days after the prediction
# Which way dealers are assumed to lean, as (calls, puts). Open interest doesn't show this. It only
# changes the sign of dealer_gamma, never where the flip is: the same line crosses zero either way.
DEALER_VIEWS = {"short_calls_long_puts": (-1, 1), "long_calls_short_puts": (1, -1)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_bars_5m (
    symbol TEXT, bar_end TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, bar_end)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS strategy_levels (
    date TEXT, symbol TEXT, sector TEXT, prev_close REAL,
    call_wall REAL, call_wall_oi REAL, put_wall REAL, put_wall_oi REAL,
    gamma_flip REAL, dealer_gamma REAL, snapshot_ts TEXT, computed_at TEXT, mode TEXT,
    PRIMARY KEY (date, symbol)
);
CREATE TABLE IF NOT EXISTS strategy_events (
    id INTEGER PRIMARY KEY, mode TEXT, date TEXT, symbol TEXT, kind TEXT, call_wall REAL,
    breakout_time TEXT, breakout_price REAL, decision_time TEXT, decision_price REAL,
    volume_ratio REAL, score INTEGER, strong INTEGER, points TEXT, reasons TEXT, notes TEXT, logged_at TEXT,
    UNIQUE (date, symbol, breakout_time)
);
CREATE TABLE IF NOT EXISTS strategy_grades (
    event_id INTEGER, checkpoint TEXT, checkpoint_time TEXT, status TEXT, price REAL, pct_move REAL,
    broke_below_at TEXT, graded_at TEXT, PRIMARY KEY (event_id, checkpoint)
);
CREATE TABLE IF NOT EXISTS strategy_state (
    symbol TEXT PRIMARY KEY, date TEXT, last_bar TEXT, last_price REAL, volume_ratio REAL,
    holding_since TEXT, holding_price REAL, updated_at TEXT
);
"""


def config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def now_et() -> datetime:
    return datetime.now(ET)


def calendar(keys: dict, start: date, end: date) -> dict[date, datetime]:
    """Trading days between start and end, each with its closing time (half days close early)."""
    days = alpaca(ALPACA_TRADE, "/v2/calendar", keys, start=start.isoformat(), end=end.isoformat())
    return {date.fromisoformat(d["date"]): datetime.combine(date.fromisoformat(d["date"]),
                                                            time.fromisoformat(d["close"]), ET) for d in days}


# ---------- gamma flip

def bs_gamma(spot: float, strike: float, years: float, iv: float) -> float:
    root = iv * math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * years) / root
    return math.exp(-0.5 * d1 * d1) / (math.sqrt(2 * math.pi) * spot * root)


def net_gamma(contracts: list[tuple], spot: float, view: tuple[int, int]) -> float:
    """Dealers' dollar gamma per 1% move if the stock were at `spot`.
    contracts: (is_call, strike, years to expiry, implied vol, open interest)."""
    total = 0.0
    for is_call, strike, years, iv, oi in contracts:
        total += (view[0] if is_call else view[1]) * oi * 100 * bs_gamma(spot, strike, years, iv) * spot * spot * 0.01
    return total


def gamma_flip(contracts: list[tuple], spot: float, view: tuple[int, int]) -> float | None:
    """The price nearest `spot` where total dealer gamma changes sign, or None if it never does."""
    if not contracts:
        return None
    steps = round(FLIP_RANGE / FLIP_STEP)
    prices = [spot * (1 + i * FLIP_STEP) for i in range(-steps, steps + 1)]
    values = [net_gamma(contracts, p, view) for p in prices]
    crossings = []
    for (p0, v0), (p1, v1) in zip(zip(prices, values), zip(prices[1:], values[1:])):
        if v0 == 0 or v0 * v1 < 0:
            crossings.append(p0 + (p1 - p0) * (0 - v0) / (v1 - v0))
    return min(crossings, key=lambda p: abs(p - spot)) if crossings else None


# ---------- levels

def walls(rows: list[tuple], day: date, window_days: int) -> dict:
    """Call and put wall: the strike with the most open interest across expirations from `day` to
    `day` + window. OCC's file still lists contracts for a day after they expire, so those are skipped."""
    last = (day + timedelta(days=window_days)).isoformat()
    calls, puts = defaultdict(float), defaultdict(float)
    for expiration, strike, call_oi, put_oi in rows:
        if day.isoformat() <= expiration <= last:
            calls[strike] += call_oi or 0
            puts[strike] += put_oi or 0
    if not calls or max(calls.values()) <= 0:
        return {}
    call_wall = max(calls, key=calls.get)
    put_wall = max(puts, key=puts.get)
    return {"call_wall": call_wall, "call_wall_oi": calls[call_wall], "put_wall": put_wall, "put_wall_oi": puts[put_wall]}


def last_snapshot_before(db, day: date) -> tuple[int, str] | None:
    return db.execute("SELECT id, started_at FROM runs WHERE job = 'snapshot' AND status = 'ok' AND rows > 0 "
                      "AND started_at < ? ORDER BY id DESC LIMIT 1", (day.isoformat(),)).fetchone()


def contracts_for(db, symbol: str, day: date, run: tuple[int, str]) -> list[tuple]:
    """Open interest as of this morning's file, with implied vol from the last snapshot before today."""
    oi = {(e, k): (c or 0, p or 0) for e, k, c, p in db.execute(
        "SELECT expiration, strike, call_oi, put_oi FROM open_interest WHERE date = ? AND underlying = ? AND product = underlying",
        (day.isoformat(), symbol))}
    asof = datetime.fromisoformat(run[1])
    out = []
    for expiration, kind, strike, iv in db.execute(
            "SELECT expiration, type, strike, iv FROM option_quotes WHERE run_id = ? AND underlying = ? AND iv > 0.01",
            (run[0], symbol)):
        if expiration < day.isoformat() or (expiration, strike) not in oi:
            continue
        expires = datetime.combine(date.fromisoformat(expiration), time(16, 0), ET)
        years = (expires - asof).total_seconds() / (365 * 86400)
        size = oi[(expiration, strike)][0 if kind == "call" else 1]
        if years > 0 and size > 0:
            out.append((kind == "call", strike, years, iv, size))
    return out


def daily_closes(keys: dict, symbols: list[str], start: date) -> dict[str, dict[str, float]]:
    end = (datetime.now(timezone.utc) - FREE_PLAN_DELAY).isoformat()
    out, token = defaultdict(dict), None
    while True:
        b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(symbols), timeframe="1Day", feed="sip",
                   adjustment="raw", start=start.isoformat(), end=end, limit=10000, page_token=token)
        for sym, xs in (b.get("bars") or {}).items():
            for x in xs:
                out[sym][x["t"][:10]] = x["c"]
        token = b.get("next_page_token")
        if not token:
            return out


def compute_levels(db, day: date, closes: dict, mode: str) -> int:
    """Levels for one day, once per stock. Returns how many were written."""
    cfg = config()
    view = DEALER_VIEWS[cfg["dealer_view"]]
    run = last_snapshot_before(db, day)
    written = 0
    for symbol, sector in cfg["stocks"].items():
        if db.execute("SELECT 1 FROM strategy_levels WHERE date = ? AND symbol = ?", (day.isoformat(), symbol)).fetchone():
            continue
        rows = db.execute("SELECT expiration, strike, call_oi, put_oi FROM open_interest "
                          "WHERE date = ? AND underlying = ? AND product = underlying", (day.isoformat(), symbol)).fetchall()
        level = walls(rows, day, cfg["wall_window_days"])
        before = [d for d in closes.get(symbol, {}) if d < day.isoformat()]
        if not level or not before:
            continue
        prev_close = closes[symbol][max(before)]
        contracts = contracts_for(db, symbol, day, run) if run else []
        flip = gamma_flip(contracts, prev_close, view)
        db.execute("INSERT INTO strategy_levels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (day.isoformat(), symbol, sector, prev_close, level["call_wall"], level["call_wall_oi"], level["put_wall"],
                    level["put_wall_oi"], flip, net_gamma(contracts, prev_close, view) if contracts else None,
                    run[1] if run else None, now_et().isoformat(timespec="seconds"), mode))
        written += 1
    db.commit()
    return written


# ---------- bars

def load_bars(db, keys: dict, symbols: list[str], start: datetime) -> int:
    """Fetch regular-session 5-minute bars into strategy_bars_5m. Raw prices, because walls are real strikes."""
    cutoff = datetime.now(timezone.utc) - FREE_PLAN_DELAY
    token, total = None, 0
    while True:
        b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(symbols), timeframe="5Min", feed="sip",
                   adjustment="raw", start=start.astimezone(timezone.utc).isoformat(), end=cutoff.isoformat(),
                   limit=10000, page_token=token)
        rows = []
        for sym, xs in (b.get("bars") or {}).items():
            for x in xs:
                started = datetime.fromisoformat(x["t"].replace("Z", "+00:00"))
                end = started + BAR
                local = end.astimezone(ET)
                # The last bar can still be filling up at the cutoff, so it waits for the next run.
                if end <= cutoff and scoring.SESSION_OPEN < local.time() <= scoring.SESSION_CLOSE:
                    rows.append((sym, local.isoformat(), x["o"], x["h"], x["l"], x["c"], x["v"]))
        db.executemany("INSERT OR REPLACE INTO strategy_bars_5m VALUES (?,?,?,?,?,?,?)", rows)
        total += len(rows)
        token = b.get("next_page_token")
        if not token:
            db.commit()
            return total


def bars_on(db, symbol: str, day: date) -> list[scoring.Bar]:
    return [scoring.Bar(datetime.fromisoformat(t), o, c, v) for t, o, c, v in db.execute(
        "SELECT bar_end, open, close, volume FROM strategy_bars_5m WHERE symbol = ? AND bar_end >= ? AND bar_end < ? ORDER BY bar_end",
        (symbol, day.isoformat(), (day + timedelta(days=1)).isoformat()))]


def volume_baseline(db, symbol: str, day: date, trading_days: list[date], lookback: int) -> dict[time, float]:
    """Average cumulative volume by time of day over the previous `lookback` trading days."""
    totals, counts, used = defaultdict(float), defaultdict(int), 0
    for past in reversed([d for d in trading_days if d < day]):
        bars = bars_on(db, symbol, past)
        if not bars:
            continue
        running = 0.0
        for bar in bars:
            running += bar.volume
            totals[bar.end.time()] += running
            counts[bar.end.time()] += 1
        used += 1
        if used == lookback:
            break
    return {t: totals[t] / counts[t] for t in totals} if used >= MIN_BASELINE_DAYS else {}


# ---------- rules and grades

def run_rules(db, day: date, trading_days: list[date], closes: dict, mode: str, live: bool) -> int:
    """Apply scoring.py to each stock's day, logging finished breakouts. Returns how many were new."""
    cfg = config()
    logged = 0
    for (symbol, sector, prev_close, call_wall, flip) in db.execute(
            "SELECT symbol, sector, prev_close, call_wall, gamma_flip FROM strategy_levels WHERE date = ?", (day.isoformat(),)).fetchall():
        bars = bars_on(db, symbol, day)
        if not bars:
            continue
        baseline = volume_baseline(db, symbol, day, trading_days, cfg["volume_baseline_days"])
        before = [d for d in closes.get(sector, {}) if d < day.isoformat()]
        sector_data = scoring.SectorData(closes[sector][max(before)], bars_on(db, sector, day)) if before else None
        result = scoring.evaluate_day(scoring.StockDay(symbol=symbol, prev_close=prev_close, bars=bars, call_wall=call_wall,
                                                       gamma_flip=flip, avg_cum_volume=baseline, sector=sector_data))
        for e in result.events:
            cur = db.execute("INSERT OR IGNORE INTO strategy_events (mode, date, symbol, kind, call_wall, breakout_time, breakout_price, "
                             "decision_time, decision_price, volume_ratio, score, strong, points, reasons, notes, logged_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (mode, day.isoformat(), symbol, e.kind.value, e.call_wall, e.breakout_time.isoformat(), e.breakout_price,
                              e.decision_time.isoformat(), e.decision_price, e.volume_ratio, e.score, int(e.strong),
                              json.dumps(e.points), json.dumps(e.reasons), json.dumps(e.notes), now_et().isoformat(timespec="seconds")))
            logged += cur.rowcount
        if live:
            ratio = None
            running = sum(b.volume for b in bars)
            if baseline.get(bars[-1].end.time()):
                ratio = running / baseline[bars[-1].end.time()]
            holding = result.holding_since
            db.execute("INSERT OR REPLACE INTO strategy_state VALUES (?,?,?,?,?,?,?,?)",
                       (symbol, day.isoformat(), bars[-1].end.isoformat(), bars[-1].close, ratio,
                        holding.end.isoformat() if holding else None, holding.close if holding else None,
                        now_et().isoformat(timespec="seconds")))
    db.commit()
    return logged


def bars_since(db, symbol: str, start: str) -> list[scoring.Bar]:
    return [scoring.Bar(datetime.fromisoformat(t), o, c, v) for t, o, c, v in db.execute(
        "SELECT bar_end, open, close, volume FROM strategy_bars_5m WHERE symbol = ? AND bar_end >= ? ORDER BY bar_end", (symbol, start))]


def grade_events(db, closes_by_day: dict[date, datetime]) -> int:
    """Grade each event at every checkpoint the bars have reached. A grade is final once written."""
    days = sorted(closes_by_day)
    written = 0
    open_events = db.execute(
        "SELECT e.id, e.symbol, e.date, e.kind, e.call_wall, e.breakout_time, e.breakout_price, e.decision_time, e.decision_price "
        "FROM strategy_events e WHERE (SELECT COUNT(*) FROM strategy_grades g WHERE g.event_id = e.id) < ?", (len(CHECKPOINTS),)).fetchall()
    for eid, symbol, day, kind, wall, b_time, b_price, d_time, d_price in open_events:
        event = scoring.Event(symbol=symbol, kind=scoring.EventKind(kind), call_wall=wall,
                              breakout_time=datetime.fromisoformat(b_time), breakout_price=b_price,
                              decision_time=datetime.fromisoformat(d_time), decision_price=d_price)
        done = {r[0] for r in db.execute("SELECT checkpoint FROM strategy_grades WHERE event_id = ?", (eid,))}
        bars = bars_since(db, symbol, d_time)
        if not bars or date.fromisoformat(day) not in days:
            continue
        start = days.index(date.fromisoformat(day))
        for name, ahead in CHECKPOINTS:
            if name in done or start + ahead >= len(days):
                continue
            checkpoint = closes_by_day[days[start + ahead]]
            grade = scoring.grade_prediction(event, bars, checkpoint)
            if bars[-1].end >= checkpoint and grade.status is not scoring.GradeStatus.PENDING:
                db.execute("INSERT OR IGNORE INTO strategy_grades VALUES (?,?,?,?,?,?,?,?)",
                           (eid, name, checkpoint.isoformat(), grade.status.value, grade.price, grade.pct_move,
                            grade.broke_below_at.isoformat() if grade.broke_below_at else None, now_et().isoformat(timespec="seconds")))
                written += 1
    db.commit()
    return written


# ---------- jobs

def symbols_needed() -> list[str]:
    cfg = config()
    return sorted(set(cfg["stocks"]) | set(cfg["stocks"].values()))


def first_bar_needed(db, day: date) -> datetime:
    """Where to resume bars: the last one stored, or enough history for the volume baseline."""
    last = db.execute("SELECT MAX(bar_end) FROM strategy_bars_5m").fetchone()[0]
    if last:
        return datetime.fromisoformat(last) - timedelta(hours=1)
    return datetime.combine(day - timedelta(days=45), time(9, 30), ET)


def process_days(db, keys: dict, days: list[date], mode: str) -> tuple[int, int, int]:
    """Levels, rules and grades for these days. Returns (levels, new events, grades)."""
    span_start = (days[0] if days else now_et().date()) - timedelta(days=60)
    trading = calendar(keys, span_start, now_et().date() + timedelta(days=10))
    trading_days = sorted(trading)
    closes = daily_closes(keys, symbols_needed(), span_start)
    today = now_et().date()
    levels = events = 0
    for day in days:
        levels += compute_levels(db, day, closes, mode)
        events += run_rules(db, day, trading_days, closes, mode, live=day == today)
    return levels, events, grade_events(db, trading)


def job_run(db, keys: dict) -> tuple[str, int, str]:
    today = now_et().date()
    trading = calendar(keys, today - timedelta(days=10), today)
    if today not in trading:
        return "skipped", 0, "market closed today"
    last = db.execute("SELECT MAX(date) FROM strategy_levels").fetchone()[0]
    # Any day the job missed (Mac asleep or off) is filled in, with the same inputs it would have used.
    days = [d for d in sorted(trading) if last and last <= d.isoformat() or d == today]
    new_bars = load_bars(db, keys, symbols_needed(), first_bar_needed(db, today))
    levels, events, grades = process_days(db, keys, days, "live")
    have = db.execute("SELECT COUNT(*) FROM strategy_levels WHERE date = ?", (today.isoformat(),)).fetchone()[0]
    wanted = len(config()["stocks"])
    # Missing levels mean missing open interest, which the watchdog already alerts on once.
    return "ok", new_bars, f"levels {have}/{wanted}, bars {new_bars}, new breakouts {events}, grades {grades}"


def job_replay(db, keys: dict, start: date | None) -> tuple[str, int, str]:
    """Past days, run after the fact. Stops before today, which belongs to the live job."""
    first = db.execute("SELECT MIN(date) FROM open_interest").fetchone()[0]
    earliest = date.fromisoformat(first) + timedelta(days=1)  # the first day with an earlier option snapshot
    start = max(start or earliest, earliest)
    today = now_et().date()
    days = [d for d in sorted(calendar(keys, start, today)) if d < today or now_et().time() > time(16, 30)]
    days = [d for d in days if not db.execute("SELECT 1 FROM strategy_levels WHERE date = ? AND mode = 'live'", (d.isoformat(),)).fetchone()]
    new_bars = load_bars(db, keys, symbols_needed(), datetime.combine(start - timedelta(days=45), time(9, 30), ET))
    levels, events, grades = process_days(db, keys, days, "replay")
    return "ok", new_bars, f"replayed {len(days)} days from {start}: levels {levels}, breakouts {events}, grades {grades}"


def main() -> int:
    replay = len(sys.argv) > 1 and sys.argv[1] == "replay"
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "strategy-replay" if replay else "strategy")
    try:
        keys = load_keys()
        if replay:
            result = job_replay(db, keys, date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None)
        else:
            result = job_run(db, keys)
    except Exception as e:
        db.rollback()
        result = ("failed", 0, f"{e}\n{traceback.format_exc()[-1500:]}")
    finish_run(db, run_id, *result)
    print(f"[{now_et():%Y-%m-%d %H:%M:%S}] strategy run {run_id}: {result[0]} rows={result[1]} {result[2][:400]}")
    return 0 if result[0] in ("ok", "skipped", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
