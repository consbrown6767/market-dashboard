#!/usr/bin/env python3
"""Save one snapshot of the 2028 Senate markets on Kalshi and Polymarket.

Run by hand for now. It writes only inside this project, to data/senate/.
A state that fails is recorded and skipped: thin state markets come and go, and one missing
state shouldn't lose the rest.

Usage: python3 snapshot_senate.py
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from collect_kalshi import fetch_event, optional_number

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "senate"
SEATS = HERE / "senate_seats.json"
NATIONAL = ("CONTROLS-2028", "KXDSENATESEATS-29", "POWER-28")
POLYMARKET_URL = "https://gamma-api.polymarket.com/events?slug=which-party-will-win-the-senate-in-2028"
SYSTEM_CERTS = "/etc/ssl/cert.pem"  # python.org Python ships without certificates
# Alabama's ticker was reissued by Kalshi with a suffix.
TICKER_OVERRIDES = {"AL": "SENATEAL-28-2"}


def state_tickers() -> dict:
    seats = json.loads(SEATS.read_text(encoding="utf-8"))["seats"]
    return {s["code"]: TICKER_OVERRIDES.get(s["code"], f"SENATE{s['code']}-28") for s in seats}


def kalshi_rows(ticker: str) -> list[dict]:
    data = fetch_event(ticker)
    markets = data["event"].get("markets") or data.get("markets") or []
    return [{
        "ticker": m["ticker"], "label": m.get("yes_sub_title") or m.get("subtitle") or m.get("title"),
        "yes_bid": optional_number(m, "yes_bid_dollars"), "yes_ask": optional_number(m, "yes_ask_dollars"),
        "last_price": optional_number(m, "last_price_dollars"), "volume": optional_number(m, "volume_fp"),
    } for m in markets if m.get("status") in ("active", "open")]


def polymarket_rows() -> list[dict]:
    request = urllib.request.Request(POLYMARKET_URL, headers={"User-Agent": "box-of-scraps-research"})
    context = ssl.create_default_context(cafile=SYSTEM_CERTS if Path(SYSTEM_CERTS).exists() else None)
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        event = json.load(response)[0]
    return [{"label": m["groupItemTitle"], "yes_bid": float(m["bestBid"]), "yes_ask": float(m["bestAsk"])}
            for m in event["markets"] if m.get("active") and not m.get("closed")]


def snapshot() -> dict:
    result = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "kalshi_states": {}, "kalshi_national": {}, "polymarket": [], "failed": {}}
    for code, ticker in state_tickers().items():
        try:
            result["kalshi_states"][code] = kalshi_rows(ticker)
        except Exception as error:
            result["failed"][ticker] = repr(error)[:120]
    for ticker in NATIONAL:
        try:
            result["kalshi_national"][ticker] = kalshi_rows(ticker)
        except Exception as error:
            result["failed"][ticker] = repr(error)[:120]
    try:
        result["polymarket"] = polymarket_rows()
    except Exception as error:
        result["failed"]["polymarket"] = repr(error)[:120]

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "snapshots.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    data = snapshot()
    print(f"states {len(data['kalshi_states'])}, national {len(data['kalshi_national'])}, "
          f"polymarket {len(data['polymarket'])}, failed {data['failed']}")
