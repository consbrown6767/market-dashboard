"""Watchdog: sends a push notification to your phone when the data collection has a problem.

Runs every 30 minutes (launchd, see install.sh). Read-only: it never writes to the database.
What counts as a problem:
  failed run     a job finished as failed / partial / stopped
  stuck run      a job has been "running" for over 2 hours (it crashed or hung)
  thin run       a snapshot or events run saved under half its usual number of rows
  missed run     a job didn't run at its scheduled time (schedules are read from the launchd plists)
  missing OI     on a weekday after 09:30, today's open interest is missing for some watchlist symbols
  dashboard      http://127.0.0.1:8765 doesn't answer
  disk           less than 10 GB free
  backup         the core backup file is over 30 hours old

One-off problems (a failed run) are sent once. Ongoing ones (dashboard down, missed runs) are sent
when they start, re-sent once a day while they last, and get a "resolved" note when they clear.
Notifications go through ntfy (https://ntfy.sh, free, no account) to the private channel name in
~/.config/market-dashboard/alert.env; the iPhone ntfy app subscribes to it. Messages say what broke
and when, nothing personal (no file paths). If the file is missing, a Mac notification is shown instead.

Usage: watchdog.py          check and alert
       watchdog.py dry      print what's wrong now, send nothing, change nothing
       watchdog.py test     send a test notification
"""

from __future__ import annotations

import json
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import traceback
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from options_collector import BACKUP_DIR, DATA_DIR, DB_PATH, ET, watchlist

ALERT_ENV = Path.home() / ".config" / "market-dashboard" / "alert.env"
STATE_PATH = DATA_DIR / "watchdog_state.json"
AGENTS = Path.home() / "Library" / "LaunchAgents"
PREFIX = "com.marketdashboard.options."
DASHBOARD_URL = "http://127.0.0.1:8765/api/health"

BAD_STATUSES = ("failed", "partial", "stopped")
STUCK_AFTER = timedelta(hours=2)
LATE_AFTER = timedelta(minutes=20)  # how long after a scheduled time before a missing run counts
THIN_JOBS = ("snapshot", "events")  # jobs whose row count is steady enough to compare
MIN_FREE_GB = 10
BACKUP_MAX_AGE = timedelta(hours=30)
REMIND_EVERY = timedelta(hours=24)


def now() -> datetime:
    return datetime.now(ET)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(ET)


# ---------- checks

def last_scheduled(entries: list[dict], before: datetime) -> datetime | None:
    """Most recent launchd calendar time at or before `before` (looks back 8 days)."""
    best = None
    for back in range(9):
        day = (before - timedelta(days=back)).date()
        launchd_weekday = (day.weekday() + 1) % 7  # launchd: 0 = Sunday
        for e in entries:
            if "Weekday" in e and e["Weekday"] % 7 != launchd_weekday:
                continue
            for hour in ([e["Hour"]] if "Hour" in e else range(24)):
                t = datetime(day.year, day.month, day.day, hour, e.get("Minute", 0), tzinfo=ET)
                if t <= before and (best is None or t > best):
                    best = t
        if best:
            return best
    return best


def schedules() -> dict[str, list[dict]]:
    out = {}
    for p in AGENTS.glob(f"{PREFIX}*.plist"):
        cal = plistlib.loads(p.read_bytes()).get("StartCalendarInterval")
        job = p.stem[len(PREFIX):]
        if cal and job != "watchdog":
            out[job] = cal if isinstance(cal, list) else [cal]
    return out


