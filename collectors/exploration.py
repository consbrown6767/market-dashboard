"""Math exploration: 15 versions of 8 methods (absorption ratio, turbulence, hidden Markov regimes, variance risk
premium, lasso lead-lag, random-matrix minimum variance, machine learning on industries, variance-ratio trend).
Plan fixed before any data was looked at: docs/exploration/PLAN.md.

Commands (run with ~/MarketData/.venv/bin/python from collectors/):
  explore    the sandbox (data up to 2005-12-31 only); results to ~/MarketData/exploration/explore-<date>.json
  holdout    opens the vault (2006-2026) for the finalists in docs/exploration/FINALISTS.md; refuses unless
             that file is committed in git and unchanged
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from options_collector import ET, connect
import vol_managed as vm
import classic_strategies as cs
import tournament as tn

warnings.filterwarnings("ignore")
RESULTS_DIR = Path.home() / "MarketData" / "exploration"
PROJECT = Path(__file__).resolve().parent.parent
FINALISTS = PROJECT / "docs" / "exploration" / "FINALISTS.md"

# ---- fixed by the plan
VAULT_START = "2006-01-01"
SANDBOX_FROM, SANDBOX_TO = "1946-01", "2005-12"
VRP_FROM = "1990-02"
VAULT_FROM, VAULT_TO = "2006-01", "2026-09"
SWITCH_COST = 0.0005
IND_COST = 0.0010
IND_FEE = 0.0020
N_TRIALS = 15


# ---------------------------------------------------------------- data, with the vault lock

def _vault_may_open() -> None:
    rel = FINALISTS.relative_to(PROJECT)
    ok = FINALISTS.exists() and subprocess.run(["git", "-C", str(PROJECT), "ls-files", "--error-unmatch", str(rel)],
                                               capture_output=True).returncode == 0
    clean = ok and subprocess.run(["git", "-C", str(PROJECT), "diff", "--quiet", "HEAD", "--", str(rel)]).returncode == 0
    if not (ok and clean):
        raise SystemExit("The vault stays shut: docs/exploration/FINALISTS.md must exist and be committed, unchanged.")


def load(db, vault: bool = False) -> dict:
    if vault:
        _vault_may_open()
    end = "2099-12-31" if vault else "2005-12-31"
    us = pd.read_sql("SELECT date, series, ret FROM ff_daily WHERE dataset='us' AND date <= ?", db, params=(end,)).pivot(
        index="date", columns="series", values="ret")
    ind = pd.read_sql("SELECT date, series, ret FROM ff_daily WHERE dataset='ind49' AND date <= ?", db, params=(end,)).pivot(
        index="date", columns="series", values="ret")
    for x in (us, ind):
        x.index = pd.to_datetime(x.index)
    ind = ind.reindex(us.index)
    px = pd.read_sql("SELECT symbol, date, close FROM index_daily WHERE symbol IN ('SPX','VIX') AND date <= ?", db,
                     params=(end,)).pivot(index="date", columns="symbol", values="close")
    px.index = pd.to_datetime(px.index)
    d = {"mkt": pd.DataFrame({"ex": us["MKT_RF"], "rf": us["RF"]}), "ind": ind, "spxvix": px.dropna()}
    if not vault:
        for k in ("mkt", "ind", "spxvix"):
            assert d[k].index.max() < pd.Timestamp(VAULT_START), "vault leak"
    return d


def monthly(r: pd.Series | pd.DataFrame):
    return (1 + r).groupby(r.index.to_period("M")).prod(min_count=1) - 1


def month_ends(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby(idx.to_period("M")).last().values)


# ---------------------------------------------------------------- turning signals into returns

def from_daily_weights(d: dict, w: pd.Series) -> pd.Series:
    """w[t] = weight in the market on day t, already decided from data up to t-1. Monthly returns.
    Signals always come from d["mkt"] and d["ind"]; what's held is d["hold"] if set (SPY in the vault)."""
    h = d.get("hold", d["mkt"])
    w = w[w.index.isin(h.index)]
    m = h.loc[w.index]
    w = w.fillna(0.0)
    r = m["rf"] + w * m["ex"] - SWITCH_COST * w.diff().abs().fillna(w.abs())
    return monthly(r)


