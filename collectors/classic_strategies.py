"""Nine classic published strategies against holding the market, on Kenneth French's data.
Plan fixed before any result: docs/classic-strategies/PLAN.md. Write-up: docs/classic-strategies/README.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  data       download French's monthly sorted portfolios into ff_monthly (daily data: vol_managed.py data)
  backtest   run the plan; results to ~/MarketData/classic_strategies/backtest-<date>.json
"""

from __future__ import annotations

import io
import json
import math
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from options_collector import ET, connect, finish_run, http_get, start_run
import vol_managed as vm

RESULTS_DIR = Path.home() / "MarketData" / "classic_strategies"
MARKETS = ("dev_ex_us", "europe", "japan", "asia_pac_ex_japan")
FILE_PREFIX = {"dev_ex_us": "Developed_ex_US", "europe": "Europe", "japan": "Japan",
               "asia_pac_ex_japan": "Asia_Pacific_ex_Japan"}
MONTHLY = {"us_mom10": "10_Portfolios_Prior_12_2_CSV", "us_2x3": "6_Portfolios_2x3_CSV",
           "us_var": "Portfolios_Formed_on_VAR_CSV", "us_op": "Portfolios_Formed_on_OP_CSV"}
for _m, _p in FILE_PREFIX.items():
    MONTHLY[f"{_m}_mom6"] = f"{_p}_6_Portfolios_ME_Prior_12_2_CSV"
    MONTHLY[f"{_m}_bm6"] = f"{_p}_6_Portfolios_ME_BE-ME_CSV"
    MONTHLY[f"{_m}_op6"] = f"{_p}_6_Portfolios_ME_OP_CSV"

# ---- fixed by the plan
US_FROM = "1927-01"
INTL_FROM, INTL_TO = "2000-07", "2026-09"
SWITCH_COST = 0.0005
BASKET_COST = 0.0010
STRATS = {   # name: (label, paper, after-publication start, kind)
    "trend10": ("Trend, 10-month", "Faber (2007)", "2006-01", "timing"),
    "trend12": ("Trend, 12-month", "Moskowitz, Ooi & Pedersen (2012)", "2010-01", "timing"),
    "halloween": ("Halloween (Nov-Apr only)", "Bouman & Jacobsen (2002)", "1999-01", "timing"),
    "tom": ("Turn of the month", "Lakonishok & Smidt (1988)", "1987-01", "timing"),
    "mom": ("Stock momentum (top decile)", "Jegadeesh & Titman (1993)", "1990-01", "portfolio"),
    "indmom": ("Industry momentum (top 10 of 49)", "Moskowitz & Grinblatt (1999)", "1996-01", "portfolio"),
    "lowvar": ("Low volatility (lowest fifth)", "Ang, Hodrick, Xing & Zhang (2006)", "2001-01", "portfolio"),
    "smallvalue": ("Small value", "Fama & French (1992)", "1991-01", "portfolio"),
    "profit": ("Profitability (top fifth)", "Novy-Marx (2013)", "2011-01", "portfolio"),
}
FIXED_COST = {"mom": 0.0025, "lowvar": 0.0005, "smallvalue": 0.0005, "profit": 0.0003}
FRENCH_COL = {"mom": ("us_mom10", "Hi PRIOR"), "lowvar": ("us_var", "Lo 20"), "smallvalue": ("us_2x3", "SMALL HiBM"),
              "profit": ("us_op", "Hi 20")}
INTL_COL = {"mom": ("mom6", "BIG HiPRIOR"), "smallvalue": ("bm6", "SMALL HiBM"), "profit": ("op6", "BIG HiOP")}
CRASHES = vm.CRASHES

SCHEMA = """
CREATE TABLE IF NOT EXISTS ff_monthly (
    dataset TEXT, series TEXT, month TEXT, ret REAL, source TEXT, fetched_at TEXT,
    PRIMARY KEY (dataset, series, month)
);
"""


# ---------------------------------------------------------------- data

def parse_monthly(text: str) -> pd.DataFrame:
    """First table (value-weighted monthly) of a French CSV: 'YYYYMM, ...' rows; percent -> decimal."""
    header, rows, idx = None, [], []
    for ln in text.splitlines():
        cells = [c.strip() for c in ln.split(",")]
        if header is None:
            if len(cells) > 1 and cells[0] == "" and cells[1]:
                header = cells[1:]
            continue
        if len(cells[0]) == 6 and cells[0].isdigit():
            rows.append(cells[1:len(header) + 1])
            idx.append(f"{cells[0][:4]}-{cells[0][4:]}")
        elif rows:
            break
    df = pd.DataFrame(rows, columns=header, index=idx).astype(float)
    return df.where(df > -99.0) / 100.0