def check_runs(db, state: dict) -> tuple[list[tuple[str, str]], int]:
    """New one-off problems among runs since the last check. Returns (problems, last run id handled)."""
    last_id = state.get("last_run_id")
    if last_id is None:  # first check: look back 6 hours instead of the whole history
        since = (now() - timedelta(hours=6)).isoformat(timespec="seconds")
        last_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM runs WHERE started_at < ?", (since,)).fetchone()[0]
    problems, handled = [], last_id
    for rid, job, started, status, rows, detail in db.execute(
            "SELECT id, job, started_at, status, rows, detail FROM runs WHERE id > ? ORDER BY id", (last_id,)).fetchall():
        when = ts(started).strftime("%a %b %-d %-I:%M %p")
        if status == "running":
            if job != "backfill" and now() - ts(started) > STUCK_AFTER:
                problems.append((f"stuck:{rid}", f"STUCK: the {job} job started {when} and never finished "
                                                 f"(it probably crashed). Log: {job}.log"))
                handled = rid
                continue
            break  # still running normally; look at it again next time
        handled = rid
        if status in BAD_STATUSES:
            problems.append((f"run:{rid}", f"{status.upper()}: the {job} job on {when}.\n"
                                           f"    {(detail or '').strip()[:600]}\n    Log: {job}.log"))
        elif status == "ok" and job in THIN_JOBS:
            usual = [r for (r,) in db.execute(
                "SELECT rows FROM runs WHERE job = ? AND status = 'ok' AND id < ? AND rows > 0 ORDER BY id DESC LIMIT 10",
                (job, rid))]
            if len(usual) >= 5 and rows < 0.5 * median(usual):
                problems.append((f"thin:{rid}", f"THIN DATA: the {job} job on {when} saved {rows:,} rows; "
                                                f"it usually saves about {median(usual):,.0f}."))
    return problems, handled


def check_conditions(db) -> list[tuple[str, str]]:
    """Ongoing problems, true right now."""
    problems, t = [], now()
    for job, entries in sorted(schedules().items()):
        due = last_scheduled(entries, t - LATE_AFTER)
        if due is None:
            continue
        ran = db.execute("SELECT 1 FROM runs WHERE job = ? AND started_at >= ? LIMIT 1",
                         (job, (due - timedelta(minutes=2)).isoformat(timespec="seconds"))).fetchone()
        if not ran:
            problems.append((f"late:{job}", f"MISSED RUN: the {job} job was due {due:%a %b %-d %-I:%M %p} and hasn't "
                                            f"run. The Mac may have been asleep/off, or the job isn't loaded "
                                            f"(fix: re-run collectors/install.sh)."))

    if t.weekday() < 5 and t.hour * 60 + t.minute >= 9 * 60 + 30:
        today = t.date().isoformat()
        have = {u for (u,) in db.execute("SELECT DISTINCT underlying FROM occ_oi WHERE fetch_date = ?", (today,))}
        missing = sorted(set(watchlist()["symbols"]) - have)
        if missing:
            problems.append(("oi-missing", f"MISSING OPEN INTEREST: no open interest for today for "
                                           f"{len(missing)} symbol(s): {', '.join(missing)}."))

    try:
        urllib.request.urlopen(DASHBOARD_URL, timeout=15).read()
    except Exception as e:
        problems.append(("dashboard", f"DASHBOARD DOWN: {DASHBOARD_URL} isn't answering ({e}). "
                                      f"Log: dashboard.log"))

    free_gb = shutil.disk_usage(DATA_DIR).free / 1e9
    if free_gb < MIN_FREE_GB:
        problems.append(("disk", f"LOW DISK: only {free_gb:.1f} GB free. The database grows ~100 MB per trading day."))

    core = BACKUP_DIR / "options-core.db.gz"
    if not core.exists():
        problems.append(("backup", f"BACKUP MISSING: {core.name} doesn't exist."))
    elif t - datetime.fromtimestamp(core.stat().st_mtime, ET) > BACKUP_MAX_AGE:
        problems.append(("backup", f"BACKUP OLD: {core.name} was last written "
                                   f"{datetime.fromtimestamp(core.stat().st_mtime, ET):%a %b %-d %-I:%M %p}."))
    return problems


# ---------- delivery

def ntfy_settings() -> dict | None:
    if not ALERT_ENV.exists():
        return None
    env = {}
    for line in ALERT_ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env if env.get("NTFY_TOPIC") else None


def send_ntfy(env: dict, title: str, body: str, urgent: bool = False,
              priority: str | None = None, tags: str | None = None) -> None:
    req = urllib.request.Request(
        f"{env.get('NTFY_SERVER', 'https://ntfy.sh').rstrip('/')}/{env['NTFY_TOPIC']}",
        data=body.encode()[:3900], method="POST",
        headers={"Title": f"Market Dashboard: {title}", "Priority": priority or ("high" if urgent else "default"),
                 "Tags": tags or ("warning" if urgent else "white_check_mark")})
    urllib.request.urlopen(req, timeout=30).read()