def from_monthly_weights(d: dict, w: pd.Series) -> pd.Series:
    """w[month] decided from data up to the end of the previous month."""
    h = d.get("hold", d["mkt"])
    mm = monthly(h["ex"] + h["rf"])
    rf = monthly(h["rf"])
    w = w.dropna()
    w.index = pd.PeriodIndex(w.index, freq="M")
    R, f = mm.reindex(w.index), rf.reindex(w.index)
    return f + w * (R - f) - SWITCH_COST * w.diff().abs().fillna(w.abs())


def from_industry_weights(d: dict, W: pd.DataFrame, fee: float = 0.0) -> pd.Series:
    """W: rows = months (decided at the end of the month before), columns = industries."""
    R = monthly(d["ind"])
    W = W.fillna(0.0)
    W.index = pd.PeriodIndex(W.index, freq="M")
    R = R.reindex(W.index)[W.columns].fillna(0.0)
    turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    return (W * R).sum(axis=1) - IND_COST * turn - (fee or d.get("fee", 0.0)) / 12


# ---------------------------------------------------------------- 1. absorption ratio

def absorption(d: dict, window: int = 500) -> pd.Series:
    """Share of variance in the top fifth of eigenvectors, each day, from the last `window` days."""
    X = d["ind"]
    out = {}
    vals = X.values
    for i in range(window, len(X)):
        block = vals[i - window:i + 1]
        cols = ~np.isnan(block).any(axis=0)
        B = block[:, cols]
        if B.shape[1] < 20:
            continue
        ev = np.linalg.eigvalsh(np.cov(B, rowvar=False))[::-1]
        k = max(1, round(B.shape[1] / 5))
        out[X.index[i]] = ev[:k].sum() / ev.sum()
    return pd.Series(out)


def ar_signal(ar: pd.Series) -> pd.Series:
    """Standardized shift: 15-day average minus 1-year average, over the 1-year standard deviation. >1 = fragile."""
    return (ar.rolling(15).mean() - ar.rolling(252).mean()) / ar.rolling(252).std()


def s1a(d, cache):
    z = cache.setdefault("ar_z", ar_signal(absorption(d)))
    ze = z.reindex(month_ends(z.index))
    w = (ze <= 1).astype(float).where(ze.notna())
    w.index = w.index.to_period("M") + 1
    return from_monthly_weights(d, w.to_timestamp()), "timing"


def s1b(d, cache):
    z = cache.setdefault("ar_z", ar_signal(absorption(d)))
    w = (z <= 1).astype(float).where(z.notna()).shift(1).dropna()
    return from_daily_weights(d, w), "timing"


# ---------------------------------------------------------------- 2. turbulence

def turbulence(d: dict, window: int = 2500) -> pd.Series:
    """Mahalanobis distance of each day's industry returns from the past `window` days (mean and covariance
    re-estimated at each month start, from data before that month)."""
    X = d["ind"]
    out = {}
    starts = pd.Series(X.index, index=X.index).groupby(X.index.to_period("M")).first()
    pos = {t: i for i, t in enumerate(X.index)}
    for _, t0 in starts.items():
        i0 = pos[t0]
        if i0 < window:
            continue
        past = X.iloc[i0 - window:i0]
        cols = past.columns[past.notna().all()]
        mu, S = past[cols].mean().values, np.cov(past[cols].values, rowvar=False)
        Si = np.linalg.pinv(S)
        month = X.loc[t0:].iloc[:23]
        month = month[month.index.to_period("M") == t0.to_period("M")]
        for t, row in month[cols].iterrows():
            v = row.values - mu
            if not np.isnan(v).any():
                out[t] = float(v @ Si @ v)
    return pd.Series(out)


def s2a(d, cache):
    tb = cache.setdefault("turb", turbulence(d))
    avg = tb.rolling(21).mean()
    me = avg.reindex(month_ends(avg.index)).dropna()
    thr = me.expanding(min_periods=60).quantile(0.8).shift(1)
    w = (me <= thr).astype(float).where(thr.notna())
    w.index = w.index.to_period("M") + 1
    return from_monthly_weights(d, w.to_timestamp()), "timing"


