#!/usr/bin/env python3
"""A simple House model, so the whole federal ballot can be compared with Kalshi's POWER-28.

This does not simulate 435 districts. It turns the national vote into seats with a straight
line: Democrats get SEATS_PER_POINT more seats for each point above the margin they need for a
majority. The House vote follows the environment, pulled partway toward the presidential result.

Usage: run through run_all.py.
"""

from __future__ import annotations

import random
from collections import Counter

from model import SEED

MAJORITY = 218
SEATS_PER_POINT = 6.5  # rough recent swing: one point of national vote is about 6-7 seats
MAJORITY_MARGIN = 1.5  # national margin Democrats need for 218, because of map geometry
TICKET_EFFECT = 0.5  # House votes follow the top of the ticket more than Senate races do
HOUSE_VOTE_NOISE = 2.0
SEAT_NOISE = 6.0

# Kalshi's labels for each president / Senate / House outcome.
POWER_LABELS = {
    (True, True, True): "Democratic Sweep", (False, False, False): "Republican Sweep",
    (False, True, True): "D-House, D-Senate, R-President", (False, True, False): "R-House, D-Senate, R-President",
    (False, False, True): "D-House, R-Senate, R-President", (True, True, False): "R-House, D-Senate, D-President",
    (True, False, True): "D-House, R-Senate, D-President", (True, False, False): "R-House, R-Senate, D-President",
}


def dem_seats(rng: random.Random, environment: float, margin: float, shift: float = 0.0) -> int:
    house_vote = environment + TICKET_EFFECT * (margin - environment) + shift + rng.gauss(0, HOUSE_VOTE_NOISE)
    seats = MAJORITY + SEATS_PER_POINT * (house_vote - MAJORITY_MARGIN) + rng.gauss(0, SEAT_NOISE)
    return max(0, min(435, round(seats)))


def simulate_house(draws: list, senate_control: list, seed: int = SEED, shift: float = 0.0) -> dict:
    """draws: (environment, margin, dem_president) per race. senate_control: True per race if Democratic.
    shift adds points to the House vote. Only the market and weighted worlds use it."""
    rng = random.Random(seed + 2)
    outcomes, seats_total, dem_house = Counter(), 0, 0
    for (environment, margin, dem_president), dem_senate in zip(draws, senate_control):
        seats = dem_seats(rng, environment, margin, shift)
        seats_total += seats
        controls = seats >= MAJORITY
        dem_house += controls
        outcomes[POWER_LABELS[(bool(dem_president), bool(dem_senate), controls)]] += 1
    runs = len(draws)
    return {"control_d": dem_house / runs, "dem_seats_mean": seats_total / runs,
            "outcomes": {label: outcomes[label] / runs for label in POWER_LABELS.values()}}
