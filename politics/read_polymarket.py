#!/usr/bin/env python3
"""Copy the 2028 Polymarket rows out of Market Dashboard's database, into data/dev/.

The dashboard's events job already archives Polymarket hourly, so this project doesn't need its
own collector for history. The database is opened read-only. Safe to re-run: each run rebuilds
data/dev/.

Usage: python3 read_polymarket.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
DB_PATH = Path.home() / "MarketData" / "options.db"
OUT_DIR = HERE / "data" / "dev"


def to_utc(timestamp: str) -> str:
    # Source times are US/Eastern, so the offset changes when the clocks do. Sorting the raw
    # text would put rows in the wrong order around that change; UTC sorts correctly.
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc).isoformat(timespec="seconds")


def rows_as_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    # Write to a temporary name first, so a failed run can't leave a half-written file.
    part = path.with_suffix(".part")
    with open(part, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    part.replace(path)


def extract(db_path: Path = DB_PATH, out_dir: Path = OUT_DIR) -> dict:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    db = sqlite3.connect(f"file:{quote(str(db_path))}?mode=ro", uri=True, timeout=30)
    # The group filter leaves out non-US-election titles such as "...before 2028".
    events = rows_as_dicts(db.execute(
        "SELECT * FROM poly_events WHERE grp = 'politics' AND title LIKE '%2028%' ORDER BY volume DESC"))
    event_ids = [e["id"] for e in events]
    marks = ",".join("?" * len(event_ids))
    markets = rows_as_dicts(db.execute(
        f"SELECT * FROM poly_markets WHERE event_id IN ({marks}) ORDER BY event_id, id", event_ids))
    snapshots = rows_as_dicts(db.execute(
        f"SELECT * FROM poly_snapshots WHERE market_id IN (SELECT id FROM poly_markets WHERE event_id IN ({marks}))", event_ids))
    db.close()
    for snapshot in snapshots:
        snapshot["fetched_utc"] = to_utc(snapshot["fetched_at"])

    if not snapshots:
        raise SystemExit("No 2028 snapshots found: refusing to replace existing data")
    snapshots.sort(key=lambda s: (s["fetched_utc"], s["market_id"]))

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "poly_events.jsonl", events)
    write_jsonl(out_dir / "poly_markets.jsonl", markets)
    write_jsonl(out_dir / "poly_snapshots.jsonl", snapshots)

    manifest = {
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Market Dashboard database (read-only)",
        "events": len(events),
        "markets": len(markets),
        "snapshots": len(snapshots),
        "first_snapshot_utc": snapshots[0]["fetched_utc"],
        "last_snapshot_utc": snapshots[-1]["fetched_utc"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(extract(), indent=2))
