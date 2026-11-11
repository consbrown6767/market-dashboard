"""The prediction ledger: every model writes its predictions here before the outcome is known, and
they're all scored the same way. The Scorecard tab reads it.

The rules, the same for every model:
1. Written down first. A live prediction is stamped with the time it's logged, and log() refuses it
   if its target window has already opened.
2. Never edited. Live rows are only ever added. Each carries a hash of its contents and of the live
   row before it, and each outcome a hash tied to its prediction, so verify() spots a changed or
   deleted row. A fixed or retuned model gets a new version, scored on its own.
3. Always next to a simple guess. Every prediction comes with one or more baselines made at the same
   moment by simple rules, scored the same way. A model is only worth keeping if it beats them.
4. Live and backtest kept apart. A backtest reruns a model on past days using only what was known at
   the time. Backtests can be rerun (clear_backtest), so they aren't chained, and the two are never
   mixed in a score.
5. No verdict too early. Until MIN_RESOLVED predictions are resolved, the verdict is "too few", and
   after that a model is only called better or worse when the gap is about twice its own noise
   (measured allowing for streaks of good and bad days, which are common in markets).

Two kinds of prediction:
- probability: the chance something happens. forecast {"p": 0.62}, outcome 1 or 0. Scored by the
  Brier score, (p - outcome)^2: lower is better, and always saying 50% scores 0.25.
- quantiles: a range for a number. forecast {"q": {"0.05": -1.4, "0.5": 0.0, "0.95": 1.3}}, outcome
  the number. Scored by the quantile (pinball) loss averaged over the levels given: lower is better.
  Coverage says how often the outcome landed inside each central range (5-95% should catch about 90%).

From a model's job:
    db = connect(); ensure(db)
    log(db, model="spx-move", version="1", mode="live", target="SPX close-to-close % change, 2026-11-10",
        kind="quantiles", opens_at=..., resolves_at=..., forecast={...}, baselines={"recent": {...}}, inputs={...})
    for p in due(db, "spx-move"):
        resolve(db, p["id"], outcome, source="...")
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MODES = ("live", "backtest")
KINDS = ("probability", "quantiles")
MIN_RESOLVED = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    model TEXT NOT NULL, version TEXT NOT NULL, mode TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL,
    made_at TEXT NOT NULL, opens_at TEXT NOT NULL, resolves_at TEXT NOT NULL,
    forecast TEXT NOT NULL, baselines TEXT NOT NULL, inputs TEXT NOT NULL,
    prev_hash TEXT, hash TEXT,
    UNIQUE (model, version, mode, target)
);
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    prediction_id INTEGER PRIMARY KEY, outcome REAL NOT NULL, source TEXT NOT NULL, resolved_at TEXT NOT NULL, hash TEXT
);
"""


