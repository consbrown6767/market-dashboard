#!/usr/bin/env python3
"""Turn prices into whole game worlds, so Raw, Market and Weighted are the same game.

Markets price a few things: who wins, who's nominated, who announces, who controls the Senate.
The game needs far more, such as who wins Iowa or what happens if Vance stays out. So this file
goes through three layers, and the dashboard labels every number with the layer it came from:

1. PRICE. A live market price, used as it stands.
2. WORKED OUT. Follows from prices by probability rules alone, with no model involved:
   - Only the leftover total is known for unlisted names, so it's shared out by raw odds.
   - Nobody can win without being nominated, or be nominated without running.
   - Candidate win prices must add up to the party's price, so they're scaled to it.
   - Nominee if running = nominee / running. Kalshi's eight-way market gives House odds under
     each White House result, which are then weighted by the party market.
3. GAME. Everything else. The candidates' numbers are fitted until the game reproduces layers 1
   and 2, then the game's own rules fill in the rest.

Where no market says anything, as with some people's chance of running, the raw number stays
and is labeled as having no market information. Nothing is invented for it.

Only the fitted copies live here. ratings.json and raw forecasts never see any of this.

Usage: run through run_all.py.
"""

from __future__ import annotations

import math
from dataclasses import replace

import blend
import house
import senate
from model import SEED, Game, simulate

FIT_ROUNDS = 14
FIT_RUNS = 10000
CHECK_RUNS = 20000
CHECK_SEED = 4056  # a separate seed, so the check isn't graded on the draws used for fitting
POINTS_PER_LOGIT = 3.5  # about how many points of margin move the win odds by one log-odds unit
MAX_STEP = 1.0  # one noisy round shouldn't throw a candidate far off
MIN_TARGET = 0.0005  # nothing is fitted below this, because a few simulated races can't measure it
MIN_NOMINEE_FOR_GENERAL = 0.01  # below this, win-if-nominated is too noisy to fit
MAX_RUN = 0.99
MAX_IF_RUNS = 0.9  # a price can't imply a near-certain nomination for someone who may not run
MAX_WIN_IF_NOMINATED = 0.95


def logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1 - p))


def clip(value: float) -> float:
    return max(-MAX_STEP, min(MAX_STEP, value))


def pool(raw: float, market: float, weight: float = blend.BLEND_WEIGHT) -> float:
    return 1 / (1 + math.exp(-(weight * logit(raw) + (1 - weight) * logit(market))))


def share_leftover(prices: dict, quoted: set, raw_odds: dict, everyone: list) -> dict:
    """Keep every quoted price. For the rest only the total is known, so split it by raw odds."""
    kept = {c: prices.get(c, 0.0) for c in everyone if c in quoted}
    others = [c for c in everyone if c not in quoted]
    leftover = max(0.0, 1 - sum(kept.values()))
    weights = {c: max(raw_odds.get(c, 0.0), MIN_TARGET) for c in others}
    total = sum(weights.values())
    return {**kept, **{c: leftover * weights[c] / total for c in others}}


def win_targets(prices: dict, quoted: set, nominee: dict, raw: dict, party_d: float, parties: dict) -> dict:
    """Win odds that add up to the party's odds and never exceed the nominee odds."""
    wins = {}
    for c, nominated in nominee.items():
        raw_nominee = raw["nominee_d" if parties[c] == "D" else "nominee_r"].get(c, 0)
        if c in quoted:
            wins[c] = prices.get(c, 0.0)
        elif raw_nominee:
            wins[c] = nominated * raw["winner"].get(c, 0) / raw_nominee
        else:
            wins[c] = 0.0
    for side, odds in (("D", party_d), ("R", 1 - party_d)):
        side_total = sum(v for c, v in wins.items() if parties[c] == side)
        wins.update({c: v * odds / side_total for c, v in wins.items() if parties[c] == side})
    return {c: min(v, MAX_WIN_IF_NOMINATED * nominee[c]) for c, v in wins.items()}


def house_from_power(power: dict, party_d: float) -> float | None:
    """House control from Kalshi's eight-way market. Its own White House total runs well above the
    party market, so only its House odds under each White House result are used, then weighted
    by the party market: P(House) = P(D) P(House | D) + P(R) P(House | R)."""
    labels = {key: power.get(label) for key, label in house.POWER_LABELS.items()}
    if not power or any(v is None for v in labels.values()):
        return None

    def house_given(president: bool) -> float:
        rows = {key: v for key, v in labels.items() if key[0] == president}
        return sum(v for key, v in rows.items() if key[2]) / sum(rows.values())

    return party_d * house_given(True) + (1 - party_d) * house_given(False)