def s2b(d, cache):
    tb = cache.setdefault("turb", turbulence(d))
    thr = tb.expanding(min_periods=1250).quantile(0.8).shift(1)
    w = (tb <= thr).astype(float).where(thr.notna()).shift(1).dropna()
    return from_daily_weights(d, w), "timing"


# ---------------------------------------------------------------- 3. hidden Markov regimes

def _forward(x, p, mu, sd, A):
    """Filtered state probabilities (scaled forward pass). Returns (alpha, scale)."""
    T = len(x)
    B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) + 1e-300
    al = np.empty((T, 2))
    c = np.empty(T)
    a = p * B[0]
    c[0] = a.sum()
    al[0] = a / c[0]
    for t in range(1, T):
        a = (al[t - 1] @ A) * B[t]
        c[t] = a.sum()
        al[t] = a / c[t]
    return al, c, B


def fit_hmm(x, init=None, iters=60):
    if init is None:
        p, mu, sd = np.array([0.5, 0.5]), np.array([x.mean(), x.mean()]), np.array([x.std() * 0.7, x.std() * 1.6])
        A = np.array([[0.98, 0.02], [0.05, 0.95]])
    else:
        p, mu, sd, A = (np.array(v, float) for v in init)
    for _ in range(iters):
        al, c, B = _forward(x, p, mu, sd, A)
        T = len(x)
        be = np.empty((T, 2))
        be[-1] = 1.0
        for t in range(T - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be
        g /= g.sum(axis=1, keepdims=True)
        xi = (al[:-1, :, None] * A[None] * (B[1:] * be[1:])[:, None, :]) / c[1:, None, None]
        A = xi.sum(axis=0) / g[:-1].sum(axis=0)[:, None]
        A /= A.sum(axis=1, keepdims=True)
        p = g[0]
        mu = (g * x[:, None]).sum(axis=0) / g.sum(axis=0)
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(axis=0) / g.sum(axis=0))
        sd = np.maximum(sd, 1e-4)
    return p, mu, sd, A


def hmm_calm_prob(d: dict) -> pd.Series:
    """Each day's filtered chance of the calm (lower-variance) state, with parameters fitted on all
    years before the current one (refit each January, from 10 years of history)."""
    x = d["mkt"]["ex"].dropna()
    years = sorted(set(x.index.year))
    out, init = [], None
    for y in years:
        past = x[x.index.year < y]
        if past.index.year.min() > y - 10 or len(past) < 2500:
            continue
        init = fit_hmm(past.values, init, iters=60 if init is None else 15)
        p, mu, sd, A = init
        upto = x[x.index.year <= y]
        al, _, _ = _forward(upto.values, p, mu, sd, A)
        calm = int(np.argmin(sd))
        cur = pd.Series(al[:, calm], index=upto.index)
        out.append(cur[cur.index.year == y])
    return pd.concat(out)


def s3a(d, cache):
    pc = cache.setdefault("hmm", hmm_calm_prob(d))
    w = (pc > 0.5).astype(float).shift(1).dropna()
    return from_daily_weights(d, w), "timing"


def s3b(d, cache):
    pc = cache.setdefault("hmm", hmm_calm_prob(d))
    me = pc.reindex(month_ends(pc.index))
    w = (me > 0.5).astype(float)
    w.index = w.index.to_period("M") + 1
    return from_monthly_weights(d, w.to_timestamp()), "timing"


# ---------------------------------------------------------------- 4. variance risk premium

def vrp(d: dict) -> pd.Series:
    sv = d["spxvix"]
    lr = np.log(sv["SPX"]).diff()
    rv = (lr ** 2).groupby(lr.index.to_period("M")).sum()
    vix = sv["VIX"].groupby(sv.index.to_period("M")).last()
    return ((vix / 100) ** 2 / 12 - rv).dropna()


def s4a(d, cache):
    v = vrp(d)
    med = v.expanding(min_periods=24).median()
    w = (v > med).astype(float).where(med.notna())
    w.index = w.index + 1
    return from_monthly_weights(d, w.to_timestamp()), "timing"


