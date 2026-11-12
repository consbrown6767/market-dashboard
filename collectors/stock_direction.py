"""Stock direction model: each week, the chance each S&P 100 stock beats SPY over the next week.

The plan, fixed before any result was seen: docs/stock-direction/PLAN.md. Read it first; this file
only carries it out. Changing an input, a rule or a period is a new version, not an edit.

Usage (python stock_direction.py ...):
  data            cash dividends (Alpaca) and the 3-month T-bill rate (FRED DTB3) into the DB
  iv [SYM ...]    daily implied-volatility measures from option_bars_daily (default: all S&P 100)
  explore         building period only: each input's record and the learned weights (the answer key)
  backtest --final   the one run on the test period; logs it to the ledger as a backtest
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
        w = (g.median() if week_stat == "median" else g.mean()).where(g.count() >= need)
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


def add_ranks(p: pd.DataFrame, wobble: bool = False) -> pd.DataFrame:
    """Within each week, among stocks with every input: ranks from 0 to 1, turned so 1 = more likely to beat."""
    p = p.copy()
    if wobble:
        # The owner's "normal wobble": each change against the same stock's past 26 weekly changes.
        for col in ("dcvol", "dpvol"):
            p = p.sort_values(["stock", "block"])
            p[col] = p.groupby("stock")[col].transform(
                lambda s: s.rolling(WOBBLE_WEEKS + 1, min_periods=WOBBLE_WEEKS + 1)
                .apply(lambda w: (w[:-1] < w[-1]).mean() if not np.isnan(w).any() else np.nan, raw=True))
    need = ["gap", "skew", "dcvol", "dpvol", "rel_week"]
    p = p.dropna(subset=need).copy()
    g = p.groupby("block")
    p["r_gap"] = g["gap"].transform(_pct_rank)
    p["r_skew"] = g["skew"].transform(lambda s: _pct_rank(-s))
    p["r_change"] = (g["dcvol"].transform(_pct_rank) + g["dpvol"].transform(lambda s: _pct_rank(-s))) / 2
    p["r_rel_week"] = g["rel_week"].transform(_pct_rank)
    p["score"] = p[["r_gap", "r_skew", "r_change", "r_rel_week"]].mean(axis=1)
    p["n_week"] = g["stock"].transform("count")
    return p[p["n_week"] >= 10]


def split(p: pd.DataFrame):
    end = pd.to_datetime(p["end"]).dt.date
    return p[end <= BUILD_END], p[(end > BUILD_END) & (end <= TEST_END)]


# ---------------------------------------------------------------- fitting and scoring

def _logit(X, y):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(penalty=None, max_iter=1000)
    m.fit(X, y)
    return m


def fit(build: pd.DataFrame) -> dict:
    rank_cols = ["r_gap", "r_skew", "r_change", "r_rel_week"]
    return {"base_rate": float(build["y"].mean()),
            "E": _logit(build[["score"]].to_numpy() - 0.5, build["y"]),
            "L": _logit(build[rank_cols].to_numpy() - 0.5, build["y"]),
            "price": _logit(build[["r_rel_week"]].to_numpy() - 0.5, build["y"])}


def predict(models: dict, p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["p_E"] = models["E"].predict_proba(p[["score"]].to_numpy() - 0.5)[:, 1]
    p["p_L"] = models["L"].predict_proba(p[["r_gap", "r_skew", "r_change", "r_rel_week"]].to_numpy() - 0.5)[:, 1]
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
                  **{k: float(v) for k, v in zip(INPUTS, models["L"].coef_[0])}},
            "price": {"intercept": float(models["price"].intercept_[0]), "slope": float(models["price"].coef_[0][0])}}


def explore(db) -> dict:
    p = add_ranks(build_panel(db))
    build, _ = split(p)
    models = fit(build)
    out = {"note": "BUILDING PERIOD ONLY, in-sample (the answer key). Not a test.",
           "fitted": _models_summary(models), "building": report(predict(models, build), "building, in-sample")}
    return out


def verdict(rep: dict) -> dict:
    vs = rep["vs"]

    def passes(m):
        a, b = vs[f"{m} vs p_base"], vs[f"{m} vs p_price"]
        lower = a["gap"] < 0 and b["gap"] < 0
        clear = a["verdict"] == "better" and b["verdict"] == "better"
        return "clear pass" if clear else "lean pass" if lower else "fail"
    e, l = passes("p_E"), passes("p_L")
    if e == "fail" and l == "fail":
        live = None
    elif l != "fail" and (e == "fail" or vs["p_L vs p_E"]["verdict"] == "better"):
        live = "L"
    else:
        live = "E"
    return {"E": e, "L": l, "goes_live": live}


def backtest_final(db) -> dict:
    import subprocess
    commit = subprocess.run(["git", "-C", str(PROJECT_DIR), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(PROJECT_DIR), "status", "--porcelain", "collectors/stock_direction.py",
                            "docs/stock-direction/PLAN.md"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("commit the code and plan first: the final run records the commit it ran from")
    p = add_ranks(build_panel(db))
    build, test = split(p)
    models = fit(build)
    test = predict(models, test)
    rep = report(test, "test")
    out = {"model": MODEL, "version": VERSION, "commit": commit, "run_at": datetime.now(ET).isoformat(timespec="seconds"),
           "fitted_on_building": _models_summary(models), "building_weeks": int(build["block"].nunique()),
           "test": rep, "verdict": verdict(rep), "robustness": {}}
    variants = {"min_trades_1": dict(min_trades=1), "min_trades_10": dict(min_trades=10),
                "skew_closest_options": dict(skew_col="skew_closest"), "tuesday_only": dict(tuesday_only=True),
                "week_mean_not_median": dict(week_stat="mean")}
    for name, kw in list(variants.items()) + [("change_vs_own_wobble", None)]:
        pp = add_ranks(build_panel(db), wobble=True) if kw is None else add_ranks(build_panel(db, **kw))
        b, t = split(pp)
        mm = fit(b)
        t = predict(mm, t)
        out["robustness"][name] = {"weeks": int(t["block"].nunique()), "brier_E": float(((t["p_E"] - t["y"]) ** 2).mean()),
                                   "brier_base": float(((t["p_base"] - t["y"]) ** 2).mean()),
                                   "E_vs_base": compare_weeks(t, "p_E", "p_base")}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"final-{date.today().isoformat()}.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    out["saved_to"] = str(path)
    log_backtest(db, test)
    return out


def log_backtest(db, test: pd.DataFrame) -> int:
    """Test-period predictions into the ledger as a backtest (E as version 1, L as 1-learned)."""
    import ledger
    ledger.ensure(db)
    n = 0
    for version, col in ((VERSION, "p_E"), (VERSION + "-learned", "p_L")):
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
                             inputs={"gap": r.gap, "skew": r.skew, "dcvol": r.dcvol, "dpvol": r.dpvol,
                                     "rel_week": r.rel_week, "excess": r.excess})
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
    elif cmd == "backtest" and "--final" in args:
        print(json.dumps(backtest_final(db), indent=2, default=str))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
