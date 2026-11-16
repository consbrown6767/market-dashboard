"""Local dashboard server: serves dashboard/static and a small JSON API over ~/MarketData/options.db.

Read-only: opens the database with mode=ro and never writes. Collectors are the only writers.
(The exceptions, outside the database: saving or removing a spread edits shared/pairs.json, and
editing a watchlist edits shared/watchlists.json.)
Listens on 127.0.0.1 only (not reachable from other machines).

Run:  ~/MarketData/.venv/bin/python dashboard/server.py      then open http://127.0.0.1:8765
(install.sh also runs it as an always-on background job.)
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
import sys
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path.home() / "MarketData" / "app"))  # reuse the collectors' API plumbing
from options_collector import (ALPACA_DATA, OCC_SERIES_URL, alpaca, http_get, load_keys,  # noqa: E402
                               parse_occ, parse_option_symbol)
import ledger  # noqa: E402  (only its read-only scoring and checking parts are used here)
import paper_record  # noqa: E402  (only its read-only summary and checking parts are used here)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import long_history  # noqa: E402  (Yahoo history before 2016 for the Spreads tab)

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
PROJECT = HERE.parent
DB_PATH = Path.home() / "MarketData" / "options.db"
POLITICS_DATA = Path.home() / "MarketData" / "politics" / "outputs" / "data.json"
POLITICS_SUMMARY = POLITICS_DATA.with_name("summary.json")
PORT = int(os.environ.get("PORT", "8765"))
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}
GROUP_ORDER = ["macro", "geopolitics", "business", "politics", "crypto", "other"]


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn, sql, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


# ---------- status

def api_health(q):
    with db() as conn:
        jobs = rows(conn, """SELECT r.job, r.started_at, r.finished_at, r.status, r.rows, substr(r.detail, 1, 300) AS detail
                             FROM runs r JOIN (SELECT job, MAX(id) id FROM runs GROUP BY job) l ON l.id = r.id
                             ORDER BY r.job""")
        # The 5-minute strategy job would otherwise fill the list; its latest run is in `jobs`.
        recent = rows(conn, "SELECT id, job, started_at, status, rows, substr(detail,1,160) AS detail FROM runs WHERE job != 'strategy' ORDER BY id DESC LIMIT 25")
    return {"now": datetime.now(ET).isoformat(timespec="seconds"), "db_mb": round(DB_PATH.stat().st_size / 1e6, 1),
            "jobs": jobs, "recent": recent}


# ---------- options tab (data status + market positioning; strategy plugs in later)

def api_options(q):
    with db() as conn:
        oi = rows(conn, """SELECT underlying, MAX(date) AS date, COUNT(*) AS strikes, MAX(from_backup) AS backup
                           FROM open_interest WHERE date = (SELECT MAX(date) FROM open_interest) AND product = underlying
                           GROUP BY underlying""")
        last_run = conn.execute("SELECT MAX(run_id) FROM stock_snapshots").fetchone()[0]
        stocks = rows(conn, """SELECT s.symbol, s.ts, s.price, s.prev_close, s.volume, s.volume_source,
                                      (SELECT COUNT(*) FROM option_quotes o WHERE o.run_id = s.run_id AND o.underlying = s.symbol) AS contracts
                               FROM stock_snapshots s WHERE s.run_id = ?""", last_run)
        gamma = rows(conn, "SELECT date, spx, gex, dix FROM market_gamma WHERE date >= ? ORDER BY date",
                     (date.today() - timedelta(days=400)).isoformat()) if table_exists(conn, "market_gamma") else []
        cftc = rows(conn, """SELECT n.* FROM cftc_net n JOIN (SELECT code, MAX(report_date) d FROM cftc_tff GROUP BY code) l
                             ON l.code = n.code AND l.d = n.report_date ORDER BY n.contract""") if table_exists(conn, "cftc_tff") else []
        cftc_hist = rows(conn, """SELECT report_date, lev_money_net_pct_oi, asset_mgr_net_pct_oi FROM cftc_net
                                  WHERE code = '13874+' AND report_date >= ? ORDER BY report_date""",
                         (date.today() - timedelta(days=3 * 365)).isoformat()) if table_exists(conn, "cftc_tff") else []
    by_sym = {o["underlying"]: o for o in oi}
    for s in stocks:
        s.update({k: by_sym.get(s["symbol"], {}).get(k) for k in ("date", "strikes", "backup")})
    return {"stocks": sorted(stocks, key=lambda s: s["symbol"]), "gamma": gamma, "cftc": cftc, "cftc_spx_history": cftc_hist}


def api_option_detail(q):
    """One symbol's options picture from the official views: open interest by strike (OCC, as of the
    last close), and the latest Alpaca snapshot (quotes, IV, volume). Expired contracts are dropped
    (OCC can still list the last expiration). Raw positioning only; no strategy rules applied."""
    sym = q.get("symbol", [""])[0].upper()
    today = datetime.now(ET).date().isoformat()
    with db() as conn:
        snap = conn.execute("SELECT run_id, ts, price, prev_close, volume FROM stock_snapshots WHERE symbol = ? ORDER BY run_id DESC LIMIT 1",
                            (sym,)).fetchone()
        if not snap:
            return {"symbol": sym, "error": "no snapshot yet"}
        price = snap["price"]
        oi_date = conn.execute("SELECT MAX(date) FROM open_interest WHERE underlying = ?", (sym,)).fetchone()[0]
        oi = rows(conn, """SELECT expiration, strike, call_oi, put_oi FROM open_interest
                           WHERE underlying = ? AND product = underlying AND date = ? AND expiration >= ?
                             AND expiration <= ? AND strike BETWEEN ? AND ?
                           ORDER BY expiration, strike""",
                  sym, oi_date, today, (date.today() + timedelta(days=60)).isoformat(), price * 0.7, price * 1.3)
        quotes = rows(conn, """SELECT expiration, type, strike, bid, ask, mid, last, volume, iv, delta, gamma
                               FROM option_quotes WHERE run_id = ? AND underlying = ? AND expiration >= ?
                               ORDER BY expiration, strike""", snap["run_id"], sym, today)

    # Per-expiration summary: OI and volume totals, ATM IV, implied move (ATM straddle / price).
    exps: dict[str, dict] = {}
    for r in oi:
        e = exps.setdefault(r["expiration"], {"expiration": r["expiration"], "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0})
        e["call_oi"] += r["call_oi"] or 0
        e["put_oi"] += r["put_oi"] or 0
    by_exp: dict[str, list] = {}
    for qt in quotes:
        by_exp.setdefault(qt["expiration"], []).append(qt)
        e = exps.setdefault(qt["expiration"], {"expiration": qt["expiration"], "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0})
        e["call_vol" if qt["type"] == "call" else "put_vol"] += qt["volume"] or 0
    for e in exps.values():
        e["days"] = (date.fromisoformat(e["expiration"]) - date.today()).days
        qs = by_exp.get(e["expiration"], [])
        if qs:
            atm = min({x["strike"] for x in qs}, key=lambda k: abs(k - price))
            c = next((x for x in qs if x["strike"] == atm and x["type"] == "call"), None)
            p = next((x for x in qs if x["strike"] == atm and x["type"] == "put"), None)
            ivs = [x["iv"] for x in (c, p) if x and x["iv"]]
            e["atm_strike"] = atm
            e["atm_iv"] = sum(ivs) / len(ivs) if ivs else None
            e["implied_move"] = (c["mid"] + p["mid"]) / price * 100 if c and p and c["mid"] and p["mid"] else None
    return {"symbol": sym, "price": price, "prev_close": snap["prev_close"], "snapshot_ts": snap["ts"],
            "stock_volume": snap["volume"], "oi_date": oi_date, "oi": oi, "quotes": quotes,
            "expirations": sorted(exps.values(), key=lambda e: e["expiration"])}


# ---------- on-demand market data (live from Alpaca/OCC when you click; not stored)
# Alpaca's free plan: stock bars are full-market (SIP) but must end 15+ minutes ago; option bars
# likewise; option chain snapshots ("indicative" feed) are near live. Cached briefly so clicking
# around doesn't hit the 200-requests-a-minute limit.

_cache: dict = {}


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and hit[0] > datetime.now().timestamp():
        return hit[1]
    val = fn()
    _cache[key] = (datetime.now().timestamp() + ttl, val)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:250]:
            _cache.pop(k, None)
    return val


def _delayed_end() -> str:
    return (datetime.now(ET) - timedelta(minutes=16)).isoformat()


def _bars(path: str, symbol: str, timeframe: str, start: datetime, **extra) -> list[dict]:
    keys, out, token = load_keys(), [], None
    while True:
        b = alpaca(ALPACA_DATA, path, keys, symbols=symbol, timeframe=timeframe, start=start.isoformat(),
                   end=_delayed_end(), limit=10000, page_token=token, **extra)
        out += (b.get("bars") or {}).get(symbol, [])
        token = b.get("next_page_token")
        if not token:
            return out


def _chart_points(bars: list[dict], intraday: bool) -> list[dict]:
    """Lightweight Charts shows times in UTC, so intraday times are shifted to New York wall-clock."""
    pts = []
    for x in bars:
        t = datetime.fromisoformat(x["t"].replace("Z", "+00:00"))
        when = int(t.timestamp() + t.astimezone(ET).utcoffset().total_seconds()) if intraday else x["t"][:10]
        pts.append({"time": when, "open": x["o"], "high": x["h"], "low": x["l"], "close": x["c"], "volume": x["v"]})
    return pts


STOCK_RANGES = {  # range -> (timeframe, lookback days, intraday)
    "1D": ("5Min", 4, True), "1W": ("15Min", 8, True), "1M": ("1Hour", 31, True),
    "3M": ("1Day", 92, False), "1Y": ("1Day", 366, False), "5Y": ("1Week", 5 * 366, False),
}


def api_stock_bars(q):
    sym, rng = q.get("symbol", [""])[0].upper(), q.get("range", ["3M"])[0]
    tf, days, intraday = STOCK_RANGES.get(rng, STOCK_RANGES["3M"])

    def fetch():
        bars = _bars("/v2/stocks/bars", sym, tf, datetime.now(ET) - timedelta(days=days), feed="sip", adjustment="all")
        if rng == "1D" and bars:  # just the latest session (including pre/post market)
            last = datetime.fromisoformat(bars[-1]["t"].replace("Z", "+00:00")).astimezone(ET).date()
            bars = [x for x in bars if datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(ET).date() == last]
        return {"symbol": sym, "range": rng, "timeframe": tf, "intraday": intraday, "bars": _chart_points(bars, intraday),
                "as_of": _delayed_end()}
    return cached(("stock", sym, rng), 60, fetch)


def _occ_oi(sym: str) -> tuple[str | None, dict]:
    """{(expiration, strike): (call_oi, put_oi)} from the database, or live from OCC for symbols not collected."""
    with db() as conn:
        d = conn.execute("SELECT MAX(date) FROM open_interest WHERE underlying = ?", (sym,)).fetchone()[0]
        if d:
            return d, {(r["expiration"], r["strike"]): (r["call_oi"], r["put_oi"]) for r in
                       conn.execute("SELECT expiration, strike, call_oi, put_oi FROM open_interest WHERE underlying = ? AND product = underlying AND date = ?", (sym, d))}

    def live():
        text = http_get(f"{OCC_SERIES_URL}?symbolType=U&symbol={sym}").decode("utf-8", "replace")
        return {(e, k): (c, p) for prod, _, e, k, c, p, _ in parse_occ(text, sym) if prod == sym}
    return "live", cached(("occ", sym), 3600, live)


def api_chain_expirations(q):
    sym = q.get("symbol", [""])[0].upper()
    today = date.today().isoformat()
    _, oi = _occ_oi(sym)
    exps = sorted({e for e, _ in oi if e >= today})
    return {"symbol": sym, "expirations": [{"expiration": e, "days": (date.fromisoformat(e) - date.today()).days} for e in exps]}


def api_chain(q):
    sym, exp = q.get("symbol", [""])[0].upper(), q.get("exp", [""])[0]

    def fetch():
        keys, snaps, token = load_keys(), {}, None
        while True:
            b = alpaca(ALPACA_DATA, f"/v1beta1/options/snapshots/{sym}", keys, feed="indicative",
                       expiration_date=exp, limit=1000, page_token=token)
            snaps.update(b.get("snapshots") or {})
            token = b.get("next_page_token")
            if not token:
                break
        spot = alpaca(ALPACA_DATA, "/v2/stocks/snapshots", keys, symbols=sym, feed="iex").get(sym) or {}
        return snaps, (spot.get("latestTrade") or {}).get("p")
    snaps, price = cached(("chain", sym, exp), 45, fetch)
    oi_date, oi = _occ_oi(sym)
    strikes: dict[float, dict] = {}
    for osym, s in snaps.items():
        parsed = parse_option_symbol(osym)
        if not parsed or parsed[0] != sym:  # skip split-adjusted roots
            continue
        _, e, typ, k = parsed
        qt, tr, bar, g = (s.get(x) or {} for x in ("latestQuote", "latestTrade", "dailyBar", "greeks"))
        bid, ask = qt.get("bp"), qt.get("ap")
        strikes.setdefault(k, {"strike": k})[typ] = {
            "symbol": osym, "bid": bid, "ask": ask, "mid": (bid + ask) / 2 if bid and ask else None,
            "last": tr.get("p"), "volume": bar.get("v"), "iv": s.get("impliedVolatility"),
            "delta": g.get("delta"), "gamma": g.get("gamma"), "theta": g.get("theta"), "vega": g.get("vega"),
            "oi": (oi.get((e, k)) or (None, None))[0 if typ == "call" else 1], "quote_ts": qt.get("t")}
    return {"symbol": sym, "expiration": exp, "days": (date.fromisoformat(exp) - date.today()).days, "price": price,
            "oi_date": oi_date, "rows": sorted(strikes.values(), key=lambda r: r["strike"]),
            "fetched_at": datetime.now(ET).isoformat(timespec="seconds")}


OPTION_RANGES = {"1D": ("5Min", 4, True), "1W": ("30Min", 8, True), "1M": ("1Hour", 31, True), "ALL": ("1Day", 800, False)}


def api_option_bars(q):
    contract, rng = q.get("contract", [""])[0].upper(), q.get("range", ["1W"])[0]
    tf, days, intraday = OPTION_RANGES.get(rng, OPTION_RANGES["1W"])

    def fetch():
        start = max(datetime.now(ET) - timedelta(days=days), datetime(2024, 2, 1, tzinfo=ET))  # free history starts Feb 2024
        bars = _bars("/v1beta1/options/bars", contract, tf, start)
        if rng == "1D" and bars:
            last = datetime.fromisoformat(bars[-1]["t"].replace("Z", "+00:00")).astimezone(ET).date()
            bars = [x for x in bars if datetime.fromisoformat(x["t"].replace("Z", "+00:00")).astimezone(ET).date() == last]
        return {"contract": contract, "range": rng, "timeframe": tf, "intraday": intraday,
                "bars": _chart_points(bars, intraday), "as_of": _delayed_end()}
    return cached(("optbars", contract, rng), 60, fetch)


# ---------- spreads tab
# Any two symbols can be compared. Legs the spreads collector already stores (pairs.json) come from
# daily_bars_adj; any other symbol is fetched from Alpaca on demand (same adjusted SIP bars, 2016 on)
# and kept in memory for a few minutes. Saving a pair adds it to pairs.json so the collector stores it.

PAIRS_PATH = PROJECT / "shared" / "pairs.json"
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
LIVE_TTL = 10 * 60
_live: dict[str, tuple[float, str, dict]] = {}  # symbol -> (fetched epoch, fetched_at iso, {date: close})
_pairs_lock = threading.Lock()


def load_pairs() -> list[dict]:
    return json.loads(PAIRS_PATH.read_text())["pairs"]


def pct(a, b):
    return (a / b - 1) * 100 if a and b else None


def symbol(q, key) -> str:
    sym = q.get(key, [""])[0].strip().upper()
    if not SYMBOL.match(sym):
        raise ValueError(f"not a valid ticker: {sym or '(blank)'}")
    return sym


def closes(conn, sym: str) -> tuple[dict, str | None]:
    """{date: adjusted close} for one symbol, and when it was fetched."""
    stored = {r["date"]: r["close"] for r in conn.execute("SELECT date, close FROM daily_bars_adj WHERE symbol = ?", (sym,))}
    if stored:
        return stored, conn.execute("SELECT MAX(fetched_at) FROM daily_bars_adj WHERE symbol = ?", (sym,)).fetchone()[0]
    hit = _live.get(sym)
    if hit and time.time() - hit[0] < LIVE_TTL:
        return hit[2], hit[1]
    now = datetime.now(ET)
    keys, out, token = load_keys(), {}, None
    while True:
        b = alpaca(ALPACA_DATA, "/v2/stocks/bars", keys, symbols=sym, timeframe="1Day", feed="sip", adjustment="all",
                   start="2016-01-01", end=(now - timedelta(minutes=16)).isoformat(), limit=10000, page_token=token)
        out.update({x["t"][:10]: x["c"] for x in (b.get("bars") or {}).get(sym, [])})
        token = b.get("next_page_token")
        if not token:
            break
    if not out:
        raise ValueError(f"no price history for {sym} (check the ticker)")
    _live[sym] = (time.time(), now.isoformat(timespec="seconds"), out)
    return out, _live[sym][1]


def api_pairs(q):
    return {"pairs": load_pairs()}


def api_pair(q):
    pairs = load_pairs()
    if "long" in q or "short" in q:
        long, short = symbol(q, "long"), symbol(q, "short")
        if long == short:
            raise ValueError("pick two different tickers")
        pair = next((p for p in pairs if p["long"] == long and p["short"] == short), None) or {
            "id": f"{long}-{short}", "long": long, "short": short, "name": f"{long} vs {short}", "kind": "custom",
            "reads": f"Rising: {long} is outperforming {short}. Falling: {short} is outperforming {long}."}
    else:
        pair = next((p for p in pairs if p["id"] == q.get("id", [""])[0]), pairs[0])
    pair = dict(pair, saved=any(p["id"] == pair["id"] for p in pairs))
    legs, notes = {}, []
    with db() as conn:
        for leg in ("long", "short"):
            sym = pair[leg]
            try:
                recent, fetched_at = closes(conn, sym)
            except ValueError:  # not on Alpaca at all: Yahoo alone, if it knows the ticker
                recent, fetched_at = {}, None
            full, joined, err = long_history.extend(sym, recent)
            if not full:
                raise ValueError(f"no price history for {sym} (check the ticker)")
            if err:
                notes.append(err)
            legs[leg] = (full, fetched_at, joined)
    (a, fa, ja), (b, fb, jb) = legs["long"], legs["short"]
    series = [{"date": d, "long": a[d], "short": b[d], "ratio": a[d] / b[d]} for d in sorted(a.keys() & b.keys()) if b[d]]
    fetched = min(f for f in (fa, fb) if f) if fa or fb else None
    if not series:
        return {"pair": pair, "series": [], "error": f"{pair['long']} and {pair['short']} have no trading days in common"}

    ratios = [r["ratio"] for r in series]
    for i, r in enumerate(series):  # moving averages of the ratio
        for n in (50, 200):
            r[f"ma{n}"] = sum(ratios[i - n + 1:i + 1]) / n if i >= n - 1 else None

    last, dates = series[-1], [r["date"] for r in series]
    year = ratios[-252:]
    mean = sum(year) / len(year)
    sd = math.sqrt(sum((x - mean) ** 2 for x in year) / len(year))

    def back(days=None, since=None):
        """Row at (or just before) a date `days` calendar days ago, or the last row before `since`."""
        target = since or (date.fromisoformat(last["date"]) - timedelta(days=days)).isoformat()
        idx = max(i for i, d in enumerate(dates) if d <= target) if dates[0] <= target else 0
        return series[idx]

    returns = []
    for label, kw in (("1D", {"days": 1}), ("1W", {"days": 7}), ("1M", {"days": 30}), ("3M", {"days": 91}),
                      ("YTD", {"since": f"{last['date'][:4]}-01-01"}), ("1Y", {"days": 365}), ("3Y", {"days": 3 * 365}),
                      ("5Y", {"days": 5 * 365}), ("10Y", {"days": 10 * 365}), ("20Y", {"days": 20 * 365})):
        if label.endswith("Y") and label != "1Y" and (date.fromisoformat(last["date"]) - timedelta(days=kw["days"])).isoformat() < dates[0]:
            continue  # not enough shared history for this period
        ref = series[-2] if label == "1D" else back(**kw)
        returns.append({"label": label, "long": pct(last["long"], ref["long"]), "short": pct(last["short"], ref["short"]),
                        "spread": pct(last["ratio"], ref["ratio"])})
    stats = {
        "date": last["date"], "fetched_at": fetched, "ratio": last["ratio"],
        "vs_ma50": pct(last["ratio"], last["ma50"]), "vs_ma200": pct(last["ratio"], last["ma200"]),
        "zscore_1y": (last["ratio"] - mean) / sd if sd else None,
        "percentile_1y": 100 * sum(1 for x in year if x <= last["ratio"]) / len(year),
        "high_1y": max(year), "low_1y": min(year),
        "from_high_1y": pct(last["ratio"], max(year)),
    }
    # Where Yahoo's older history meets Alpaca's, per leg, and where each leg's own history begins.
    history = {"joins": {pair["long"]: ja, pair["short"]: jb}, "starts": {pair["long"]: min(a), pair["short"]: min(b)},
               "notes": notes}
    return {"pair": pair, "series": series, "stats": stats, "returns": returns, "history": history}


def api_save_pair(body):
    """Add a pair to pairs.json (the spreads collector stores its legs from its next run) or remove one."""
    with _pairs_lock:
        data = json.loads(PAIRS_PATH.read_text())
        if body.get("remove"):
            data["pairs"] = [p for p in data["pairs"] if p["id"] != body["remove"]]
        else:
            q = {"long": [body.get("long", "")], "short": [body.get("short", "")]}
            long, short = symbol(q, "long"), symbol(q, "short")
            pid = f"{long}-{short}"
            if not any(p["id"] == pid for p in data["pairs"]):
                data["pairs"].append({"id": pid, "long": long, "short": short,
                                      "name": (body.get("name") or "").strip() or f"{long} vs {short}", "kind": "pair",
                                      "reads": f"Rising: {long} is outperforming {short}. Falling: {short} is outperforming {long}."})
        tmp = PAIRS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(PAIRS_PATH)
    return {"pairs": data["pairs"]}


# ---------- watchlists
# Universal watchlist: every symbol with data in the database (options snapshots / open interest, or
# spread legs), built from the data itself, so it grows on its own when collection grows. Custom
# watchlists are named subsets of it, saved in shared/watchlists.json for later use (other tabs,
# strategy, backtests). Separate from shared/watchlist.json, which is what gets collected.

WATCHLISTS_PATH = Path(os.environ.get("WATCHLISTS", PROJECT / "shared" / "watchlists.json"))
_lists_lock = threading.Lock()


def universe(conn) -> dict[str, dict]:
    """Symbol -> latest price, change today, and which kinds of data exist for it."""
    out: dict[str, dict] = {}
    for r in rows(conn, """SELECT s.symbol, s.ts, s.price, s.prev_close FROM stock_snapshots s
                           JOIN (SELECT symbol, MAX(run_id) r FROM stock_snapshots GROUP BY symbol) l
                             ON l.symbol = s.symbol AND l.r = s.run_id"""):
        out[r["symbol"]] = {"symbol": r["symbol"], "price": r["price"], "change": pct(r["price"], r["prev_close"]),
                            "as_of": r["ts"], "options": True, "spreads": False}
    for (sym,) in conn.execute("SELECT DISTINCT underlying FROM open_interest WHERE product = underlying"):
        out.setdefault(sym, {"symbol": sym, "price": None, "change": None, "as_of": None, "spreads": False})["options"] = True
    if table_exists(conn, "daily_bars_adj"):
        for (sym,) in conn.execute("SELECT DISTINCT symbol FROM daily_bars_adj"):
            u = out.setdefault(sym, {"symbol": sym, "price": None, "change": None, "as_of": None, "options": False})
            u["spreads"] = True
            if u["price"] is None:  # spread-only legs: last two daily closes (today's bar is partial)
                last = conn.execute("SELECT date, close FROM daily_bars_adj WHERE symbol = ? ORDER BY date DESC LIMIT 2", (sym,)).fetchall()
                if last:
                    u.update(price=last[0][1], as_of=last[0][0], change=pct(last[0][1], last[1][1]) if len(last) > 1 else None)
    return out


def load_lists() -> list[dict]:
    return json.loads(WATCHLISTS_PATH.read_text())["lists"] if WATCHLISTS_PATH.exists() else []


def api_watchlists(q):
    with db() as conn:
        u = universe(conn)
    return {"universe": sorted(u.values(), key=lambda x: x["symbol"]), "lists": load_lists()}


def api_save_watchlists(body):
    """One edit per call: {"action": "create", "name"}, {"action": "rename", "id", "name"},
    {"action": "delete", "id"}, {"action": "add" | "remove", "id", "symbol"}. Lists keep a stable id
    (from the first name) so renaming doesn't break anything that refers to them later."""
    action = body.get("action")
    name = str(body.get("name") or "").strip()[:40]
    with _lists_lock:
        lists = load_lists()
        found = next((l for l in lists if l["id"] == body.get("id")), None)
        if action in ("create", "rename"):
            if not name:
                raise ValueError("give the watchlist a name")
            if any(l["name"].lower() == name.lower() and l is not found for l in lists):
                raise ValueError(f"there's already a watchlist called {name}")
        if action == "create":
            base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "list"
            lid, n = base, 2
            while any(l["id"] == lid for l in lists):
                lid, n = f"{base}-{n}", n + 1
            found = {"id": lid, "name": name, "symbols": []}
            lists.append(found)
        elif found is None:
            raise ValueError("that watchlist doesn't exist")
        elif action == "rename":
            found["name"] = name
        elif action == "delete":
            lists.remove(found)
        elif action in ("add", "remove"):
            sym = str(body.get("symbol") or "").upper()
            if action == "add":
                with db() as conn:
                    if sym not in universe(conn):
                        raise ValueError(f"no data for {sym or '(blank)'}: only stocks in the universal watchlist can be added")
                if sym not in found["symbols"]:
                    found["symbols"].append(sym)
            else:
                found["symbols"] = [x for x in found["symbols"] if x != sym]
        else:
            raise ValueError(f"unknown action: {action}")
        tmp = WATCHLISTS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"lists": lists}, indent=2) + "\n")
        tmp.replace(WATCHLISTS_PATH)
    return {"lists": lists, "id": found["id"] if action != "delete" else None}


