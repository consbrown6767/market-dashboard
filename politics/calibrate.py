#!/usr/bin/env python3
"""Check the Senate model's settings against real 2022 and 2024 races.

For each race: how far did the result land from what state lean plus the national environment
predicted? The spread of those misses is what SEAT_NOISE should be. Incumbents' average
overperformance is the typical `edge`.

Data: history_senate.csv, extracted from Wikipedia. Races without a normal D-vs-R contest
(Alaska and Utah in 2022, Maine, Nebraska and Vermont in 2024) are left out. The 2022 check uses
2024 state leans, which is an approximation.

It also checks how often early primary poll leaders won, against what the model gives today's
leaders. history_primaries.csv is from memory: "early leader" means roughly two years out, and
some of those calls are debatable, so treat the rate as a rough base rate.

Usage: python3 calibrate.py
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from model import simulate
from turns import current_game

HERE = Path(__file__).resolve().parent
ENVIRONMENT = {2022: -2.8, 2024: -2.7}  # national House vote margin, D minus R, from memory
COMPETITIVE = 25  # races in states further from the middle than this behave differently


def races() -> list:
    states = json.loads((HERE / "states.json").read_text(encoding="utf-8"))
    leans = {u["code"]: u["pres_2024"] - states["national_2024_margin"] for u in states["units"]}
    rows = []
    with open(HERE / "history_senate.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            year, lean = int(row["year"]), leans[row["state"]]
            rows.append({**row, "lean": lean, "miss": float(row["dem_margin"]) - lean - ENVIRONMENT[year]})
    return rows


def signed_edge(row: dict) -> float:
    return row["miss"] if row["incumbent_party"] == "D" else -row["miss"]


def summary(rows: list) -> dict:
    incumbents = [r for r in rows if r["incumbent_running"] == "Y"]
    edge = statistics.mean(signed_edge(r) for r in incumbents)
    residuals = [r["miss"] - (edge if r["incumbent_party"] == "D" else -edge) if r["incumbent_running"] == "Y" else r["miss"]
                 for r in rows]
    return {"races": len(rows), "incumbent_edge": edge, "noise": statistics.pstdev(residuals)}


def primary_base_rate() -> dict:
    with open(HERE / "history_primaries.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    veterans = [r for r in rows if r["sitting_or_former_vp_or_president"] == "Y"]
    others = [r for r in rows if r["sitting_or_former_vp_or_president"] == "N"]

    def rate(group):
        return sum(r["won_nomination"] == "Y" for r in group) / len(group)

    return {"races": len(rows), "all": rate(rows), "veterans": rate(veterans), "veteran_races": len(veterans),
            "others": rate(others), "other_races": len(others)}


def model_poll_leaders() -> dict:
    game = current_game()
    result = simulate(game)
    ratings = json.loads((HERE / "ratings.json").read_text(encoding="utf-8"))["candidates"]
    leaders = {}
    for party, market in (("D", "nominee_d"), ("R", "nominee_r")):
        leader = max((c for c in ratings if c["party"] == party), key=lambda c: c["poll"])
        leaders[leader["id"]] = result[market][leader["id"]]
    return leaders


def main() -> None:
    rows = races()
    competitive = [r for r in rows if abs(r["lean"]) <= COMPETITIVE]
    for label, group in (("all races", rows), (f"lean within {COMPETITIVE}", competitive)):
        result = summary(group)
        print(f"{label:18} races {result['races']:3}  incumbent edge {result['incumbent_edge']:+.1f}  noise {result['noise']:.1f}")
    rate = primary_base_rate()
    print(f"\nEarly primary leaders won {rate['all']:.0%} of {rate['races']} open races: "
          f"{rate['veterans']:.0%} of {rate['veteran_races']} who had been VP or president, "
          f"{rate['others']:.0%} of {rate['other_races']} others.")
    print("The model gives today's poll leaders: " + ", ".join(f"{k} {v:.0%}" for k, v in model_poll_leaders().items()))


if __name__ == "__main__":
    main()