def job_data(db) -> tuple[str, int, str]:
    now = datetime.now(ET).isoformat(timespec="seconds")
    n, notes, missing = 0, [], []
    for name, file in MONTHLY.items():
        try:
            z = zipfile.ZipFile(io.BytesIO(http_get(vm.FRENCH + file + ".zip")))
        except Exception as ex:
            missing.append(f"{name} ({type(ex).__name__})")
            continue
        df = parse_monthly(z.read(z.namelist()[0]).decode("latin-1"))
        rows = [(name, s, m, float(v), "french", now) for s in df.columns for m, v in df[s].dropna().items()]
        db.executemany("INSERT OR REPLACE INTO ff_monthly VALUES (?,?,?,?,?,?)", rows)
        n += len(rows)
        notes.append(f"{name} {df.index[0]}..{df.index[-1]}")
    db.commit()
    return ("ok" if not missing else "partial"), n, "; ".join(notes) + (f"; missing: {', '.join(missing)}" if missing else "")


def french(db, dataset: str, series: str) -> pd.Series:
    s = pd.read_sql("SELECT month, ret FROM ff_monthly WHERE dataset=? AND series=? ORDER BY month", db,
                    params=(dataset, series), index_col="month")["ret"]
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s


def market(db, mk: str = "us") -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = vm.load(db, mk)
    mo = vm.monthly(daily)[["R", "rf", "x"]]
    return daily, mo


# ---------------------------------------------------------------- the nine rules

def timing_returns(mo: pd.DataFrame, w: pd.Series) -> pd.Series:
    """w in {0,1}, decided before each month. Cost on each switch."""
    w = w.dropna()
    sw = w.diff().abs().fillna(0)
    r = mo["rf"].loc[w.index] + w * mo["x"].loc[w.index] - SWITCH_COST * sw
    return r


def trend10(mo):
    lvl = (1 + mo["R"]).cumprod()
    sig = (lvl > lvl.rolling(10).mean()).astype(float).where(lvl.rolling(10).count() == 10)
    return timing_returns(mo, sig.shift(1))


def trend12(mo):
    a = (1 + mo["R"]).rolling(12).apply(np.prod, raw=True)
    b = (1 + mo["rf"]).rolling(12).apply(np.prod, raw=True)
    return timing_returns(mo, (a > b).astype(float).where(a.notna()).shift(1))


def halloween(mo):
    w = pd.Series([1.0 if p.month in (11, 12, 1, 2, 3, 4) else 0.0 for p in mo.index], index=mo.index)
    return timing_returns(mo, w)


def tom(daily: pd.DataFrame) -> pd.Series:
    m = daily.index.to_period("M")
    pos = daily.groupby(m).cumcount()
    size = daily.groupby(m)["ex"].transform("size")
    inside = ((pos < 3) | (pos == size - 1)).astype(float)
    sw = inside.diff().abs().fillna(0)
    r = daily["rf"] + inside * daily["ex"] - SWITCH_COST * sw
    out = (1 + r).groupby(m).prod() - 1
    return out.iloc[1:]


def indmom(db, mo: pd.DataFrame) -> tuple[pd.Series, float]:
    names = [r[0] for r in db.execute("SELECT DISTINCT series FROM ff_daily WHERE dataset='ind49'")]
    d = pd.read_sql("SELECT date, series, ret FROM ff_daily WHERE dataset='ind49'", db).pivot(
        index="date", columns="series", values="ret")
    d.index = pd.to_datetime(d.index)
    monthly = (1 + d).groupby(d.index.to_period("M")).prod(min_count=10) - 1
    monthly = monthly[names]
    past = (1 + monthly).rolling(6).apply(np.prod, raw=True) - 1
    out, held, turns = {}, None, []
    for i in range(6, len(monthly)):
        t = monthly.index[i]
        score = past.iloc[i - 1].dropna()
        score = score[monthly.iloc[i].notna().reindex(score.index, fill_value=False)]
        if len(score) < 20:
            continue
        pick = score.nlargest(10).index
        new = pd.Series(0.1, index=pick)
        prev = held if held is not None else new
        turn = float(new.sub(prev, fill_value=0).abs().sum())
        turns.append(turn)
        rr = monthly.iloc[i][pick]
        r = float((new * rr).sum()) - BASKET_COST * turn
        out[t] = r
        grown = new * (1 + rr)
        held = grown / grown.sum()
    return pd.Series(out), float(np.mean(turns))


