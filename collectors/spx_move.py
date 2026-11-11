"""S&P 500 move-size model: every evening, a range for how big the next trading day's S&P 500 move will be.

What it predicts: the next trading day's close-to-close % change of the S&P 500 index (SPX), as five
quantiles (5%, 25%, 50%, 75%, 95%), i.e. a 90% range and a 50% range. Size, not direction: the middle
is close to zero and the width is what matters. Scored in the prediction ledger (ledger.py).

When: after today's close, from values fixed at today's close. The index doesn't print again until
9:30 tomorrow, so that's when the ledger window opens. Futures trade overnight; the model ignores them.

Inputs, all known when the prediction is made:
  recent moves  today's, the last week's and the last month's realized variance (daily high/low range
                plus the opening gap)
  VIX           today's close (Cboe)
  dealer gamma  SqueezeMetrics GEX from the trading day before (today's may not be out yet): whether
                it's negative, and where it ranks in the past year
  down day      how far the index fell today, if it fell
  events        whether tomorrow has a scheduled Fed decision, CPI or jobs report

Method (version 1, agreed with the owner before any testing): a HAR regression. The log of each day's
realized variance is regressed on the last day, week and month of it, plus the other inputs, refit each
evening on every past day since mid-2012 (when a year of dealer gamma exists). The fit gives tomorrow's
typical move; the range comes from how big past surprises actually were (empirical quantiles of moves
divided by their forecast), not a bell curve.

Baselines logged beside every prediction (the simple guesses it must beat):
  recent  the last 21 trading days' standard deviation, bell curve centred on 0
  vix     VIX / sqrt(252) as the one-day standard deviation, bell curve centred on 0 (VIX at face value)

Data kept in options.db:
  index_daily    SPX daily OHLC (Yahoo ^GSPC, 1990 on) and VIX, VIX9D, VIX3M (Cboe, full history).
                 source says where each row came from; 'yahoo-backup' marks a VIX close taken from
                 Yahoo because Cboe hadn't posted it in time (Cboe's value replaces it later).
  econ_calendar  scheduled Fed decisions (federalreserve.gov; unscheduled and cancelled meetings and
                 notation votes left out, since nobody knew of them in advance) and CPI and jobs-report
                 days (BLS, via shared/release_dates.json because BLS blocks scripts).

Usage:
  python spx_move.py             the job: refresh data, resolve finished predictions, predict the next day
  python spx_move.py backtest    rerun the walk-forward backtest into the ledger (mode backtest)
  python spx_move.py research    compare variants, GARCH and a machine-learning challenger (no writes)
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time as clock
import traceback
import warnings
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import ledger
from options_collector import ALPACA_TRADE, ET, PROJECT_DIR, alpaca, connect, finish_run, http_get, load_keys, start_run

MODEL, VERSION = "spx-move", "1"
LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
NORMAL_Z = (-1.6448536, -0.6744898, 0.0, 0.6744898, 1.6448536)
SPEC = {"1": ("log_rv", "log_rv_w", "log_rv_m", "log_iv", "down", "gex_neg", "gex_rank", "fomc", "cpi", "jobs")}
MIN_TRAIN = 500        # past days needed before the first prediction (about two years)
RV_FLOOR = 0.0025      # %^2: a 0.05% day, so a dead-calm day can't send the log to minus infinity
GEX_MAX_AGE = 7        # calendar days; older dealer gamma counts as missing
RUN_TIME = time(16, 50)  # when the evening job runs (backtest predictions are stamped with it)

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
CBOE_SYMBOLS = ("VIX", "VIX9D", "VIX3M")
SPX_START = "1990-01-01"
FED_CURRENT = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_HISTORY = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{}.htm"
FED_FIRST_YEAR = 2002
_here = Path(__file__).with_name("release_dates.json")
RELEASES_PATH = Path(os.environ.get("RELEASES", _here if _here.exists() else PROJECT_DIR / "shared" / "release_dates.json"))
CALENDAR_WARN_DAYS = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS index_daily (
    symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, source TEXT, fetched_at TEXT,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS econ_calendar (
    date TEXT, event TEXT, time_et TEXT, detail TEXT, source TEXT, fetched_at TEXT,
    PRIMARY KEY (date, event)
);
"""
EVENT_NAMES = {"fomc": "Fed decision", "cpi": "CPI (inflation)", "jobs": "Jobs report"}


def now_et() -> datetime:
    return datetime.now(ET)


# ---------- data: Cboe VIX family, Yahoo S&P 500, Fed and BLS calendars

