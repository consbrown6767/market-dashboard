#!/usr/bin/env python3
"""The 2028 Senate map: simulate every seat in the same worlds as the presidential model.

Each seat's Democratic margin is:
    state lean (2024 result vs the nation) + national environment + incumbent edge + noise

Every seat shares the same environment in a given simulated race, so seats tend to swing
together. Sharing it with the presidential race also gives joint odds such as a Democratic
sweep. Seats stay independent of market prices, which are only compared afterwards.

Usage: python3 senate.py
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from model import SEED, SIMULATIONS, load_game, simulate

HERE = Path(__file__).resolve().parent
SEATS = HERE / "senate_seats.json"
SNAPSHOTS = HERE / "data" / "senate" / "snapshots.jsonl"

# Candidate quality and local surprises in one race. calibrate.py measures about 5-6 points on
# real 2022 and 2024 races. This adds a little because 2028's candidates aren't known yet, and
# because 2026 produced flips in states well to the right of the nation.
SEAT_NOISE = 6.5
TICKET_EFFECT = 0.25  # how much of the presidential matchup carries down the ballot
FLOOR_PRICE = 0.08  # where long-dated Kalshi prices seem to bottom out in safe states
THIN_SPREAD = 0.10  # a market this wide is too thin to treat as a real price


def load_map(path: Path = SEATS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rating(p_dem: float) -> str:
    if p_dem >= 0.95:
        return "Safe D"
    if p_dem >= 0.85:
        return "Likely D"
    if p_dem >= 0.65:
        return "Lean D"
    if p_dem > 0.35:
        return "Toss-up"
    if p_dem > 0.15:
        return "Lean R"
    if p_dem > 0.05:
        return "Likely R"
    return "Safe R"


def dem_controls(dem_seats: int, dem_president: bool) -> bool:
    # At 50-50 the vice president breaks ties, so the White House decides control.
    return dem_seats >= 51 or (dem_seats == 50 and dem_president)


def simulate_senate(senate_map: dict, draws: list, seed: int = SEED, shift: float = 0.0) -> dict:
    """shift adds points to every seat. Only the market and weighted worlds use it."""
    rng = random.Random(seed + 1)
    seats = senate_map["seats"]
    national = senate_map["national_2024_margin"]
    lean = [s["pres_2024"] - national for s in seats]
    edge = [s["edge"] if s["party"] == "D" else -s["edge"] for s in seats]
    p_open = [s.get("p_open", 0) for s in seats]
    dem_wins, totals = [0] * len(seats), Counter()
    control = sweep = rep_sweep = control_given_d = control_given_r = president_d = 0
    control_by_race = []
    for environment, margin, dem_president in draws:
        ticket_environment = environment + TICKET_EFFECT * (margin - environment)
        total = senate_map["not_up_in_2028"]["D"]
        total += sum(rng.random() < s["p_dem"] for s in senate_map["uncalled_2026"]["seats"])
        for i in range(len(seats)):
            # An open seat has no incumbent, so the sitting party loses its edge.
            advantage = 0 if rng.random() < p_open[i] else edge[i]
            if lean[i] + advantage + ticket_environment + shift + rng.gauss(0, SEAT_NOISE) > 0:
                dem_wins[i] += 1
                total += 1
        totals[total] += 1
        controls = dem_controls(total, dem_president)
        control_by_race.append(controls)
        control += controls
        sweep += controls and dem_president
        rep_sweep += not controls and not dem_president
        president_d += dem_president
        control_given_d += controls and dem_president
        control_given_r += controls and not dem_president
    runs = len(draws)
    seat_rows = []
    for seat, wins in zip(seats, dem_wins):
        p_dem = wins / runs
        seat_rows.append({**seat, "p_dem": p_dem, "rating": rating(p_dem),
                          "flip": p_dem > 0.5 if seat["party"] == "R" else p_dem < 0.5})
    return {
        "seats": seat_rows,
        "control_by_race": control_by_race,
        "control_d": control / runs,
        "dem_seats_mean": sum(k * v for k, v in totals.items()) / runs,
        "dem_seats": {k: v / runs for k, v in sorted(totals.items())},
        "sweep_d": sweep / runs,
        "sweep_r": rep_sweep / runs,
        "control_if_d_president": control_given_d / max(president_d, 1),
        "control_if_r_president": control_given_r / max(runs - president_d, 1),
    }


def midpoint(row: dict) -> float | None:
    if row.get("yes_bid") is None or row.get("yes_ask") is None:
        return None
    return (row["yes_bid"] + row["yes_ask"]) / 2


def latest_markets(path: Path = SNAPSHOTS) -> dict:
    """The newest snapshot as simple numbers: Democratic odds per state, plus control."""
    if not path.exists():
        return {}
    snapshot = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    states = {}
    for code, rows in snapshot["kalshi_states"].items():
        for row in rows:
            if str(row["label"]).startswith("Democratic") and midpoint(row) is not None:
                states[code] = {"p_dem": midpoint(row), "thin": row["yes_ask"] - row["yes_bid"] >= THIN_SPREAD}

    def democratic(rows):
        return next((midpoint(r) for r in rows if str(r["label"]).startswith("Democratic")), None)

    seat_rows = snapshot["kalshi_national"].get("KXDSENATESEATS-29", [])
    power = snapshot["kalshi_national"].get("POWER-28", [])
    return {
        "power": {r["label"]: midpoint(r) for r in power},
        "fetched_at": snapshot["fetched_at"], "states": states,
        "control_kalshi": democratic(snapshot["kalshi_national"].get("CONTROLS-2028", [])),
        "control_polymarket": democratic(snapshot["polymarket"]),
        "above_56": next((midpoint(r) for r in seat_rows if r["label"] == "Above 56"), None),
        "sweep_d": next((midpoint(r) for r in power if r["label"] == "Democratic Sweep"), None),
        "sweep_r": next((midpoint(r) for r in power if r["label"] == "Republican Sweep"), None),
    }


def market_seat_check(result: dict, markets: dict, senate_map: dict) -> dict:
    """Do Kalshi's state prices add up to its seat-count market? States with no market use the
    model. Prices are also shown with a floor removed, because long-dated prices rarely go below
    about 8% even in safe states, which pulls the total toward the middle."""
    floor = FLOOR_PRICE
    base = senate_map["not_up_in_2028"]["D"] + sum(s["p_dem"] for s in senate_map["uncalled_2026"]["seats"])
    raw_total = adjusted_total = base
    for seat in result["seats"]:
        market = markets.get("states", {}).get(seat["code"])
        price = market["p_dem"] if market else seat["p_dem"]
        raw_total += price
        adjusted_total += min(1, max(0, (price - floor) / (1 - 2 * floor))) if market else price
    return {"from_state_prices": raw_total, "floor_removed": adjusted_total, "model": result["dem_seats_mean"]}


def run(game=None, runs: int = SIMULATIONS) -> dict:
    president = simulate(game or load_game(), runs=runs, keep_draws=True)
    return simulate_senate(load_map(), president["draws"])


def main() -> None:
    result, markets = run(), latest_markets()
    result.pop("control_by_race")
    above_56 = sum(v for k, v in result["dem_seats"].items() if k > 56)
    print(f"Democratic control {result['control_d']:.1%} (Kalshi {markets.get('control_kalshi')}, "
          f"Polymarket {markets.get('control_polymarket')})")
    print(f"Average Democratic seats {result['dem_seats_mean']:.1f}; above 56 {above_56:.1%} (Kalshi {markets.get('above_56')})")
    print(f"Democratic sweep of White House and Senate {result['sweep_d']:.1%}")
    print(f"Control if Democrats win White House {result['control_if_d_president']:.1%}, "
          f"if Republicans do {result['control_if_r_president']:.1%}\n")
    print("Seat              Now  Model   Kalshi  Rating")
    for s in sorted(result["seats"], key=lambda s: abs(s["p_dem"] - 0.5)):
        market = markets.get("states", {}).get(s["code"])
        price = f"{market['p_dem']:6.0%}{'*' if market['thin'] else ' '}" if market else "    -- "
        print(f"{s['state'][:17]:17} {s['party']}  {s['p_dem']:6.0%}  {price} {s['rating']}{'  FLIP' if s['flip'] else ''}")


if __name__ == "__main__":
    main()