# ---------- events tab

def api_events(q):
    group = q.get("group", ["all"])[0]
    search = q.get("q", [""])[0].strip().lower()
    with db() as conn:
        latest = conn.execute("SELECT MAX(fetched_at) FROM poly_snapshots").fetchone()[0]
        prev = conn.execute("SELECT MAX(fetched_at) FROM poly_snapshots WHERE fetched_at < ?", (latest,)).fetchone()[0]
        events = rows(conn, """SELECT id, title, grp, tags, end_date, neg_risk, volume, volume_24h, liquidity, url
                               FROM poly_events WHERE last_seen = ? ORDER BY volume_24h DESC""", latest)
        markets = rows(conn, """SELECT m.id, m.event_id, m.question, m.label, m.outcomes, m.end_date, s.price, s.change_1d,
                                       s.change_1w, s.volume_24h, s.liquidity, s.best_bid, s.best_ask
                                FROM poly_snapshots s JOIN poly_markets m ON m.id = s.market_id
                                WHERE s.fetched_at = ?""", latest)
        runs = conn.execute("SELECT COUNT(DISTINCT fetched_at) FROM poly_snapshots").fetchone()[0]
    by_event: dict[str, list] = {}
    for m in markets:
        m["outcomes"] = json.loads(m["outcomes"] or "[]")
        by_event.setdefault(m["event_id"], []).append(m)
    out = []
    for e in events:
        ms = sorted(by_event.get(e["id"], []), key=lambda m: -(m["price"] or 0))
        if not ms:
            continue
        if (group == "all" and e["grp"] == "other") or (group != "all" and e["grp"] != group):
            continue  # "all" means every market-relevant group; sports/other only when picked
        if search and search not in e["title"].lower() and not any(search in (m["question"] or "").lower() for m in ms):
            continue
        e["tags"] = json.loads(e["tags"] or "[]")
        e["markets"] = ms
        out.append(e)

    # Movers: liquid markets only, and not ones resolving within 48h (those converge to 0/100 by
    # design: vote counts, "up or down today" markets), which would otherwise crowd out real repricing.
    near = (datetime.now(ET) + timedelta(hours=48)).astimezone(ZoneInfo("UTC")).isoformat()
    liquid = [m for m in markets if (m["volume_24h"] or 0) >= 10_000 and m["change_1d"] is not None
              and not (m["end_date"] and m["end_date"] <= near)]
    titles = {e["id"]: e for e in events}
    movers = sorted(liquid, key=lambda m: -abs(m["change_1d"]))
    movers = [dict(m, event_title=titles.get(m["event_id"], {}).get("title"), grp=titles.get(m["event_id"], {}).get("grp"),
                   url=titles.get(m["event_id"], {}).get("url")) for m in movers
              if titles.get(m["event_id"], {}).get("grp") != "other"][:25]
    soon = (datetime.now(ET) + timedelta(days=7)).astimezone(ZoneInfo("UTC")).isoformat()
    ending = [e for e in out if e["end_date"] and e["end_date"] <= soon and e["grp"] != "other"][:20]
    counts = {g: sum(1 for e in events if e["grp"] == g) for g in GROUP_ORDER}
    return {"fetched_at": latest, "previous_fetch": prev, "snapshots_collected": runs, "counts": counts,
            "events": out[:300], "movers": movers, "ending": ending}