def power_president(power: dict) -> float | None:
    """The chance of a Democratic president that Kalshi's eight-way market adds up to."""
    labels = {key: power.get(label) for key, label in house.POWER_LABELS.items()}
    if not power or any(v is None for v in labels.values()):
        return None
    return sum(v for key, v in labels.items() if key[0]) / sum(labels.values())


def market_targets(game: Game, raw: dict, tables: dict, views: dict, run_prices: dict, senate_price: float | None,
                   house_price: float | None, power: dict) -> dict:
    parties = {c.id: c.party for c in game.candidates}
    quoted = {m: set(views["polymarket"][m]["odds"]) | set(views["kalshi"][m]["odds"]) for m in blend.RAW_MARKETS}
    party_d = tables["party"]["D"]["market"]
    prices = {m: {c: row["market"] for c, row in tables[m].items()} for m in blend.RAW_MARKETS}
    nominee = {}
    for market, side in (("nominee_d", "D"), ("nominee_r", "R")):
        everyone = [c.id for c in game.candidates if c.party == side]
        nominee[market] = share_leftover(prices[market], quoted[market], raw[market], everyone)
    all_nominees = {**nominee["nominee_d"], **nominee["nominee_r"]}
    run = {c: max(min(MAX_RUN, p), all_nominees.get(c, 0) / MAX_IF_RUNS) for c, p in run_prices.items() if c in parties}
    basis = {"run": {c: "price" if c in run else "none" for c in parties},
             "nominee": {c: "price" if c in quoted["nominee_d"] | quoted["nominee_r"] else "share" for c in parties},
             "winner": {c: "scaled" if c in quoted["winner"] else "share" for c in parties},
             "senate": "price" if senate_price is not None else "none",
             "house": "worked out" if house_price is not None else "none"}
    # Worth showing: these are places where the prices themselves can't all be true at once.
    conflicts = {"candidates_d": sum(p for c, p in prices["winner"].items() if parties.get(c) == "D"), "power_d": power_president(power)}
    return {"party_d": party_d, **nominee, "run": run, "senate": senate_price, "house": house_price, "basis": basis,
            "conflicts": conflicts, "winner": win_targets(prices["winner"], quoted["winner"], all_nominees, raw, party_d, parties)}


def weighted_targets(game: Game, raw: dict, market: dict, raw_senate: float, raw_house: float) -> dict:
    """The same log-odds blend the dashboard uses, then the same rules as the market world."""
    parties = {c.id: c.party for c in game.candidates}
    party_d = pool(raw["party"]["D"], market["party_d"])
    nominee = {m: blend.blend_odds(raw[m], market[m]) for m in ("nominee_d", "nominee_r")}
    nominee = {m: {c: v for c, v in odds.items() if c in parties} for m, odds in nominee.items()}
    all_nominees = {**nominee["nominee_d"], **nominee["nominee_r"]}
    run = {c: max(pool(raw["ran"][c], p), all_nominees.get(c, 0) / MAX_IF_RUNS) for c, p in market["run"].items()}
    wins = blend.blend_odds(raw["winner"], market["winner"])
    return {"party_d": party_d, **nominee, "run": run, "basis": market["basis"],
            "senate": None if market["senate"] is None else pool(raw_senate, market["senate"]),
            "house": None if market["house"] is None else pool(raw_house, market["house"]),
            "winner": win_targets(wins, set(all_nominees), all_nominees, raw, party_d, parties)}


def fit_step(game: Game, result: dict, targets: dict, damp: float, runs: int) -> Game:
    """Nudge every candidate toward the targets, then let the mood carry the party total."""
    tiny = 0.5 / runs
    changes, general_moves = {}, {"D": {}, "R": {}}
    for c in game.candidates:
        market = "nominee_d" if c.party == "D" else "nominee_r"
        simulated, wanted = max(result[market].get(c.id, 0), tiny), max(targets[market].get(c.id, 0), MIN_TARGET)
        ran, wanted_run = max(result["ran"].get(c.id, 0), tiny), targets["run"].get(c.id)
        strength = clip(logit(wanted / (wanted_run or ran)) - logit(simulated / ran))
        # A candidate who defers runs less often than their p_run, so correct the outcome, not the input.
        p_run = c.p_run if wanted_run is None else min(1.0, c.p_run * (wanted_run / ran) ** damp)
        changes[c.id] = (c.strength + damp * strength, p_run)
        if result[market].get(c.id, 0) >= MIN_NOMINEE_FOR_GENERAL and targets["winner"].get(c.id, 0) > 0:
            simulated_win = result["winner"].get(c.id, 0) / result[market][c.id]
            wanted_win = targets["winner"][c.id] / wanted
            general_moves[c.party][c.id] = POINTS_PER_LOGIT * clip(logit(wanted_win) - logit(simulated_win))
    moves = {}
    for side, market in (("D", "nominee_d"), ("R", "nominee_r")):
        # Raising a whole party is the mood's job, so each party's moves are centered on zero.
        weights = {c: result[market][c] for c in general_moves[side]}
        center = sum(general_moves[side][c] * w for c, w in weights.items()) / max(sum(weights.values()), tiny)
        moves.update({c: move - center for c, move in general_moves[side].items()})
    fitted = tuple(replace(c, strength=changes[c.id][0], p_run=changes[c.id][1], general=c.general + damp * moves.get(c.id, 0.0))
                   for c in game.candidates)
    mood = POINTS_PER_LOGIT * clip(logit(targets["party_d"]) - logit(result["party"]["D"]))
    return replace(game, candidates=fitted, env_mean=game.env_mean + damp * mood)


