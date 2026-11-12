"""Stock direction model: each week, the chance each S&P 100 stock beats SPY over the next week.

The plan, fixed before any result was seen: docs/stock-direction/PLAN.md. Read it first; this file
only carries it out. Changing an input, a rule or a period is a new version, not an edit.

Usage (python stock_direction.py ...):
  data            cash dividends (Alpaca) and the 3-month T-bill rate (FRED DTB3) into the DB
  iv [SYM ...]    daily implied-volatility measures from option_bars_daily (default: all S&P 100)
  explore         building period only: each input's record and the learned weights (the answer key)
  tune            building period only: try the planned variants, learn 2024/score 2025 and back
  backtest --final   the one run on the test period (v1, and v2 from tuning); logs it to the ledger
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from options_collector import (ALPACA_DATA, ET, PROJECT_DIR, alpaca, connect, finish_run, http_get, load_keys,
                               start_run)

MODEL, VERSION = "stock-direction", "1"
SP100_PATH = PROJECT_DIR / "shared" / "sp100.json"
RESULTS_DIR = Path.home() / "MarketData" / "stock_direction"

# ---- fixed by the plan
MIN_DTE, MAX_DTE = 10, 60            # days to expiry (Xing, Zhang & Zhao)
MIN_TRADES = 5                       # main version; 1 and 10 are robustness checks
TRADE_VARIANTS = (1, 5, 10)
IV_MIN, IV_MAX = 0.03, 2.00
MIN_TIME_VALUE = 0.10                # share of the price above exercise value; below it IV is guesswork
OTM_PUT = (0.80, 0.95)               # strike / stock, open below 0.95 and above 0.80
ATM = (0.95, 1.05)
MIN_DAYS_PER_WEEK = 3
CHANGE_WEEKS = 4                     # input 3: change over about a month (An, Ang, Bali & Cakici)
WOBBLE_WEEKS = 26                    # robustness: the owner's "normal wobble"
BUILD_END = date(2025, 12, 31)       # building: outcome window ends on or before this
TEST_END = date(2026, 11, 11)        # test: outcome window ends after BUILD_END, up to this
INPUTS = ("gap", "skew", "change", "rel_week")

SCHEMA = """
CREATE TABLE IF NOT EXISTS dividends (
    symbol TEXT, ex_date TEXT, amount REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (symbol, ex_date)
);
CREATE TABLE IF NOT EXISTS rates_daily (
    series TEXT, date TEXT, value REAL, source TEXT, fetched_at TEXT, PRIMARY KEY (series, date)
);
-- One row per stock, day and minimum-trades rule. IVs are annualized decimals (0.30 = 30%).
CREATE TABLE IF NOT EXISTS direction_iv_daily (
    underlying TEXT, date TEXT, min_trades INTEGER, stock_vwap REAL,
    gap REAL, gap_pairs INTEGER,             -- call IV minus put IV, same strike and expiry, volume-weighted
    skew REAL, skew_puts INTEGER,            -- OTM put IV minus ATM call IV, volume-weighted
    cvol REAL, cvol_n INTEGER,               -- ATM call IV, volume-weighted
    pvol REAL, pvol_n INTEGER,               -- ATM put IV, volume-weighted
    skew_closest REAL,                       -- put closest to 0.95 minus call closest to 1.0 (Xing's main version)
    computed_at TEXT,
    PRIMARY KEY (underlying, date, min_trades)
);
"""


def sp100() -> dict:
    return json.loads(SP100_PATH.read_text())


# ---------------------------------------------------------------- pricing
# Dividends are taken out of the stock price (the present value of cash dividends going ex before
# expiration), which leaves no carry, so an American call is worth the European one. An American put
# keeps its early-exercise value: European price plus an early-exercise premium from a Cox-Ross-
# Rubinstein binomial tree (what OptionMetrics, the papers' data, uses). The tree is slow, so the
# premium is worked out once on a grid and looked up. In units of the strike it depends only on
# S/K, sigma*sqrt(T) and r*T, so a 3-D grid covers every option.

def bs_call(S, K, T, r, sig):
    sT = sig * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sig * sig) * T) / sT
    return S * ndtr(d1) - K * np.exp(-r * T) * ndtr(d1 - sT)


def bs_put(S, K, T, r, sig):
    sT = sig * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sig * sig) * T) / sT
    return K * np.exp(-r * T) * ndtr(sT - d1) - S * ndtr(-d1)


GRID_SK = np.linspace(0.78, 1.32, 55)                                     # S / K
GRID_V = np.concatenate([np.linspace(0.003, 0.10, 30), np.linspace(0.105, 0.95, 50)])  # sigma * sqrt(T)
GRID_RT = np.linspace(0.0, 0.014, 8)                                      # r * T
_EEP = None


def _crr_put_both(sk, v, rt, steps):
    """American and European put on the same tree (K = 1, T = 1), vectorized over grid points. Taking
    the difference on one tree cancels most of the tree's own error."""
    dt = 1.0 / steps
    u = np.exp(v * np.sqrt(dt))[:, None]
    d = 1 / u
    disc = np.exp(-rt * dt)[:, None]
    p = (np.exp(rt * dt)[:, None] - d) / (u - d)
    j = np.arange(steps + 1)[None, :]
    S = sk[:, None] * u ** (2 * j - steps)
    am = np.maximum(1 - S, 0)
    eu = am.copy()
    for i in range(steps, 0, -1):
        S = S[:, 1:] / u
        am = np.maximum(disc * (p * am[:, 1:] + (1 - p) * am[:, :-1]), 1 - S)
        eu = disc * (p * eu[:, 1:] + (1 - p) * eu[:, :-1])
    return am[:, 0], eu[:, 0]


def eep_grid():
    """Early-exercise premium per unit of strike on the grid, cached in RESULTS_DIR."""
    global _EEP
    if _EEP is not None:
        return _EEP
    path = RESULTS_DIR / "eep_grid_v1.npy"
    shape = (len(GRID_SK), len(GRID_V), len(GRID_RT))
    if path.exists():
        g = np.load(path)
        if g.shape == shape:
            _EEP = g
            return g
    sk, v, rt = (x.ravel() for x in np.meshgrid(GRID_SK, GRID_V, GRID_RT, indexing="ij"))
    out = np.empty(len(sk))
    for i in range(0, len(sk), 4000):
        sl = slice(i, i + 4000)
        prem = []
        for steps in (500, 501):                # two neighbouring step counts damp the tree's zig-zag
            am, eu = _crr_put_both(sk[sl], v[sl], rt[sl], steps)
            prem.append(am - eu)
        out[sl] = np.maximum((prem[0] + prem[1]) / 2, 0)
    g = out.reshape(shape)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(path, g)
    _EEP = g
    return g


_INTERP = None


def american_put(S, K, T, r, sig):
    global _INTERP
    if _INTERP is None:
        from scipy.interpolate import RegularGridInterpolator
        _INTERP = RegularGridInterpolator((GRID_SK, GRID_V, GRID_RT), eep_grid(), bounds_error=False, fill_value=None)
    interp = _INTERP
    pts = np.stack([np.clip(S / K, GRID_SK[0], GRID_SK[-1]), np.clip(sig * np.sqrt(T), GRID_V[0], GRID_V[-1]),
                    np.clip(r * T, GRID_RT[0], GRID_RT[-1])], axis=-1)
    eep = np.maximum(interp(pts.reshape(-1, 3)).reshape(np.shape(S)), 0) * K
    return np.maximum(bs_put(S, K, T, r, sig) + eep, K - S)     # never below exercising now


def implied_vol(price, S, K, T, r, is_call, iters=45):
    """Bisection, all options at once. NaN when the price can't be matched between IV_MIN and IV_MAX, or
    when it's no more than the lowest-volatility price (a deep in-the-money put worth only its exercise
    value says nothing about volatility)."""
    price, S, K, T, r = (np.asarray(x, dtype=float) for x in (price, S, K, T, r))
    is_call = np.asarray(is_call, dtype=bool)

    def f(sig):
        out = np.empty_like(price)
        out[is_call] = bs_call(S[is_call], K[is_call], T[is_call], r[is_call], sig[is_call])
        p = ~is_call
        out[p] = american_put(S[p], K[p], T[p], r[p], sig[p])
        return out

    lo, hi = np.full_like(price, IV_MIN), np.full_like(price, IV_MAX)
    ok = (f(lo) < price) & (price <= f(hi)) & (price > 0)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        above = f(mid) > price
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return np.where(ok, 0.5 * (lo + hi), np.nan)


# ---------------------------------------------------------------- data: dividends and rates

def job_data(db) -> tuple[str, int, str]:
    keys = load_keys()
    u = sp100()
    symbols = sorted(set(u["stocks"]) | set(u["sector_etf"].values()) | {"SPY"})
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows = []
    for i in range(0, len(symbols), 50):
        token = None
        while True:
            b = alpaca(ALPACA_DATA, "/v1/corporate-actions", keys, symbols=",".join(symbols[i:i + 50]),
                       types="cash_dividend", start="2023-12-01", end=(date.today() + timedelta(days=90)).isoformat(),
                       limit=1000, page_token=token)
            for d in (b.get("corporate_actions") or {}).get("cash_dividends", []):
                rows.append((d["symbol"], d["ex_date"], float(d["rate"]), "alpaca", now))
            token = b.get("next_page_token")
            if not token:
                break
    # Same ex-date twice (a regular and a special dividend): add them.
    merged: dict[tuple, list] = {}
    for s, ex, amt, src, at in rows:
        merged.setdefault((s, ex), [s, ex, 0.0, src, at])[2] += amt
    db.executemany("INSERT OR REPLACE INTO dividends VALUES (?,?,?,?,?)", [tuple(v) for v in merged.values()])

    # FRED drops requests with our own user-agent name but answers Python's standard one (honest, not a
    # browser's), so this one fetch goes out with urllib's default headers.
    with urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd=2023-12-01", timeout=60) as resp:
        text = resp.read().decode()
    rates = []
    for line in text.splitlines()[1:]:
        d, v = line.split(",")
        if v not in ("", "."):
            rates.append(("DTB3", d, float(v), "fred", now))
    db.executemany("INSERT OR REPLACE INTO rates_daily VALUES (?,?,?,?,?)", rates)
    db.commit()
    return "ok", len(merged) + len(rates), f"dividends={len(merged)} rates={len(rates)} (last {rates[-1][1]})"


# ---------------------------------------------------------------- daily implied-volatility measures

def _rate_lookup(db) -> pd.Series:
    r = pd.read_sql("SELECT date, value FROM rates_daily WHERE series='DTB3' ORDER BY date", db)
    s = pd.Series(np.log1p(r["value"].to_numpy() / 100), index=pd.to_datetime(r["date"]))
    return s


def _vw(iv, vol):
    w = vol.sum()
    return (iv * vol).sum() / w if w > 0 else np.nan


def daily_measures(opts: pd.DataFrame) -> list[dict]:
    """opts: one underlying's options for one day, already priced (iv), trades filter applied."""
    out = {}
    m = opts["moneyness"]
    calls, puts = opts[opts["type"] == "call"], opts[opts["type"] == "put"]
    pairs = calls.merge(puts, on=["expiration", "strike"], suffixes=("_c", "_p"))
    if len(pairs):
        w = pairs["volume_c"] + pairs["volume_p"]
        out["gap"], out["gap_pairs"] = float(((pairs["iv_c"] - pairs["iv_p"]) * w).sum() / w.sum()), len(pairs)
    else:
        out["gap"], out["gap_pairs"] = None, 0
    otm_p = puts[(puts["moneyness"] > OTM_PUT[0]) & (puts["moneyness"] < OTM_PUT[1])]
    atm_c = calls[(calls["moneyness"] >= ATM[0]) & (calls["moneyness"] <= ATM[1])]
    atm_p = puts[(puts["moneyness"] >= ATM[0]) & (puts["moneyness"] <= ATM[1])]
    cv, pv, op = _vw(atm_c["iv"], atm_c["volume"]), _vw(atm_p["iv"], atm_p["volume"]), _vw(otm_p["iv"], otm_p["volume"])
    out["cvol"], out["cvol_n"] = (None if np.isnan(cv) else float(cv)), len(atm_c)
    out["pvol"], out["pvol_n"] = (None if np.isnan(pv) else float(pv)), len(atm_p)
    out["skew"] = None if (np.isnan(op) or np.isnan(cv)) else float(op - cv)
    out["skew_puts"] = len(otm_p)
    if len(otm_p) and len(atm_c):
        p1 = otm_p.assign(k=(otm_p["moneyness"] - 0.95).abs()).sort_values(["k", "dte"]).iloc[0]
        c1 = atm_c.assign(k=(atm_c["moneyness"] - 1.0).abs()).sort_values(["k", "dte"]).iloc[0]
        out["skew_closest"] = float(p1["iv"] - c1["iv"])
    else:
        out["skew_closest"] = None
    return out


def compute_iv(db, symbol: str, rates: pd.Series, divs: pd.DataFrame) -> int:
    q = f"""SELECT o.date, o.expiration, o.type, o.strike, o.vwap AS price, o.volume, o.trades, s.vwap AS stock
            FROM option_bars_daily o JOIN stock_bars_daily s ON s.symbol = o.underlying AND s.date = o.date
            WHERE o.underlying = ? AND o.vwap > 0 AND o.trades >= 1 AND s.vwap > 0
              AND julianday(o.expiration) - julianday(o.date) BETWEEN {MIN_DTE} AND {MAX_DTE}"""
    df = pd.read_sql(q, db, params=(symbol,))
    if df.empty:
        return 0
    df["moneyness"] = df["strike"] / df["stock"]
    df = df[(df["moneyness"] > OTM_PUT[0]) & (df["moneyness"] < 1.2)].copy()
    d, e = pd.to_datetime(df["date"]), pd.to_datetime(df["expiration"])
    df["dte"] = (e - d).dt.days
    T = df["dte"].to_numpy() / 365.0
    r = rates.reindex(pd.DatetimeIndex(d.unique()).union(rates.index)).sort_index().ffill().reindex(d).to_numpy()
    # Present value of cash dividends going ex after the day and on or before expiration.
    pv = np.zeros(len(df))
    my = divs[divs["symbol"] == symbol]
    dn, en = d.to_numpy(), e.to_numpy()
    for ex, amt in zip(pd.to_datetime(my["ex_date"]).to_numpy(), my["amount"].to_numpy()):
        hit = (ex > dn) & (ex <= en)
        if hit.any():
            tau = (ex - dn[hit]) / np.timedelta64(1, "D") / 365.0
            pv[hit] += amt * np.exp(-r[hit] * tau)
    S = df["stock"].to_numpy() - pv
    K, price, is_call = df["strike"].to_numpy(), df["price"].to_numpy(), (df["type"] == "call").to_numpy()
    exercise = np.maximum(np.where(is_call, S - K * np.exp(-r * T), K - S), 0)
    keep = price - exercise >= MIN_TIME_VALUE * price
    iv = np.full(len(df), np.nan)
    iv[keep] = implied_vol(price[keep], S[keep], K[keep], T[keep], r[keep], is_call[keep])
    df["iv"] = iv
    df = df[df["iv"].notna()]
    now = datetime.now(ET).isoformat(timespec="seconds")
    rows = []
    for day, g in df.groupby("date"):
        for mt in TRADE_VARIANTS:
            gg = g[g["trades"] >= mt]
            if gg.empty:
                continue
            m = daily_measures(gg)
            rows.append((symbol, day, mt, float(gg["stock"].iloc[0]), m["gap"], m["gap_pairs"], m["skew"],
                         m["skew_puts"], m["cvol"], m["cvol_n"], m["pvol"], m["pvol_n"], m["skew_closest"], now))
    db.execute("DELETE FROM direction_iv_daily WHERE underlying = ?", (symbol,))
    db.executemany("INSERT INTO direction_iv_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return len(rows)


def job_iv(db, symbols: list[str]) -> tuple[str, int, str]:
    rates = _rate_lookup(db)
    divs = pd.read_sql("SELECT symbol, ex_date, amount FROM dividends", db)
    total, failed = 0, []
    for s in symbols:
        try:
            n = compute_iv(db, s, rates, divs)
            total += n
            print(f"{s:6} {n:6} day rows", flush=True)
        except Exception as ex:
            failed.append(f"{s}: {ex}")
            print(f"{s:6} FAILED {ex}", flush=True)
    return ("ok" if not failed else "partial"), total, f"rows={total}" + ("; " + " | ".join(failed) if failed else "")


# ---------------------------------------------------------------- weekly panel

def _trading_days(db) -> list[date]:
    return [date.fromisoformat(r[0]) for r in db.execute("SELECT DISTINCT date FROM stock_bars_daily WHERE symbol='SPY' ORDER BY date")]


def _block(d: date) -> date:
    """Weeks run Wednesday to Tuesday; a block is named by its Wednesday."""
    return d - timedelta(days=(d.weekday() - 2) % 7)


def _total_return_index(db, symbols: list[str]) -> pd.DataFrame:
    """Total-return index per symbol per day: split-adjusted close, with each cash dividend reinvested on
    its ex-date (dividend amounts put in today's share terms too)."""
    px = pd.read_sql(f"SELECT symbol, date, close, split_factor FROM stock_bars_split_adj WHERE symbol IN "
                     f"({','.join('?' * len(symbols))})", db, params=symbols)
    dv = pd.read_sql("SELECT symbol, ex_date AS date, amount FROM dividends", db)
    px = px.merge(dv, on=["symbol", "date"], how="left").fillna({"amount": 0.0})
    px["div_adj"] = px["amount"] * px["split_factor"]
    px = px.sort_values(["symbol", "date"])
    prev = px.groupby("symbol")["close"].shift(1)
    px["gross"] = ((px["close"] + px["div_adj"]) / prev).fillna(1.0)
    px["tri"] = px.groupby("symbol")["gross"].cumprod()
    return px.pivot(index="date", columns="symbol", values="tri").sort_index()


def _trimmed(x: np.ndarray) -> float:
    """Average without the outliers: drop the highest and the lowest day (with 3 days, the middle one)."""
    x = np.sort(x)
    return float(x[1:-1].mean()) if len(x) >= 3 else float(x.mean())


WEEK_STATS = ("median", "mean", "trimmed", "mix2", "mix3")


def week_value(g, how: str) -> pd.Series:
    """One number per stock-week from its daily values. median: the middle day. mean: the average.
    trimmed: the average without the highest and lowest day. mix2: half median, half mean.
    mix3: a third each of median, mean and trimmed (the owner's suggestions, 2026-11-11)."""
    if how == "median":
        return g.median()
    if how == "mean":
        return g.mean()
    tr = g.agg(lambda s: _trimmed(s.to_numpy()))
    if how == "trimmed":
        return tr
    if how == "mix2":
        return 0.5 * g.median() + 0.5 * g.mean()
    if how == "mix3":
        return (g.median() + g.mean() + tr) / 3
    raise ValueError(how)


def build_panel(db, min_trades: int = MIN_TRADES, tuesday_only: bool = False, skew_col: str = "skew",
                week_stat: str = "median") -> pd.DataFrame:
    """One row per (prediction week, stock): raw inputs, excess return over the outcome window, outcome."""
    u = sp100()
    stocks = list(u["stocks"])
    sector = {s: u["sector_etf"][g] for s, g in u["stocks"].items()}
    days = _trading_days(db)
    blocks: dict[date, list[date]] = {}
    for d in days:
        blocks.setdefault(_block(d), []).append(d)
    order = sorted(blocks)
    last_day = {b: blocks[b][-1] for b in order}
    first_after = {}
    for i, b in enumerate(order[:-1]):
        first_after[b] = blocks[order[i + 1]][0]     # the next trading day after the block ends

    iv = pd.read_sql(f"SELECT underlying, date, gap, {skew_col} AS skew, cvol, pvol FROM direction_iv_daily "
                     "WHERE min_trades = ?", db, params=(min_trades,))
    iv["block"] = pd.to_datetime(iv["date"]).dt.date.map(_block)
    if tuesday_only:
        iv = iv[iv["date"] == iv["block"].map(lambda b: last_day.get(b, date.min).isoformat())]
        need = 1
    else:
        need = MIN_DAYS_PER_WEEK
    weekly = {}
    for col in ("gap", "skew", "cvol", "pvol"):
        g = iv.dropna(subset=[col]).groupby(["underlying", "block"])[col]
        w = week_value(g, week_stat).where(g.count() >= need)
        weekly[col] = w.unstack("underlying")           # rows: block, columns: stock
    blk_index = pd.Index(order)
    for k in weekly:
        weekly[k] = weekly[k].reindex(blk_index)
    dc = weekly["cvol"] - weekly["cvol"].shift(CHANGE_WEEKS)
    dp = weekly["pvol"] - weekly["pvol"].shift(CHANGE_WEEKS)

    tri = _total_return_index(db, stocks + sorted(set(sector.values())) + ["SPY"])
    tri.index = pd.to_datetime(tri.index).date

    def ret(sym, d0, d1):
        try:
            return tri.at[d1, sym] / tri.at[d0, sym] - 1
        except KeyError:
            return np.nan

    rows = []
    for i, b in enumerate(order):
        if i == 0 or b not in first_after or order[i + 1] not in first_after:
            continue
        pred_day, prev_day = last_day[b], last_day[order[i - 1]]
        start, end = first_after[b], first_after[order[i + 1]]
        spy = ret("SPY", start, end)
        for s in stocks:
            r_week = ret(s, prev_day, pred_day) - ret(sector[s], prev_day, pred_day)
            r_out = ret(s, start, end)
            rows.append({"block": b, "pred_day": pred_day, "start": start, "end": end, "stock": s,
                         "gap": weekly["gap"].at[b, s] if s in weekly["gap"] else np.nan,
                         "skew": weekly["skew"].at[b, s] if s in weekly["skew"] else np.nan,
                         "dcvol": dc.at[b, s] if s in dc else np.nan,
                         "dpvol": dp.at[b, s] if s in dp else np.nan,
                         "rel_week": r_week, "excess": r_out - spy})
    p = pd.DataFrame(rows)
    p = p.dropna(subset=["excess"])
    p["y"] = (p["excess"] > 0).astype(int)
    return p


def _pct_rank(x: pd.Series) -> pd.Series:
    n = x.notna().sum()
    return (x.rank(method="average") - 1) / (n - 1) if n > 1 else x * np.nan


V1 = {"min_trades": MIN_TRADES, "week_stat": "median", "skew_col": "skew", "tuesday_only": False,
      "wobble": False, "rel_dir": 1, "inputs": INPUTS, "weights": "E"}
PANEL_KEYS = ("min_trades", "week_stat", "skew_col", "tuesday_only")


def add_ranks(p: pd.DataFrame, wobble: bool = False, rel_dir: int = 1, inputs=INPUTS) -> pd.DataFrame:
    """Within each week, among stocks with every input: ranks from 0 to 1, turned so 1 = more likely to beat.
    The same stock-weeks are kept whichever inputs are used, so versions are compared on the same rows."""
    p = p.copy()
    if wobble:
        # The owner's "normal wobble": each change against the same stock's past 26 weekly changes.
        p = p.sort_values(["stock", "block"])
        for col in ("dcvol", "dpvol"):
            p[col] = p.groupby("stock")[col].transform(
                lambda s: s.rolling(WOBBLE_WEEKS + 1, min_periods=WOBBLE_WEEKS + 1)
                .apply(lambda w: (w[:-1] < w[-1]).mean() if not np.isnan(w).any() else np.nan, raw=True))
    need = ["gap", "skew", "dcvol", "dpvol", "rel_week"]
    p = p.dropna(subset=need).copy()
    g = p.groupby("block")
    p["r_gap"] = g["gap"].transform(_pct_rank)
    p["r_skew"] = g["skew"].transform(lambda s: _pct_rank(-s))
    p["r_change"] = (g["dcvol"].transform(_pct_rank) + g["dpvol"].transform(lambda s: _pct_rank(-s))) / 2
    p["r_rel_week"] = g["rel_week"].transform(lambda s: _pct_rank(rel_dir * s))
    p["score"] = p[[f"r_{k}" for k in inputs]].mean(axis=1)
    p["n_week"] = g["stock"].transform("count")
    return p[p["n_week"] >= 10]


def ranked(db, cfg: dict, cache: dict | None = None) -> pd.DataFrame:
    key = tuple(cfg[k] for k in PANEL_KEYS)
    if cache is not None and key in cache:
        base = cache[key]
    else:
        base = build_panel(db, **{k: cfg[k] for k in PANEL_KEYS})
        if cache is not None:
            cache[key] = base
    return add_ranks(base, wobble=cfg["wobble"], rel_dir=cfg["rel_dir"], inputs=cfg["inputs"])


def split(p: pd.DataFrame):
    end = pd.to_datetime(p["end"]).dt.date
    return p[end <= BUILD_END], p[(end > BUILD_END) & (end <= TEST_END)]


# ---------------------------------------------------------------- fitting and scoring

def _logit(X, y):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(penalty=None, max_iter=1000)
    m.fit(X, y)
    return m


def fit(build: pd.DataFrame, inputs=INPUTS) -> dict:
    rank_cols = [f"r_{k}" for k in inputs]
    return {"base_rate": float(build["y"].mean()), "inputs": tuple(inputs),
            "E": _logit(build[["score"]].to_numpy() - 0.5, build["y"]),
            "L": _logit(build[rank_cols].to_numpy() - 0.5, build["y"]),
            "price": _logit(build[["r_rel_week"]].to_numpy() - 0.5, build["y"])}


def predict(models: dict, p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["p_E"] = models["E"].predict_proba(p[["score"]].to_numpy() - 0.5)[:, 1]
    p["p_L"] = models["L"].predict_proba(p[[f"r_{k}" for k in models["inputs"]]].to_numpy() - 0.5)[:, 1]
    p["p_price"] = models["price"].predict_proba(p[["r_rel_week"]].to_numpy() - 0.5)[:, 1]
    p["p_base"] = models["base_rate"]
    p["p_coin"] = 0.5
    return p


def weekly_brier(p: pd.DataFrame, col: str) -> pd.Series:
    return ((p[col] - p["y"]) ** 2).groupby(p["block"]).mean()


def compare_weeks(p: pd.DataFrame, model: str, base: str) -> dict:
    from ledger import compare
    m, b = weekly_brier(p, model), weekly_brier(p, base)
    return compare(list(m), list(b))


def input_records(p: pd.DataFrame) -> dict:
    """Each input alone: average weekly rank correlation with the excess return, and its t-statistic."""
    out = {}
    for col in ("r_gap", "r_skew", "r_change", "r_rel_week", "score"):
        ics = p.groupby("block").apply(lambda g: g[col].corr(g["excess"].rank(), method="spearman"), include_groups=False)
        ics = ics.dropna()
        out[col] = {"mean_ic": float(ics.mean()), "t": float(ics.mean() / (ics.std(ddof=1) / math.sqrt(len(ics)))),
                    "weeks": int(len(ics)), "share_positive": float((ics > 0).mean())}
    return out


def top_minus_bottom(p: pd.DataFrame, col: str = "score") -> dict:
    def one(g):
        q = g[col].rank(pct=True)
        return g.loc[q > 0.8, "excess"].mean() - g.loc[q <= 0.2, "excess"].mean()
    s = p.groupby("block").apply(one, include_groups=False).dropna()
    return {"mean_weekly": float(s.mean()), "t": float(s.mean() / (s.std(ddof=1) / math.sqrt(len(s)))), "weeks": int(len(s))}


def calibration(p: pd.DataFrame, col: str) -> list[dict]:
    bins = [0, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54, 0.56, 1]
    c = pd.cut(p[col], bins)
    t = p.groupby(c, observed=True).agg(n=("y", "size"), predicted=(col, "mean"), happened=("y", "mean"))
    return [{"band": str(k), **{kk: float(v) for kk, v in r.items()}} for k, r in t.iterrows()]


def report(p: pd.DataFrame, label: str) -> dict:
    out = {"period": label, "weeks": int(p["block"].nunique()), "predictions": int(len(p)),
           "stocks_per_week": float(p.groupby("block").size().mean()), "share_beat_spy": float(p["y"].mean()),
           "brier": {c: float(((p[c] - p["y"]) ** 2).mean()) for c in ("p_E", "p_L", "p_price", "p_base", "p_coin")},
           "vs": {}}
    for m in ("p_E", "p_L"):
        for b in ("p_base", "p_price", "p_coin"):
            out["vs"][f"{m} vs {b}"] = compare_weeks(p, m, b)
    out["vs"]["p_L vs p_E"] = compare_weeks(p, "p_L", "p_E")
    out["vs"]["p_price vs p_base"] = compare_weeks(p, "p_price", "p_base")
    out["inputs"] = input_records(p)
    out["top_minus_bottom_E"] = top_minus_bottom(p, "p_E")
    out["calibration_E"] = calibration(p, "p_E")
    out["calibration_L"] = calibration(p, "p_L")
    return out


def _models_summary(models: dict) -> dict:
    return {"base_rate": models["base_rate"],
            "E": {"intercept": float(models["E"].intercept_[0]), "slope": float(models["E"].coef_[0][0])},
            "L": {"intercept": float(models["L"].intercept_[0]),
                  **{k: float(v) for k, v in zip(models["inputs"], models["L"].coef_[0])}},
            "price": {"intercept": float(models["price"].intercept_[0]), "slope": float(models["price"].coef_[0][0])}}


def explore(db) -> dict:
    p = ranked(db, V1)
    build, _ = split(p)
    models = fit(build)
    out = {"note": "BUILDING PERIOD ONLY, in-sample (the answer key). Not a test.",
           "fitted": _models_summary(models), "building": report(predict(models, build), "building, in-sample")}
    return out


# ---------------------------------------------------------------- tuning on 2024-25 only
# Two folds inside the building period: learn on 2024 and score 2025, then learn on 2025 and score
# 2024. A change is adopted only if it beats v1 in BOTH folds (one lucky year isn't enough). The test
# period is never read here. Rules written in docs/stock-direction/PLAN.md before this ran.

FOLD_SPLIT = date(2024, 12, 31)


def _folds(p: pd.DataFrame):
    end = pd.to_datetime(p["end"]).dt.date
    a = p[end <= FOLD_SPLIT]
    b = p[(end > FOLD_SPLIT) & (end <= BUILD_END)]
    return a, b


def _model_col(cfg: dict) -> str:
    return "p_E" if cfg["weights"] == "E" else "p_L"


def fold_scores(p: pd.DataFrame, cfg: dict) -> dict:
    """Per fold: weekly Brier gap of the model against the base rate, both learned on the other year."""
    a, b = _folds(p)
    out = {}
    for name, learn, score in (("learn24_score25", a, b), ("learn25_score24", b, a)):
        models = fit(learn, cfg["inputs"])
        sc = predict(models, score)
        rows = sc[["block", "stock", "y"]].assign(loss=(sc[_model_col(cfg)] - sc["y"]) ** 2)
        out[name] = {"weeks": int(sc["block"].nunique()), "vs_base": compare_weeks(sc, _model_col(cfg), "p_base"),
                     "rows": rows}
    return out


def paired(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """a against b on the stock-weeks both have (each: block, stock, loss): weekly average of a's loss
    minus b's, judged with the ledger's compare. Negative gap = a better."""
    from ledger import compare
    m = a.merge(b, on=["block", "stock"], suffixes=("_a", "_b"))
    wk = m.groupby("block")[["loss_a", "loss_b"]].mean()
    r = compare(list(wk["loss_a"]), list(wk["loss_b"]))
    r["shared_rows"] = int(len(m))
    return r


TUNING_DIMENSIONS = {
    "week_stat": [{"week_stat": w} for w in ("mean", "trimmed", "mix2", "mix3")] + [{"tuesday_only": True}],
    "min_trades": [{"min_trades": 1}, {"min_trades": 10}],
    "skew": [{"skew_col": "skew_closest"}],
    "change": [{"wobble": True}],
    "rel_week_direction": [{"rel_dir": -1}],
    "inputs": [{"inputs": tuple(k for k in INPUTS if k != drop)} for drop in INPUTS],
    "weights": [{"weights": "L"}],
}


def _vs_v1(cand: dict, v1: dict) -> dict:
    """Candidate against v1 in each fold, week by week (negative gap = candidate better)."""
    return {f: paired(cand[f]["rows"], v1[f]["rows"]) for f in v1}


def tune(db) -> dict:
    cache: dict = {}
    log = []
    v1 = fold_scores(ranked(db, V1, cache), V1)
    log.append({"name": "v1", "cfg": V1, "folds": {k: v["vs_base"] for k, v in v1.items()}})
    best_per_dim = {}
    for dim, changes in TUNING_DIMENSIONS.items():
        winners = []
        for ch in changes:
            cfg = {**V1, **ch}
            sc = fold_scores(ranked(db, cfg, cache), cfg)
            vs = _vs_v1(sc, v1)
            both = all(v["gap"] < 0 for v in vs.values())
            avg_gap = sum(v["gap"] for v in vs.values()) / len(vs)
            log.append({"name": f"{dim}: {ch}", "cfg": cfg, "folds": {k: v["vs_base"] for k, v in sc.items()},
                        "vs_v1": vs, "beats_v1_both_folds": both})
            if both:
                winners.append((avg_gap, ch))
        if winners:
            best_per_dim[dim] = min(winners, key=lambda w: w[0])[1]
    v2 = dict(V1)
    for ch in best_per_dim.values():
        v2.update(ch)
    combined = None
    if best_per_dim:
        sc = fold_scores(ranked(db, v2, cache), v2)
        vs = _vs_v1(sc, v1)
        combined = {"cfg": v2, "folds": {k: v["vs_base"] for k, v in sc.items()}, "vs_v1": vs,
                    "beats_v1_both_folds": all(v["gap"] < 0 for v in vs.values())}
        if not combined["beats_v1_both_folds"]:
            # The changes don't add up; keep only the single change with the best average gain.
            best = min(((e["vs_v1"], e["cfg"]) for e in log if e.get("beats_v1_both_folds")),
                       key=lambda x: sum(v["gap"] for v in x[0].values()))
            v2 = best[1]
    out = {"note": "Tuning on 2024-25 only (two folds). The 2026 test period was not read.",
           "tried": len(log) - 1, "log": log, "adopted": best_per_dim, "combined": combined,
           "v2": v2 if v2 != V1 else None}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"tuning-{date.today().isoformat()}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def verdict(rep: dict, col: str) -> str:
    vs = rep["vs"]
    a, b = vs[f"{col} vs p_base"], vs[f"{col} vs p_price"]
    if a["verdict"] == "better" and b["verdict"] == "better":
        return "clear pass"
    return "lean pass" if (a["gap"] < 0 and b["gap"] < 0) else "fail"


def _git_state():
    import subprocess
    commit = subprocess.run(["git", "-C", str(PROJECT_DIR), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(PROJECT_DIR), "status", "--porcelain", "collectors/stock_direction.py",
                            "docs/stock-direction/PLAN.md"], capture_output=True, text=True).stdout.strip()
    return commit, dirty


def run_on_test(db, cfg: dict, cache: dict) -> tuple[pd.DataFrame, dict, dict]:
    p = ranked(db, cfg, cache)
    build, test = split(p)
    models = fit(build, cfg["inputs"])
    test = predict(models, test)
    return test, report(test, "test"), _models_summary(models)


def backtest_final(db) -> dict:
    """The one run on the sealed test period: v1 (E and L, as planned) and v2 from the tuning file."""
    commit, dirty = _git_state()
    if dirty:
        raise SystemExit("commit the code and plan first: the final run records the commit it ran from")
    tuning = sorted(RESULTS_DIR.glob("tuning-*.json"))
    v2 = json.loads(tuning[-1].read_text()).get("v2") if tuning else None
    if v2:
        v2["inputs"] = tuple(v2["inputs"])
    cache: dict = {}
    test1, rep1, fit1 = run_on_test(db, V1, cache)
    e, l = verdict(rep1, "p_E"), verdict(rep1, "p_L")
    out = {"model": MODEL, "commit": commit, "run_at": datetime.now(ET).isoformat(timespec="seconds"),
           "v1": {"cfg": V1, "fitted_on_building": fit1, "test": rep1, "verdict": {"E": e, "L": l}}}
    # v1's planned choice between E and L
    if e == "fail" and l == "fail":
        v1_live = None
    elif l != "fail" and (e == "fail" or rep1["vs"]["p_L vs p_E"]["verdict"] == "better"):
        v1_live = "L"
    else:
        v1_live = "E"
    out["v1"]["goes_live"] = v1_live
    to_log = [("1", test1, "p_E"), ("1-learned", test1, "p_L")]
    if v2:
        test2, rep2, fit2 = run_on_test(db, v2, cache)
        col = _model_col(v2)
        out["v2"] = {"cfg": v2, "fitted_on_building": fit2, "test": rep2, "verdict": verdict(rep2, col)}
        v1col = {"E": "p_E", "L": "p_L"}.get(v1_live or "E")
        out["v2"]["vs_v1"] = paired(test2[["block", "stock"]].assign(loss=(test2[col] - test2["y"]) ** 2),
                                    test1[["block", "stock"]].assign(loss=(test1[v1col] - test1["y"]) ** 2))
        to_log.append(("2", test2, col))
    out["robustness_v1"] = {}
    variants = {"min_trades_1": {"min_trades": 1}, "min_trades_10": {"min_trades": 10},
                "skew_closest_options": {"skew_col": "skew_closest"}, "tuesday_only": {"tuesday_only": True},
                "week_mean_not_median": {"week_stat": "mean"}, "change_vs_own_wobble": {"wobble": True}}
    for name, ch in variants.items():
        t, rep, _ = run_on_test(db, {**V1, **ch}, cache)
        out["robustness_v1"][name] = {"weeks": rep["weeks"], "brier_E": rep["brier"]["p_E"],
                                      "brier_base": rep["brier"]["p_base"], "E_vs_base": rep["vs"]["p_E vs p_base"]}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"final-{date.today().isoformat()}.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    out["saved_to"] = str(path)
    out["ledger_rows"] = log_backtest(db, to_log)
    return out


def log_backtest(db, runs: list[tuple[str, pd.DataFrame, str]]) -> int:
    """Test-period predictions into the ledger as backtests: (version, predictions, column) each."""
    import ledger
    ledger.ensure(db)
    n = 0
    for version, test, col in runs:
        ledger.clear_backtest(db, MODEL, version)
        for r in test.itertuples():
            made = datetime.combine(r.pred_day, dtime(18, 0), ET)
            opens = datetime.combine(r.start, dtime(16, 0), ET)
            resolves = datetime.combine(r.end, dtime(16, 0), ET)
            pid = ledger.log(db, model=MODEL, version=version, mode="backtest",
                             target=f"{r.stock} beats SPY, close {r.start} to close {r.end}", kind="probability",
                             opens_at=opens, resolves_at=resolves, made_at=made,
                             forecast={"p": round(float(getattr(r, col)), 4)},
                             baselines={"base_rate": {"p": round(float(r.p_base), 4)},
                                        "price_only": {"p": round(float(r.p_price), 4)}},
                             inputs={k: (None if pd.isna(getattr(r, k)) else round(float(getattr(r, k)), 6))
                                     for k in ("gap", "skew", "dcvol", "dpvol", "rel_week", "excess")})
            if pid:
                ledger.resolve(db, pid, int(r.y), source="stock_bars_split_adj + dividends (total return vs SPY)")
                n += 1
    return n


# ---------------------------------------------------------------- command line

def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    db = connect()
    db.executescript(SCHEMA)
    if cmd == "data":
        run = start_run(db, "direction-data")
        status, n, detail = job_data(db)
        finish_run(db, run, status, n, detail)
        print(detail)
    elif cmd == "iv":
        syms = [a.upper() for a in args[1:]] or list(sp100()["stocks"])
        run = start_run(db, "direction-iv")
        status, n, detail = job_iv(db, syms)
        finish_run(db, run, status, n, detail)
        print(detail)
    elif cmd == "explore":
        print(json.dumps(explore(db), indent=2, default=str))
    elif cmd == "tune":
        out = tune(db)
        print(json.dumps({k: v for k, v in out.items() if k != "log"}, indent=2, default=str))
        for e in out["log"]:
            g = {f: round(v["gap"] * 1e4, 2) for f, v in e["folds"].items()}
            print(f"{e['name'][:60]:60} vs base (x1e-4): {g}  beats v1 both folds: {e.get('beats_v1_both_folds', '-')}")
    elif cmd == "backtest" and "--final" in args:
        print(json.dumps(backtest_final(db), indent=2, default=str))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