# ---------------------------------------------------------------- scoring

def stats(r: pd.Series, rf: pd.Series) -> dict:
    return vm.stats(r, rf)


def nw_t(x: np.ndarray, lags: int = 12) -> float:
    """t-statistic of the mean with Newey-West standard errors (allows for streaks)."""
    x = np.asarray(x, float)
    n = len(x)
    e = x - x.mean()
    s = e @ e / n
    for L in range(1, lags + 1):
        s += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean() / math.sqrt(s / n))


def deflated_sharpe(gap: np.ndarray, trial_srs: list[float]) -> dict:
    """Bailey & López de Prado (2014): chance the best of N tries has a true Sharpe above zero."""
    n = len(gap)
    sr = gap.mean() / gap.std(ddof=1)
    g3 = float(pd.Series(gap).skew())
    g4 = float(pd.Series(gap).kurt()) + 3
    N = len(trial_srs)
    V = float(np.var(trial_srs, ddof=1))
    em = 0.5772156649
    sr0 = math.sqrt(V) * ((1 - em) * norm.ppf(1 - 1 / N) + em * norm.ppf(1 - 1 / (N * math.e)))
    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return {"monthly_sharpe_of_gap": round(float(sr), 3), "luck_hurdle": round(float(sr0), 3),
            "prob_real": round(float(norm.cdf(z)), 3)}


def evaluate(r: pd.Series, mkt: pd.DataFrame, pub: str | None, cost_per_month: float | None = None) -> dict:
    r = r.dropna()
    r = r.loc[pd.Period(US_FROM, "M"):]
    b = mkt["R"].reindex(r.index)
    keep = b.notna()
    r, b = r[keep], b[keep]
    rf = mkt["rf"]
    gap = (r - b).values
    out = {"from": str(r.index[0]), "to": str(r.index[-1]),
           "whole": {"strategy": stats(r, rf), "market": stats(b, rf)},
           "t_gap": round(nw_t(gap), 2)}
    if pub:
        p = pd.Period(pub, "M")
        pre, post = r.loc[:p - 1], r.loc[p:]
        bpre, bpost = b.loc[pre.index], b.loc[post.index]
        out["post"] = {"strategy": stats(post, rf), "market": stats(bpost, rf),
                       "gap_per_month": round(float((post - bpost).mean()) * 100, 3),
                       "t_gap": round(nw_t((post - bpost).values), 2)}
        out["pre_gap_per_year"] = round(float((pre - bpre).mean()) * 1200, 2)
        out["post_gap_per_year"] = round(float((post - bpost).mean()) * 1200, 2)
        if cost_per_month is not None:
            out["post_break_even_cost_per_month"] = round(cost_per_month * 100 + out["post"]["gap_per_month"], 3)
    dec, won = {}, 0
    for d0 in range(1920, 2030, 10):
        sl = r.loc[pd.Period(f"{d0}-01", "M"):pd.Period(f"{d0 + 9}-12", "M")]
        if len(sl) < 120:
            continue
        a, m = float(np.prod(1 + sl) - 1), float(np.prod(1 + b.loc[sl.index]) - 1)
        dec[f"{d0}s"] = {"strategy": round(a * 100, 1), "market": round(m * 100, 1)}
        won += a > m
    out["decades"] = dec
    out["decades_won"] = f"{won} of {len(dec)}"
    yrs = {}
    for y, g in r.groupby(r.index.year):
        yrs[str(y)] = [round(float(np.prod(1 + g) - 1) * 100, 1), round(float(np.prod(1 + b.loc[g.index]) - 1) * 100, 1)]
    out["years"] = yrs
    cr = {}
    for name, (a, z) in CRASHES.items():
        sl = r.loc[pd.Period(a, "M"):pd.Period(z, "M")]
        if len(sl):
            cr[name] = [round(float(np.prod(1 + sl) - 1) * 100, 1), round(float(np.prod(1 + b.loc[sl.index]) - 1) * 100, 1)]
    out["crashes"] = cr
    return out, gap


