"""Economy gauges for the Today tab: a handful of FRED series, refreshed once a day into
`macro_series` (source "fred-gauges"). Context for big decisions, not a market-timing signal
(macro timing failed its test: docs/macro-timing/).

Series: T10Y3M (10-year minus 3-month Treasury yield), SAHMREALTIME (Sahm recession rule, as first
published), UNRATE (unemployment), ICSA (weekly jobless claims), CPIAUCSL and CPILFESL (consumer
prices, all items and core), DFF (Fed funds rate), BAMLH0A0HYM2 (junk-bond yield spread).

    macro_gauges.py          # refresh (job `gauges`, daily)
"""

from __future__ import annotations

import urllib.request
from datetime import datetime

from options_collector import ET, connect, finish_run, start_run  # importing it also sets up certificates

SERIES = ("T10Y3M", "SAHMREALTIME", "UNRATE", "ICSA", "CPIAUCSL", "CPILFESL", "DFF", "BAMLH0A0HYM2")
SCHEMA = """CREATE TABLE IF NOT EXISTS macro_series (
    series TEXT, date TEXT, value REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (series, date))"""


def fred(series_id: str) -> list[tuple[str, float]]:
    # FRED answers Python's standard user agent; no key needed for the chart download.
    with urllib.request.urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=90) as r:
        text = r.read().decode()
    out = []
    for ln in text.splitlines()[1:]:
        d, v = ln.split(",")[:2]
        if v not in ("", "."):
            out.append((d, float(v)))
    return out


def main() -> int:
    db = connect()
    db.executescript(SCHEMA)
    run_id = start_run(db, "gauges")
    now = datetime.now(ET).isoformat(timespec="seconds")
    n, failed, latest = 0, [], {}
    for s in SERIES:
        try:
            rows = fred(s)
            if not rows:
                raise RuntimeError("no rows")
            db.executemany("INSERT OR REPLACE INTO macro_series VALUES (?,?,?,?,?)", [(s, d, v, "fred-gauges", now) for d, v in rows])
            db.commit()
            n += len(rows)
            latest[s] = rows[-1][0]
        except Exception as ex:
            db.rollback()
            failed.append(f"{s}: {ex}")
    status = "ok" if not failed else "partial" if latest else "failed"
    detail = " ".join(f"{k}={v}" for k, v in latest.items()) + (f" FAILED {'; '.join(failed)}" if failed else "")
    finish_run(db, run_id, status, n, detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] gauges run {run_id}: {status} {detail[:300]}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
