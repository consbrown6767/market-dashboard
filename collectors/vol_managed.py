"""Volatility-managed market model (Moreira & Muir 2017): hold more of the market after calm months,
less after wild ones. Plan fixed before any result: docs/vol-managed/PLAN.md. Write-up:
docs/vol-managed/README.md.

Commands (run with ~/MarketData/.venv/bin/python):
  data       download Kenneth French's daily market, international and 49-industry returns into ff_daily
  backtest   run the plan's full test; results to ~/MarketData/vol_managed/backtest-<date>.json
  now        today's amount for the coming month (from the latest data)
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from options_collector import ET, connect, finish_run, http_get, start_run

RESULTS_DIR = Path.home() / "MarketData" / "vol_managed"
FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
DATASETS = {   # name -> French file (daily, percent returns)
    "us": "F-F_Research_Data_Factors_daily_CSV",
    "dev_ex_us": "Developed_ex_US_3_Factors_Daily_CSV",
    "europe": "Europe_3_Factors_Daily_CSV",
    "japan": "Japan_3_Factors_Daily_CSV",
    "asia_pac_ex_japan": "Asia_Pacific_ex_Japan_3_Factors_Daily_CSV",
    "ind49": "49_Industry_Portfolios_daily_CSV",
}
OTHER_MARKETS = ("dev_ex_us", "europe", "japan", "asia_pac_ex_japan")

# ---- fixed by the plan
DAYS_PER_MONTH = 22
WARMUP_MONTHS = 120
US_START, OTHER_START = "1937-01", "2000-07"
POST_PUB = "2016-01"
TRADE_COST = 0.0005          # per dollar traded
BORROW_SPREAD = 0.01         # a year, over the T-bill
CAPS = {"up_to_1.5x": 1.5, "never_borrow": 1.0}
CRASHES = {"1987 crash": ("1987-08", "1987-12"), "2000-02 tech bust": ("2000-09", "2002-09"),
           "2008 crisis": ("2007-11", "2009-02"), "2020 Covid crash": ("2020-02", "2020-03"),
           "2020 rebound (Apr-Dec)": ("2020-04", "2020-12"), "2022 bear year": ("2022-01", "2022-12")}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ff_daily (
    dataset TEXT, series TEXT, date TEXT, ret REAL, source TEXT, fetched_at TEXT,
    PRIMARY KEY (dataset, series, date)
);
"""


# ---------------------------------------------------------------- data

def _parse_french(text: str) -> pd.DataFrame:
    """First table of a French CSV: rows 'YYYYMMDD, v1, v2...' under a header line; percent -> decimal."""
    lines = text.splitlines()
    header, rows = None, []
    for ln in lines:
        cells = [c.strip() for c in ln.split(",")]
        if len(cells) > 1 and cells[0] == "" and header is None:
            header = cells[1:]
            continue
        if header is not None:
            if len(cells[0]) == 8 and cells[0].isdigit():
                rows.append(cells)
            elif rows:      # end of the first table (value-weighted, for the industries)
                break
    df = pd.DataFrame([r[1:] for r in rows], columns=header, index=[r[0] for r in rows]).astype(float)
    df = df.where(df > -99.0)    # -99.99 means missing
    df.index = pd.to_datetime(df.index, format="%Y%m%d").strftime("%Y-%m-%d")
    return df / 100.0


def job_data(db) -> tuple[str, int, str]:
    now = datetime.now(ET).isoformat(timespec="seconds")
    n, notes = 0, []
    for name, file in DATASETS.items():
        z = zipfile.ZipFile(io.BytesIO(http_get(FRENCH + file + ".zip")))
        df = _parse_french(z.read(z.namelist()[0]).decode("latin-1"))
        if name != "ind49":
            df = df[["Mkt-RF", "RF"]].rename(columns={"Mkt-RF": "MKT_RF"})
        rows = [(name, s, d, float(v), "french", now) for s in df.columns for d, v in df[s].dropna().items()]
        db.executemany("INSERT OR REPLACE INTO ff_daily VALUES (?,?,?,?,?,?)", rows)
        n += len(rows)
        notes.append(f"{name} {df.index[0]}..{df.index[-1]}")
    db.commit()
    return "ok", n, "; ".join(notes)