def load_cboe(db, now: datetime) -> int:
    """Full history of each Cboe index every run (a few hundred KB). Replaces any Yahoo backup rows."""
    total = 0
    for sym in CBOE_SYMBOLS:
        text = http_get(CBOE_URL.format(sym)).decode("utf-8")
        rows = []
        for line in text.splitlines()[1:]:
            parts = line.strip().split(",")
            if len(parts) != 5:
                continue
            m, d, y = parts[0].split("/")
            rows.append((sym, f"{y}-{m}-{d}", *(float(x) for x in parts[1:]), "cboe", now.isoformat(timespec="seconds")))
        if len(rows) < 1000:
            raise RuntimeError(f"Cboe {sym}: only {len(rows)} rows; format may have changed")
        db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
        total += len(rows)
    return total


def yahoo_bars(ticker: str, **kw) -> pd.DataFrame:
    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        h = yf.Ticker(ticker).history(interval="1d", auto_adjust=False, **kw)
    h = h.dropna(subset=["Close"])
    h.index = h.index.strftime("%Y-%m-%d")
    return h


def complete_bars(h: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Drop today's bar until 16:15, so a half-finished day is never stored as a close."""
    today = now.date().isoformat()
    return h[(h.index < today) | ((h.index == today) & (now.time() >= time(16, 15)))]


def load_spx(db, now: datetime) -> int:
    have = db.execute("SELECT COUNT(*) FROM index_daily WHERE symbol='SPX'").fetchone()[0]
    h = complete_bars(yahoo_bars("^GSPC", start=SPX_START) if have < 1000 else yahoo_bars("^GSPC", period="1mo"), now)
    if have < 1000 and len(h) < 8000:
        raise RuntimeError(f"Yahoo ^GSPC: only {len(h)} days of history")
    rows = [("SPX", d, r.Open, r.High, r.Low, r.Close, "yahoo", now.isoformat(timespec="seconds")) for d, r in h.iterrows()]
    db.executemany("INSERT OR REPLACE INTO index_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def vix_backup(db, day: str, now: datetime) -> bool:
    """Cboe hasn't posted today's VIX close in time: take Yahoo's, flagged, so the prediction can go out."""
    h = complete_bars(yahoo_bars("^VIX", period="5d"), now)
    if day not in h.index:
        return False
    r = h.loc[day]
    db.execute("INSERT OR IGNORE INTO index_daily VALUES (?,?,?,?,?,?,?,?)",
               ("VIX", day, r.Open, r.High, r.Low, r.Close, "yahoo-backup", now.isoformat(timespec="seconds")))
    db.commit()
    return True


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
FED_HEADING = re.compile(r"^([A-Za-z]+)\s+(\d{1,2})(?:\s*-\s*(?:([A-Za-z]+)\s+)?(\d{1,2}))?\s+Meeting\s+-\s+(\d{4})$")


def fed_meetings(html: str) -> dict[str, str]:
    """Scheduled FOMC decision days (the last day of each meeting) on one federalreserve.gov page,
    date -> detail. Works on the current calendar page and the yearly history pages."""
    from bs4 import BeautifulSoup
    soup, out = BeautifulSoup(html, "lxml"), {}
    for panel in soup.select("div.panel"):  # current page: one panel per year
        head = panel.select_one(".panel-heading")
        y = re.match(r"(\d{4}) FOMC Meetings", head.get_text(" ", strip=True)) if head else None
        if not y:
            continue
        for m in panel.select(".fomc-meeting"):
            month, days = (m.select_one(f".fomc-meeting__{k}") for k in ("month", "date"))
            if not (month and days) or "(" in days.get_text():
                continue  # notation votes, unscheduled or cancelled meetings
            text = days.get_text(strip=True)
            d = date(int(y.group(1)), MONTHS[month.get_text(strip=True).split("/")[-1][:3].lower()],
                     int(text.replace("*", "").split("-")[-1]))
            out[d.isoformat()] = "with projections" if "*" in text else ""
    for h in soup.select("h5"):  # history pages: "January 31-February 1 Meeting - 2012"
        m = FED_HEADING.match(h.get_text(" ", strip=True))
        if m:
            month = m.group(3) or m.group(1)
            out[date(int(m.group(5)), MONTHS[month[:3].lower()], int(m.group(4) or m.group(2))).isoformat()] = ""
    return out


def load_fed(db, now: datetime) -> int:
    """History pages once per year missing, the current calendar page once a day."""
    stamp, n = now.isoformat(timespec="seconds"), 0
    have = {r[0] for r in db.execute("SELECT DISTINCT substr(date, 1, 4) FROM econ_calendar WHERE event='fomc'")}
    current = fed_meetings(http_get(FED_CURRENT).decode("utf-8"))
    current_years = {d[:4] for d in current}
    for y in range(FED_FIRST_YEAR, now.year + 1):
        if str(y) in have or str(y) in current_years:
            continue
        found = fed_meetings(http_get(FED_HISTORY.format(y)).decode("utf-8"))
        if len(found) < 6:
            raise RuntimeError(f"Fed history {y}: only {len(found)} meetings found; page format may have changed")
        db.executemany("INSERT OR REPLACE INTO econ_calendar VALUES (?,?,?,?,?,?)",
                       [(d, "fomc", "14:00", v, FED_HISTORY.format(y), stamp) for d, v in found.items()])
        n += len(found)
        clock.sleep(1)
    if len(current) < 30:
        raise RuntimeError(f"Fed calendar: only {len(current)} meetings found; page format may have changed")
    for y in current_years:  # replace those years whole, so a moved meeting doesn't leave its old date behind
        db.execute("DELETE FROM econ_calendar WHERE event='fomc' AND substr(date, 1, 4) = ?", (y,))
    db.executemany("INSERT OR REPLACE INTO econ_calendar VALUES (?,?,?,?,?,?)",
                   [(d, "fomc", "14:00", v, FED_CURRENT, stamp) for d, v in current.items()])
    return n + len(current)


def load_bls(db, now: datetime) -> int:
    doc = json.loads(RELEASES_PATH.read_text())
    rows = []
    for event in ("cpi", "jobs"):
        e = doc[event]
        for kind in ("past", "upcoming"):
            src = f"{doc['sources'][f'{event}_{kind}']} (read {doc['read_on']})"
            detail = "released" if kind == "past" else "scheduled"
            rows += [(d, event, e["time_et"], detail, src, now.isoformat(timespec="seconds")) for d in e[kind]]
    db.execute("DELETE FROM econ_calendar WHERE event IN ('cpi', 'jobs')")
    db.executemany("INSERT OR REPLACE INTO econ_calendar VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def calendar_runs_out(db) -> str | None:
    """The CPI or jobs schedule ends within CALENDAR_WARN_DAYS: time to refresh release_dates.json."""
    soon = (now_et().date() + timedelta(days=CALENDAR_WARN_DAYS)).isoformat()
    ends = {e: db.execute("SELECT MAX(date) FROM econ_calendar WHERE event=?", (e,)).fetchone()[0] for e in ("cpi", "jobs", "fomc")}
    short = [f"{EVENT_NAMES[e]} dates end {d}" for e, d in ends.items() if not d or d < soon]
    return "; ".join(short) + " (refresh shared/release_dates.json from bls.gov, see its 'about')" if short else None


def spx_check(db) -> str | None:
    """Yahoo's S&P closes against SqueezeMetrics' for the last 10 days both have."""
    rows = db.execute("""SELECT i.date, i.close, m.spx FROM index_daily i JOIN market_gamma m ON m.date = i.date
                         WHERE i.symbol = 'SPX' AND m.spx > 0 ORDER BY i.date DESC LIMIT 10""").fetchall()
    bad = [f"{d} {a:.2f} vs {b:.2f}" for d, a, b in rows if abs(a / b - 1) > 0.0005]
    return f"S&P closes from Yahoo and SqueezeMetrics differ: {', '.join(bad)}" if bad else None


# ---------- features: one row per trading day D, from values fixed at D's close

def load_inputs(db) -> dict[str, pd.DataFrame]:
    q = lambda sql: pd.read_sql_query(sql, db)  # noqa: E731
    return {
        "spx": q("SELECT date, open, high, low, close FROM index_daily WHERE symbol='SPX' ORDER BY date"),
        "vix": q("SELECT date, close AS vix, source AS vix_source FROM index_daily WHERE symbol='VIX' ORDER BY date"),
        "vix9d": q("SELECT date, close AS vix9d FROM index_daily WHERE symbol='VIX9D' ORDER BY date"),
        "vix3m": q("SELECT date, close AS vix3m FROM index_daily WHERE symbol='VIX3M' ORDER BY date"),
        "gex": q("SELECT date, gex FROM market_gamma WHERE gex IS NOT NULL ORDER BY date"),
        "events": q("SELECT date, event FROM econ_calendar"),
    }


def build_frame(inp: dict[str, pd.DataFrame], next_day: str | None = None) -> pd.DataFrame:
    """Inputs for each day D (known at D's close) and, where it has happened, D+1's outcome.
    next_day is the trading day after the last row (for a live prediction); earlier rows use the next row."""
    f = inp["spx"].copy()
    prev = f.close.shift(1)
    f["ret"] = 100 * (f.close / prev - 1)
    park = (100 * np.log(f.high / f.low)) ** 2 / (4 * math.log(2))  # Parkinson: variance from the day's range
    gap = (100 * np.log(f.open / prev)) ** 2                          # plus the opening gap
    rv = (park + gap.fillna(0.0)).where(f.high > f.low, f.ret ** 2)    # bad range data: squared move instead
    f["rv"] = rv.clip(lower=RV_FLOOR)
    f["rv_w"] = f.rv.rolling(5).mean()
    f["rv_m"] = f.rv.rolling(22).mean()
    f["sd21"] = f.ret.rolling(21).std()
    for k in ("vix", "vix9d", "vix3m"):
        f = f.merge(inp[k], on="date", how="left")
    f["dt"] = pd.to_datetime(f.date)
    g = inp["gex"].copy()
    g["dt"] = pd.to_datetime(g.date)
    g["gex_rank"] = g.gex.rolling(252).apply(lambda x: (x <= x[-1]).mean(), raw=True)
    g = g.rename(columns={"date": "gex_date"})[["dt", "gex_date", "gex", "gex_rank"]]
    f = pd.merge_asof(f, g, on="dt", allow_exact_matches=False)  # latest gamma dated before D
    stale = (f.dt - pd.to_datetime(f.gex_date)).dt.days > GEX_MAX_AGE
    f.loc[stale, ["gex", "gex_rank"]] = np.nan
    f["next_day"] = f.date.shift(-1)
    if next_day is not None:
        f.loc[f.index[-1], "next_day"] = next_day
    ev = inp["events"]
    for e in ("fomc", "cpi", "jobs"):
        f[e] = f.next_day.isin(set(ev.date[ev.event == e])).astype(float)
    f["log_rv"], f["log_rv_w"], f["log_rv_m"] = np.log(f.rv), np.log(f.rv_w), np.log(f.rv_m)
    f["log_iv"] = np.log(f.vix ** 2 / 252)
    f["log_iv9d"] = np.log(f.vix9d ** 2 / 252)
    f["term"] = np.log(f.vix / f.vix3m)
    f["down"] = (-f.ret).clip(lower=0)
    f["gex_neg"] = (f.gex < 0).astype(float).where(f.gex.notna())
    f["y_next"] = f.log_rv.shift(-1)
    f["r_next"] = f.ret.shift(-1)
    return f.reset_index(drop=True)


# ---------- the model

class Design:
    """The regression's inputs for every day, built once. Training starts at `start` (a date) or at the
    first day with every input; a variant can be told to start where v1 does, for a fair comparison."""

    def __init__(self, f: pd.DataFrame, cols: tuple[str, ...], start: str | None = None):
        self.cols, self.dates = cols, f.date.to_numpy()
        self.X = np.column_stack([np.ones(len(f))] + [f[c].to_numpy(float) for c in cols])
        self.y, self.r = f.y_next.to_numpy(float), f.r_next.to_numpy(float)
        self.ok = np.isfinite(self.X).all(axis=1)
        self.trainable = self.ok & np.isfinite(self.y) & np.isfinite(self.r)
        if start is not None:
            self.trainable &= self.dates >= start

    def first(self) -> str:
        return self.dates[int(np.argmax(self.trainable))]


class Fit:
    """One HAR fit on the days before position i (each with its next-day outcome known by i's close),
    ready to forecast day i's next-day move."""

    def __init__(self, d: Design, i: int, min_train: int = MIN_TRAIN):
        train = d.trainable[:i]
        self.ready = bool(d.ok[i]) and train.sum() >= min_train
        if not self.ready:
            return
        Xt = d.X[:i][train]
        self.beta = np.linalg.lstsq(Xt, d.y[:i][train], rcond=None)[0]
        z = d.r[:i][train] / np.exp(Xt @ self.beta / 2)  # past moves measured in units of their forecast
        self.qz = np.quantile(z, LEVELS)
        self.sigma = float(np.exp(d.X[i] @ self.beta / 2))
        self.n, self.cols, self.first = int(train.sum()), d.cols, d.dates[:i][train][0]

    def quantiles(self) -> dict:
        return {"q": {str(k): round(float(self.sigma * z), 3) for k, z in zip(LEVELS, self.qz)}}


def baselines(row) -> dict:
    out = {}
    for name, sd in (("recent", row.sd21), ("vix", row.vix / math.sqrt(252))):
        out[name] = {"q": {str(k): round(float(sd * z), 3) for k, z in zip(LEVELS, NORMAL_Z)}}
    return out


def inputs_of(row, fit: Fit, live: bool = False) -> dict:
    x = {"day": row.date, "next_day": row.next_day, "spx_close": round(row.close, 2), "vix": row.vix,
         "gex": None if pd.isna(row.gex) else round(row.gex / 1e9, 3), "gex_date": row.gex_date,
         "gex_rank": None if pd.isna(row.gex_rank) else round(row.gex_rank, 3),
         "move_today": round(row.ret, 3), "rv_day": round(math.sqrt(row.rv), 3), "rv_week": round(math.sqrt(row.rv_w), 3),
         "rv_month": round(math.sqrt(row.rv_m), 3), "events": [e for e in ("fomc", "cpi", "jobs") if row[e]],
         "sigma": round(fit.sigma, 4), "train_days": fit.n}
    if live:
        x |= {"vix_source": row.vix_source, "train_from": fit.first,
              "coef": dict(zip(("const", *fit.cols), (round(float(b), 4) for b in fit.beta))),
              "z_quantiles": [round(float(z), 3) for z in fit.qz]}
    return x


def target_text(day: str) -> str:
    return f"S&P 500 close-to-close % change, {day}"


def stamps(day: str, next_day: str, close: datetime | None = None) -> tuple[datetime, datetime, datetime]:
    d, t = date.fromisoformat(day), date.fromisoformat(next_day)
    return (datetime.combine(d, RUN_TIME, ET), datetime.combine(t, time(9, 30), ET),
            close or datetime.combine(t, time(16, 0), ET))


# ---------- the job

def trading_days(keys: dict, start: date, end: date) -> dict[str, datetime]:
    days = alpaca(ALPACA_TRADE, "/v2/calendar", keys, start=start.isoformat(), end=end.isoformat())
    return {d["date"]: datetime.combine(date.fromisoformat(d["date"]), time.fromisoformat(d["close"]), ET) for d in days}


def resolve_due(db) -> list[str]:
    done = []
    for p in ledger.due(db, MODEL):
        x = json.loads(db.execute("SELECT inputs FROM predictions WHERE id = ?", (p["id"],)).fetchone()[0])
        rows = dict(db.execute("SELECT date, close FROM index_daily WHERE symbol='SPX' AND date IN (?, ?)",
                               (x["day"], x["next_day"])).fetchall())
        if x["next_day"] not in rows or x["day"] not in rows:
            continue  # the close isn't in yet; a later run will get it
        move = round(100 * (rows[x["next_day"]] / rows[x["day"]] - 1), 4)
        ledger.resolve(db, p["id"], move, source=f"SPX close {x['day']} to {x['next_day']} (Yahoo ^GSPC)")
        done.append(f"{x['next_day']} {move:+.2f}%")
    return done


def predict_next(db, keys: dict, now: datetime) -> tuple[str, bool]:
    """Log the prediction for the next trading day if it's due. Returns (note, problem)."""
    days = trading_days(keys, now.date() - timedelta(days=10), now.date() + timedelta(days=10))
    closed = [d for d, c in days.items() if c + timedelta(minutes=15) <= now]
    day = max(closed)
    nxt = min(d for d in days if d > day)
    made, opens, _ = stamps(day, nxt)
    if db.execute("SELECT 1 FROM predictions WHERE model=? AND version=? AND mode='live' AND target=?",
                  (MODEL, VERSION, target_text(nxt))).fetchone():
        return f"{nxt} already predicted", False
    last_chance = now.date().isoformat() == nxt or now.time() >= time(20, 30)
    if now >= opens:
        started = db.execute("SELECT 1 FROM predictions WHERE model=? AND version=? AND mode='live' LIMIT 1",
                             (MODEL, VERSION)).fetchone()
        return (f"missed {nxt}: the market opened before a prediction was made", True) if started else \
               (f"live predictions start after the next close ({nxt} opened before the first run)", False)
    have = lambda sym: db.execute("SELECT source FROM index_daily WHERE symbol=? AND date=?", (sym, day)).fetchone()  # noqa: E731
    if not have("SPX"):
        return f"waiting for the S&P close of {day}", last_chance and now.date().isoformat() == nxt
    if not have("VIX") and not (last_chance and vix_backup(db, day, now)):
        return f"waiting for Cboe's VIX close of {day}", last_chance and now.date().isoformat() == nxt
    f = build_frame(load_inputs(db), next_day=nxt)
    i = int(f.index[f.date == day][0])
    fit = Fit(Design(f, SPEC[VERSION]), i)
    row = f.iloc[i]
    if not fit.ready:
        missing = [c for c in SPEC[VERSION] if not np.isfinite(row[c])]
        return f"can't predict {nxt}: missing {', '.join(missing) or 'training data'}", True
    fc = fit.quantiles()
    ledger.log(db, model=MODEL, version=VERSION, mode="live", target=target_text(nxt), kind="quantiles",
               opens_at=opens, resolves_at=days[nxt], forecast=fc, baselines=baselines(row),
               inputs=inputs_of(row, fit, live=True))
    q = fc["q"]
    return f"predicted {nxt}: 90% {q['0.05']:+.2f}% to {q['0.95']:+.2f}%, 50% {q['0.25']:+.2f}% to {q['0.75']:+.2f}%", False


def job() -> int:
    db = connect()
    db.executescript(SCHEMA)
    ledger.ensure(db)
    run_id = start_run(db, "spxmove")
    now = now_et()
    counts, problems, notes = {}, [], []
    loaders = [("spx", load_spx), ("vix", load_cboe), ("bls", load_bls)]
    fed_today = db.execute("SELECT MAX(fetched_at) FROM econ_calendar WHERE event='fomc'").fetchone()[0]
    if not fed_today or fed_today[:10] != now.date().isoformat():
        loaders.append(("fed", load_fed))
    for name, loader in loaders:
        try:
            counts[name] = loader(db, now)
            db.commit()
        except Exception as e:
            db.rollback()
            problems.append(f"{name}: {e} {traceback.format_exc()[-300:]}")
    try:
        notes += [f"resolved {x}" for x in resolve_due(db)]
    except Exception as e:
        db.rollback()
        problems.append(f"resolving: {e} {traceback.format_exc()[-400:]}")
    try:
        note, bad = predict_next(db, load_keys(), now)
        (problems if bad else notes).append(note)
    except Exception as e:
        db.rollback()
        problems.append(f"predicting: {e} {traceback.format_exc()[-400:]}")
    for check in (spx_check(db), calendar_runs_out(db) if now.weekday() == 0 and now.hour == 16 else None):
        if check:
            problems.append(check)
    detail = "; ".join([" ".join(f"{k}={v}" for k, v in counts.items()), *notes, *problems])
    status = "ok" if not problems else "partial" if counts or notes else "failed"
    finish_run(db, run_id, status, sum(counts.values()), detail)
    print(f"[{now:%Y-%m-%d %H:%M:%S}] spxmove run {run_id}: {status} {detail[:500]}")
    return 0 if status != "failed" else 1


# ---------- backtest and research

def walk_forward(f: pd.DataFrame, cols: tuple[str, ...], start: str | None = None, only=None) -> dict[int, Fit]:
    """A fresh fit for every day whose next-day outcome is known, each using only earlier days."""
    d, out = Design(f, cols, start), {}
    for i in (range(len(f)) if only is None else only):
        if np.isfinite(d.r[i]):
            fit = Fit(d, i)
            if fit.ready:
                out[i] = fit
    return out


def backtest(db) -> str:
    f = build_frame(load_inputs(db))
    fits = walk_forward(f, SPEC[VERSION])
    cleared = ledger.clear_backtest(db, MODEL, VERSION)
    for i, fit in fits.items():
        row = f.iloc[i]
        made, opens, resolves = stamps(row.date, row.next_day)
        pid = ledger.log(db, model=MODEL, version=VERSION, mode="backtest", target=target_text(row.next_day),
                         kind="quantiles", made_at=made, opens_at=opens, resolves_at=resolves,
                         forecast=fit.quantiles(), baselines=baselines(row), inputs=inputs_of(row, fit))
        ledger.resolve(db, pid, round(float(row.r_next), 4), source="SPX close to close (Yahoo ^GSPC)")
    days = sorted(f.next_day.iat[i] for i in fits)
    return f"backtest v{VERSION}: cleared {cleared}, logged and resolved {len(fits)} days, {days[0]} to {days[-1]}"


def _pinball(q: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Average pinball loss per day; q is (days, levels)."""
    lv = np.array(LEVELS)
    miss = y[:, None] - q
    return np.maximum(lv * miss, (lv - 1) * miss).mean(axis=1)


def _garch(f: pd.DataFrame, test: list[int]) -> np.ndarray:
    """GJR-GARCH(1,1), the standard volatility model from returns alone: refit monthly by maximum
    likelihood on the same past days, ranges from its own past surprises."""
    from scipy.optimize import minimize
    from scipy.signal import lfilter
    r = f.ret.to_numpy(float)
    start = int(np.argmax(Design(f, SPEC[VERSION]).trainable))  # same training start as v1

    def variance(p, x):
        w, a, g, b = p
        u = np.empty(len(x) + 1)
        u[0] = np.var(x)
        u[1:] = w + (a + g * (x < 0)) * x ** 2
        return lfilter([1.0], [1.0, -b], u)  # sigma^2[t] for t = 0..len(x); the last is the next day

    def nll(p, x):
        if p[1] + p[2] / 2 + p[3] >= 0.999:
            return 1e10
        s2 = variance(p, x)[:-1]
        return 0.5 * np.sum(np.log(s2) + x ** 2 / s2)

    out, p, month = np.full((len(f), len(LEVELS)), np.nan), np.array([0.02, 0.03, 0.12, 0.88]), None
    for i in test:
        if f.date.iat[i][:7] != month:
            month = f.date.iat[i][:7]
            x = r[start + 1:i + 1]
            p = minimize(nll, p, args=(x,), method="L-BFGS-B",
                         bounds=[(1e-6, 1), (0, 0.5), (0, 0.5), (0.5, 0.999)]).x
            s = np.sqrt(variance(p, x))
            qz = np.quantile(x[1:] / s[1:-1], LEVELS)
        s_next = math.sqrt(variance(p, r[start + 1:i + 1])[-1])
        out[i] = s_next * qz
    return out


def _boosted(f: pd.DataFrame, test: list[int], cols: tuple[str, ...]) -> np.ndarray:
    """Machine-learning challenger: gradient-boosted trees fit straight to each quantile of tomorrow's
    move, from the same inputs as v1. Refit monthly on the same past days."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    X, y = f[list(cols)].to_numpy(float), f.r_next.to_numpy(float)
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    out, models, month = np.full((len(f), len(LEVELS)), np.nan), None, None
    for i in test:
        if f.date.iat[i][:7] != month:
            month, tr = f.date.iat[i][:7], ok[:i]
            models = [HistGradientBoostingRegressor(loss="quantile", quantile=lv, max_iter=200, learning_rate=0.05,
                                                    max_leaf_nodes=15, min_samples_leaf=50, random_state=0)
                      .fit(X[:i][tr], y[:i][tr]) for lv in LEVELS]
        out[i] = np.sort([m.predict(X[i:i + 1])[0] for m in models])
    return out


def _gap(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    c = ledger.compare(list(a), list(b))
    return c["gap"], c["gap_se"]


def research(db) -> dict:
    """Every variant on the same test days as v1. Prints a table and returns the numbers."""
    f = build_frame(load_inputs(db))
    v1 = walk_forward(f, SPEC[VERSION])
    test = sorted(v1)
    y = f.r_next.to_numpy(float)[test]
    sd = f.sd21.to_numpy(float)[test][:, None] * np.array(NORMAL_Z)
    vx = (f.vix.to_numpy(float)[test] / math.sqrt(252))[:, None] * np.array(NORMAL_Z)
    q = {"Recent moves (baseline)": sd, "VIX at face value (baseline)": vx}
    variants = {
        "v1: HAR + VIX + gamma + down days + events": SPEC[VERSION],
        "Recent moves only (HAR)": ("log_rv", "log_rv_w", "log_rv_m"),
        "HAR + down days": ("log_rv", "log_rv_w", "log_rv_m", "down"),
        "HAR + VIX": ("log_rv", "log_rv_w", "log_rv_m", "log_iv"),
        "HAR + VIX + down days": ("log_rv", "log_rv_w", "log_rv_m", "log_iv", "down"),
        "HAR + VIX + down days + events": ("log_rv", "log_rv_w", "log_rv_m", "log_iv", "down", "fomc", "cpi", "jobs"),
        "VIX only, rescaled": ("log_iv",),
        "v1 + VIX9D": SPEC[VERSION] + ("log_iv9d",),
        "v1 + VIX term structure": SPEC[VERSION] + ("term",),
    }
    start = Design(f, SPEC[VERSION]).first()
    for name, cols in variants.items():
        fits = v1 if cols == SPEC[VERSION] else walk_forward(f, cols, start=start, only=test)
        q[name] = np.array([fits[i].sigma * fits[i].qz if i in fits else [np.nan] * 5 for i in test])
    t0 = clock.time()
    q["GJR-GARCH(1,1)"] = _garch(f, test)[test]
    t1 = clock.time()
    q["Boosted trees (machine learning)"] = _boosted(f, test, SPEC[VERSION])[test]
    t2 = clock.time()
    base = _pinball(q["v1: HAR + VIX + gamma + down days + events"], y)
    rows = {}
    for name, qq in q.items():
        ok = np.isfinite(qq).all(axis=1)
        L = _pinball(qq[ok], y[ok])
        rows[name] = {
            "days": int(ok.sum()), "loss": float(L.mean()),
            "vs_recent": 1 - L.mean() / _pinball(sd[ok], y[ok]).mean(),
            "vs_vix": 1 - L.mean() / _pinball(vx[ok], y[ok]).mean(),
            "cover90": float(((qq[ok, 0] <= y[ok]) & (y[ok] <= qq[ok, 4])).mean()),
            "cover50": float(((qq[ok, 1] <= y[ok]) & (y[ok] <= qq[ok, 3])).mean()),
            "gap_vs_v1": _gap(L, base[ok]),
        }
    dates = f.next_day.to_numpy()[test]
    periods = {"2014-2019": ("2014", "2019-12-31"), "2020-2022": ("2020", "2022-12-31"), "2023-2026": ("2023", "2027")}
    by_period = {}
    for p, (a, b) in periods.items():
        m = (dates >= a) & (dates <= b)
        by_period[p] = {"days": int(m.sum()), **{n: float(_pinball(q[n][m], y[m]).mean()) for n in
                        ("v1: HAR + VIX + gamma + down days + events", "Recent moves (baseline)", "VIX at face value (baseline)")}}
    ev = {}
    nxt = f.iloc[test]
    for e in ("fomc", "cpi", "jobs"):
        m = nxt[e].to_numpy() > 0
        ev[e] = {"days": int(m.sum()), "avg_abs_move": float(np.abs(y[m]).mean()),
                 "v1_width90": float((q["v1: HAR + VIX + gamma + down days + events"][m, 4] - q["v1: HAR + VIX + gamma + down days + events"][m, 0]).mean()),
                 "cover90": float(((q["v1: HAR + VIX + gamma + down days + events"][m, 0] <= y[m]) & (y[m] <= q["v1: HAR + VIX + gamma + down days + events"][m, 4])).mean())}
    quiet = (nxt[["fomc", "cpi", "jobs"]].sum(axis=1) == 0).to_numpy()
    ev["none"] = {"days": int(quiet.sum()), "avg_abs_move": float(np.abs(y[quiet]).mean())}
    g = nxt.gex_neg.to_numpy() > 0
    implied = f.vix.to_numpy(float)[test] / math.sqrt(252) * math.sqrt(2 / math.pi)  # expected |move| if VIX were right
    gamma = {"negative_days": int(g.sum()), "positive_days": int((~g).sum()),
             "move_vs_vix_negative": float(np.abs(y[g]).mean() / implied[g].mean()),
             "move_vs_vix_positive": float(np.abs(y[~g]).mean() / implied[~g].mean())}
    coef = dict(zip(("const", *SPEC[VERSION]), (round(float(b), 4) for b in v1[test[-1]].beta)))
    out = {"test_days": len(test), "first": dates[0], "last": dates[-1], "variants": rows, "by_period": by_period,
           "events": ev, "gamma": gamma, "latest_coef": coef, "seconds": {"garch": round(t1 - t0), "boosted": round(t2 - t1)}}
    print(f"{len(test)} test days, {dates[0]} to {dates[-1]}. Loss = average pinball loss (lower is better).")
    print(f"{'':48} {'loss':>7} {'vs recent':>9} {'vs VIX':>7} {'90% in':>7} {'50% in':>7} {'gap vs v1 (se)':>16}")
    for name, r in rows.items():
        gp, se = r["gap_vs_v1"]
        print(f"{name:48} {r['loss']:7.4f} {r['vs_recent']:9.1%} {r['vs_vix']:7.1%} {r['cover90']:7.1%} {r['cover50']:7.1%} "
              f"{gp:+8.4f} ({se:.4f})")
    print(json.dumps({k: out[k] for k in ("by_period", "events", "gamma", "latest_coef", "seconds")}, indent=1, default=str))
    return out


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "job"
    if cmd == "job":
        return job()
    db = connect()
    db.executescript(SCHEMA)
    ledger.ensure(db)
    if cmd == "backtest":
        print(backtest(db))
    elif cmd == "research":
        out = research(db)
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
