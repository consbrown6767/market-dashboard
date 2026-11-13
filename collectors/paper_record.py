"""Live paper record of three trading rules: leveraged trend (SSO above SPY's 200-day average), the
10-month trend (SPY), and the pre-Fed drift (SPY from 2 pm the day before a Fed decision to 2 pm on it).
Nothing is traded. Positions are written before they take effect, never edited, hash-chained, and
scored afterwards from real prices next to SPY. Plan fixed before the start: docs/paper-record/PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  (none)     the job: log due positions, mark finished days (launchd, weekdays 09:10, 16:40, 20:40)
  status     the summary as JSON
  verify     recompute both hash chains

Tables: paper_positions (decisions), paper_marks (daily or per-meeting results), paper_skips.
This module's reading parts (summary, verify) use only the standard library, so the dashboard server
can import them on its read-only connection.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ---- fixed by the plan (a change is a new version)
STRATEGIES = {
    "lev-trend": {"version": "1", "asset": "SSO", "kind": "trend", "name": "Leveraged trend",
                  "what": "2x S&P 500 (SSO) while SPY is above its 200-day average, else cash"},
    "trend10": {"version": "1", "asset": "SPY", "kind": "trend", "name": "10-month trend",
                "what": "SPY while it's above its average of the last 10 month-ends, else cash"},
    "fed-drift": {"version": "1", "asset": "SPY", "kind": "fed", "name": "Pre-Fed drift",
                  "what": "SPY from 2 pm the day before each Fed decision to 2 pm on decision day"},
}
START = "2026-11-12"          # first signal day used (its trade is at the 2026-11-13 close)
SWITCH_COST = 0.0005
FED_COST = 0.0001
MA_DAYS = 200
MA_MONTHS = 10
FED_LOOKAHEAD_DAYS = 14
TREND_VERDICT_YEARS = 3
FED_VERDICT_MEETINGS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY, strategy TEXT NOT NULL, version TEXT NOT NULL, signal_date TEXT NOT NULL,
    trade_at TEXT NOT NULL, decided_at TEXT NOT NULL, position TEXT NOT NULL, inputs TEXT NOT NULL,
    prev_hash TEXT, hash TEXT NOT NULL, UNIQUE (strategy, version, signal_date)
);
CREATE TABLE IF NOT EXISTS paper_marks (
    id INTEGER PRIMARY KEY, strategy TEXT NOT NULL, version TEXT NOT NULL, date TEXT NOT NULL,
    position_id INTEGER NOT NULL, held TEXT NOT NULL, ret REAL, spy_ret REAL, cost REAL NOT NULL,
    detail TEXT NOT NULL, recorded_at TEXT NOT NULL, prev_hash TEXT, hash TEXT NOT NULL,
    UNIQUE (strategy, version, date)
);
CREATE TABLE IF NOT EXISTS paper_skips (
    strategy TEXT NOT NULL, version TEXT NOT NULL, signal_date TEXT NOT NULL, noted_at TEXT NOT NULL,
    reason TEXT NOT NULL, PRIMARY KEY (strategy, version, signal_date)
);
"""

POS_FIELDS = ("strategy", "version", "signal_date", "trade_at", "decided_at", "position", "inputs")
MARK_FIELDS = ("strategy", "version", "date", "position_id", "held", "ret", "spy_ret", "cost", "detail", "recorded_at")