def api_market_history(q):
    mid = q.get("id", [""])[0]
    with db() as conn:
        pts = rows(conn, "SELECT fetched_at, price FROM poly_snapshots WHERE market_id = ? ORDER BY fetched_at", mid)
    return {"id": mid, "points": pts}


# ---------- gamma tab (read-only view of what strategy_collector.py logged)

GRADE_POINTS = ("eod", "next_day", "three_days")
GROUPS = ("strong", "prediction", "no_prediction", "failed_hold")


def _gamma_group(e: dict) -> str:
    return ("strong" if e["strong"] else "prediction") if e["kind"] == "prediction" else e["kind"]


def _gamma_scorecard(events: list[dict]) -> dict:
    """For each kind of breakout and each checkpoint: how many were graded, how many held, average move."""
    out = {}
    for mode in ("live", "replay"):
        table = {}
        for group in GROUPS:
            members = [e for e in events if e["mode"] == mode and _gamma_group(e) == group]
            row = {"count": len(members)}
            for point in GRADE_POINTS:
                graded = [e["grades"][point] for e in members if point in e["grades"]]
                moves = [g["pct_move"] for g in graded if g["pct_move"] is not None]
                row[point] = {"graded": len(graded), "held": sum(g["status"] == "held" for g in graded),
                              "avg_move": sum(moves) / len(moves) if moves else None}
            table[group] = row
        out[mode] = table
    return out