def s4b(d, cache):
    v = vrp(d)
    mm = monthly(d["mkt"]["ex"])
    w = {}
    for i in range(36, len(v)):
        t = v.index[i]
        X = v.iloc[:i].values                       # VRP at months up to t-1
        y = mm.reindex(v.index[1:i + 1]).values     # next months' excess returns, up to t
        ok = ~np.isnan(y)
        b = np.polyfit(X[ok], y[ok], 1)
        f = b[0] * v.iloc[i] + b[1]
        var = np.nanvar(mm.loc[:t].values[-120:])
        w[t + 1] = float(np.clip(f / (3 * var), 0, 1.5))
    w = pd.Series(w)
    return from_monthly_weights(d, w.to_timestamp()), "timing"


# ---------------------------------------------------------------- 5. lasso lead-lag

def _lasso_forecasts(X: pd.DataFrame, y: pd.Series, first_year: int) -> pd.Series:
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import TimeSeriesSplit
    Xl = X.shift(1).fillna(0.0)
    out = {}
    model = None
    for t in X.index:
        if t.year < first_year:
            continue
        if model is None or t.month == 1:
            tr = (Xl.index < t) & y.notna() & (Xl.index >= Xl.index[13])
            mu, sd = Xl[tr].mean(), Xl[tr].std().replace(0, 1)
            model = (LassoCV(cv=TimeSeriesSplit(5), alphas=30, max_iter=5000).fit(((Xl[tr] - mu) / sd).values, y[tr].values), mu, sd)
        m, mu, sd = model
        out[t] = float(m.predict(((X.loc[[t]] - mu) / sd).fillna(0.0).values)[0])   # this month's returns -> next month
    return pd.Series(out)


def s5a(d, cache):
    R = monthly(d["ind"])
    rf = monthly(d["mkt"]["rf"])
    ex = monthly(d["mkt"]["ex"] + d["mkt"]["rf"]) - rf
    f = _lasso_forecasts(R.sub(rf, axis=0), ex, 1946)
    w = (f > 0).astype(float)
    w.index = w.index + 1
    return from_monthly_weights(d, w.to_timestamp()), "timing"


def s5b(d, cache):
    R = monthly(d["ind"])
    rf = monthly(d["mkt"]["rf"])
    X = R.sub(rf, axis=0)
    F = {}
    for c in R.columns:
        y = X[c]
        if y.first_valid_index() is None or y.first_valid_index().year > 1940:
            continue
        F[c] = _lasso_forecasts(X, y, 1946)
    F = pd.DataFrame(F)
    W = F.apply(lambda r: (r.rank(ascending=False) <= 10).astype(float) / 10, axis=1)
    W.index = W.index + 1
    return from_industry_weights(d, W.to_timestamp()), "industries"


# ---------------------------------------------------------------- 6. random-matrix minimum variance

def _minvar(S: np.ndarray, cap: float = 0.10) -> np.ndarray:
    from scipy.optimize import minimize
    n = len(S)
    res = minimize(lambda w: w @ S @ w, np.full(n, 1 / n), jac=lambda w: 2 * S @ w, method="SLSQP",
                   bounds=[(0, cap)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 200, "ftol": 1e-12})
    return res.x


def _clip_cov(B: np.ndarray) -> np.ndarray:
    T, N = B.shape
    sd = B.std(axis=0, ddof=1)
    C = np.corrcoef(B, rowvar=False)
    ev, V = np.linalg.eigh(C)
    lam_plus = (1 + math.sqrt(N / T)) ** 2
    noise = ev < lam_plus
    if noise.any():
        ev[noise] = ev[noise].mean()
    C2 = V @ np.diag(ev) @ V.T
    dd = np.sqrt(np.diag(C2))
    C2 = C2 / np.outer(dd, dd)
    return C2 * np.outer(sd, sd)


def _minvar_weights(d: dict, how: str) -> pd.DataFrame:
    from sklearn.covariance import LedoitWolf
    X = d["ind"]
    me = month_ends(X.index)
    rows = {}
    for t in me:
        if t.year < 1945:
            continue
        B = X.loc[:t].iloc[-250:]
        B = B.loc[:, B.notna().all()]
        S = _clip_cov(B.values) if how == "clip" else LedoitWolf().fit(B.values).covariance_
        rows[t.to_period("M") + 1] = pd.Series(_minvar(S), index=B.columns)
    W = pd.DataFrame(rows).T.fillna(0.0)
    return W.to_timestamp()