def notify(subject: str) -> None:
    subprocess.run(["osascript", "-e", f"display notification {json.dumps(subject)} with title \"Market Dashboard\""],
                   check=False, capture_output=True)


def deliver(subject: str, body: str, urgent: bool) -> bool:
    """Phone notification via ntfy, else a Mac notification. False if sending failed (retried next check)."""
    env = ntfy_settings()
    if env is None:
        notify(subject + " (phone alerts not set up; see README)")
        return True
    try:
        send_ntfy(env, subject, body, urgent)
        return True
    except Exception as e:
        print(f"ntfy failed: {e}")
        notify(f"{subject} (phone alert failed: {e})")
        return False


# ---------- main

def check(dry: bool = False) -> int:
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    t = now()
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
        new_events, handled = check_runs(db, state)
        current = dict(check_conditions(db))
        db.close()
    except Exception as e:
        new_events, handled = [], state.get("last_run_id")
        current = {"watchdog": f"WATCHDOG ERROR: couldn't check the database: {e}\n{traceback.format_exc()[-800:]}"}

    if dry:
        for _, text in new_events + list(current.items()):
            print(text)
        print("no problems" if not (new_events or current) else "")
        return 0

    open_ = state.get("open", {})  # key -> {"text", "since", "emailed" (= last sent)}
    started = {k: v for k, v in current.items() if k not in open_}
    resolved = {k: v for k, v in open_.items() if k not in current}
    reminders = {k: v for k, v in current.items()
                 if k in open_ and t - ts(open_[k]["emailed"]) > REMIND_EVERY}
    pending = state.get("unsent", []) + [text for _, text in new_events]

    sections = []
    if pending or started:
        sections.append("NEW PROBLEMS\n" + "\n\n".join(pending + list(started.values())))
    if reminders:
        sections.append("STILL HAPPENING\n" + "\n\n".join(
            f"{v} (since {ts(open_[k]['since']):%a %b %-d %-I:%M %p})" for k, v in reminders.items()))
    if resolved:
        sections.append("RESOLVED\n" + "\n\n".join(v["text"] for v in resolved.values()))

    sent = True
    if sections:
        n_bad = len(pending) + len(started) + len(reminders)
        subject = (f"{n_bad} problem{'s' if n_bad != 1 else ''} with data collection" if n_bad
                   else f"resolved: {len(resolved)} problem{'s' if len(resolved) != 1 else ''}")
        body = "\n\n".join(sections) + "\n\nDetails: Status tab at http://127.0.0.1:8765"
        sent = deliver(subject, body, urgent=bool(n_bad))
        print(f"[{t:%Y-%m-%d %H:%M:%S}] alert {'sent' if sent else 'NOT sent'}: {subject}")
    else:
        print(f"[{t:%Y-%m-%d %H:%M:%S}] all good")

    stamp = t.isoformat(timespec="seconds")
    new_open = {}
    for k, text in current.items():
        prev = open_.get(k)
        emailed_now = sent and (k in started or k in reminders)
        new_open[k] = {"text": text, "since": prev["since"] if prev else stamp,
                       "emailed": stamp if emailed_now else (prev["emailed"] if prev else "1970-01-01T00:00:00+00:00")}
    if not sent:  # keep resolved ones open so the "resolved" note goes out with the retry
        new_open.update({k: v for k, v in resolved.items()})
    state = {"last_run_id": handled, "open": new_open, "unsent": [] if sent else pending, "checked_at": stamp}
    STATE_PATH.write_text(json.dumps(state, indent=1))
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "test":
        env = ntfy_settings()
        if env is None:
            print(f"phone alerts not set up: put NTFY_TOPIC in {ALERT_ENV} (see README)")
            return 1
        send_ntfy(env, "test alert", "This is a test. If you can read it, failure alerts will reach your phone.")
        print("test notification sent")
        return 0
    if cmd in ("check", "dry"):
        return check(dry=cmd == "dry")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
