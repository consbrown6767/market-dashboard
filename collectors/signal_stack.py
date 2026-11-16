"""The signal stack: many weak published signals on S&P 500 stocks, directions fixed from the papers,
equal weights, weekly. Plan fixed first: docs/signal-stack/PLAN.md. Research only.

    signal_stack.py run      # the plan's test, once; writes ~/MarketData/signal_stack/results-<date>.json
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DB = Path.home() / "MarketData" / "options.db"
OUT = Path.home() / "MarketData" / "signal_stack"
HISTORY = Path(__file__).resolve().parent.parent / "shared" / "sp500_history.json"
if not HISTORY.exists():
    HISTORY = Path.home() / "Code" / "market-dashboard" / "shared" / "sp500_history.json"

# ---- fixed by the plan
START, END = "2017-01-01", "2026-10-31"
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-10-31")}
COST, BORROW = 0.0005, 0.005
MIN_COVER = 0.30   # plan change 1 (before results): was 0.80
TOP, KEEP = 0.20, 0.40
BLOCK, DRAWS, SEED = 8, 2000, 11
# name: (family, direction)
SIGNALS = {
    "mom_12_2": ("Momentum", 1), "mom_6_2": ("Momentum", 1), "mom_12_7": ("Momentum", 1), "high_52w": ("Momentum", 1),
    "resid_mom": ("Momentum", 1), "ma200": ("Momentum", 1), "sector_mom": ("Momentum", 1),
    "rev_1w": ("Reversal", -1), "rev_1m": ("Reversal", -1), "rev_36_13": ("Reversal", -1),
    "vol_12m": ("Low risk", -1), "idio_vol_1m": ("Low risk", -1), "beta": ("Low risk", -1), "max_1m": ("Low risk", -1),
    "amihud": ("Trading", 1), "dollar_volume": ("Trading", -1), "abn_volume": ("Trading", 1),
    "same_month": ("Calendar", 1), "earnings_week": ("Calendar", 1), "dividend_month": ("Calendar", 1),
    "earnings_drift": ("Earnings", 1),
    "opt_skew": ("Options", -1), "opt_gap": ("Options", 1), "opt_dcall": ("Options", 1), "opt_dput": ("Options", -1),
    "opt_iv_rv": ("Options", 1), "opt_os": ("Options", -1),
}


def load():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bars = pd.read_sql("SELECT symbol, date, close, volume FROM daily_bars_adj", db)
    close = bars.pivot(index="date", columns="symbol", values="close").sort_index()
    volume = bars.pivot(index="date", columns="symbol", values="volume").sort_index()
    close.index = volume.index = pd.to_datetime(close.index)
    close = close[close.index <= END]
    volume = volume.reindex(close.index)
    rf = pd.read_sql("SELECT date, ret FROM ff_daily WHERE dataset='us' AND series='RF'", db, index_col="date")["ret"]
    rf.index = pd.to_datetime(rf.index)
    rf = rf.reindex(close.index).ffill().fillna(0.0)
    earn = pd.read_sql("SELECT symbol, ts FROM earnings_dates", db)
    div = pd.read_sql("SELECT symbol, ex_date FROM dividends", db)
    iv = pd.read_sql("SELECT underlying, date, gap, skew, cvol, pvol FROM direction_iv_daily WHERE min_trades = 5", db)
                     "(SELECT MAX(min_trades) FROM direction_iv_daily)", db)
    cache = OUT / "option_volume.csv"
    if cache.exists():
        ov = pd.read_csv(cache)
    else:
        ov = pd.read_sql("SELECT underlying, date, SUM(volume) AS ov FROM option_bars_daily GROUP BY underlying, date", db)
        OUT.mkdir(parents=True, exist_ok=True)
        ov.to_csv(cache, index=False)
    members = {int(y): v["members"] for y, v in json.loads(HISTORY.read_text())["years"].items()}
    return close, volume, rf, earn, div, iv, ov, members


def weeks(idx: pd.DatetimeIndex) -> list[tuple[int, int]]:
    """(signal day, entry day) positions: the last trading day on or before Tuesday, and the day after."""
    out = []
    iso = idx.isocalendar()
    for _, g in pd.Series(np.arange(len(idx)), index=idx).groupby([iso.year.values, iso.week.values]):
        days = [p for p in g.values if idx[p].weekday() <= 1]
        if days and days[-1] + 1 < len(idx):
            out.append((int(days[-1]), int(days[-1]) + 1))
    return sorted(out)


def build_signals(close, volume, earn, div, iv, ov, wk):
    """{name: frame of raw values at each signal day (rows) by symbol}. Uses data up to the signal day only."""
    r = close.pct_change(fill_method=None)
    m = r["SPY"]
    S = [s for s, _ in wk]
    at = lambda f: f.iloc[S]                                    # noqa: E731
    sig = {}
    sig["mom_12_2"] = at(close.shift(21) / close.shift(252) - 1)
    sig["mom_6_2"] = at(close.shift(21) / close.shift(126) - 1)
    sig["mom_12_7"] = at(close.shift(126) / close.shift(252) - 1)
    sig["high_52w"] = at(close / close.rolling(252, min_periods=200).max())
    mm, vm_ = m.rolling(252, min_periods=200).mean(), m.rolling(252, min_periods=200).var()
    beta = (r.mul(m, axis=0).rolling(252, min_periods=200).mean() - r.rolling(252, min_periods=200).mean().mul(mm, axis=0)).div(vm_, axis=0)
    mkt_12_2 = close["SPY"].shift(21) / close["SPY"].shift(252) - 1
    sig["resid_mom"] = at((close.shift(21) / close.shift(252) - 1) - beta.mul(mkt_12_2, axis=0))
    sig["ma200"] = at(close / close.rolling(200, min_periods=160).mean())
    sig["rev_1w"] = at(close / close.shift(5) - 1)
    sig["rev_1m"] = at(close / close.shift(21) - 1)
    sig["rev_36_13"] = at(close.shift(252) / close.shift(756) - 1)
    sig["vol_12m"] = at(r.rolling(252, min_periods=200).std())
    resid = r - beta.mul(m, axis=0)
    sig["idio_vol_1m"] = at(resid.rolling(21, min_periods=15).std())
    sig["beta"] = at(beta)
    sig["max_1m"] = at(r.rolling(21, min_periods=15).max())
    dollars = close * volume
    sig["amihud"] = at((r.abs() / dollars.where(dollars > 0)).rolling(63, min_periods=40).mean())
    sig["dollar_volume"] = at(dollars.rolling(63, min_periods=40).mean())
    sig["abn_volume"] = at(volume.rolling(5).mean() / volume.rolling(63, min_periods=40).mean())
    sig["_ret6m"] = at(close / close.shift(126) - 1)            # for sector momentum, ranked later by members

    # same calendar month in past years (needs 2+ earlier years), for the month the position is held in
    mclose = close.resample("ME").last()
    mret = mclose.pct_change(fill_method=None)
    same = pd.DataFrame(index=close.index[S], columns=close.columns, dtype=float)
    cache = {}
    for (s, e) in wk:
        d = close.index[e]
        key = (d.year, d.month)
        if key not in cache:
            past = mret[(mret.index.month == d.month) & (mret.index.year < d.year)]
            cache[key] = past.mean().where(past.count() >= 2)
        same.loc[close.index[s]] = cache[key]
    sig["same_month"] = same

    # earnings: a report due in the holding week; and the 3-day return around the last report, minus SPY's
    idx = close.index
    earn = earn.copy()
    ts = pd.to_datetime(earn["ts"], utc=True).dt.tz_convert("America/New_York")
    day = ts.dt.tz_localize(None).dt.normalize()
    pos = idx.searchsorted(day.values)                           # first trading day on or after the report day
    pos = np.where(ts.dt.hour.values >= 16, idx.searchsorted(day.values, side="right"), pos)   # after the close: next day
    earn["pos"], earn["day"] = pos, day.values
    week_flag = pd.DataFrame(np.nan, index=idx[S], columns=close.columns)
    drift = pd.DataFrame(np.nan, index=idx[S], columns=close.columns)
    cvals, spy = close.values, close["SPY"].values
    col = {c: i for i, c in enumerate(close.columns)}
    entry_of = {s: e for s, e in wk}
    nxt = {wk[i][0]: (wk[i + 1][1] if i + 1 < len(wk) else len(idx) - 1) for i in range(len(wk))}
    for sym, g in earn.groupby("symbol"):
        if sym not in col:
            continue
        j = col[sym]
        ps = np.sort(g["pos"].values)
        week_flag[sym] = 0.0
        for s in S:
            if ((ps > entry_of[s]) & (ps <= nxt[s])).any():
                week_flag.at[idx[s], sym] = 1.0
            done = ps[ps + 1 <= s]                               # reaction window complete by the signal day
            if len(done):
                p = int(done[-1])
                if p >= 2 and (idx[s] - idx[p]).days <= 60:
                    a = cvals[p + 1, j] / cvals[p - 2, j] - 1
                    drift.at[idx[s], sym] = a - (spy[p + 1] / spy[p - 2] - 1)
    sig["earnings_week"], sig["earnings_drift"] = week_flag, drift

    # a dividend expected in the holding month: one was paid 3, 6, 9 or 12 months earlier
    div = div.copy()
    div["ym"] = pd.to_datetime(div["ex_date"]).dt.to_period("M")
    paid = {sym: set(g["ym"]) for sym, g in div.groupby("symbol")}
    dm = pd.DataFrame(np.nan, index=idx[S], columns=close.columns)
    for sym, months in paid.items():
        if sym in col:
            dm[sym] = [1.0 if any((idx[e].to_period("M") - k) in months for k in (3, 6, 9, 12)) else 0.0 for _, e in wk]
    sig["dividend_month"] = dm

    # options (weekly value = average of the 5 days ending on the signal day)
    def wide(df, c):
        w = df.pivot(index="date", columns="underlying", values=c)
        w.index = pd.to_datetime(w.index)
        return w.reindex(idx).reindex(columns=close.columns)
    wmean = lambda f: f.rolling(5, min_periods=3).mean()         # noqa: E731
    skew, gap, cv, pv = (wmean(wide(iv, c)) for c in ("skew", "gap", "cvol", "pvol"))
    sig["opt_skew"], sig["opt_gap"] = at(skew), at(gap)
    sig["opt_dcall"], sig["opt_dput"] = at(cv - cv.shift(20)), at(pv - pv.shift(20))
    sig["opt_iv_rv"] = at((cv + pv) / 2 - r.rolling(21, min_periods=15).std() * np.sqrt(252))
    ovw = wide(ov, "ov")
    sig["opt_os"] = at(ovw.rolling(5, min_periods=3).sum() / volume.rolling(5, min_periods=3).sum())
    return sig, r


def stats(x: pd.Series, rf: pd.Series) -> dict:
    x = x.dropna()
    if len(x) < 20:
        return {"weeks": len(x)}
    ex = x - rf.reindex(x.index)
    w = (1 + x).cumprod()
    return {"weeks": len(x), "per_year": round(float(w.iloc[-1] ** (52 / len(x)) - 1) * 100, 2),
            "sharpe": round(float(ex.mean() / ex.std() * np.sqrt(52)), 3),
            "worst_drop": round(float((w / w.cummax() - 1).min()) * 100, 1), "10k_becomes": round(float(w.iloc[-1] * 10000))}


def block_boot(x: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    n = len(x)
    k = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n - BLOCK + 1, size=(DRAWS, k))
    means = np.array([np.concatenate([x[s:s + BLOCK] for s in row])[:n].mean() for row in starts])
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def run() -> dict:
    close, volume, rf, earn, div, iv, ov, members = load()
    wk = weeks(close.index)
    sig, r = build_signals(close, volume, earn, div, iv, ov, wk)
    idx = close.index
    px = close.ffill(limit=10)                                   # a stock that stops trading keeps its last price briefly
    rfw, rows, used_log = {}, [], {k: 0 for k in SIGNALS}
    ic = {k: [] for k in SIGNALS}
    held = {v: {"long": set(), "short": set()} for v in ("A", "B")}
    w_old = {v: {"long": pd.Series(dtype=float), "short": pd.Series(dtype=float)} for v in ("A", "B")}
    ew_old = pd.Series(dtype=float)
    for i in range(len(wk) - 1):
        s, e = wk[i]
        e2 = wk[i + 1][1]
        d_sig, d_in, d_out = idx[s], idx[e], idx[e2]
        if d_in < pd.Timestamp(START) or d_in > pd.Timestamp(END):
            continue
        mem = members.get(d_sig.year, {})
        names = [c for c in mem if c in close.columns and pd.notna(close.at[d_sig, c]) and pd.notna(px.at[d_in, c])]
        if len(names) < 300:
            continue
        fwd = (px.loc[d_out, names] / px.loc[d_in, names] - 1).fillna(0.0)
        rfw[d_in] = float((1 + rf.iloc[e + 1:e2 + 1]).prod() - 1)
        # sector momentum from this year's sector map
        sec = pd.Series({c: mem[c] for c in names})
        r6 = sig["_ret6m"].loc[d_sig, names]
        sector_mom = r6.groupby(sec).transform("mean")
        fams, flat = {}, []
        for name, (fam, sign) in SIGNALS.items():
            raw = sector_mom if name == "sector_mom" else sig[name].loc[d_sig, names]
            raw = pd.to_numeric(raw, errors="coerce")
            if raw.notna().mean() < MIN_COVER:
                continue
            score = ((raw.rank(method="average") - 0.5) / raw.notna().sum() - 0.5) * sign
            if raw.nunique() > 1:
                ic[name].append(float(score.corr(fwd, method="spearman")))
            score = score.fillna(0.0)
            used_log[name] += 1
            fams.setdefault(fam, []).append(score)
            flat.append(score)
        if not flat:
            continue
        combo = {"A": pd.concat([pd.concat(v, axis=1).mean(axis=1) for v in fams.values()], axis=1).mean(axis=1),
                 "B": pd.concat(flat, axis=1).mean(axis=1)}
        row = {"date": d_in, "spy": float(px.at[d_out, "SPY"] / px.at[d_in, "SPY"] - 1), "n": len(names), "signals": len(flat)}
        # all stocks in equal amounts, with trading cost
        w_new = pd.Series(1 / len(names), index=names)
        turn = float(w_new.sub(ew_old, fill_value=0).abs().sum()) if len(ew_old) else 1.0
        g = w_new * (1 + fwd)
        row["ew"] = float(g.sum() - 1) - COST * turn
        ew_old = g / g.sum()
        for v, c in combo.items():
            pct = c.rank(pct=True)
            for side, top, keep in (("long", pct >= 1 - TOP, pct >= 1 - KEEP), ("short", pct <= TOP, pct <= KEEP)):
                h = held[v][side]
                now = set(top[top].index) | {x for x in h if x in keep.index and keep[x]}
                held[v][side] = now
                w_new = pd.Series(1 / len(now), index=sorted(now))
                old = w_old[v][side]
                turn = float(w_new.sub(old, fill_value=0).abs().sum()) if len(old) else 1.0
                g = w_new * (1 + fwd.reindex(w_new.index).fillna(0.0))
                row[f"{v}_{side}"] = float(g.sum() - 1)
                row[f"{v}_{side}_cost"] = COST * turn
                row[f"{v}_{side}_n"] = len(now)
                w_old[v][side] = g / g.sum()
            row[f"{v}1"] = row[f"{v}_long"] - row[f"{v}_long_cost"]
            row[f"{v}2"] = (row[f"{v}_long"] - row[f"{v}_short"]) - row[f"{v}_long_cost"] - row[f"{v}_short_cost"] - BORROW / 52
        rows.append(row)
    t = pd.DataFrame(rows).set_index("date")
    rfs = pd.Series(rfw)
    res = {"made": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"), "plan": "docs/signal-stack/PLAN.md",
           "weeks": len(t), "first": str(t.index[0].date()), "last": str(t.index[-1].date()),
           "stocks_per_week": [int(t["n"].min()), int(t["n"].median()), int(t["n"].max())],
           "signals_per_week": [int(t["signals"].min()), int(t["signals"].max())],
           "signal_weeks_used": used_log, "versions": {}, "benchmarks": {}}
    spans = {"whole": (START, END), **HALVES}
    for name, (a, b) in spans.items():
        x = t.loc[a:b]
        res["benchmarks"][name] = {"spy": stats(x["spy"], rfs), "equal_amounts": stats(x["ew"], rfs)}
    for v in ("A", "B"):
        lo_name, ov_name = f"{v}1", f"{v}2"
        long_res, over_res = {}, {}
        for name, (a, b) in spans.items():
            x = t.loc[a:b]
            long_res[name] = stats(x[lo_name], rfs)
            over = x[ov_name]
            over_res[name] = {"overlay_per_year": round(float(over.mean()) * 5200, 2), "spy_plus_overlay": stats(x["spy"] + over, rfs)}
        lo, hi = block_boot(t[ov_name].values)
        over_res["mean_week_95"] = [round(lo * 5200, 2), round(hi * 5200, 2)]
        bm = res["benchmarks"]
        beats = lambda mine, other: mine["10k_becomes"] > other["10k_becomes"] and mine["sharpe"] > other["sharpe"]   # noqa: E731
        long_res["pass"] = all(beats(long_res[k], bm[k]["spy"]) and beats(long_res[k], bm[k]["equal_amounts"]) for k in spans)
        over_res["pass"] = bool(lo > 0 and all(over_res[k]["overlay_per_year"] > 0 for k in HALVES)
                                and beats(over_res["whole"]["spy_plus_overlay"], bm["whole"]["spy"]))
        long_res["avg_holdings"] = round(float(t[f"{v}_long_n"].mean()), 1)
        long_res["turnover_per_year"] = round(float(t[f"{v}_long_cost"].mean() / COST * 52), 1)
        res["versions"][lo_name], res["versions"][ov_name] = long_res, over_res
    res["signal_ic"] = {k: {"family": SIGNALS[k][0], "weeks": len(v), "mean": round(float(np.mean(v)), 4),
                            "t": round(float(np.mean(v) / (np.std(v, ddof=1) / np.sqrt(len(v)))), 2)}
                        for k, v in ic.items() if len(v) >= 20}
    res["signals_never_used"] = [k for k, n in used_log.items() if n == 0]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"results-{datetime.now().date()}.json").write_text(json.dumps(res, indent=1, default=str))
    t.to_csv(OUT / "weekly.csv")
    return res


if __name__ == "__main__":
    if sys.argv[1:] != ["run"]:
        raise SystemExit(__doc__)
    print(json.dumps(run(), indent=1, default=str))