def s6a(d, cache):
    return from_industry_weights(d, _minvar_weights(d, "clip")), "industries"


def s6b(d, cache):
    return from_industry_weights(d, _minvar_weights(d, "lw")), "industries"


# ---------------------------------------------------------------- 7. machine learning on industries

def panel(d: dict) -> pd.DataFrame:
    X = d["ind"]
    mk = d["mkt"]["ex"] + d["mkt"]["rf"]
    R = monthly(X)
    rf = monthly(d["mkt"]["rf"])
    E = R.sub(rf, axis=0)
    me = month_ends(X.index)
    vol = X.rolling(63).std().reindex(me)
    mx = X.rolling(21).max().reindex(me)
    mvar = mk.rolling(252).var()
    beta = pd.DataFrame({c: X[c].rolling(252).cov(mk) / mvar for c in X.columns}).reindex(me)
    for f in (vol, mx, beta):
        f.index = f.index.to_period("M")
    cum = lambda k: (1 + R).rolling(k).apply(np.prod, raw=True) - 1
    feats = {"r1": R, "r3": cum(3), "r6": cum(6), "r12": cum(12), "vol": vol, "max": mx, "beta": beta}
    mret = monthly(mk) - rf
    rows = []
    for name, f in feats.items():
        s = f.stack().rename(name)
        rows.append(s)
    P = pd.concat(rows, axis=1)
    P.index.names = ["month", "ind"]
    P["mkt1"] = mret.reindex(P.index.get_level_values("month")).values
    P["y"] = E.shift(-1).stack().reindex(P.index).values      # next month's excess return
    return P.dropna(subset=["r12", "vol", "beta", "max"])


def _ml_weights(d: dict, cache, kind: str) -> pd.DataFrame:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    P = cache.setdefault("panel", panel(d))
    feats = ["r1", "r3", "r6", "r12", "vol", "max", "beta", "mkt1"]
    months = sorted(set(P.index.get_level_values("month")))
    W, model = {}, None
    for m in months:
        if m.year < 1946 - 1 or (m.year == 1945 and m.month < 12):
            continue
        if model is None or m.month == 12:
            tr = P[(P.index.get_level_values("month") < m)].dropna(subset=["y"])
            tr = tr[tr.index.get_level_values("month") <= m - 1]
            if kind == "gbm":
                model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                      min_samples_leaf=200, random_state=0).fit(tr[feats], tr["y"])
                scale = None
            else:
                mu, sd = tr[feats].mean(), tr[feats].std()
                model = Ridge(alpha=1.0).fit((tr[feats] - mu) / sd, tr["y"])
                scale = (mu, sd)
        cur = P.xs(m, level="month")
        Xc = cur[feats] if scale is None else (cur[feats] - scale[0]) / scale[1]
        f = pd.Series(model.predict(Xc), index=cur.index)
        top = f.rank(ascending=False) <= 10
        W[m + 1] = top.astype(float) / top.sum()
    return pd.DataFrame(W).T.fillna(0.0).to_timestamp()


def s7a(d, cache):
    return from_industry_weights(d, _ml_weights(d, cache, "gbm")), "industries"


def s7b(d, cache):
    return from_industry_weights(d, _ml_weights(d, cache, "ridge")), "industries"


# ---------------------------------------------------------------- 8. variance-ratio trend filter

def s8a(d, cache):
    mk = d["mkt"]["ex"] + d["mkt"]["rf"]
    lr = np.log1p(mk)
    me = month_ends(mk.index)
    lvl = (1 + monthly(mk)).cumprod()
    trend = (lvl > lvl.rolling(10).mean()).astype(float).where(lvl.rolling(10).count() == 10)
    w = {}
    for t in me:
        x = lr.loc[:t].iloc[-250:]
        if len(x) < 250:
            continue
        v1 = x.var()
        v10 = x.rolling(10).sum().dropna().var()
        vr = v10 / (10 * v1)
        p = t.to_period("M")
        tr = trend.get(p)
        if tr is None or np.isnan(tr):
            continue
        w[p + 1] = tr if vr > 1 else 1.0
    w = pd.Series(w)
    return from_monthly_weights(d, w.to_timestamp()), "timing"


