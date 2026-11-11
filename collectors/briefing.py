"""Daily update: a 10 am phone notification answering "what matters this morning?"

Runs every day at 10:00 (launchd, see install.sh) on the same ntfy channel as the watchdog's alerts.
Plain rules, no LLM. Every move is shown next to a normal day's move (average size of the last 20
daily moves), and the headline (the notification's title) is the 2-3 moves that are biggest
relative to their normal; under 1.5x normal counts as a quiet morning.

Trading days:
  markets   SPY and the Mag 7 (average, best, worst, plus any name moving 2.5x its own normal):
            live price from Alpaca IEX vs the previous official close (Alpaca SIP daily bars).
            S&P 500 futures (ES) overnight: yesterday's 4 pm to today's 9:30 am, from Yahoo 30-min bars.
            WTI (CL), Brent (BZ), 10-year yield (^TNX, in basis points), VIX (^VIX, in points):
            Yahoo, the only free source for these; today's price vs the previous settle/close.
            Futures are always compared within one contract (see front_contract): Yahoo's continuous
            series jumps when a contract expires, which once showed Brent -10.8% on a -7.5% day.
  new bets  the 3 biggest open-interest increases overnight across the watchlist (official OCC data)
  events    the 3 biggest 24h odds moves on liquid Polymarket markets (same rules as the Events tab)
  system    one line; problems go to the top
Weekends and market holidays: system line and events only.

Usage: briefing.py          build and send
       briefing.py dry      print it, send nothing
       FORCE=1 ...          treat now as a trading day (for testing after hours)
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import warnings
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from options_collector import (ALPACA_DATA, ALPACA_TRADE, ET, alpaca, connect, finish_run, load_keys, start_run)
from watchdog import STATE_PATH, ntfy_settings, send_ntfy

MAG7 = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
NORMAL_DAYS = 20
HEADLINE_RATIO = 1.5  # a move this many times its normal size makes the headline
OUTLIER_RATIO = 2.5   # a single Mag 7 name this unusual gets called out


class Move:
    def __init__(self, name: str, text: str, change: float, normal: float | None, headline: str):
        self.name, self.text, self.change, self.normal, self.headline = name, text, change, normal, headline

    @property
    def ratio(self) -> float:
        return abs(self.change) / self.normal if self.normal else 0.0

    def line(self, unit: str = "%") -> str:
        normal = f" [{self.normal:.1f}{unit}]" if self.normal is not None else ""
        flag = f"  <- {self.ratio:.0f}x normal" if self.ratio >= HEADLINE_RATIO else ""
        return f"{self.text}{normal}{flag}"


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


def normal_of(changes: list[float]) -> float | None:
    recent = [abs(c) for c in changes[-NORMAL_DAYS:]]
    return mean(recent) if len(recent) >= 10 else None


# ---------- market data

def stock_moves(keys: dict, today: date) -> tuple[dict[str, float], dict[str, float], dict[str, list[float]], date]:
    """price now, % change vs previous close, past daily % changes, previous trading day."""
    syms = ["SPY", *MAG7]
    end = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
    bars = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=",".join(syms), timeframe="1Day",
                  start=(today - timedelta(days=50)).isoformat(), end=end, feed="sip", adjustment="all",
                  limit=10000)["bars"]
    snaps = alpaca(ALPACA_DATA, "/v2/stocks/snapshots", keys, symbols=",".join(syms), feed="iex")
    price, change, history = {}, {}, {}
    prev_day = None
    for s in syms:
        closes = [(b["t"][:10], b["c"]) for b in bars.get(s, []) if b["t"][:10] < today.isoformat()]
        if len(closes) < 2 or not snaps.get(s):
            continue
        prev_day = date.fromisoformat(closes[-1][0])
        price[s] = snaps[s]["latestTrade"]["p"]
        change[s] = pct(price[s], closes[-1][1])
        history[s] = [pct(closes[i][1], closes[i - 1][1]) for i in range(1, len(closes))]
    return price, change, history, prev_day


def yahoo_history(ticker: str, period: str, interval: str):
    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # expired contracts we probe are expected 404s
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return yf.Ticker(ticker).history(period=period, interval=interval)["Close"].dropna()


def front_contract(root: str, exchange: str, months: str, today: date) -> str:
    """The specific futures contract Yahoo's continuous `root=F` currently points at, e.g. BZF27.NYM.

    The continuous series switches contracts when one expires (Brent and WTI monthly, ES quarterly),
    so comparing its prices across a switch shows a fake move. Comparing one contract with itself doesn't.
    Falls back to the continuous series if no contract matches."""
    cont = yahoo_history(f"{root}=F", "5d", "1d")
    for ahead in range(6):
        y, m = today.year + (today.month - 1 + ahead) // 12, (today.month - 1 + ahead) % 12 + 1
        code = "FGHJKMNQUVXZ"[m - 1]
        if code not in months:
            continue
        sym = f"{root}{code}{y % 100:02d}.{exchange}"
        try:
            h = yahoo_history(sym, "5d", "1d")
        except Exception:
            continue
        if len(h) and h.index[-1].date() == cont.index[-1].date() and abs(h.iloc[-1] - cont.iloc[-1]) < 0.02:
            return sym
    return f"{root}=F"


def yahoo_daily(ticker: str, today: date) -> tuple[float, float, list[float]]:
    """latest price, previous close, past daily closes (excluding today)."""
    h = yahoo_history(ticker, "3mo", "1d")
    closes = [(ix.date(), float(v)) for ix, v in h.items()]
    past = [c for d, c in closes if d < today]
    last = closes[-1][1] if closes[-1][0] == today else past[-1]
    return last, past[-1], past


def es_overnight(today: date) -> tuple[float, list[float]]:
    """S&P 500 futures % move from the previous session's 4 pm to today's 9:30 am, plus past ones."""
    h = yahoo_history(front_contract("ES", "CME", "HMUZ", today), "1mo", "30m")
    at_close, at_open = {}, {}  # date -> price
    for ix, v in h.items():
        t = ix.tz_convert(ET)
        if (t.hour, t.minute) == (15, 30):  # bar ending 16:00
            at_close[t.date()] = float(v)
        elif (t.hour, t.minute) == (9, 0):  # bar ending 09:30
            at_open[t.date()] = float(v)
    moves = {}
    for d in sorted(at_open):
        before = [c for c in at_close if c < d]
        if before:
            moves[d] = pct(at_open[d], at_close[max(before)])
    if today not in moves:
        raise RuntimeError("no 9:30 futures price yet")
    return moves[today], [m for d, m in sorted(moves.items()) if d < today]


def markets(keys: dict, today: date) -> tuple[list[str], list[Move], date | None]:
    lines, moves, prev_day = [], [], None
    try:
        price, change, history, prev_day = stock_moves(keys, today)
        spy = Move("SPY", f"SPY {price['SPY']:.2f} {change['SPY']:+.1f}%", change["SPY"],
                   normal_of(history["SPY"]), f"SPY {change['SPY']:+.1f}%")
        moves.append(spy)
        lines.append(spy.line())
    except Exception as e:
        price, change, history = {}, {}, {}
        lines.append(f"SPY / Mag 7 unavailable ({str(e)[:80]})")

    try:
        es, es_hist = es_overnight(today)
        m = Move("ES", f"S&P futures overnight {es:+.1f}% (4 pm to 9:30 am)", es, normal_of(es_hist),
                 f"S&P futures {es:+.1f}% overnight")
        moves.append(m)
        lines.append(m.line())
    except Exception as e:
        lines.append(f"S&P futures unavailable ({str(e)[:80]})")

    mag = [s for s in MAG7 if s in change]
    if len(mag) == len(MAG7):
        avg = mean(change[s] for s in mag)
        n = min(len(history[s]) for s in mag)
        avg_hist = [mean(history[s][-n + i] for s in mag) for i in range(n)]
        best, worst = max(mag, key=change.get), min(mag, key=change.get)
        m = Move("MAG7", f"Mag 7 avg {avg:+.1f}%", avg, normal_of(avg_hist), f"Mag 7 {avg:+.1f}%")
        moves.append(m)
        extra = [f"{s} {change[s]:+.1f}% ({abs(change[s]) / normal_of(history[s]):.0f}x its normal)"
                 for s in mag if s not in (best, worst) and normal_of(history[s])
                 and abs(change[s]) / normal_of(history[s]) >= OUTLIER_RATIO]
        lines.append(m.line() + f"\n  best {best} {change[best]:+.1f}%, worst {worst} {change[worst]:+.1f}%"
                     + "".join(f"\n  {x}" for x in extra))
        for s in mag:
            nm = normal_of(history[s])
            if nm and abs(change[s]) / nm >= OUTLIER_RATIO:
                moves.append(Move(s, "", change[s], nm, f"{s} {change[s]:+.1f}%"))

    for ticker, label, kind in (("CL", "WTI", "$"), ("BZ", "Brent", "$"), ("^TNX", "10Y", "bp"), ("^VIX", "VIX", "pts")):
        try:
            if kind == "$":
                ticker = front_contract(ticker, "NYM", "FGHJKMNQUVXZ", today)
            last, prev, past = yahoo_daily(ticker, today)
            if kind == "$":
                ch = pct(last, prev)
                m = Move(label, f"{label} ${last:.2f} {ch:+.1f}%", ch,
                         normal_of([pct(past[i], past[i - 1]) for i in range(1, len(past))]), f"{label} {ch:+.1f}%")
                lines.append(m.line())
            elif kind == "bp":
                ch = (last - prev) * 100
                m = Move(label, f"{label} {last:.2f}% {ch:+.0f} bp", ch,
                         normal_of([(past[i] - past[i - 1]) * 100 for i in range(1, len(past))]), f"10Y {ch:+.0f} bp")
                lines.append(m.line(" bp"))
            else:
                ch = last - prev
                m = Move(label, f"{label} {last:.1f} {ch:+.1f}", ch,
                         normal_of([past[i] - past[i - 1] for i in range(1, len(past))]), f"VIX {ch:+.1f}")
                lines.append(m.line(" pts"))
            moves.append(m)
        except Exception as e:
            lines.append(f"{label} unavailable ({str(e)[:80]})")
    return lines, moves, prev_day


# ---------- your data

def new_bets(db, today: date) -> list[str]:
    prev = db.execute("SELECT MAX(date) FROM open_interest WHERE date < ?", (today.isoformat(),)).fetchone()[0]
    if not prev:
        return []

    def load(d):
        return {(u, e, k): (c or 0, p or 0) for u, e, k, c, p in db.execute(
            "SELECT underlying, expiration, strike, call_oi, put_oi FROM open_interest "
            "WHERE date = ? AND product = underlying", (d,))}
    now, before = load(today.isoformat()), load(prev)
    if not now:
        return ["(today's open interest isn't in yet)"]
    adds = []
    for key, (c, p) in now.items():
        c0, p0 = before.get(key, (0, 0))
        adds += [(c - c0, key, "calls"), (p - p0, key, "puts")]
    out = []
    for n, (u, e, k), side in sorted(adds, reverse=True)[:3]:
        exp = date.fromisoformat(e)
        out.append(f"{u} {exp:%b %-d}{'' if exp.year == today.year else f' {exp.year}'} ${k:g} {side} +{n / 1000:.0f}K")
    return out


def event_moves(db) -> list[str]:
    latest = db.execute("SELECT MAX(fetched_at) FROM poly_snapshots").fetchone()[0]
    if not latest:
        return []
    near = (datetime.now(ET) + timedelta(hours=48)).astimezone(timezone.utc).isoformat()
    rows = db.execute("""SELECT m.question, s.price, s.change_1d FROM poly_snapshots s
                         JOIN poly_markets m ON m.id = s.market_id JOIN poly_events e ON e.id = m.event_id
                         WHERE s.fetched_at = ? AND s.volume_24h >= 10000 AND s.change_1d IS NOT NULL
                           AND e.grp != 'other' AND NOT (m.end_date IS NOT NULL AND m.end_date <= ?)
                         ORDER BY ABS(s.change_1d) DESC LIMIT 3""", (latest, near)).fetchall()
    return [f"{q[:80]}: {round((p - c) * 100)}% -> {round(p * 100)}%" for q, p, c in rows]


def system_line(db, t: datetime) -> tuple[str, bool]:
    since = (t - timedelta(hours=24)).isoformat(timespec="seconds")
    bad = db.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ? AND job NOT IN ('backfill', 'briefing') "
                     "AND status IN ('failed', 'partial', 'stopped')", (since,)).fetchone()[0]
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    problems = [v["text"].split(":")[0] for v in state.get("open", {}).values()]
    stale = not state.get("checked_at") or t - datetime.fromisoformat(state["checked_at"]) > timedelta(hours=1)
    if not (problems or bad or stale):
        return "SYSTEM: all good", True
    parts = problems[:4] + ([f"{bad} failed run(s) in 24h"] if bad else []) + (["watchdog not checking"] if stale else [])
    return "SYSTEM NEEDS A LOOK: " + "; ".join(parts), False


# ---------- assemble

def build(db) -> tuple[str, str]:
    t = datetime.now(ET)
    keys = load_keys()
    trading = bool(alpaca(ALPACA_TRADE, "/v2/clock", keys).get("is_open")) or os.environ.get("FORCE") == "1"
    system, healthy = system_line(db, t)
    events = event_moves(db)
    events_block = "EVENTS (biggest 24h odds moves)\n" + ("\n".join(events) if events else "nothing notable")

    if not trading:
        title = ("Markets closed" if healthy else "System needs a look") + f" | {t:%a %b %-d}"
        return title, f"{system}\n\n{events_block}"

    lines, moves, _ = markets(keys, t.date())
    big = sorted((m for m in moves if m.ratio >= HEADLINE_RATIO), key=lambda m: -m.ratio)[:3]
    title = (" | ".join(f"{m.headline} ({m.ratio:.0f}x)" for m in big) if big else "Quiet morning: no unusual moves")
    if not healthy:
        title = "SYSTEM ISSUE | " + title
    bets = new_bets(db, t.date())
    body = ([system, ""] if not healthy else []) + [
        "MARKETS vs prior close [a normal day's move]", *lines, "",
        "NEW OPTION BETS (open interest added overnight)", *(bets or ["none yet"]), "",
        events_block] + (["", system] if healthy else [])
    return title, "\n".join(body)


def main() -> int:
    dry = len(sys.argv) > 1 and sys.argv[1] == "dry"
    db = connect()
    if dry:
        title, body = build(db)
        print(f"TITLE: {title}\n\n{body}")
        return 0
    run_id = start_run(db, "briefing")
    try:
        title, body = build(db)
        send_ntfy(ntfy_settings(), title, body, priority="default", tags="chart_with_upwards_trend")
        result = ("ok", 1, title)
    except Exception as e:
        result = ("failed", 0, f"{e}\n{traceback.format_exc()[-1500:]}")
    finish_run(db, run_id, *result)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] briefing run {run_id}: {result[0]} {result[2][:300]}")
    return 0 if result[0] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