def load(db, dataset: str, series: str | None = None) -> pd.DataFrame:
    """Daily frame with columns ex (excess return) and rf, indexed by date."""
    us = pd.read_sql("SELECT date, series, ret FROM ff_daily WHERE dataset='us'", db).pivot(
        index="date", columns="series", values="ret")
    if dataset == "ind49":
        r = pd.read_sql("SELECT date, ret FROM ff_daily WHERE dataset='ind49' AND series=?", db, params=(series,),
                        index_col="date")["ret"]
        df = pd.DataFrame({"ex": r - us["RF"].reindex(r.index), "rf": us["RF"].reindex(r.index)})
    elif dataset == "spx":
        px = pd.read_sql("SELECT date, close FROM index_daily WHERE symbol='SPX' ORDER BY date", db,
                         index_col="date")["close"]
        r = px.pct_change().dropna()
        rf = us["RF"].reindex(r.index).ffill()      # French's T-bill lags a month or two: carry the last value
        df = pd.DataFrame({"ex": r - rf, "rf": rf})
    else:
        d = pd.read_sql("SELECT date, series, ret FROM ff_daily WHERE dataset=?", db, params=(dataset,)).pivot(
            index="date", columns="series", values="ret")
        df = pd.DataFrame({"ex": d["MKT_RF"], "rf": d["RF"]})
    df = df.dropna()
    df.index = pd.to_datetime(df.index)
    return df


# ---------------------------------------------------------------- the rule

def monthly(df: pd.DataFrame, measure: str = "var1m") -> pd.DataFrame:
    """One row per month: market total return R, T-bill return rf, jumpiness measured in that month,
    first-day pieces (for the one-day delay check)."""
    m = df.index.to_period("M")
    g = df.groupby(m)
    tot = (1 + df["ex"] + df["rf"])
    out = pd.DataFrame({
        "R": g.apply(lambda x: float(np.prod(1 + x["ex"] + x["rf"]) - 1)),
        "rf": g["rf"].apply(lambda x: float(np.prod(1 + x) - 1)),
        "n": g.size(),
    })
    first = df.groupby(m).head(1)
    first.index = first.index.to_period("M")
    out["R1"] = first["ex"] + first["rf"]
    out["rf1"] = first["rf"]
    out["Rrest"] = (1 + out["R"]) / (1 + out["R1"]) - 1
    out["rfrest"] = (1 + out["rf"]) / (1 + out["rf1"]) - 1
    ex = df["ex"]
    if measure == "var1m":          # Moreira & Muir: variance of the month's daily returns, 22-day month
        out["jump"] = g["ex"].apply(lambda x: x.var(ddof=0) * DAYS_PER_MONTH)
    elif measure in ("var1w", "var3m", "var6m"):
        n = {"var1w": 5, "var3m": 63, "var6m": 126}[measure]
        roll = ex.rolling(n).var(ddof=0) * DAYS_PER_MONTH
        out["jump"] = roll.groupby(m).last()
    elif measure == "vol1m":        # 1/volatility (Harvey et al.)
        out["jump"] = np.sqrt(g["ex"].apply(lambda x: x.var(ddof=0) * DAYS_PER_MONTH))
    elif measure == "down1m":       # downside variance (Wang & Yan)
        out["jump"] = g["ex"].apply(lambda x: (np.minimum(x, 0) ** 2).sum() * DAYS_PER_MONTH / len(x))
    out = out[out["n"] >= 10]       # a part-month at the start of a file is dropped
    out["x"] = out["R"] - out["rf"]
    return out


def weights(mo: pd.DataFrame, cap: float) -> pd.Series:
    """Amount held in month t, decided at the end of month t-1 from data through t-1 only."""
    s = (1.0 / mo["jump"]).shift(1)             # signal known at the end of the month before
    managed = s * mo["x"]
    w = pd.Series(np.nan, index=mo.index)
    for i in range(WARMUP_MONTHS, len(mo)):
        # c from months up to and including t-1: managed returns as volatile as holding the market.
        past_x, past_m = mo["x"].iloc[1:i], managed.iloc[1:i]
        c = past_x.std() / past_m.std()
        w.iloc[i] = min(c * s.iloc[i], cap)
    return w


