#!/usr/bin/env python3
"""Save one snapshot of Kalshi's 2028 presidential markets. Meant to run hourly.

Kalshi's public API needs no key. Past hourly and daily prices are available through
backfill_history.py, so missed hours can be recovered. Each run is all-or-nothing: if any event
fails or looks wrong, nothing is saved for that hour and the run exits with an error.

Files, kept outside iCloud because background jobs and sync don't mix well:
  ~/MarketData/politics/kalshi/snapshots-YYYY-MM.jsonl   append-only, one line per market
  ~/MarketData/politics/kalshi/last_run.json             result of the latest run

Usage: python3 collect_kalshi.py            take a snapshot
       python3 collect_kalshi.py status     show the latest run
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.elections.kalshi.com/trade-api/v2"
EVENTS = ("KXPRESPERSON-28", "KXPRESNOMD-28", "KXPRESNOMR-28", "KXPRESPARTY-2028")
DATA_DIR = Path(os.environ.get("PGM_DATA_DIR", Path(__file__).resolve().parent)) / "kalshi"
RETRY_WAITS = (5, 15)  # seconds to wait before the second and third attempts

# macOS keeps a certificate list here. Using it directly means this works with any Python,
# including python.org builds that ship without certificates.
SYSTEM_CERTS = "/etc/ssl/cert.pem"


def fetch_event(ticker: str) -> dict:
    url = f"{API}/events/{ticker}?with_nested_markets=true"
    request = urllib.request.Request(url, headers={"User-Agent": "box-of-scraps-research"})
    context = ssl.create_default_context(cafile=SYSTEM_CERTS if Path(SYSTEM_CERTS).exists() else None)
    for wait in (*RETRY_WAITS, None):
        try:
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                return json.load(response)
        except (OSError, ValueError):
            if wait is None:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")


def price(market: dict, field: str) -> float:
    value = float(market[field])
    if not 0 <= value <= 1:
        raise ValueError(f"{market['ticker']} {field} is outside 0-1: {value}")
    return value


def optional_number(market: dict, field: str) -> float | None:
    value = market.get(field)
    return None if value in (None, "") else float(value)


def parse_event(data: dict, ticker: str, fetched_at: str) -> list[dict]:
    """Turn Kalshi's response into snapshot rows. Missing price fields raise an error,
    so a change to Kalshi's API stops the run instead of saving bad data."""
    markets = data["event"].get("markets") or data.get("markets") or []
    rows = [{
        "fetched_at": fetched_at,
        "event_ticker": ticker,
        "ticker": m["ticker"],
        "label": m["yes_sub_title"],
        "yes_bid": price(m, "yes_bid_dollars"),
        "yes_ask": price(m, "yes_ask_dollars"),
        "last_price": price(m, "last_price_dollars"),
        "yes_bid_size": optional_number(m, "yes_bid_size_fp"),
        "yes_ask_size": optional_number(m, "yes_ask_size_fp"),
        "volume": optional_number(m, "volume_fp"),
        "volume_24h": optional_number(m, "volume_24h_fp"),
        "open_interest": optional_number(m, "open_interest_fp"),
    } for m in markets if m["status"] in ("active", "open")]
    if not rows:
        raise ValueError(f"{ticker} returned no open markets")
    return rows


def write_status(data_dir: Path, status: dict) -> None:
    part = data_dir / "last_run.part"
    part.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    part.replace(data_dir / "last_run.json")


def collect(data_dir: Path = DATA_DIR) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat(timespec="seconds")
    try:
        rows = []
        for ticker in EVENTS:
            rows += parse_event(fetch_event(ticker), ticker, fetched_at)
    except Exception as error:
        write_status(data_dir, {"fetched_at": fetched_at, "ok": False, "error": repr(error)})
        raise

    # One write for the whole snapshot, so a run can't leave half an hour's rows behind.
    output = data_dir / f"snapshots-{now:%Y-%m}.jsonl"
    with open(output, "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

    status = {"fetched_at": fetched_at, "ok": True, "rows": len(rows), "file": output.name}
    write_status(data_dir, status)
    return status


def main() -> int:
    if sys.argv[1:] == ["status"]:
        path = DATA_DIR / "last_run.json"
        print(path.read_text(encoding="utf-8") if path.exists() else "No runs yet")
        return 0
    print(json.dumps(collect()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
