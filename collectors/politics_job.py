"""Hourly job for the political game machine: fresh prices and headlines, then a rebuild.

The machine's code is in politics/ (project folder). install.sh copies it to ~/MarketData/politics,
and it runs there, next to its data: background jobs and iCloud don't mix well. The Politics tab
reads outputs/data.json from that folder.

A price step that fails makes the run `partial`, and the rebuild uses the last good data. Headlines
are only hints, so a failed scan is just noted. Only a failed rebuild counts as a failed run.
Past prices (daily history, the Polymarket archive in options.db) change slowly, so those two steps
run once a day.

Forecasts aren't logged here. That stays a deliberate step: run_all.py --log (see politics/HANDOFF.md).

Usage: python politics_job.py [--daily]     --daily forces the once-a-day steps
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from options_collector import DATA_DIR, ET, connect, finish_run, start_run

HOME = DATA_DIR / "politics"
HOURLY = (["collect_kalshi.py"], ["snapshot_polymarket.py"], ["snapshot_polymarket.py", "states"],
          ["snapshot_senate.py"], ["news_scan.py"])
DAILY = (["read_polymarket.py"], ["backfill_history.py"])
DAILY_HOUR = 2  # the 2:25 am run
NOT_WORTH_AN_ALERT = "news_scan.py"
STEP_TIMEOUT = 600
REBUILD_TIMEOUT = 1500


def step(args: list[str], timeout: int) -> str | None:
    """Run one script from the machine's folder. Returns what went wrong, or None."""
    try:
        done = subprocess.run([sys.executable, *args], cwd=HOME, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "PGM_DATA_DIR": str(HOME)})
    except subprocess.TimeoutExpired:
        return f"{args[0]}: timed out after {timeout}s"
    if done.returncode:
        return f"{args[0]}: {(done.stderr or done.stdout).strip()[-300:]}"
    return None


def main() -> int:
    db = connect()
    run_id = start_run(db, "politics")
    db.close()  # the steps take minutes, and this job writes nothing else to the database
    now = datetime.now(ET)
    steps = HOURLY + (DAILY if now.hour == DAILY_HOUR or "--daily" in sys.argv else ())
    problems = [p for p in (step(args, STEP_TIMEOUT) for args in steps) if p]
    rebuild = step(["run_all.py"], REBUILD_TIMEOUT)
    serious = [p for p in problems if not p.startswith(NOT_WORTH_AN_ALERT)]
    status = "failed" if rebuild else "partial" if serious else "ok"
    detail = "; ".join(([rebuild] if rebuild else []) + problems) or f"{len(steps)} data steps and rebuild ok"
    db = connect()
    finish_run(db, run_id, status, 0 if rebuild else 1, detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] politics run {run_id}: {status} {detail[:400]}")
    return 1 if rebuild else 0


if __name__ == "__main__":
    sys.exit(main())
