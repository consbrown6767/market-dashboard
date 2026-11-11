#!/usr/bin/env python3
"""Pull past prices from the public Kalshi and Polymarket APIs into data/history/.

  kalshi_hourly.jsonl   the last 14 days of hourly bid and ask, in the same format as the live
                        collector, so clean_markets.py can read it straight in
  daily.json            about a year of daily prices for leading candidates on both venues

Safe to re-run: each run replaces these files. Only markets that are open today are included, so
candidates who have since been removed don't appear.

Usage: python3 backfill_history.py
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import clean_markets as cm
from collect_kalshi import API, EVENTS, fetch_event

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "history"
HOURLY_DAYS = 14
DAILY_DAYS = 400
MIN_PRICE = 0.01  # daily history skips long shots
POLYMARKET_EVENTS = {"winner": "presidential-election-winner-2028", "nominee_d": "democratic-presidential-nominee-2028",
                     "nominee_r": "republican-presidential-nominee-2028"}
SYSTEM_CERTS = "/etc/ssl/cert.pem"
PAUSE = 0.3  # Kalshi rate-limits faster requests
RETRY_WAITS = (5, 15, 30)


def get_json(url: str) -> dict | list:
    request = urllib.request.Request(url, headers={"User-Agent": "box-of-scraps-research"})
    context = ssl.create_default_context(cafile=SYSTEM_CERTS if Path(SYSTEM_CERTS).exists() else None)
    for wait in (*RETRY_WAITS, None):
        try:
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or wait is None:  # 429 means "too many requests": back off and retry
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")


def to_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def candle_quote(candle: dict) -> tuple:
    """Closing bid and ask from one Kalshi candle, or (None, None) if either side was empty."""
    bid, ask = candle.get("yes_bid", {}).get("close_dollars"), candle.get("yes_ask", {}).get("close_dollars")
    if bid in (None, "") or ask in (None, ""):
        return None, None
    return float(bid), float(ask)


def kalshi_candles(series: str, ticker: str, days: int, period: int) -> list:
    now = int(time.time())
    url = (f"{API}/series/{series}/markets/{ticker}/candlesticks"
           f"?start_ts={now - days * 86400}&end_ts={now}&period_interval={period}")
    return get_json(url).get("candlesticks") or []


def kalshi_markets() -> list:
    """Every open market in the four main events, with its series name."""
    rows = []
    for event_ticker in EVENTS:
        event = fetch_event(event_ticker)
        markets = event["event"].get("markets") or event.get("markets") or []
        rows += [{"event": event_ticker, "series": event["event"]["series_ticker"], "ticker": m["ticker"],
                  "label": m["yes_sub_title"], "price": float(m["yes_ask_dollars"])}
                 for m in markets if m["status"] in ("active", "open")]
    return rows


def hourly_rows(market: dict, candles: list) -> list:
    rows = []
    for candle in candles:
        bid, ask = candle_quote(candle)
        if bid is not None:
            rows.append({"fetched_at": to_iso(candle["end_period_ts"]), "event_ticker": market["event"], "ticker": market["ticker"],
                         "label": market["label"], "yes_bid": bid, "yes_ask": ask})
    return rows


def daily_points(candles: list) -> dict:
    points = {}
    for candle in candles:
        bid, ask = candle_quote(candle)
        if bid is not None:
            points[to_iso(candle["end_period_ts"])[:10]] = round((bid + ask) / 2, 4)
    return points


def polymarket_daily(market: dict) -> dict:
    token = json.loads(market["clobTokenIds"])[0]
    data = get_json(f"https://clob.polymarket.com/prices-history?market={token}&interval=max&fidelity=1440")
    return {to_iso(point["t"])[:10]: round(point["p"], 4) for point in data.get("history") or []}


def backfill() -> dict:
    candidates = cm.load_candidates()
    kalshi_names, poly_names = cm.name_lookup(candidates, "kalshi"), cm.name_lookup(candidates, "polymarket")
    daily = {market: {} for market in POLYMARKET_EVENTS}
    hourly, failed = [], []

    for market in kalshi_markets():
        try:
            hourly += hourly_rows(market, kalshi_candles(market["series"], market["ticker"], HOURLY_DAYS, 60))
            key = cm.KALSHI_EVENTS[market["event"]]
            person = kalshi_names.get(market["label"])
            if key in daily and person and market["price"] >= MIN_PRICE:
                candles = kalshi_candles(market["series"], market["ticker"], DAILY_DAYS, 1440)
                daily[key].setdefault(person, {})["kalshi"] = daily_points(candles)
        except Exception as error:
            failed.append(f"{market['ticker']}: {error!r}"[:100])
        time.sleep(PAUSE)

    for key, slug in POLYMARKET_EVENTS.items():
        event = get_json(f"https://gamma-api.polymarket.com/events?slug={slug}")[0]
        for market in event["markets"]:
            person = poly_names.get(market.get("groupItemTitle"))
            price = float(market.get("bestAsk") or 0)
            if not market.get("active") or market.get("closed") or not person or price < MIN_PRICE:
                continue
            try:
                daily[key].setdefault(person, {})["polymarket"] = polymarket_daily(market)
            except Exception as error:
                failed.append(f"{person}: {error!r}"[:100])
            time.sleep(PAUSE)

    OUT.mkdir(parents=True, exist_ok=True)
    hourly.sort(key=lambda r: r["fetched_at"])
    part = OUT / "kalshi_hourly.part"
    part.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in hourly), encoding="utf-8")
    part.replace(OUT / "kalshi_hourly.jsonl")
    (OUT / "daily.json").write_text(json.dumps({"fetched_at": to_iso(int(time.time())), "markets": daily}) + "\n", encoding="utf-8")
    return {"hourly_rows": len(hourly), "daily_people": {k: len(v) for k, v in daily.items()}, "failed": failed[:5], "failed_count": len(failed)}


if __name__ == "__main__":
    print(json.dumps(backfill()))
