"""Ships passing the world's 28 shipping chokepoints (Hormuz, Bab el-Mandeb, Suez, ...), daily.

Source: IMF PortWatch (free, no key), built from ship-tracking (AIS) signals. One row per
chokepoint per day: ships by type and their carrying capacity (deadweight tonnes). PortWatch
publishes with a lag of a few days and revises recent days, so each run re-reads the last
REFRESH_DAYS and overwrites them. The first run backfills everything from 2019 (~80,000 rows, ~6 MB).

Table: chokepoint_daily (see SCHEMA). Usage: python shipping_collector.py [backfill]
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import date, datetime, timedelta

from options_collector import ET, connect, finish_run, http_get, start_run

URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
       "Daily_Chokepoints_Data/FeatureServer/0/query")
PAGE = 1000  # the service's maximum per request
REFRESH_DAYS = 45
COLUMNS = ["date", "portid", "portname", "n_total", "n_tanker", "n_container", "n_dry_bulk",
           "n_general_cargo", "n_roro", "n_cargo", "capacity", "capacity_tanker", "capacity_container",
           "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro", "capacity_cargo"]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS chokepoint_daily (
    date TEXT, portid TEXT, portname TEXT,
    n_total INTEGER, n_tanker INTEGER, n_container INTEGER, n_dry_bulk INTEGER,
    n_general_cargo INTEGER, n_roro INTEGER, n_cargo INTEGER,
    capacity INTEGER, capacity_tanker INTEGER, capacity_container INTEGER, capacity_dry_bulk INTEGER,
    capacity_general_cargo INTEGER, capacity_roro INTEGER, capacity_cargo INTEGER,
    fetched_at TEXT,
    PRIMARY KEY (date, portid)
);
CREATE INDEX IF NOT EXISTS chokepoint_daily_port ON chokepoint_daily (portid, date);
"""


def fetch(since: str | None) -> list[dict]:
    where = f"date >= DATE '{since}'" if since else "1=1"
    rows, offset = [], 0
    while True:
        q = {"f": "json", "where": where, "outFields": ",".join(COLUMNS), "returnGeometry": "false",
             "orderByFields": "ObjectId", "resultOffset": offset, "resultRecordCount": PAGE}
        d = json.loads(http_get(f"{URL}?{urllib.parse.urlencode(q)}"))
        if "error" in d:
            raise RuntimeError(f"PortWatch error: {d['error']}")
        batch = [f["attributes"] for f in d.get("features", [])]
        rows += batch
        if len(batch) < PAGE and not d.get("exceededTransferLimit"):
            break
        offset += PAGE
    return rows


def main() -> int:
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "shipping")
    now = datetime.now(ET).isoformat(timespec="seconds")
    try:
        have = db.execute("SELECT count(*) FROM chokepoint_daily").fetchone()[0]
        full = have == 0 or (len(sys.argv) > 1 and sys.argv[1] == "backfill")
        since = None if full else (date.today() - timedelta(days=REFRESH_DAYS)).isoformat()
        rows = fetch(since)
        if not rows:
            raise RuntimeError("PortWatch returned no rows")
        db.executemany(f"INSERT OR REPLACE INTO chokepoint_daily VALUES ({','.join('?' * (len(COLUMNS) + 1))})",
                       [[r.get(c) for c in COLUMNS] + [now] for r in rows])
        db.commit()
        latest = db.execute("SELECT max(date) FROM chokepoint_daily").fetchone()[0]
        status, detail = "ok", f"{'backfill' if full else 'refresh'} rows={len(rows)} latest_day={latest}"
    except Exception as ex:
        db.rollback()
        status, rows, detail = "failed", [], str(ex)
    finish_run(db, run_id, status, len(rows), detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] shipping run {run_id}: {status} {detail[:300]}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