def run_strategy(mo: pd.DataFrame, w: pd.Series, cost: float = TRADE_COST, spread: float = BORROW_SPREAD,
                 delay: bool = False) -> pd.Series:
    """Monthly returns of the managed portfolio, after trading and borrowing costs."""
    out, w_held = [], None
    for t, row in mo.iterrows():
        wt = w.get(t)
        if wt is None or np.isnan(wt):
            continue
        prev = wt if w_held is None else w_held
        if delay and w_held is not None:
            r1 = row["rf1"] + prev * (row["R1"] - row["rf1"]) - max(prev - 1, 0) * spread / 252
            r2 = row["rfrest"] + wt * (row["Rrest"] - row["rfrest"]) - max(wt - 1, 0) * spread / 12
            r = (1 + r1) * (1 + r2) - 1
        else:
            r = row["rf"] + wt * row["x"] - max(wt - 1, 0) * spread / 12
        r -= cost * abs(wt - prev)
        out.append((t, r))
        w_held = wt * (1 + row["R"]) / (1 + r)       # the weight the month's moves leave you at
    return pd.Series(dict(out))


# ---------------------------------------------------------------- scoring

def stats(r: pd.Series, rf: pd.Series) -> dict:
    ex = r - rf.reindex(r.index)
    wealth = (1 + r).cumprod()
    dd = wealth / wealth.cummax() - 1
    years = len(r) / 12
    return {"months": len(r), "per_year": round(float(wealth.iloc[-1] ** (1 / years) - 1) * 100, 2),
            "vol": round(float(r.std() * np.sqrt(12)) * 100, 2),
            "sharpe": round(float(ex.mean() / ex.std() * np.sqrt(12)), 3),
            "worst_drop": round(float(dd.min()) * 100, 1),
            "10k_becomes": round(float(10000 * wealth.iloc[-1]))}


def sharpe(ex: np.ndarray) -> float:
    return float(ex.mean() / ex.std() * np.sqrt(12))