def api_gamma(q):
    with db() as conn:
        if not table_exists(conn, "strategy_events"):
            return {"ready": False}
        day = conn.execute("SELECT MAX(date) FROM strategy_levels").fetchone()[0]
        if not day:
            return {"ready": False}
        nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        levels = rows(conn, """SELECT l.*, s.volume_ratio, s.holding_since, s.holding_price
                               FROM strategy_levels l LEFT JOIN strategy_state s ON s.symbol = l.symbol AND s.date = l.date
                               WHERE l.date = ? ORDER BY l.symbol""", day)
        last = {r["symbol"]: r for r in rows(conn, """SELECT symbol, close, MAX(bar_end) AS bar_end FROM strategy_bars_5m
                                                      WHERE bar_end >= ? AND bar_end < ? GROUP BY symbol""", day, nxt)}
        events = rows(conn, "SELECT * FROM strategy_events ORDER BY decision_time DESC, id DESC")
        grades = rows(conn, "SELECT * FROM strategy_grades")
        run = conn.execute("SELECT started_at, status, detail FROM runs WHERE job = 'strategy' ORDER BY id DESC LIMIT 1").fetchone()
        days = dict(conn.execute("SELECT mode, COUNT(DISTINCT date) FROM strategy_levels GROUP BY mode").fetchall())
    by_event: dict[int, dict] = {}
    for g in grades:
        by_event.setdefault(g["event_id"], {})[g["checkpoint"]] = g
    for e in events:
        e["group"] = _gamma_group(e)
        e["grades"] = by_event.get(e["id"], {})
        e["points"], e["reasons"], e["notes"] = (json.loads(e[k] or "[]") for k in ("points", "reasons", "notes"))
    for lv in levels:
        bar = last.get(lv["symbol"], {})
        lv["price"], lv["bar_end"] = bar.get("close"), bar.get("bar_end")
        lv["events"] = [{"group": e["group"], "decision_time": e["decision_time"]} for e in events
                        if e["symbol"] == lv["symbol"] and e["date"] == day]
    return {"ready": True, "date": day, "levels": levels, "events": events, "scorecard": _gamma_scorecard(events),
            "last_bar": max((b["bar_end"] for b in last.values()), default=None),
            "run": dict(run) if run else None, "live_days": days.get("live", 0), "replay_days": days.get("replay", 0)}