def ensure(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def _now() -> datetime:
    return datetime.now(ET)


def _iso(t: datetime) -> str:
    return t.astimezone(ET).isoformat(timespec="seconds")


def _json(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def _sha(*parts) -> str:
    return hashlib.sha256("\x1f".join("" if p is None else repr(p) if isinstance(p, float) else str(p)
                                      for p in parts).encode()).hexdigest()


def _last_hash(db, table: str) -> str | None:
    r = db.execute(f"SELECT hash FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else None


# ---------- writing (the job only)

def log_position(db, strategy: str, signal_date: str, trade_at: datetime, position: dict, inputs: dict) -> int | None:
    """Write one decision. Refused once its trade time has passed; None if already logged."""
    s = STRATEGIES[strategy]
    now = _now()
    if now >= trade_at:
        raise ValueError(f"too late: {strategy} {signal_date} trades at {_iso(trade_at)}, now {_iso(now)}")
    if db.execute("SELECT 1 FROM paper_positions WHERE strategy=? AND version=? AND signal_date=?",
                  (strategy, s["version"], signal_date)).fetchone():
        return None
    row = {"strategy": strategy, "version": s["version"], "signal_date": signal_date, "trade_at": _iso(trade_at),
           "decided_at": _iso(now), "position": _json(position), "inputs": _json(inputs)}
    prev = _last_hash(db, "paper_positions")
    h = _sha(*(row[f] for f in POS_FIELDS), prev)
    cur = db.execute(f"INSERT INTO paper_positions ({', '.join(POS_FIELDS)}, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?)",
                     (*row.values(), prev, h))
    db.commit()
    return cur.lastrowid


def add_mark(db, strategy: str, day: str, position_id: int, held: str, ret: float | None, spy_ret: float | None,
             cost: float, detail: dict) -> bool:
    s = STRATEGIES[strategy]
    if db.execute("SELECT 1 FROM paper_marks WHERE strategy=? AND version=? AND date=?", (strategy, s["version"], day)).fetchone():
        return False
    row = {"strategy": strategy, "version": s["version"], "date": day, "position_id": position_id, "held": held,
           "ret": None if ret is None else float(ret), "spy_ret": None if spy_ret is None else float(spy_ret),
           "cost": float(cost), "detail": _json(detail), "recorded_at": _iso(_now())}
    prev = _last_hash(db, "paper_marks")
    h = _sha(*(row[f] for f in MARK_FIELDS), prev)
    db.execute(f"INSERT INTO paper_marks ({', '.join(MARK_FIELDS)}, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (*row.values(), prev, h))
    db.commit()
    return True


def skip(db, strategy: str, signal_date: str, reason: str) -> None:
    db.execute("INSERT OR IGNORE INTO paper_skips VALUES (?,?,?,?,?)",
               (strategy, STRATEGIES[strategy]["version"], signal_date, _iso(_now()), reason))
    db.commit()


# ---------- reading and checking (standard library only; safe on a read-only connection)

def _exists(db, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def verify(db) -> dict:
    if not _exists(db, "paper_positions"):
        return {"ok": True, "positions": 0, "marks": 0, "problems": []}
    problems = []
    counts = {}
    for table, fields in (("paper_positions", POS_FIELDS), ("paper_marks", MARK_FIELDS)):
        prev, n = None, 0
        for r in db.execute(f"SELECT id, {', '.join(fields)}, prev_hash, hash FROM {table} ORDER BY id"):
            n += 1
            rid, vals, ph, h = r[0], r[1:-2], r[-2], r[-1]
            if ph != prev:
                problems.append(f"{table} {rid}: doesn't follow the row before it (a row was removed?)")
            if h != _sha(*vals, ph):
                problems.append(f"{table} {rid}: changed after it was written")
            prev = h
        counts[table] = n
    return {"ok": not problems, "positions": counts["paper_positions"], "marks": counts["paper_marks"], "problems": problems[:20]}


def _drop(wealth: list[float]) -> float:
    peak, worst = 1.0, 0.0
    for w in wealth:
        peak = max(peak, w)
        worst = min(worst, w / peak - 1)
    return worst


def _sharpe(ex: list[float]) -> float | None:
    if len(ex) < 20:
        return None
    m = sum(ex) / len(ex)
    sd = math.sqrt(sum((x - m) ** 2 for x in ex) / (len(ex) - 1))
    return m / sd * math.sqrt(252) if sd else None


def summary(db) -> dict:
    """Everything the Scorecard panel shows, per strategy."""
    if not _exists(db, "paper_positions"):
        return {"ready": False, "strategies": []}
    out = []
    spy_days = {}
    for d, sr in db.execute("SELECT date, spy_ret FROM paper_marks WHERE strategy='lev-trend' AND spy_ret IS NOT NULL"):
        spy_days[d] = sr
    for key, s in STRATEGIES.items():
        v = s["version"]
        pos = db.execute("SELECT signal_date, trade_at, decided_at, position FROM paper_positions WHERE strategy=? AND version=? "
                         "ORDER BY signal_date DESC LIMIT 1", (key, v)).fetchone()
        marks = db.execute("SELECT date, held, ret, spy_ret, cost, detail FROM paper_marks WHERE strategy=? AND version=? ORDER BY date",
                           (key, v)).fetchall()
        skips = [{"signal_date": a, "reason": b} for a, b in db.execute(
            "SELECT signal_date, reason FROM paper_skips WHERE strategy=? AND version=? ORDER BY signal_date", (key, v))]
        e = {"strategy": key, "version": v, "name": s["name"], "what": s["what"], "kind": s["kind"],
             "latest_position": None if not pos else {"signal_date": pos[0], "trade_at": pos[1], "decided_at": pos[2],
                                                       **json.loads(pos[3])},
             "skips": skips, "marks": len(marks)}
        if s["kind"] == "trend":
            w = sw = 1.0
            curve, ex, spy_ex = [], [], []
            for d, held, ret, sr, cost, det in marks:
                rf = json.loads(det).get("rf", 0.0)
                w *= 1 + ret
                sw *= 1 + sr
                curve.append({"date": d, "rule": round(w * 10000, 2), "spy": round(sw * 10000, 2), "held": held})
                ex.append(ret - rf)
                spy_ex.append(sr - rf)
            first = marks[0][0] if marks else None
            years = (date.fromisoformat(marks[-1][0]) - date.fromisoformat(first)).days / 365.25 if marks else 0
            e.update({"first_day": first, "last_day": marks[-1][0] if marks else None, "years": round(years, 2),
                      "rule_10k": round(w * 10000, 2), "spy_10k": round(sw * 10000, 2),
                      "rule_sharpe": _sharpe(ex), "spy_sharpe": _sharpe(spy_ex),
                      "rule_worst_drop": _drop([c["rule"] / 10000 for c in curve]),
                      "spy_worst_drop": _drop([c["spy"] / 10000 for c in curve]),
                      "days_in_market": sum(1 for m in marks if m[1] != "cash"),
                      "switches": sum(1 for m in marks if m[4] > 0), "curve": curve})
            if years < TREND_VERDICT_YEARS:
                e["verdict"] = "too early"
            else:
                better = e["rule_10k"] > e["spy_10k"] and (e["rule_sharpe"] or 0) > (e["spy_sharpe"] or 0)
                e["verdict"] = "beats SPY" if better else "doesn't beat SPY"
        else:
            done = [m for m in marks if m[2] is not None]
            rets = [m[2] for m in done]
            first = done[0][0] if done else None
            avg_day = None
            if first:
                xs = [r for d, r in spy_days.items() if d >= first]
                avg_day = sum(xs) / len(xs) if xs else None
            t = None
            if len(rets) >= 2 and avg_day is not None:
                m = sum(rets) / len(rets)
                sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
                t = (m - avg_day) / (sd / math.sqrt(len(rets))) if sd else None
            e.update({"meetings": len(done), "void": len(marks) - len(done), "first_day": first,
                      "avg_window": sum(rets) / len(rets) if rets else None, "avg_spy_day": avg_day, "t": t,
                      "share_up": sum(r > 0 for r in rets) / len(rets) if rets else None,
                      "windows": [{"date": m[0], "ret": m[2], "spy_day": m[3], **json.loads(m[5])} for m in marks]})
            if len(done) < FED_VERDICT_MEETINGS:
                e["verdict"] = "too early"
            else:
                e["verdict"] = "beats an average day" if (t or 0) >= 2 else "no clear edge"
        out.append(e)
    return {"ready": True, "strategies": out, "verify": verify(db),
            "verdict_rules": {"trend_years": TREND_VERDICT_YEARS, "fed_meetings": FED_VERDICT_MEETINGS}}


# ---------- the job

def _calendar(keys, alpaca, trade_base, start: date, end: date) -> list[dict]:
    cal = alpaca(trade_base, "/v2/calendar", keys, start=start.isoformat(), end=end.isoformat())
    out = []
    for c in cal:
        d = date.fromisoformat(c["date"])
        hh, mm = (int(x) for x in c["close"].split(":"))
        out.append({"date": c["date"], "close": datetime.combine(d, time(hh, mm), ET)})
    return out


def _daily_closes(keys, alpaca, data_base, sym: str, start: date) -> dict[str, float]:
    end = _now() - timedelta(minutes=16)
    out, token = {}, None
    while True:
        b = alpaca(data_base, "/v2/stocks/bars", keys, symbols=sym, timeframe="1Day", feed="sip", adjustment="all",
                   start=start.isoformat(), end=end.isoformat(), limit=10000, page_token=token)
        for x in (b.get("bars") or {}).get(sym) or []:
            out[x["t"][:10]] = float(x["c"])
        token = b.get("next_page_token")
        if not token:
            return out


def _minute_close(keys, alpaca, data_base, sym: str, at: datetime) -> float | None:
    b = alpaca(data_base, "/v2/stocks/bars", keys, symbols=sym, timeframe="1Min", feed="sip", adjustment="all",
               start=at.isoformat(), end=(at + timedelta(minutes=1)).isoformat(), limit=5)
    bars = (b.get("bars") or {}).get(sym) or []
    return float(bars[0]["c"]) if bars and bars[0]["t"].startswith(at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M")) else None


def _rf_by_day(db, days: list[str]) -> dict[str, float]:
    """Daily T-bill return for each trading day: the latest DTB3 known the day before, /360 per calendar day."""
    rates = db.execute("SELECT date, value FROM rates_daily WHERE series='DTB3' ORDER BY date").fetchall()
    out = {}
    for i in range(1, len(days)):
        prev, d = days[i - 1], days[i]
        known = [v for x, v in rates if x < d]
        r = known[-1] / 100 if known else 0.0
        out[d] = r / 360 * (date.fromisoformat(d) - date.fromisoformat(prev)).days
    return out


def _refresh_tbill(db) -> str:
    import urllib.request
    try:
        with urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=60) as r:
            text = r.read().decode()
    except Exception as ex:  # keep going on the stored rates
        return f"T-bill refresh failed ({ex.__class__.__name__}); using stored rates"
    now = _iso(_now())
    rows = [("DTB3", d, float(v), "fred", now) for d, v in (ln.split(",") for ln in text.splitlines()[1:]) if v not in ("", ".")]
    db.executemany("INSERT OR REPLACE INTO rates_daily VALUES (?,?,?,?,?)", rows[-400:])
    db.commit()
    return f"T-bill to {rows[-1][1]}"


def _trend_signals(db, key: str, cal: list[dict], done: list[str], closes: dict, notes: list) -> None:
    """Log every due signal of a trend rule; skip ones whose trade close has passed."""
    s = STRATEGIES[key]
    days = [c["date"] for c in cal]
    close_at = {c["date"]: c["close"] for c in cal}
    have = {r[0] for r in db.execute("SELECT signal_date FROM paper_positions WHERE strategy=? AND version=?", (key, s["version"]))}
    skipped = {r[0] for r in db.execute("SELECT signal_date FROM paper_skips WHERE strategy=? AND version=?", (key, s["version"]))}
    spy_days = [d for d in sorted(closes["SPY"]) if d in close_at]
    for d in [x for x in done if x >= START and x not in have and x not in skipped]:
        nxt = days[days.index(d) + 1]
        if key == "trend10":
            month_end = date.fromisoformat(nxt).month != date.fromisoformat(d).month
            first = not have
            if not month_end and not first:
                continue
            ends = [x for i, x in enumerate(spy_days) if x <= d and (i + 1 == len(spy_days) or spy_days[i + 1][:7] != x[:7])]
            if not month_end:   # start-up: the rule's current state, from the last completed month-end
                ends = [x for x in ends if x[:7] < d[:7]]
            ends = ends[-MA_MONTHS:]
            if len(ends) < MA_MONTHS:
                raise RuntimeError(f"trend10: only {len(ends)} month-ends of SPY")
            level, avg = closes["SPY"][ends[-1]], sum(closes["SPY"][x] for x in ends) / MA_MONTHS
            inputs = {"month_end": ends[-1], "spy_close": level, "avg_10_month_ends": round(avg, 4),
                      "start_up": not month_end}
        else:
            hist = [x for x in spy_days if x <= d][-MA_DAYS:]
            if len(hist) < MA_DAYS or hist[-1] != d:
                raise RuntimeError(f"lev-trend: SPY history short or missing {d}")
            level, avg = closes["SPY"][d], sum(closes["SPY"][x] for x in hist) / MA_DAYS
            inputs = {"spy_close": level, "avg_200_days": round(avg, 4)}
        hold = s["asset"] if level > avg else "cash"
        try:
            log_position(db, key, d, close_at[nxt], {"hold": hold, "trade_date": nxt}, inputs)
            notes.append(f"{key} {d}: {hold} from the {nxt} close")
            have.add(d)
        except ValueError:
            skip(db, key, d, f"not logged before the {nxt} close (Mac asleep or job not run)")
            notes.append(f"{key} {d}: SKIPPED (trade close passed)")


def _trend_marks(db, key: str, done: list[str], closes: dict, rf: dict) -> int:
    s = STRATEGIES[key]
    pos = db.execute("SELECT id, position FROM paper_positions WHERE strategy=? AND version=? ORDER BY signal_date",
                     (key, s["version"])).fetchall()
    if not pos:
        return 0
    pos = [(pid, json.loads(p)) for pid, p in pos]
    marked = {r[0] for r in db.execute("SELECT date FROM paper_marks WHERE strategy=? AND version=?", (key, s["version"]))}
    last = db.execute("SELECT held FROM paper_marks WHERE strategy=? AND version=? ORDER BY date DESC LIMIT 1",
                      (key, s["version"])).fetchone()
    prev_held = last[0] if last else "cash"
    n = 0
    for i, d in enumerate(done):
        if d in marked or i == 0:
            continue
        live = [(pid, p) for pid, p in pos if p["trade_date"] < d]
        if not live:
            continue
        pid, p = live[-1]
        held, y = p["hold"], done[i - 1]
        a = s["asset"]
        if a not in closes or d not in closes[a] or y not in closes[a] or d not in closes["SPY"] or y not in closes["SPY"]:
            raise RuntimeError(f"{key}: prices missing for {y} or {d}")
        spy_ret = closes["SPY"][d] / closes["SPY"][y] - 1
        asset_ret = closes[a][d] / closes[a][y] - 1
        r_f = rf.get(d, 0.0)
        cost = SWITCH_COST if held != prev_held else 0.0
        ret = (asset_ret if held != "cash" else r_f) - cost
        add_mark(db, key, d, pid, held, ret, spy_ret, cost, {"rf": r_f, "asset_ret": asset_ret})
        prev_held = held
        n += 1
    return n


def _fed(db, keys, alpaca, data_base, cal: list[dict], closes: dict, notes: list) -> int:
    s = STRATEGIES["fed-drift"]
    days = [c["date"] for c in cal]
    now = _now()
    meetings = {r[0] for r in db.execute("SELECT date FROM econ_calendar WHERE event='fomc'")}
    # log upcoming windows
    for m in sorted(meetings):
        md = date.fromisoformat(m)
        if not (now.date() <= md <= now.date() + timedelta(days=FED_LOOKAHEAD_DAYS)) or m not in days:
            continue
        d1 = days[days.index(m) - 1]
        buy = datetime.combine(date.fromisoformat(d1), time(13, 59), ET)
        sell = datetime.combine(md, time(13, 59), ET)
        if db.execute("SELECT 1 FROM paper_positions WHERE strategy='fed-drift' AND version=? AND signal_date=?", (s["version"], d1)).fetchone():
            continue
        try:
            log_position(db, "fed-drift", d1, buy, {"hold": "SPY", "buy_at": _iso(buy), "sell_at": _iso(sell), "decision_day": m}, {})
            notes.append(f"fed-drift: SPY {d1} 2 pm to {m} 2 pm")
        except ValueError:
            skip(db, "fed-drift", d1, "not logged before 1:59 pm the day before")
    # mark finished windows
    n = 0
    marked = {r[0] for r in db.execute("SELECT date FROM paper_marks WHERE strategy='fed-drift' AND version=?", (s["version"],))}
    for pid, p in db.execute("SELECT id, position FROM paper_positions WHERE strategy='fed-drift' AND version=?", (s["version"],)).fetchall():
        p = json.loads(p)
        m = p["decision_day"]
        sell = datetime.fromisoformat(p["sell_at"])
        if m in marked or now < sell + timedelta(minutes=17):
            continue
        if m not in meetings:
            add_mark(db, "fed-drift", m, pid, "void", None, None, 0.0, {"why": "meeting no longer on the Fed calendar"})
            n += 1
            continue
        y = days[days.index(m) - 1]
        if m not in closes["SPY"]:
            continue   # decision day's close not in yet; the evening run marks it
        p0 = _minute_close(keys, alpaca, data_base, "SPY", datetime.fromisoformat(p["buy_at"]))
        p1 = _minute_close(keys, alpaca, data_base, "SPY", sell)
        if p0 is None or p1 is None:
            raise RuntimeError(f"fed-drift {m}: 1:59 pm bar missing")
        ret = p1 / p0 - 1 - 2 * FED_COST
        spy_day = closes["SPY"][m] / closes["SPY"][y] - 1
        add_mark(db, "fed-drift", m, pid, "SPY", ret, spy_day, 2 * FED_COST, {"buy_price": p0, "sell_price": p1})
        notes.append(f"fed-drift {m}: {ret * 100:+.2f}%")
        n += 1
    return n


def job() -> int:
    from options_collector import ALPACA_DATA, ALPACA_TRADE, alpaca, connect, finish_run, load_keys, start_run
    db = connect()
    ensure(db)
    run_id = start_run(db, "paper")
    notes, n = [], 0
    try:
        keys = load_keys()
        notes.append(_refresh_tbill(db))
        today = _now().date()
        cal = _calendar(keys, alpaca, ALPACA_TRADE, date(2025, 1, 1), today + timedelta(days=FED_LOOKAHEAD_DAYS + 10))
        now = _now()
        done = [c["date"] for c in cal if c["close"] + timedelta(minutes=16) <= now]
        closes = {sym: _daily_closes(keys, alpaca, ALPACA_DATA, sym, date(2025, 1, 1)) for sym in ("SPY", "SSO")}
        done = [d for d in done if d in closes["SPY"] and d in closes["SSO"]]
        rf = _rf_by_day(db, done)
        for key in ("lev-trend", "trend10"):
            _trend_signals(db, key, cal, done, closes, notes)
            n += _trend_marks(db, key, done, closes, rf)
        n += _fed(db, keys, alpaca, ALPACA_DATA, cal, closes, notes)
        v = verify(db)
        if not v["ok"]:
            raise RuntimeError("hash check failed: " + "; ".join(v["problems"][:3]))
        detail = f"marks={n}; " + "; ".join(notes)
        finish_run(db, run_id, "ok", n, detail)
        print(f"[{_now():%Y-%m-%d %H:%M:%S}] paper run {run_id}: ok {detail}")
        return 0
    except Exception as ex:
        import traceback
        finish_run(db, run_id, "failed", n, f"{ex} {traceback.format_exc()[-400:]}")
        print(f"[{_now():%Y-%m-%d %H:%M:%S}] paper run {run_id}: FAILED {ex}")
        return 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "job"
    if cmd == "job":
        return job()
    from options_collector import connect
    db = connect()
    ensure(db)
    if cmd == "status":
        s = summary(db)
        for e in s["strategies"]:
            e.pop("curve", None)
        print(json.dumps(s, indent=1, default=str))
    elif cmd == "verify":
        print(json.dumps(verify(db), indent=1))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