def intl_money(r: pd.Series, mkt: pd.DataFrame) -> dict:
    sl = slice(pd.Period(INTL_FROM, "M"), pd.Period(INTL_TO, "M"))
    r = r.dropna().loc[sl]
    b = mkt["R"].reindex(r.index)
    return {"strategy_10k": round(float(10000 * np.prod(1 + r))), "market_10k": round(float(10000 * np.prod(1 + b))),
            "strategy_sharpe": stats(r, mkt["rf"])["sharpe"], "market_sharpe": stats(b, mkt["rf"])["sharpe"],
            "strategy_worst": stats(r, mkt["rf"])["worst_drop"], "market_worst": stats(b, mkt["rf"])["worst_drop"],
            "won": bool(np.prod(1 + r) > np.prod(1 + b))}


def strategy_series(db, name: str, daily, mo, mk: str = "us") -> tuple[pd.Series | None, float | None]:
    if name == "trend10":
        return trend10(mo), None
    if name == "trend12":
        return trend12(mo), None
    if name == "halloween":
        return halloween(mo), None
    if name == "tom":
        return tom(daily), None
    if name == "indmom":
        if mk != "us":
            return None, None
        r, turn = indmom(db, mo)
        return r, turn
    cost = FIXED_COST[name]
    if mk == "us":
        ds, col = FRENCH_COL[name]
    elif name in INTL_COL:
        ds, col = f"{mk}_{INTL_COL[name][0]}", INTL_COL[name][1]
    else:
        return None, None
    s = french(db, ds, col)
    if s.empty:
        return None, None
    return s - cost, cost


def verdict(name: str, ev: dict, intl: dict) -> dict:
    post, whole = ev["post"], ev["whole"]
    r1 = post["strategy"]["10k_becomes"] > post["market"]["10k_becomes"] and post["strategy"]["sharpe"] > post["market"]["sharpe"]
    r2 = ev["t_gap"] >= 3.0
    w, n = (int(x) for x in ev["decades_won"].split(" of "))
    r3 = n > 0 and w / n >= 0.6
    wins = [v["won"] for v in intl.values()]
    r4 = None if not wins else sum(wins) >= 3
    beats = r1 and r2 and r3 and (r4 is not False)
    out = {"1_after_pub_more_money_and_sharpe": r1, "2_full_t_at_least_3": r2, "3_decades_60pct": r3,
           "4_other_markets_3_of_4": r4 if r4 is not None else "n/a", "beats_market": beats}
    if STRATS[name][3] == "timing":
        safer = (post["strategy"]["sharpe"] > post["market"]["sharpe"] and post["strategy"]["worst_drop"] > post["market"]["worst_drop"]
                 and whole["strategy"]["sharpe"] > whole["market"]["sharpe"] and whole["strategy"]["worst_drop"] > whole["market"]["worst_drop"])
        out["safer_not_better"] = safer
    return out


def job_backtest(db) -> dict:
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/classic-strategies/PLAN.md",
           "strategies": {}}
    daily, mo = market(db, "us")
    others = {mk: market(db, mk) for mk in MARKETS}
    gaps = {}
    for name, (label, paper, pub, kind) in STRATS.items():
        r, extra = strategy_series(db, name, daily, mo)
        cost = extra if name in FIXED_COST else None
        ev, gap = evaluate(r, mo, pub, cost)
        if name == "indmom":
            ev["avg_turnover_per_month"] = round(extra, 3)
            ev["post_break_even_cost_per_dollar_traded"] = round((ev["post"]["gap_per_month"] / 100 + BASKET_COST * extra) / extra * 100, 3)
        intl = {}
        for mk, (d2, m2) in others.items():
            r2, _ = strategy_series(db, name, d2, m2, mk)
            if r2 is not None:
                intl[mk] = intl_money(r2, m2)
        ev["other_markets"] = intl
        ev["verdict"] = verdict(name, ev, intl)
        ev["label"], ev["paper"], ev["after_publication"] = label, paper, pub
        res["strategies"][name] = ev
        p = pd.Period(pub, "M")
        rr = r.dropna().loc[p:]
        gaps[name] = (rr - mo["R"].reindex(rr.index)).dropna().values
    srs = {k: float(g.mean() / g.std(ddof=1)) for k, g in gaps.items()}
    best = max(srs, key=srs.get)
    res["deflated_sharpe"] = {"best_after_publication": best, **deflated_sharpe(gaps[best], list(srs.values())),
                              "all_monthly_sharpes_of_gap": {k: round(v, 3) for k, v in srs.items()}}
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
        run = start_run(db, "classic-data")
        status, n, detail = job_data(db)
        finish_run(db, run, status, n, detail)
        print(detail)
    elif cmd == "backtest":
        print(json.dumps(job_backtest(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