def fit_game(game: Game, targets: dict, rounds: int = FIT_ROUNDS, runs: int = FIT_RUNS) -> Game:
    for number in range(rounds):
        # Later rounds take smaller steps, so noise from one round doesn't undo the last.
        damp = 0.8 if number < rounds * 0.6 else 0.35
        game = fit_step(game, simulate(game, runs=runs, seed=SEED + number), targets, damp, runs)
    return game


def solve_shift(measure, target: float, low: float = -15.0, high: float = 15.0, steps: int = 10) -> float:
    """The points to add so that measure(points), which rises with points, reaches the target."""
    for _ in range(steps):
        middle = (low + high) / 2
        low, high = (middle, high) if measure(middle) < target else (low, middle)
    return (low + high) / 2


def down_ballot(result: dict, targets: dict) -> dict:
    """One shift each for the Senate and House, so both reproduce their odds."""
    seat_map, draws = senate.load_map(), result["draws"]
    short = draws[:6000]
    senate_shift = 0.0
    if targets["senate"] is not None:
        senate_shift = solve_shift(lambda s: senate.simulate_senate(seat_map, short, shift=s)["control_d"], targets["senate"])
    seats = senate.simulate_senate(seat_map, draws, shift=senate_shift)
    house_shift = 0.0
    if targets["house"] is not None:
        house_shift = solve_shift(lambda s: house.simulate_house(short, seats["control_by_race"], shift=s)["control_d"], targets["house"])
    lower = house.simulate_house(draws, seats["control_by_race"], shift=house_shift)
    return {"senate_shift": senate_shift, "house_shift": house_shift, "senate_d": seats["control_d"], "house_d": lower["control_d"]}


def people(game: Game) -> dict:
    return {c.id: {"strength": round(c.strength, 4), "p_run": round(c.p_run, 4), "general": round(c.general, 3)} for c in game.candidates}


def fit_report(result: dict, targets: dict, ballot: dict) -> dict:
    """How closely the fitted game reproduces its targets, on a seed it wasn't fitted on."""
    worst = {}
    for market in ("nominee_d", "nominee_r", "winner"):
        worst[market] = max(abs(result[market].get(c, 0) - p) for c, p in targets[market].items())
    worst["run"] = max((abs(result["ran"].get(c, 0) - p) for c, p in targets["run"].items()), default=0)
    return {"worst": worst, "party_d": {"target": targets["party_d"], "game": result["party"]["D"]},
            "senate": {"target": targets["senate"], "game": ballot["senate_d"]},
            "house": {"target": targets["house"], "game": ballot["house_d"]}}


def build_world(game: Game, targets: dict) -> dict:
    fitted = fit_game(game, targets)
    result = simulate(fitted, runs=CHECK_RUNS, seed=CHECK_SEED, keep_draws=True)
    ballot = down_ballot(result, targets)
    return {"env_mean": round(fitted.env_mean, 3), "senate_shift": round(ballot["senate_shift"], 3),
            "house_shift": round(ballot["house_shift"], 3), "people": people(fitted), "targets": targets,
            "fit": fit_report(result, targets, ballot)}


def build_worlds(game: Game, raw: dict, raw_senate: float, raw_house: float, tables: dict, views: dict, run_prices: dict,
                 senate_price: float | None, power: dict) -> dict:
    house_price = house_from_power(power, tables["party"]["D"]["market"])
    market = market_targets(game, raw, tables, views, run_prices, senate_price, house_price, power)
    weighted = weighted_targets(game, raw, market, raw_senate, raw_house)
    return {"raw": {"env_mean": game.env_mean, "senate_shift": 0, "house_shift": 0, "people": people(game)},
            "market": build_world(game, market), "weighted": build_world(game, weighted)}