METHODS = {
    "1a_absorption_monthly": s1a, "1b_absorption_daily": s1b,
    "2a_turbulence_monthly": s2a, "2b_turbulence_daily": s2b,
    "3a_hmm_daily": s3a, "3b_hmm_monthly": s3b,
    "4a_vrp_median": s4a, "4b_vrp_regression": s4b,
    "5a_lasso_timing": s5a, "5b_lasso_rotation": s5b,
    "6a_minvar_rmt_clip": s6a, "6b_minvar_ledoit_wolf": s6b,
    "7a_ml_boosted_trees": s7a, "7b_ml_ridge": s7b,
    "8a_variance_ratio_trend": s8a,
}


# ---------------------------------------------------------------- scoring

def stats_vs(r: pd.Series, b: pd.Series, rf: pd.Series) -> dict:
    idx = r.dropna().index.intersection(b.dropna().index)
    r, b = r.loc[idx], b.loc[idx]
    return {"strategy": vm.stats(r, rf), "market": vm.stats(b, rf),
            "sharpe_gap": round(vm.sharpe((r - rf.reindex(idx)).values) - vm.sharpe((b - rf.reindex(idx)).values), 3),
            "t_active": round(cs.nw_t((r - b).values), 2)}


def deflated_gap(r_ex: np.ndarray, b_ex: np.ndarray, trial_gaps: list[float]) -> float:
    """Chance the Sharpe gap is real given N tries (Bailey & López de Prado, applied to the monthly gap)."""
    n = len(r_ex)
    sr_r, sr_b = r_ex.mean() / r_ex.std(ddof=1), b_ex.mean() / b_ex.std(ddof=1)
    gap = sr_r - sr_b
    V = float(np.var(np.array(trial_gaps) / math.sqrt(12), ddof=1))
    em = 0.5772156649
    N = len(trial_gaps)
    sr0 = math.sqrt(V) * ((1 - em) * norm.ppf(1 - 1 / N) + em * norm.ppf(1 - 1 / (N * math.e)))
    g3, g4 = float(pd.Series(r_ex).skew()), float(pd.Series(r_ex).kurt()) + 3
    z = (gap - sr0) * math.sqrt(n - 1) / math.sqrt(max(1 - g3 * sr_r + (g4 - 1) / 4 * sr_r ** 2, 1e-9))
    return round(float(norm.cdf(z)), 3)


def job_explore(db) -> dict:
    d = load(db, vault=False)
    rf = monthly(d["mkt"]["rf"])
    mkt = monthly(d["mkt"]["ex"] + d["mkt"]["rf"])
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "plan": "docs/exploration/PLAN.md",
           "sandbox_ends": str(d["mkt"].index.max().date()), "methods": {}}
    cache, series = {}, {}
    for name, fn in METHODS.items():
        t0 = datetime.now()
        r, kind = fn(d, cache)
        a = VRP_FROM if name.startswith("4") else SANDBOX_FROM
        r = r.loc[pd.Period(a, "M"):pd.Period(SANDBOX_TO, "M")].dropna()
        series[name] = r
        res["methods"][name] = {"kind": kind, **stats_vs(r, mkt, rf), "seconds": round((datetime.now() - t0).total_seconds())}
        print(name, res["methods"][name]["strategy"], res["methods"][name]["market"], res["methods"][name]["sharpe_gap"], flush=True)
    gaps = [m["sharpe_gap"] for m in res["methods"].values()]
    for name, r in series.items():
        b = mkt.reindex(r.index)
        res["methods"][name]["deflated_prob"] = deflated_gap((r - rf.reindex(r.index)).values, (b - rf.reindex(r.index)).values, gaps)
    # each decade (information)
    for name, r in series.items():
        res["methods"][name]["decades"] = {f"{y}s": round(float(np.prod(1 + r[(r.index.year >= y) & (r.index.year < y + 10)]) - 1) * 100, 1)
                                           for y in range(1940, 2010, 10) if ((r.index.year >= y) & (r.index.year < y + 10)).any()}
    res["market_decades"] = {f"{y}s": round(float(np.prod(1 + mkt[(mkt.index.year >= y) & (mkt.index.year < y + 10) & (mkt.index >= pd.Period(SANDBOX_FROM, 'M'))]) - 1) * 100, 1)
                             for y in range(1940, 2010, 10)}
    ranked = sorted(res["methods"], key=lambda k: res["methods"][k]["sharpe_gap"], reverse=True)
    res["ranked_by_sharpe_gap"] = [(k, res["methods"][k]["sharpe_gap"]) for k in ranked]
    res["finalists_by_rule"] = [k for k in ranked if res["methods"][k]["sharpe_gap"] > 0][:3]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"explore-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = connect()
    if cmd == "explore":
        r = job_explore(db)
        print(json.dumps({k: r[k] for k in ("ranked_by_sharpe_gap", "finalists_by_rule", "_path")}, indent=1))
    elif cmd == "holdout":
        print(json.dumps(job_holdout(db), indent=1, default=str))
    else:
        print(__doc__)
        return 1
    return 0