def ensure(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def _now() -> datetime:
    return datetime.now(ET)


def _time(x: datetime | str) -> datetime:
    t = datetime.fromisoformat(x) if isinstance(x, str) else x
    if t.tzinfo is None:
        raise ValueError(f"time without a time zone: {x}")
    return t


def _iso(t: datetime) -> str:
    return t.astimezone(ET).isoformat(timespec="seconds")


def _json(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def _sha(*parts: str | None) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


PREDICTION_FIELDS = ("model", "version", "mode", "target", "kind", "made_at", "opens_at", "resolves_at",
                     "forecast", "baselines", "inputs")


def _prediction_hash(row: dict, prev_hash: str | None) -> str:
    return _sha(*(row[f] for f in PREDICTION_FIELDS), prev_hash)


def _outcome_hash(prediction_hash: str, outcome: float, source: str, resolved_at: str) -> str:
    return _sha(prediction_hash, repr(float(outcome)), source, resolved_at)


def _check_forecast(kind: str, f: dict) -> None:
    if kind == "probability":
        if not (isinstance(f.get("p"), (int, float)) and 0 <= f["p"] <= 1):
            raise ValueError(f"a probability forecast needs p between 0 and 1: {f}")
    else:
        q = f.get("q")
        if not q or not all(0 < float(k) < 1 and isinstance(v, (int, float)) for k, v in q.items()):
            raise ValueError(f"a quantile forecast needs levels between 0 and 1 with numbers: {f}")
        values = [v for _, v in sorted(q.items(), key=lambda kv: float(kv[0]))]
        if values != sorted(values):
            raise ValueError(f"quantiles must rise with their level: {f}")


# ---------- writing (collectors only)

def log(db: sqlite3.Connection, *, model: str, version: str, mode: str, target: str, kind: str,
        opens_at: datetime | str, resolves_at: datetime | str, forecast: dict, baselines: dict,
        inputs: dict | None = None, made_at: datetime | str | None = None) -> int | None:
    """Add one prediction. Returns its id, or None if this model version already logged that target.
    Live predictions are stamped now (made_at is not accepted); backtests must say when they were made."""
    if mode not in MODES or kind not in KINDS:
        raise ValueError(f"mode must be one of {MODES} and kind one of {KINDS}")
    if not baselines:
        raise ValueError("every prediction needs at least one baseline")
    for f in (forecast, *baselines.values()):
        _check_forecast(kind, f)
    opens, resolves = _time(opens_at), _time(resolves_at)
    if mode == "live":
        if made_at is not None:
            raise ValueError("live predictions are stamped with the time they're logged")
        made = _now()
    else:
        if made_at is None:
            raise ValueError("a backtest prediction must say when it would have been made")
        made = _time(made_at)
    if not made < opens <= resolves:
        raise ValueError(f"too late: made {_iso(made)}, but its window opens {_iso(opens)}")
    row = {"model": model, "version": str(version), "mode": mode, "target": target, "kind": kind,
           "made_at": _iso(made), "opens_at": _iso(opens), "resolves_at": _iso(resolves),
           "forecast": _json(forecast), "baselines": _json(baselines), "inputs": _json(inputs or {})}
    if db.execute("SELECT 1 FROM predictions WHERE model=? AND version=? AND mode=? AND target=?",
                  (model, row["version"], mode, target)).fetchone():
        return None
    prev = hash_ = None
    if mode == "live":
        last = db.execute("SELECT hash FROM predictions WHERE mode='live' ORDER BY id DESC LIMIT 1").fetchone()
        prev = last[0] if last else None
        hash_ = _prediction_hash(row, prev)
    cur = db.execute(f"INSERT INTO predictions ({', '.join(PREDICTION_FIELDS)}, prev_hash, hash) VALUES "
                     f"({', '.join('?' * len(PREDICTION_FIELDS))}, ?, ?)", (*row.values(), prev, hash_))
    db.commit()
    return cur.lastrowid


def due(db: sqlite3.Connection, model: str, mode: str = "live") -> list[dict]:
    """Predictions whose outcome should be known by now and hasn't been recorded."""
    now = _now()
    out = []
    for r in db.execute("""SELECT p.id, p.target, p.opens_at, p.resolves_at FROM predictions p
                           LEFT JOIN prediction_outcomes o ON o.prediction_id = p.id
                           WHERE p.model = ? AND p.mode = ? AND o.prediction_id IS NULL ORDER BY p.id""", (model, mode)):
        if mode == "backtest" or _time(r[3]) <= now:
            out.append({"id": r[0], "target": r[1], "opens_at": r[2], "resolves_at": r[3]})
    return out


def resolve(db: sqlite3.Connection, prediction_id: int, outcome: float, source: str) -> None:
    """Record what actually happened. Once only, and for live predictions not before resolves_at."""
    p = db.execute("SELECT mode, kind, resolves_at, hash FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    if not p:
        raise ValueError(f"no prediction {prediction_id}")
    mode, kind, resolves_at, p_hash = p
    if not (isinstance(outcome, (int, float)) and math.isfinite(outcome)):
        raise ValueError(f"outcome must be a number: {outcome}")
    if kind == "probability" and outcome not in (0, 1):
        raise ValueError("a probability prediction resolves to 1 (it happened) or 0 (it didn't)")
    now = _now()
    if mode == "live" and now < _time(resolves_at):
        raise ValueError(f"prediction {prediction_id} can't be resolved before {resolves_at}")
    if db.execute("SELECT 1 FROM prediction_outcomes WHERE prediction_id = ?", (prediction_id,)).fetchone():
        raise ValueError(f"prediction {prediction_id} is already resolved")
    at = _iso(now)
    h = _outcome_hash(p_hash, outcome, source, at) if mode == "live" else None
    db.execute("INSERT INTO prediction_outcomes VALUES (?, ?, ?, ?, ?)", (prediction_id, float(outcome), source, at, h))
    db.commit()


def clear_backtest(db: sqlite3.Connection, model: str, version: str) -> int:
    """Throw away one version's backtest before rerunning it. Live rows can't be removed this way."""
    ids = [r[0] for r in db.execute("SELECT id FROM predictions WHERE model=? AND version=? AND mode='backtest'",
                                    (model, str(version)))]
    db.executemany("DELETE FROM prediction_outcomes WHERE prediction_id = ?", [(i,) for i in ids])
    db.executemany("DELETE FROM predictions WHERE id = ?", [(i,) for i in ids])
    db.commit()
    return len(ids)


# ---------- reading and scoring (safe on a read-only connection)

def brier(forecast: dict, outcome: float) -> float:
    return (forecast["p"] - outcome) ** 2


def pinball(forecast: dict, outcome: float) -> float:
    losses = []
    for level, q in forecast["q"].items():
        t, miss = float(level), outcome - q
        losses.append(max(t * miss, (t - 1) * miss))
    return sum(losses) / len(losses)


def loss(kind: str, forecast: dict, outcome: float) -> float:
    return brier(forecast, outcome) if kind == "probability" else pinball(forecast, outcome)


def coverage(pairs: list[tuple[dict, float]]) -> dict[str, dict]:
    """For each central range in the forecasts (5-95%, 25-75%...), how often the outcome landed inside."""
    out: dict[str, dict] = {}
    for f, y in pairs:
        q = {round(float(k), 4): v for k, v in f["q"].items()}
        for lo in sorted(k for k in q if k < 0.5):
            hi = round(1 - lo, 4)
            if hi not in q:
                continue
            c = out.setdefault(f"{lo * 100:g}-{hi * 100:g}%", {"expected": round(hi - lo, 4), "inside": 0, "n": 0})
            c["n"] += 1
            c["inside"] += q[lo] <= y <= q[hi]
    for c in out.values():
        c["share"] = c["inside"] / c["n"]
    return out


def _streak_se(diffs: list[float], gap: float) -> float:
    """Standard error of the mean gap, allowing for streaks (Newey-West, Bartlett weights). Errors on
    consecutive days are related (a stormy week is stormy for every model), and treating them as
    independent would make the noise look smaller than it is. Never below the plain standard error."""
    n = len(diffs)
    c = [d - gap for d in diffs]
    plain = sum(x * x for x in c) / (n - 1)
    var = sum(x * x for x in c) / n
    lags = min(int(4 * (n / 100) ** (2 / 9)), n - 1)
    for k in range(1, lags + 1):
        var += 2 * (1 - k / (lags + 1)) * sum(c[i] * c[i - k] for i in range(k, n)) / n
    return math.sqrt(max(var, plain) / n)


def compare(model_losses: list[float], base_losses: list[float]) -> dict:
    """Paired comparison, prediction by prediction. Negative gap means the model's losses are lower."""
    n = len(model_losses)
    diffs = [m - b for m, b in zip(model_losses, base_losses)]
    mean_m, mean_b = sum(model_losses) / n, sum(base_losses) / n
    gap = sum(diffs) / n
    se = _streak_se(diffs, gap) if n > 1 else math.inf
    if n < MIN_RESOLVED:
        verdict = "too few"
    elif gap + 2 * se < 0:
        verdict = "better"
    elif gap - 2 * se > 0:
        verdict = "worse"
    else:
        verdict = "no clear difference"
    return {"model_loss": mean_m, "baseline_loss": mean_b, "skill": 1 - mean_m / mean_b if mean_b else None,
            "gap": gap, "gap_se": se if math.isfinite(se) else None, "verdict": verdict}


def summary(db: sqlite3.Connection) -> list[dict]:
    """One entry per model, version and mode: counts, scores and a verdict against each baseline."""
    groups: dict[tuple, dict] = {}
    for r in db.execute("""SELECT p.model, p.version, p.mode, p.kind, p.made_at, p.forecast, p.baselines, o.outcome
                           FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id = p.id ORDER BY p.id"""):
        model, version, mode, kind, made_at, f, b, y = r
        g = groups.setdefault((model, version, mode), {"model": model, "version": version, "mode": mode, "kind": kind,
                                                        "logged": 0, "resolved": 0, "first": made_at, "last": made_at,
                                                        "_pairs": [], "_base": {}})
        g["logged"] += 1
        g["last"] = made_at
        if y is None:
            continue
        g["resolved"] += 1
        f = json.loads(f)
        g["_pairs"].append((f, y))
        for name, bf in json.loads(b).items():
            g["_base"].setdefault(name, []).append((len(g["_pairs"]) - 1, bf))
    out = []
    for g in groups.values():
        pairs, kind = g.pop("_pairs"), g["kind"]
        model_losses = [loss(kind, f, y) for f, y in pairs]
        g["model_loss"] = sum(model_losses) / len(model_losses) if model_losses else None
        g["baselines"] = {}
        for name, items in g.pop("_base").items():
            if len(items) < 2:
                g["baselines"][name] = {"resolved": len(items), "verdict": "too few"}
                continue
            mine = [model_losses[i] for i, _ in items]
            theirs = [loss(kind, bf, pairs[i][1]) for i, bf in items]
            g["baselines"][name] = {"resolved": len(items), **compare(mine, theirs)}
        if kind == "quantiles":
            g["coverage"] = coverage(pairs)
        out.append(g)
    return out


def recent(db: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """The latest predictions with their outcome and losses, newest first."""
    out = []
    for r in db.execute("""SELECT p.id, p.model, p.version, p.mode, p.target, p.kind, p.made_at, p.resolves_at,
                                  p.forecast, p.baselines, o.outcome, o.resolved_at
                           FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id = p.id
                           ORDER BY p.made_at DESC, p.id DESC LIMIT ?""", (limit,)):
        d = dict(zip(("id", "model", "version", "mode", "target", "kind", "made_at", "resolves_at", "forecast",
                      "baselines", "outcome", "resolved_at"), r))
        d["forecast"], d["baselines"] = json.loads(d["forecast"]), json.loads(d["baselines"])
        if d["outcome"] is not None:
            d["loss"] = loss(d["kind"], d["forecast"], d["outcome"])
            d["baseline_loss"] = {k: loss(d["kind"], f, d["outcome"]) for k, f in d["baselines"].items()}
        out.append(d)
    return out


def verify(db: sqlite3.Connection) -> dict:
    """Recompute the live chain. Catches a changed row, a removed row in the middle, or a changed
    outcome. (Removing the very last rows only shows as a lower count.)"""
    problems, prev, n = [], None, 0
    for r in db.execute(f"SELECT id, {', '.join(PREDICTION_FIELDS)}, prev_hash, hash FROM predictions "
                        "WHERE mode = 'live' ORDER BY id"):
        n += 1
        row = dict(zip(("id", *PREDICTION_FIELDS, "prev_hash", "hash"), r))
        if row["prev_hash"] != prev:
            problems.append(f"prediction {row['id']}: doesn't follow the one before it (a row was removed?)")
        if row["hash"] != _prediction_hash(row, row["prev_hash"]):
            problems.append(f"prediction {row['id']}: contents changed after it was logged")
        prev = row["hash"]
    for pid, outcome, source, at, h, p_hash in db.execute(
            """SELECT o.prediction_id, o.outcome, o.source, o.resolved_at, o.hash, p.hash FROM prediction_outcomes o
               JOIN predictions p ON p.id = o.prediction_id WHERE p.mode = 'live'"""):
        if h != _outcome_hash(p_hash, outcome, source, at):
            problems.append(f"outcome of prediction {pid}: changed after it was recorded")
    orphans = db.execute("""SELECT COUNT(*) FROM prediction_outcomes o LEFT JOIN predictions p ON p.id = o.prediction_id
                            WHERE p.id IS NULL""").fetchone()[0]
    if orphans:
        problems.append(f"{orphans} outcome(s) whose prediction is gone")
    return {"live_predictions": n, "ok": not problems, "problems": problems[:20]}
