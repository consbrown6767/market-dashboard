"""Polymarket event tracking for the Events tab.

Borrowed from polymarket-bot-v2's ingestion layer (Gamma paging, outcome/price parsing,
negRisk end dates, deterministic volume/liquidity filters). Its LLM agent chain, signal,
sizing and trading layers are intentionally not used: this only records what markets price.

Every run (hourly, all week: Polymarket trades around the clock):
  1. Page through active events from the Gamma API, highest 24h volume first.
  2. Keep events with real activity (24h volume >= MIN_EVENT_VOLUME_24H or liquidity >=
     MIN_EVENT_LIQUIDITY), and within them markets that are open with some liquidity.
  3. Classify each event into a dashboard group from its Polymarket tags (deterministic map).
     Sports / culture ("other") keeps only the top OTHER_EVENT_LIMIT events by 24h volume.
  4. Upsert events and markets; append one price snapshot per market.

Tables: poly_events, poly_markets, poly_snapshots (see SCHEMA). Usage: python events_collector.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone

from options_collector import ET, connect, finish_run, http_get, start_run

GAMMA = "https://gamma-api.polymarket.com"
PAGE = 100
MIN_EVENT_VOLUME_24H = 5_000
MIN_EVENT_LIQUIDITY = 25_000
MIN_MARKET_LIQUIDITY = 5_000
MIN_MARKET_VOLUME_24H = 2_500
STOP_BELOW_VOLUME_24H = 1_000  # pages are sorted by 24h volume; stop once a whole page is below this
OTHER_EVENT_LIMIT = 50

# First matching group wins, in this order. Matched against lowercased tag labels.
GROUPS = [
    ("macro", {"economy", "fed", "fed rates", "fomc", "inflation", "recession", "macro indicators",
               "economic policy", "global rates", "gdp", "jobs", "jobs report", "cpi", "interest rates",
               "treasuries", "unemployment", "economics"}),
    ("geopolitics", {"geopolitics", "world", "middle east", "ukraine", "russia", "china", "israel", "iran",
                     "military", "war", "nato", "taiwan", "gaza", "north korea", "foreign policy", "world affairs"}),
    ("business", {"business", "tech", "ai", "stocks", "earnings", "ipos", "ipo", "companies", "big tech",
                  "finance", "tariffs", "trade", "trade war", "commodities", "oil", "equities"}),
    ("politics", {"politics", "elections", "us politics", "trump", "congress", "senate", "global elections",
                  "us elections", "supreme court", "courts"}),
    ("crypto", {"crypto", "bitcoin", "ethereum", "crypto prices", "solana", "stablecoins"}),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS poly_events (
    id TEXT PRIMARY KEY, slug TEXT, title TEXT, grp TEXT, tags TEXT, end_date TEXT, neg_risk INTEGER,
    volume REAL, volume_24h REAL, liquidity REAL, open_interest REAL, url TEXT,
    first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS poly_markets (
    id TEXT PRIMARY KEY, event_id TEXT, question TEXT, label TEXT, outcomes TEXT, end_date TEXT,
    slug TEXT, first_seen TEXT, last_seen TEXT
);
-- price = first outcome's price ("Yes" for binary markets), 0..1. change_* are Gamma's.
CREATE TABLE IF NOT EXISTS poly_snapshots (
    fetched_at TEXT, market_id TEXT, price REAL, last_trade REAL, best_bid REAL, best_ask REAL,
    spread REAL, change_1h REAL, change_1d REAL, change_1w REAL, change_1m REAL,
    volume_24h REAL, volume REAL, liquidity REAL,
    PRIMARY KEY (fetched_at, market_id)
);
CREATE INDEX IF NOT EXISTS poly_snapshots_market ON poly_snapshots (market_id, fetched_at);
CREATE INDEX IF NOT EXISTS poly_markets_event ON poly_markets (event_id);
"""


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def json_list(raw) -> list:
    """Gamma returns some lists as JSON strings ('["Yes", "No"]')."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.startswith("["):
        try:
            return json.loads(raw)
        except ValueError:
            return []
    return []


def classify(tag_labels: list[str]) -> str:
    labels = {t.lower() for t in tag_labels}
    for name, keys in GROUPS:
        if labels & keys:
            return name
    return "other"


def fetch_events() -> list[dict]:
    events, offset = [], 0
    while True:
        q = {"active": "true", "closed": "false", "limit": PAGE, "offset": offset,
             "order": "volume24hr", "ascending": "false"}
        batch = json.loads(http_get(f"{GAMMA}/events?{urllib.parse.urlencode(q)}"))
        if not batch:
            break
        events += batch
        if all((num(e.get("volume24hr")) or 0) < STOP_BELOW_VOLUME_24H for e in batch):
            break
        offset += PAGE
        time.sleep(0.2)
    return events


def main() -> int:
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "events")
    now = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    try:
        raw = fetch_events()
        kept, other_count, n_markets = [], 0, 0
        for e in raw:
            if (num(e.get("volume24hr")) or 0) < MIN_EVENT_VOLUME_24H and (num(e.get("liquidity")) or 0) < MIN_EVENT_LIQUIDITY:
                continue
            tags = [t.get("label", "") for t in e.get("tags") or []]
            grp = classify(tags)
            if grp == "other":
                if other_count >= OTHER_EVENT_LIMIT:
                    continue
                other_count += 1
            kept.append((e, grp, tags))

        for e, grp, tags in kept:
            eid = str(e["id"])
            db.execute("""INSERT INTO poly_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, title=excluded.title, grp=excluded.grp,
                          tags=excluded.tags, end_date=excluded.end_date, neg_risk=excluded.neg_risk,
                          volume=excluded.volume, volume_24h=excluded.volume_24h, liquidity=excluded.liquidity,
                          open_interest=excluded.open_interest, url=excluded.url, last_seen=excluded.last_seen""",
                       (eid, e.get("slug"), e.get("title"), grp, json.dumps(tags), e.get("endDate"),
                        int(bool(e.get("negRisk"))), num(e.get("volume")), num(e.get("volume24hr")),
                        num(e.get("liquidity")), num(e.get("openInterest")),
                        f"https://polymarket.com/event/{e.get('slug', eid)}", now, now))
            for m in e.get("markets") or []:
                if m.get("closed") or not m.get("active"):
                    continue
                if (num(m.get("liquidityNum")) or 0) < MIN_MARKET_LIQUIDITY and (num(m.get("volume24hr")) or 0) < MIN_MARKET_VOLUME_24H:
                    continue
                prices = [num(p) for p in json_list(m.get("outcomePrices"))]
                # For negRisk (mutually exclusive) events the market endDate is a placeholder;
                # the real resolution date is the event's (same rule as the polybot).
                end = e.get("endDate") if e.get("negRisk") else (m.get("endDate") or e.get("endDate"))
                db.execute("""INSERT INTO poly_markets VALUES (?,?,?,?,?,?,?,?,?)
                              ON CONFLICT(id) DO UPDATE SET event_id=excluded.event_id, question=excluded.question,
                              label=excluded.label, outcomes=excluded.outcomes, end_date=excluded.end_date,
                              slug=excluded.slug, last_seen=excluded.last_seen""",
                           (str(m["id"]), eid, m.get("question"), m.get("groupItemTitle") or None,
                            json.dumps(json_list(m.get("outcomes"))), end, m.get("slug"), now, now))
                db.execute("INSERT OR REPLACE INTO poly_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (now, str(m["id"]), prices[0] if prices else None, num(m.get("lastTradePrice")),
                            num(m.get("bestBid")), num(m.get("bestAsk")), num(m.get("spread")),
                            num(m.get("oneHourPriceChange")), num(m.get("oneDayPriceChange")),
                            num(m.get("oneWeekPriceChange")), num(m.get("oneMonthPriceChange")),
                            num(m.get("volume24hr")), num(m.get("volumeNum")), num(m.get("liquidityNum"))))
                n_markets += 1
        db.commit()
        status, rows = "ok", n_markets
        detail = f"events_scanned={len(raw)} events_kept={len(kept)} markets={n_markets}"
    except Exception as ex:
        db.rollback()
        status, rows, detail = "failed", 0, str(ex)
    finish_run(db, run_id, status, rows, detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] events run {run_id}: {status} {detail[:300]}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
