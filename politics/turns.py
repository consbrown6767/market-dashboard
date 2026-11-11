#!/usr/bin/env python3
"""The game log. Each turn is one piece of news or one change in who's in the race.

Write the multiplier BEFORE looking at how markets moved, so your judgment stays independent.
A multiplier of 1.3 means "this news is 1.3 times more likely if this person ends up winning."
It's applied to the candidate's strength, so it moves their odds roughly, not exactly, by that factor.

Usage:
  python3 turns.py add --headline "Newsom forms exploratory committee" --source https://... \\
                       --status gavin-newsom=running --multiplier jon-ossoff=1.2 --env 0.5
  python3 turns.py list

Statuses: running (chance of running becomes 100%), out (chance becomes 0%).
--env moves the national environment, in points toward Democrats.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import blend
import forecasts
from model import Game, load_game, simulate, with_changes

HERE = Path(__file__).resolve().parent
TURNS = HERE / "data" / "turns.jsonl"

MULTIPLIER_MIN, MULTIPLIER_MAX = 0.5, 2.0
PHASES = ("Shadow primary", "Declared field", "Early states", "Super Tuesday and later", "Conventions", "General election")


def parse_pairs(pairs: list | None) -> dict:
    return dict(pair.split("=", 1) for pair in pairs or [])


def check_changes(game: Game, multipliers: dict, statuses: dict) -> None:
    known = {c.id for c in game.candidates}
    for name in [*multipliers, *statuses]:
        if name not in known:
            raise SystemExit(f"Unknown candidate id: {name} (see ratings.json)")
    for name, value in multipliers.items():
        if not MULTIPLIER_MIN <= value <= MULTIPLIER_MAX:
            raise SystemExit(f"{name}: ordinary news is capped between {MULTIPLIER_MIN}x and {MULTIPLIER_MAX}x")
    for name, status in statuses.items():
        if status not in ("running", "out"):
            raise SystemExit(f"{name}: status must be running or out")


def apply_turns(game: Game, turns: list) -> Game:
    """The game as it stands after every logged turn."""
    for turn in turns:
        changes = turn["changes"]
        p_run = {name: 1.0 if status == "running" else 0.0 for name, status in changes["statuses"].items()}
        shift = {name: math.log(value) for name, value in changes["multipliers"].items()}
        game = with_changes(game, p_run=p_run, strength_shift=shift, env_shift=changes["env_shift"])
    return game


def current_game(path: Path = TURNS) -> Game:
    return apply_turns(load_game(), forecasts.read_log(path))


def odds_summary(tables: dict) -> dict:
    """Compact numbers to store with a turn, for the odds-by-turn chart."""
    return {market: {name: {k: round(row[k], 4) for k in ("raw", "market", "blend")} for name, row in table.items()}
            for market, table in tables.items()}


def add_turn(headline: str, source: str, multipliers: dict, statuses: dict, env_shift: float, phase: int,
             path: Path = TURNS, views: dict | None = None) -> dict:
    game = current_game(path)
    check_changes(game, multipliers, statuses)
    changes = {"multipliers": multipliers, "statuses": statuses, "env_shift": env_shift}
    updated = apply_turns(game, [{"changes": changes}])
    tables = blend.build_tables(simulate(updated), views or blend.market_views())
    return forecasts.chain_append(path, {"at": forecasts.now_utc(), "phase": PHASES[phase], "headline": headline,
                                         "source": source, "changes": changes, "odds": odds_summary(tables)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a turn or list the game so far.")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("--headline", required=True)
    add.add_argument("--source", default="")
    add.add_argument("--multiplier", action="append", help="candidate-id=1.2")
    add.add_argument("--status", action="append", help="candidate-id=running or candidate-id=out")
    add.add_argument("--env", type=float, default=0.0)
    add.add_argument("--phase", type=int, default=0, help=f"0-{len(PHASES) - 1}")
    commands.add_parser("list")
    args = parser.parse_args()

    if args.command == "list":
        for turn in forecasts.read_log(TURNS):
            print(f"{turn['seq']:>3} {turn['at'][:10]} [{turn['phase']}] {turn['headline']}")
        return
    multipliers = {k: float(v) for k, v in parse_pairs(args.multiplier).items()}
    turn = add_turn(args.headline, args.source, multipliers, parse_pairs(args.status), args.env, args.phase)
    print(f"Logged turn {turn['seq']}. Democrats: raw {turn['odds']['party']['D']['raw']:.1%}, "
          f"market {turn['odds']['party']['D']['market']:.1%}, blend {turn['odds']['party']['D']['blend']:.1%}")


if __name__ == "__main__":
    main()