def api_gamma_bars(q):
    sym, count = q.get("symbol", [""])[0].upper(), int(q.get("days", ["1"])[0])
    with db() as conn:
        days = [r[0] for r in conn.execute("""SELECT DISTINCT substr(bar_end, 1, 10) FROM strategy_bars_5m WHERE symbol = ?
                                              ORDER BY 1 DESC LIMIT ?""", (sym, count))]
        if not days:
            return {"symbol": sym, "bars": [], "levels": None, "events": []}
        bars = rows(conn, "SELECT * FROM strategy_bars_5m WHERE symbol = ? AND bar_end >= ? ORDER BY bar_end", sym, days[-1])
        levels = conn.execute("SELECT * FROM strategy_levels WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,)).fetchone()
        events = rows(conn, "SELECT kind, strong, breakout_time, decision_time FROM strategy_events WHERE symbol = ? AND date >= ?", sym, days[-1])

    def chart_time(iso: str, back: int = 0) -> int:  # New York wall clock, like _chart_points
        t = datetime.fromisoformat(iso) - timedelta(minutes=back)
        return int(t.timestamp() + t.utcoffset().total_seconds())
    for e in events:
        e["breakout"], e["decision"] = chart_time(e["breakout_time"], 5), chart_time(e["decision_time"], 5)
    return {"symbol": sym, "levels": dict(levels) if levels else None, "events": events,
            "bars": [{"time": chart_time(b["bar_end"], 5), "open": b["open"], "high": b["high"], "low": b["low"],
                      "close": b["close"], "volume": b["volume"]} for b in bars]}


# ---------- politics tab (the political game machine rebuilds this file hourly; see collectors/politics_job.py)

def api_politics(q):
    if not POLITICS_DATA.exists():
        return {"ready": False}
    if q.get("meta"):
        return {"ready": True, "generated_at": json.loads(POLITICS_SUMMARY.read_text())["generated_at"]}
    return {"ready": True, **json.loads(POLITICS_DATA.read_text())}


def politics_engine() -> bytes:
    """The game's simulation, wrapped so its helper names stay out of the page's global scope.
    The file ends by filling in module.exports, which is how the Python tests load it too."""
    source = (PROJECT / "politics" / "game_engine.js").read_text(encoding="utf-8")
    return f"const GameEngine = (() => {{ const module = {{}};\n{source}\nreturn module.exports; }})();\n".encode()


# ---------- scorecard tab: every model's record in one place. New models write to the prediction
# ledger (collectors/ledger.py); the gamma tracker and the political machine keep their own records.

def _gamma_record() -> dict:
    g = api_gamma({})
    if not g.get("ready"):
        return {"ready": False}
    live = [e for e in g["events"] if e["mode"] == "live"]
    return {"ready": True, "live_days": g["live_days"], "first_live": min((e["date"] for e in live), default=None),
            "breakouts": len(live), "predictions": sum(e["kind"] == "prediction" for e in live),
            "table": g["scorecard"]["live"]}


def _politics_record() -> dict:
    if not POLITICS_DATA.exists():
        return {"ready": False}
    log = POLITICS_DATA.parent.parent / "data" / "forecasts.jsonl"
    first = None
    if log.exists():
        with log.open() as f:
            line = f.readline()
            first = json.loads(line).get("made_at") if line.strip() else None
    d = json.loads(POLITICS_DATA.read_text())
    return {"ready": True, "generated_at": d["generated_at"], "first_forecast": first, **d["scorecard"]}


def _spx_record(conn, days: int = 120) -> dict:
    """The S&P move-size model: its newest live prediction, the next scheduled events, and the last
    `days` predicted ranges against what happened (live where it exists, backtest before that)."""
    if not table_exists(conn, "predictions"):
        return {"ready": False}
    by_day = {}
    for r in conn.execute("""SELECT p.mode, p.made_at, p.forecast, p.baselines, p.inputs, o.outcome
                             FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id = p.id
                             WHERE p.model = 'spx-move' ORDER BY p.opens_at DESC LIMIT ?""", (days * 3,)):
        x = json.loads(r["inputs"])
        day = x["next_day"]
        if day not in by_day or r["mode"] == "live":
            by_day[day] = {"day": day, "mode": r["mode"], "made_at": r["made_at"], "q": json.loads(r["forecast"])["q"],
                           "baselines": {k: v["q"] for k, v in json.loads(r["baselines"]).items()},
                           "outcome": r["outcome"], "inputs": x}
    if not by_day:
        return {"ready": False}
    history = [by_day[d] for d in sorted(by_day)[-days:]]
    live = [h for h in history if h["mode"] == "live"]
    now = datetime.now(ET)  # today's news counts until the close
    upcoming = rows(conn, f"SELECT date, event, time_et, detail FROM econ_calendar WHERE date {'>' if now.hour >= 16 else '>='} ? "
                          "ORDER BY date, time_et LIMIT 6", now.date().isoformat()) if table_exists(conn, "econ_calendar") else []
    return {"ready": True, "latest": live[-1] if live else None, "last": history[-1], "upcoming": upcoming,
            "history": [{k: h[k] for k in ("day", "mode", "q", "baselines", "outcome")} for h in history]}


def api_scorecard(q):
    out = {"ledger": None, "min_resolved": ledger.MIN_RESOLVED, "gamma": _gamma_record(), "politics": _politics_record()}
    with db() as conn:
        if table_exists(conn, "predictions"):
            out["ledger"] = {"models": ledger.summary(conn), "recent": ledger.recent(conn, 60), "verify": ledger.verify(conn)}
        out["spx"] = _spx_record(conn)
        out["paper"] = paper_record.summary(conn)
    return out


# ---------- news tab (read-only view of what news_collector.py and shipping_collector.py stored)

NEWS_TOPICS = ["fed", "economy", "markets", "business", "tech", "energy", "shipping", "ukraine", "middle_east",
               "china", "politics", "world", "crypto"]
# Chokepoints shown first, in this order; the rest follow by traffic.
CHOKEPOINT_ORDER = ["chokepoint6", "chokepoint4", "chokepoint1", "chokepoint2", "chokepoint5", "chokepoint3",
                    "chokepoint7", "chokepoint8", "chokepoint11", "chokepoint9", "chokepoint28"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def _fts_query(text: str) -> str:
    """User words to a safe FTS5 query: each word quoted (no operators), all must match, prefix on the last."""
    words = re.findall(r"[\w'.-]+", text)[:8]
    return " ".join(f'"{w.replace(chr(34), "")}"' for w in words[:-1]) + (f' "{words[-1]}"*' if words else "")


def api_news(q):
    topic = q.get("topic", ["all"])[0]
    search = q.get("q", [""])[0].strip()
    hours = min(max(int(q.get("hours", ["24"])[0] or 24), 1), 24 * 30)
    since = (datetime.now(ET) - timedelta(hours=hours)).isoformat(timespec="seconds")
    tclause = "" if topic == "all" else " AND topics LIKE ?"
    targs = () if topic == "all" else (f"%,{topic},%",)
    # Minimum reliability (0 = everything). Stories filter on trust, headlines on their outlet's rating.
    # Government sources have no number; they stay in unless official=0.
    min_rel = min(max(int(q.get("min", ["0"])[0] or 0), 0), 100)
    keep_official = q.get("official", ["1"])[0] != "0"
    s_rel = "" if not min_rel else f" AND (trust >= {min_rel}{" OR trust_label = 'Official'" if keep_official else ''})"
    i_rel = "" if not min_rel else f" AND (rating >= {min_rel}{" OR outlet = 'official'" if keep_official else ''})"
    with db() as conn:
        if not table_exists(conn, "news_stories"):
            return {"ready": False}
        stories = rows(conn, f"""SELECT id, title, link, best_tier, first_published, last_seen, n_items, n_sources, sources,
                                        topics, alert, importance, best_rating, trust, trust_label, trust_why FROM news_stories
                                 WHERE first_published >= ?{tclause}{s_rel} ORDER BY importance DESC, last_seen DESC LIMIT 40""",
                       since, *targs)
        for s in stories:
            s["sources"] = json.loads(s["sources"] or "[]")
            s["items"] = rows(conn, "SELECT title, source, tier, outlet, rating, link, published_at FROM news_items WHERE story_id = ? "
                                    f"{i_rel} ORDER BY (outlet = 'official'), rating DESC, published_at LIMIT 25", s["id"])
        if search:
            latest = rows(conn, f"""SELECT i.id, i.title, i.source, i.tier, i.outlet, i.rating, i.link, i.published_at, i.summary, i.topics, i.alert
                                    FROM news_fts f JOIN news_items i ON i.id = f.rowid
                                    WHERE news_fts MATCH ?{tclause.replace('topics', 'i.topics')}{i_rel.replace('rating', 'i.rating').replace('outlet', 'i.outlet')}
                                    ORDER BY i.published_at DESC LIMIT 150""", _fts_query(search), *targs)
        else:
            latest = rows(conn, f"""SELECT id, title, source, tier, outlet, rating, link, published_at, summary, topics, alert FROM news_items
                                    WHERE published_at >= ?{tclause}{i_rel} ORDER BY published_at DESC LIMIT 150""", since, *targs)
        counts = {t: conn.execute(f"SELECT count(*) FROM news_stories WHERE first_published >= ? AND topics LIKE ?{s_rel}",
                                  (since, f"%,{t},%")).fetchone()[0] for t in NEWS_TOPICS}
        total = conn.execute("SELECT count(*) FROM news_items").fetchone()[0]
        newest = conn.execute("SELECT max(first_seen) FROM news_items").fetchone()[0]
        feeds = rows(conn, "SELECT feed, last_try, last_ok, items, error FROM news_feed_status ORDER BY error IS NULL, feed")
        fed = _fed_panel(conn)
    return {"ready": True, "topic": topic, "hours": hours, "min": min_rel, "official": keep_official, "stories": stories, "latest": latest, "counts": counts,
            "total_headlines": total, "newest": newest, "feeds": feeds, "fed": fed}


def _fed_panel(conn) -> dict:
    now = datetime.now(ET)
    upcoming = rows(conn, "SELECT date, event, time_et, detail FROM econ_calendar WHERE date > ? OR (date = ? AND time_et > ?) "
                          "ORDER BY date, time_et LIMIT 8", now.date().isoformat(), now.date().isoformat(),
                    now.strftime("%H:%M")) if table_exists(conn, "econ_calendar") else []
    nxt = next((u for u in upcoming if u["event"] == "fomc"), None)
    odds = []
    if nxt and table_exists(conn, "poly_events"):
        month = MONTHS[int(nxt["date"][5:7]) - 1]
        latest = conn.execute("SELECT max(fetched_at) FROM poly_snapshots").fetchone()[0]
        ev = conn.execute("SELECT id, title, url FROM poly_events WHERE title = ? AND last_seen = ?",
                          (f"Fed Decision in {month}?", latest)).fetchone()
        if ev:
            odds = rows(conn, """SELECT m.label, m.question, s.price, s.change_1d FROM poly_snapshots s
                                 JOIN poly_markets m ON m.id = s.market_id
                                 WHERE m.event_id = ? AND s.fetched_at = ? ORDER BY s.price DESC""", ev["id"], latest)
            nxt = dict(nxt, market_title=ev["title"], market_url=ev["url"], market_asof=latest)
    statements = rows(conn, """SELECT title, link, published_at, feed FROM news_items
                               WHERE feed IN ('Federal Reserve', 'Federal Reserve Speeches') ORDER BY published_at DESC LIMIT 8""") \
        if table_exists(conn, "news_items") else []
    return {"upcoming": upcoming, "next_fomc": nxt, "odds": odds, "statements": statements}


def api_shipping(q):
    pid = q.get("id", [""])[0]
    with db() as conn:
        if not table_exists(conn, "chokepoint_daily"):
            return {"ready": False}
        last = conn.execute("SELECT max(date) FROM chokepoint_daily").fetchone()[0]
        d = date.fromisoformat(last)
        w7, w30 = (d - timedelta(days=6)).isoformat(), (d - timedelta(days=29)).isoformat()
        yr = (d - timedelta(days=371)).isoformat(), (d - timedelta(days=358)).isoformat()
        # "Normal": Jan-Oct 2023, the last stretch before Red Sea attacks and the Hormuz crisis rerouted traffic.
        ports = rows(conn, """SELECT portid, max(portname) portname,
              avg(CASE WHEN date >= ? THEN n_total END) avg7,
              avg(CASE WHEN date >= ? THEN n_total END) avg30,
              avg(CASE WHEN date BETWEEN ? AND ? THEN n_total END) year_ago,
              avg(CASE WHEN date BETWEEN '2023-01-01' AND '2023-10-31' THEN n_total END) normal,
              avg(CASE WHEN date >= ? THEN n_tanker END) tankers7,
              avg(CASE WHEN date BETWEEN '2023-01-01' AND '2023-10-31' THEN n_tanker END) tankers_normal,
              avg(CASE WHEN date >= ? THEN capacity END) capacity7,
              avg(CASE WHEN date BETWEEN '2023-01-01' AND '2023-10-31' THEN capacity END) capacity_normal
              FROM chokepoint_daily WHERE date >= '2023-01-01' GROUP BY portid""", w7, w30, *yr, w7, w7)
        spark_from = (d - timedelta(days=179)).isoformat()
        series: dict[str, list] = {}
        for r in conn.execute("SELECT portid, date, n_total FROM chokepoint_daily WHERE date >= ? ORDER BY date", (spark_from,)):
            series.setdefault(r[0], []).append(r[2])
        detail = rows(conn, "SELECT date, n_total, n_tanker, n_container, n_dry_bulk, capacity FROM chokepoint_daily "
                            "WHERE portid = ? ORDER BY date", pid) if pid else None
    rank = {p: i for i, p in enumerate(CHOKEPOINT_ORDER)}
    ports.sort(key=lambda p: (rank.get(p["portid"], 99), -(p["avg7"] or 0)))
    for p in ports:
        p["spark"] = series.get(p["portid"], [])
    return {"ready": True, "latest_day": last, "ports": ports, "detail": detail, "id": pid}


# ---------- today and research tabs (plain summaries of records the other tabs already hold; decide nothing)

RESEARCH_PATH = PROJECT / "shared" / "research.json"
# Today tab filters: stories must carry a market-relevant topic; betting markets drop novelty bets
# (tweet counts, press-office timing, "mention" markets) that move a lot but say nothing about markets.
MARKET_TOPICS = ("fed", "economy", "markets", "business", "tech", "energy", "shipping", "ukraine", "middle_east", "china", "politics")
NOISE = re.compile(r"tweets?|full lid|\bsay\b|mention|post on truth|wear|announcer|weather|temperature|mayor|arena|divorce|press secretary", re.I)
# Stories the topic tagger files under markets or politics that aren't (films, celebrities, crime trials).
STORY_NOISE = re.compile(r"james bond|box office|film|movie|actor|actress|celebrity|retrial|murder|sentenced|trial of|grammy|oscar", re.I)
HOLD_NAMES = {"SSO": "SSO (2x S&P 500)", "SPY": "SPY", "cash": "cash (T-bills)"}
BAD_RUN = ("failed", "partial", "stopped")


def _day_text(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def _ledger_verdict(m: dict) -> str:
    verdicts = {b["verdict"] for b in m["baselines"].values()}
    if not verdicts or "too few" in verdicts:
        return "too early"
    if verdicts == {"better"}:
        return "beats its simple guesses"
    return "worse than a simple guess" if "worse" in verdicts else "no clear difference"


def _live_tests(conn) -> list[dict]:
    """One row per thing on a live test: what it's doing now, its record so far, its verdict and
    what a verdict needs. Reads the same records as the Scorecard tab."""
    out = []
    for e in paper_record.summary(conn).get("strategies", []):
        lp = e["latest_position"]
        if e["kind"] == "fed":
            now = (f"Next window: {_day_text(lp['buy_at'])} 2 pm to {_day_text(lp['decision_day'])} 2 pm" if lp
                   else "Waiting for the next Fed meeting to come within two weeks")
            record = (f"{e['meetings']} meeting{'s' if e['meetings'] != 1 else ''}, average {e['avg_window'] * 100:+.2f}% a window"
                      if e.get("meetings") else "No meeting finished yet")
            needs = "30 meetings"
        else:
            now = f"Holding {HOLD_NAMES.get(lp['hold'], lp['hold'])} from the {_day_text(lp['trade_date'])} close" if lp else "No position yet"
            record = (f"${e['rule_10k']:,.0f} against SPY's ${e['spy_10k']:,.0f} from $10,000, since {_day_text(e['first_day'])}"
                      if e["marks"] else "Starts at its first close")
            needs = "3 years"
        out.append({"id": f"paper-{e['strategy']}", "name": e["name"], "what": e["what"], "now": now, "record": record,
                    "verdict": e["verdict"], "needs": needs, "tab": "scorecard"})

    live = [m for m in ledger.summary(conn) if m["mode"] == "live"] if table_exists(conn, "predictions") else []
    for m in live:
        if m["model"] == "spx-move":
            s = _spx_record(conn, 5).get("latest")
            now = (f"90% range for {_day_text(s['day'])}: {s['q']['0.05']:+.2f}% to {s['q']['0.95']:+.2f}%" if s and s["outcome"] is None
                   else "Next range is made this evening")
            vix = m["baselines"].get("vix", {})
            record = f"{m['resolved']} of {m['logged']} predictions resolved"
            if vix.get("skill") is not None:
                record += f". Error {abs(vix['skill']) * 100:.0f}% {'smaller' if vix['skill'] >= 0 else 'bigger'} than the VIX-implied guess so far"
            out.append({"id": "spx-move", "name": "S&P 500 move size", "what": "How big tomorrow's S&P 500 move will be (a range, not a direction)",
                        "now": now, "record": record, "verdict": _ledger_verdict(m), "needs": f"{ledger.MIN_RESOLVED} results", "tab": "scorecard"})
        elif m["model"] == "stock-direction":
            four = m["version"].endswith("@sp400")
            base = m["baselines"].get("base_rate", {})
            record = f"{m['resolved']:,} of {m['logged']:,} predictions resolved"
            if base.get("skill") is not None:
                record += f". Error {abs(base['skill']) * 100:.1f}% {'smaller' if base['skill'] >= 0 else 'bigger'} than the base rate so far"
            out.append({"id": f"stock-direction-{m['version']}", "name": f"Stock direction v{m['version']}",
                        "what": f"Each week, the chance each {'of the other 400 S&P 500 stocks' if four else 'S&P 100 stock'} beats SPY",
                        "now": f"{m['logged'] - m['resolved']:,} predictions open", "record": record,
                        "verdict": _ledger_verdict(m), "needs": f"{ledger.MIN_RESOLVED} weeks", "tab": "scorecard"})
        elif m["model"] in ("event-forecast", "owner-forecast"):
            mine = m["model"] == "owner-forecast"
            mk = m["baselines"].get("market", {})
            open_rows = rows(conn, """SELECT p.target, p.forecast, p.baselines FROM predictions p LEFT JOIN prediction_outcomes o
                                      ON o.prediction_id = p.id WHERE p.model = ? AND p.mode = 'live' AND o.prediction_id IS NULL
                                      ORDER BY p.resolves_at LIMIT 1""", m["model"])
            now = "Nothing open"
            if open_rows:
                r = open_rows[0]
                now = (f"Next: {r['target']}: {json.loads(r['forecast'])['p']:.0%} "
                       f"(market {json.loads(r['baselines'])['market']['p']:.0%} when logged)")
            record = f"{m['resolved']} of {m['logged']} forecasts settled"
            if mk.get("skill") is not None:
                record += f". Error {abs(mk['skill']) * 100:.0f}% {'smaller' if mk['skill'] >= 0 else 'bigger'} than the betting market so far"
            out.append({"id": m["model"], "name": "Your forecast journal" if mine else "Event forecasts",
                        "what": ("Your own chances for dated events" if mine else "Chances for dated events, set by a written rule")
                                + ", scored against the betting market",
                        "now": now, "record": record, "verdict": _ledger_verdict(m), "needs": f"{ledger.MIN_RESOLVED} events", "tab": "scorecard"})
    if not any(m["model"] == "stock-direction" for m in live):
        out.append({"id": "stock-direction", "name": "Stock direction", "what": "Each week, the chance each S&P 500 stock beats SPY, from options prices",
                    "now": "First weekly predictions are made on its next Tuesday evening run", "record": "Not started",
                    "verdict": "too early", "needs": f"{ledger.MIN_RESOLVED} weeks", "tab": "scorecard"})

    g = _gamma_record()
    if g.get("ready"):
        t = g["table"]
        graded = sum(t[k]["eod"]["graded"] for k in ("strong", "prediction"))
        held = sum(t[k]["eod"]["held"] for k in ("strong", "prediction"))
        out.append({"id": "gamma", "name": "Gamma breakout tracker", "what": "Whether a breakout above the biggest call strike keeps holding",
                    "now": f"{g['breakouts']} breakouts watched over {g['live_days']} trading days",
                    "record": f"{g['predictions']} prediction{'s' if g['predictions'] != 1 else ''}; {held} of {graded} held to the close",
                    "verdict": "too early", "needs": f"{ledger.MIN_RESOLVED} predictions", "tab": "gamma"})
    p = _politics_record()
    if p.get("ready"):
        out.append({"id": "politics", "name": "Political game machine", "what": "Chances of 2028 election outcomes, against betting markets",
                    "now": f"{p['open_questions']} questions open", "record": f"{p['forecasts']} forecasts logged, {p['resolved']} settled",
                    "verdict": "too early", "needs": "elections to settle (2028)", "tab": "politics"})
    return out


VIX_BANDS = [(0, 15, "below 15 (calm)"), (15, 20, "15 to 20"), (20, 30, "20 to 30 (nervous)"), (30, 999, "above 30 (panic)")]


def _risk() -> dict:
    """History's base rates for days like today: how often the S&P 500 went on to fall 5% or 10%
    within the next 21 trading days, by trend (close vs its 200-day average) and VIX band. Every
    day since 1990 is used, so this describes the past; it isn't a tested prediction model."""
    with db() as conn:
        spx = conn.execute("SELECT date, close FROM index_daily WHERE symbol = 'SPX' ORDER BY date").fetchall()
        vix = dict(conn.execute("SELECT date, close FROM index_daily WHERE symbol = 'VIX'").fetchall())
    dates, px = [r[0] for r in spx], [r[1] for r in spx]
    cells: dict[tuple, list] = {}
    run, today = sum(px[:200]), None
    for i in range(199, len(px)):
        if i > 199:
            run += px[i] - px[i - 200]
        v = vix.get(dates[i])
        if v is None:
            continue
        key = (px[i] > run / 200, next(k for k, (lo, hi, _) in enumerate(VIX_BANDS) if lo <= v < hi))
        if i == len(px) - 1:
            today = {"date": dates[i], "up": key[0], "band": key[1], "vix": v, "gap": (px[i] / (run / 200) - 1) * 100}
        if i + 21 < len(px):
            worst = min(px[i + 1:i + 22]) / px[i] - 1
            moves = [abs(px[j] / px[j - 1] - 1) * 100 for j in range(i + 1, i + 22)]
            cells.setdefault(key, []).append((worst <= -0.05, worst <= -0.10, sum(moves) / 21))

    def stats(xs):
        n = len(xs)
        if not n:
            return {"n": 0}
        return {"n": n, "drop5": sum(x[0] for x in xs) / n, "drop10": sum(x[1] for x in xs) / n, "avg_move": sum(x[2] for x in xs) / n}
    table = [{"up": up, "band": b, "band_name": VIX_BANDS[b][2], **stats(cells.get((up, b), []))}
             for up in (True, False) for b in range(len(VIX_BANDS))]
    return {"today": today, "table": table, "all": stats([x for xs in cells.values() for x in xs]),
            "since": dates[199], "horizon_days": 21}


def _priced_in() -> dict:
    """What markets expect: SPY's options-implied move for coming expirations, and the busiest
    macro, politics and geopolitics betting markets with their leading outcomes."""
    d = api_option_detail({"symbol": ["SPY"]})
    moves = [{"expiration": e["expiration"], "days": e["days"], "move": e["implied_move"], "iv": e.get("atm_iv")}
             for e in d.get("expirations", []) if e.get("implied_move") and e["days"] >= 1]
    picks, seen = [], set()
    for target in (7, 30, 60):
        best = min(moves, key=lambda m: abs(m["days"] - target), default=None)
        if best and best["expiration"] not in seen:
            seen.add(best["expiration"])
            picks.append(best)
    ev = api_events({})
    markets = [{"title": e["title"], "grp": e["grp"], "url": e["url"], "volume_24h": e["volume_24h"], "end_date": e["end_date"],
                "top": [{"label": m["label"] or m["question"], "price": m["price"], "change_1d": m["change_1d"]} for m in e["markets"][:2]]}
               for e in ev["events"] if e["grp"] in ("macro", "politics", "geopolitics") and not NOISE.search(e["title"])][:8]
    return {"spy_price": d.get("price"), "moves": picks, "snapshot_ts": d.get("snapshot_ts"), "markets": markets,
            "markets_asof": ev["fetched_at"]}


def _today() -> dict:
    now = datetime.now(ET)
    today = now.date().isoformat()
    since = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    with db() as conn:
        spy = conn.execute("SELECT ts, price, prev_close FROM stock_snapshots WHERE symbol = 'SPY' ORDER BY run_id DESC LIMIT 1").fetchone()
        past = [r[0] for r in conn.execute("SELECT close FROM daily_bars_adj WHERE symbol = 'SPY' AND date < ? ORDER BY date DESC LIMIT 200", (today,))]
        vix = conn.execute("SELECT date, close FROM index_daily WHERE symbol = 'VIX' ORDER BY date DESC LIMIT 1").fetchone() \
            if table_exists(conn, "index_daily") else None
        latest = _spx_record(conn, 5).get("latest")
        fed = _fed_panel(conn)
        tests = _live_tests(conn)
        stories = rows(conn, """SELECT id, title, link, first_published, n_sources, topics, alert, trust, trust_label, trust_why
                                FROM news_stories WHERE first_published >= ? AND (trust >= 70 OR trust_label = 'Official')
                                AND (topics LIKE '%,fed,%' OR topics LIKE '%,economy,%' OR topics LIKE '%,markets,%' OR topics LIKE '%,business,%' OR topics LIKE '%,tech,%' OR topics LIKE '%,energy,%' OR topics LIKE '%,shipping,%' OR topics LIKE '%,ukraine,%' OR topics LIKE '%,middle_east,%' OR topics LIKE '%,china,%' OR topics LIKE '%,politics,%')
                                ORDER BY importance DESC, last_seen DESC LIMIT 16""", since) if table_exists(conn, "news_stories") else []
        newest_news = conn.execute("SELECT max(first_seen) FROM news_items").fetchone()[0] if table_exists(conn, "news_items") else None
        jobs = rows(conn, """SELECT r.job, r.started_at, r.status, substr(r.detail, 1, 160) AS detail
                             FROM runs r JOIN (SELECT job, MAX(id) id FROM runs GROUP BY job) l ON l.id = r.id
                             WHERE r.started_at >= ? ORDER BY r.job""", (now - timedelta(days=4)).isoformat(timespec="seconds"))
    stories = [x for x in stories if not STORY_NOISE.search(x["title"] or "")][:8]
    ev = api_events({})
    avg200 = sum(past) / len(past) if len(past) == 200 else None
    market = {"spy": dict(spy) if spy else None, "avg200": avg200, "vix": dict(vix) if vix else None,
              "range": {"day": latest["day"], "q": latest["q"], "outcome": latest["outcome"], "is_today": latest["day"] == today} if latest else None}
    return {"today": today, "market": market, "tests": tests, "stories": stories, "newest_news": newest_news,
            "movers": [m for m in ev["movers"] if m.get("grp") in ("macro", "politics", "geopolitics", "business")
                       and not NOISE.search(f"{m.get('event_title') or ''} {m.get('question') or ''}")][:10], "movers_asof": ev["fetched_at"], "calendar": fed,
            "jobs": {"total": len(jobs), "bad": [j for j in jobs if j["status"] in BAD_RUN]},
            "db_mb": round(DB_PATH.stat().st_size / 1e6, 1),
            "risk": cached("risk", 3600, _risk), "priced": cached("priced", 300, _priced_in)}


def api_today(q):
    return cached("today", 45, _today)


def api_research(q):
    data = json.loads(RESEARCH_PATH.read_text())

    def tests():
        with db() as conn:
            return _live_tests(conn)
    return {"lessons": data["lessons"], "studies": data["studies"], "tests": cached("live-tests", 45, tests)}


ROUTES = {"/api/today": api_today, "/api/research": api_research, "/api/health": api_health, "/api/options": api_options, "/api/option_detail": api_option_detail,
          "/api/stock_bars": api_stock_bars, "/api/chain_expirations": api_chain_expirations, "/api/chain": api_chain,
          "/api/option_bars": api_option_bars, "/api/pairs": api_pairs, "/api/pair": api_pair, "/api/watchlists": api_watchlists,
          "/api/events": api_events, "/api/market_history": api_market_history,
          "/api/gamma": api_gamma, "/api/gamma_bars": api_gamma_bars, "/api/politics": api_politics,
          "/api/scorecard": api_scorecard, "/api/news": api_news, "/api/shipping": api_shipping}
POST_ROUTES = {"/api/pairs": api_save_pair, "/api/watchlists": api_save_watchlists}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ROUTES:
            try:
                body, code = json.dumps(ROUTES[url.path](parse_qs(url.query)), default=str).encode(), 200
            except Exception as e:
                body, code = json.dumps({"error": str(e)}).encode(), 500
            return self.send(code, body, "application/json")
        if url.path == "/politics-engine.js":
            return self.send(200, politics_engine(), CONTENT_TYPES[".js"])
        path = (STATIC / (url.path.lstrip("/") or "index.html")).resolve()
        if STATIC not in path.parents and path != STATIC / "index.html" or not path.is_file():
            return self.send(404, b"not found", "text/plain")
        self.send(200, path.read_bytes(), CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def do_POST(self):
        url = urlparse(self.path)
        if url.path not in POST_ROUTES:
            return self.send(404, b"not found", "text/plain")
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            body, code = json.dumps(POST_ROUTES[url.path](data)).encode(), 200
        except Exception as e:
            body, code = json.dumps({"error": str(e)}).encode(), 400
        self.send(code, body, "application/json")

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # keep the log to errors only
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    print(f"Market Dashboard on http://127.0.0.1:{PORT}  (database {DB_PATH})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