def finalists() -> list[str]:
    """Version names listed in FINALISTS.md as '- finalist: <name>'."""
    names = [ln.split(":", 1)[1].strip() for ln in FINALISTS.read_text().splitlines() if ln.startswith("- finalist:")]
    unknown = [n for n in names if n not in METHODS]
    if unknown or not names or len(names) > 3:
        raise SystemExit(f"FINALISTS.md must list 1 to 3 known versions; got {names}")
    return names


def job_holdout(db) -> dict:
    d = load(db, vault=True)          # refuses unless FINALISTS.md is committed and unchanged
    names = finalists()
    spy = tn._daily_index(db, "SPY_ADJ").pct_change().dropna()
    rf_d = d["mkt"]["rf"].reindex(spy.index).ffill()
    d["hold"] = pd.DataFrame({"ex": spy - rf_d, "rf": rf_d}).dropna()
    d["fee"] = IND_FEE
    rfm = tn.rf_monthly(db)
    spym = monthly(spy).loc[pd.Period(VAULT_FROM, "M"):pd.Period(VAULT_TO, "M")]
    res = {"made": datetime.now(ET).isoformat(timespec="seconds"), "finalists_file": str(FINALISTS.relative_to(PROJECT)),
           "commit": subprocess.run(["git", "-C", str(PROJECT), "log", "-1", "--format=%h", "--", str(FINALISTS.relative_to(PROJECT))],
                                    capture_output=True, text=True).stdout.strip(),
           "window": [VAULT_FROM, VAULT_TO], "spy": vm.stats(spym, rfm), "finalists": {}}
    cache = {}
    for name in names:
        r, kind = METHODS[name](d, cache)
        r = r.loc[pd.Period(VAULT_FROM, "M"):pd.Period(VAULT_TO, "M")].dropna()
        idx = r.index.intersection(spym.index)
        r, b = r.loc[idx], spym.loc[idx]
        s, m = vm.stats(r, rfm), vm.stats(b, rfm)
        boot = vm.bootstrap_gap((r - rfm.reindex(idx)).values, (b - rfm.reindex(idx)).values)
        beats = s["10k_becomes"] > m["10k_becomes"] and s["sharpe"] > m["sharpe"]
        safer = (not beats) and s["sharpe"] > m["sharpe"] and s["worst_drop"] > m["worst_drop"]
        res["finalists"][name] = {"kind": kind, "strategy": s, "spy": m, "bootstrap_sharpe_gap": boot,
                                  "years": {str(y): [round(float(np.prod(1 + r[r.index.year == y]) - 1) * 100, 1),
                                                     round(float(np.prod(1 + b[b.index.year == y]) - 1) * 100, 1)]
                                            for y in sorted(set(idx.year))},
                                  "verdict": "beats SPY" if beats else "safer, not better" if safer else "fails"}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"holdout-{date.today().isoformat()}.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    res["_path"] = str(path)
    return res


if __name__ == "__main__":
    sys.exit(main())