def bootstrap_gap(a_ex: np.ndarray, b_ex: np.ndarray, draws: int = 2000, block: int = 12, seed: int = 1) -> dict:
    rng = np.random.default_rng(seed)
    n = len(a_ex)
    gaps = []
    for _ in range(draws):
        starts = rng.integers(0, n - block + 1, size=n // block + 1)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        gaps.append(sharpe(a_ex[idx]) - sharpe(b_ex[idx]))
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return {"gap": round(sharpe(a_ex) - sharpe(b_ex), 3), "range_95": [round(float(lo), 3), round(float(hi), 3)]}


def placebo(mo: pd.DataFrame, w: pd.Series, draws: int = 1000, seed: int = 2) -> dict:
    rng = np.random.default_rng(seed)
    ww = w.dropna()
    real = run_strategy(mo, ww)
    real_s = sharpe((real - mo["rf"].reindex(real.index)).values)
    beats = 0
    shuffled = []
    for _ in range(draws):
        sw = pd.Series(rng.permutation(ww.values), index=ww.index)
        r = run_strategy(mo, sw)
        s = sharpe((r - mo["rf"].reindex(r.index)).values)
        shuffled.append(s)
        beats += real_s > s
    return {"real_sharpe": round(real_s, 3), "shuffled_median": round(float(np.median(shuffled)), 3),
            "share_beaten": round(beats / draws, 3)}


def compare(mo: pd.DataFrame, strat: pd.Series, since: str, until: str | None = None) -> dict:
    sl = slice(pd.Period(since, "M"), pd.Period(until, "M") if until else None)
    s = strat.loc[sl]
    b = mo["R"].loc[s.index]
    return {"managed": stats(s, mo["rf"]), "buy_hold": stats(b, mo["rf"])}


def full_test(mo: pd.DataFrame, cap: float, since: str, extra: bool = True) -> dict:
    w = weights(mo, cap)
    strat = run_strategy(mo, w)
    strat = strat.loc[pd.Period(since, "M"):]
    rf = mo["rf"]
    b = mo["R"].loc[strat.index]
    out = {"whole": {"managed": stats(strat, rf), "buy_hold": stats(b, rf)},
           "avg_amount": round(float(w.loc[strat.index].mean()), 3),
           "share_months_at_cap": round(float((w.loc[strat.index] >= cap - 1e-9).mean()), 3),
           "boot": bootstrap_gap((strat - rf.loc[strat.index]).values, (b - rf.loc[strat.index]).values)}
    if extra:
        dec = {}
        for d0 in range(int(since[:3] + "0"), 2030, 10):
            sl = slice(pd.Period(f"{max(d0, int(since[:4]))}-01", "M"), pd.Period(f"{d0 + 9}-12", "M"))
            s, bb = strat.loc[sl], b.loc[sl]
            if len(s) < 36:
                continue
            dec[f"{d0}s"] = {"managed": round(sharpe((s - rf.loc[s.index]).values), 3),
                             "buy_hold": round(sharpe((bb - rf.loc[bb.index]).values), 3),
                             "managed_per_year": stats(s, rf)["per_year"], "buy_hold_per_year": stats(bb, rf)["per_year"]}
        out["decades"] = dec
        yrs = {}
        for y, g in strat.groupby(strat.index.year):
            yrs[str(y)] = {"managed": round(float(np.prod(1 + g) - 1) * 100, 1),
                           "buy_hold": round(float(np.prod(1 + b.loc[g.index]) - 1) * 100, 1),
                           "avg_amount": round(float(w.loc[g.index].mean()), 2)}
        out["years"] = yrs
        out["delay_1day"] = stats(run_strategy(mo, w, delay=True).loc[strat.index], rf)
        out["high_costs"] = stats(run_strategy(mo, w, cost=0.002, spread=0.03).loc[strat.index], rf)
    return out, strat, w


def crash_table(mo, strat, w):
    out = {}
    for name, (a, z) in CRASHES.items():
        sl = slice(pd.Period(a, "M"), pd.Period(z, "M"))
        s = strat.loc[sl]
        if len(s) == 0:
            continue
        out[name] = {"managed": round(float(np.prod(1 + s) - 1) * 100, 1),
                     "buy_hold": round(float(np.prod(1 + mo["R"].loc[s.index]) - 1) * 100, 1),
                     "avg_amount": round(float(w.loc[s.index].mean()), 2)}
    return out


def job_backtest(db) -> dict:
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/vol-managed/PLAN.md"}
    us = monthly(load(db, "us"))
    res["us_data"] = [str(us.index[0]), str(us.index[-1])]
    for name, cap in CAPS.items():
        r = {}
        full, strat, w = full_test(us, cap, US_START)
        r["full"] = full
        r["post_pub"] = compare(us, strat, POST_PUB)
        r["paper_period"] = compare(us, strat, US_START, "2015-12")
        r["crashes"] = crash_table(us, strat, w)
        r["placebo"] = placebo(us, w)
        others = {}
        for mk in OTHER_MARKETS:
            mo = monthly(load(db, mk))
            f, s2, w2 = full_test(mo, cap, OTHER_START, extra=False)
            others[mk] = f
        r["other_markets"] = others
        res[name] = r
    # Variants: information only.
    var = {}
    for meas in ("var1w", "var3m", "var6m", "vol1m", "down1m"):
        mo = monthly(load(db, "us"), meas)
        for name, cap in CAPS.items():
            f, s, w = full_test(mo, cap, US_START, extra=False)
            var[f"{meas}/{name}"] = {"whole": f["whole"]["managed"], "post_pub": compare(mo, s, POST_PUB)["managed"]}
    res["variants"] = var
    # 49 industries.
    names = [r[0] for r in db.execute("SELECT DISTINCT series FROM ff_daily WHERE dataset='ind49'")]
    ind = {}
    for nm in names:
        mo = monthly(load(db, "ind49", nm))
        if len(mo) < WARMUP_MONTHS + 120:
            continue
        since = max(US_START, str(mo.index[WARMUP_MONTHS]))
        f, s, w = full_test(mo, CAPS["up_to_1.5x"], since, extra=False)
        ind[nm] = {"since": since, "managed": f["whole"]["managed"]["sharpe"], "buy_hold": f["whole"]["buy_hold"]["sharpe"]}
    res["industries"] = {"count": len(ind), "managed_better": sum(v["managed"] > v["buy_hold"] for v in ind.values()),
                         "each": ind}
    # S&P 500 price only.
    spx = monthly(load(db, "spx"))
    spx = spx.loc[:pd.Period(date.today().strftime("%Y-%m"), "M") - 1]     # whole months only
    sp = {}
    for name, cap in CAPS.items():
        f, s, w = full_test(spx, cap, "2000-01", extra=False)
        sp[name] = {"whole": f["whole"], "post_pub": compare(spx, s, POST_PUB), "last_12_amounts":
                    {str(k): round(float(v), 2) for k, v in w.iloc[-12:].items()}}
    res["spx_price_only"] = sp
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"backtest-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    db = connect()
    db.executescript(SCHEMA)
    if cmd == "data":
        run = start_run(db, "volmanaged-data")
        status, n, detail = job_data(db)
        finish_run(db, run, status, n, detail)
        print(detail)
    elif cmd == "backtest":
        res = job_backtest(db)
        print(json.dumps(res, indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
