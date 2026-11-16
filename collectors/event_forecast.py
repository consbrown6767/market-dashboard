"""Fast event forecasts: one-off chances for dated events (leadership votes, Fed meetings,
confirmations), written to the prediction ledger before the event and scored against the betting
market's price at the same moment. Run by hand; nothing is scheduled.

Each forecast is a JSON file in docs/event-forecasts/ (kept in git as the evidence):
    {"id": "...", "target": "plain statement that will be true or false",
     "opens_at": "when the event starts (no forecast after this)", "resolves_at": "when the answer is known",
     "who": "claude" (default) or "owner" (the owner's own forecast journal),
     "p": 0.03, "method": "how p was set, by a fixed rule", "sources": [...],
     "market": {"poly_market_id": "...", "note": "how well the market matches the target"}}

    event_forecast.py log docs/event-forecasts/<file>.json      # refused once the event has started
    event_forecast.py due                                       # forecasts waiting for an answer
    event_forecast.py resolve <prediction id> <1|0> "<source>"  # 1 = it happened

Rules (the ledger's, plus two): the chance must come from a written rule and sourced evidence, never
from the market price it's compared with; and the market baseline is the latest stored Polymarket
price at the moment of logging, not one picked by hand.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "MarketData" / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

DB_PATH = Path.home() / "MarketData" / "options.db"
# "who": "owner" in the file logs it to the owner's own forecast journal, scored the same way.
MODELS = {"claude": "event-forecast", "owner": "owner-forecast"}
VERSION = "1"


def market_price(db, market_id: str) -> tuple[float, str]:
    r = db.execute("SELECT price, fetched_at FROM poly_snapshots WHERE market_id = ? ORDER BY fetched_at DESC LIMIT 1",
                   (market_id,)).fetchone()
    if not r or r[0] is None:
        raise SystemExit(f"no stored price for Polymarket market {market_id}")
    return float(r[0]), r[1]


def log(db, path: Path) -> None:
    spec = json.loads(path.read_text())
    price, asof = market_price(db, spec["market"]["poly_market_id"])
    pid = ledger.log(db, model=MODELS[spec.get("who", "claude")], version=VERSION, mode="live", target=spec["target"], kind="probability",
                     opens_at=spec["opens_at"], resolves_at=spec["resolves_at"], forecast={"p": spec["p"]},
                     baselines={"market": {"p": round(price, 4)}, "even": {"p": 0.5}},
                     inputs={"id": spec["id"], "file": f"docs/event-forecasts/{path.name}", "method": spec["method"],
                             "sources": spec.get("sources", []), "market": {**spec["market"], "price_asof": asof}})
    print(f"logged prediction {pid}: {spec['p']:.1%} against the market's {price:.1%} (as of {asof})" if pid
          else "already logged: a forecast is never changed; a new view needs a new target or version")


def main(argv: list[str]) -> None:
    db = sqlite3.connect(DB_PATH, timeout=60)
    ledger.ensure(db)
    if argv[:1] == ["log"] and len(argv) == 2:
        log(db, Path(argv[1]))
    elif argv[:1] == ["due"]:
        for model in MODELS.values():
            for p in ledger.due(db, model):
                print(p["id"], model, p["resolves_at"], p["target"])
    elif argv[:1] == ["resolve"] and len(argv) == 4 and argv[2] in ("0", "1"):
        ledger.resolve(db, int(argv[1]), int(argv[2]), argv[3])
        print("resolved")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
