#!/usr/bin/env python3
"""The raw presidential model: run the 2028 race many times and count who wins.

One simulated race:
  1. Draw the national environment (the generic popular vote margin).
  2. Each candidate decides whether to run. Some defer to a named rival.
  3. Each party's primary runs state by state in five windows (primaries.json). Regions favor
     some lanes, candidates get a home-state boost, and winners gain momentum. Weak candidates
     drop out between windows, and their support goes mostly to candidates in the same lane.
  4. The nominees meet in the general: environment plus each nominee's strength plus noise
     sets the national margin. Every state then votes: its 2024 lean, plus that margin, plus
     regional and state noise, plus a home-state edge. The winner needs 270 electoral votes.

The model never reads market prices. Same inputs and seed always give the same answer.

Usage: python3 model.py
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
RATINGS = HERE / "ratings.json"
STATES = HERE / "states.json"
PRIMARIES = HERE / "primaries.json"

# Two years out, early polls predict little. calibrate.py finds early leaders won about 57% of open
# races: all four who had been VP or president, and 40% of the rest. These two settings split that
# uncertainty between "before voting" and "during voting". Chosen by sweeping values: a 42%-polling
# sitting VP wins about 60% of the time, and early-state winners win the nomination 50-75% of the time.
STRENGTH_SD = 1.0
STAGE_DRIFT = 1.25  # lasting shocks between windows: scandals, debates, endorsements
CONTEST_NOISE = 0.35  # how much one state strays from a candidate's overall strength
HOME_PRIMARY_EDGE = 1.0  # candidates usually run well ahead in their home state's primary
LANE_TRANSFER = 0.8  # how strongly a dropout's support goes to lane-mates
GENERAL_NOISE = 2.0  # campaign and matchup surprises on top of the environment
STATE_NOISE = 2.5  # how far one state strays from the national swing
REGION_NOISE = 1.5  # neighbors tend to stray together
HOME_STATE_EDGE = 2.0
EV_TO_WIN = 270  # a 269-269 tie goes to Republicans here: the House vote by state delegation is too uncertain to model
SIMULATIONS = 20000
SEED = 2028


@dataclass(frozen=True)
class Contest:
    code: str
    weight: int  # electoral votes stand in for delegates
    region: str


@dataclass(frozen=True)
class Stage:
    name: str
    contests: tuple
    survivors: int  # candidates left after this window
    momentum: float  # boost for the window's winner; the runner-up gets a third of it


def load_calendar() -> tuple:
    calendar = json.loads(PRIMARIES.read_text(encoding="utf-8"))
    units = json.loads(STATES.read_text(encoding="utf-8"))["units"]
    weights, regions = Counter(), {}
    for unit in units:  # Maine and Nebraska's districts count toward the state
        code = unit["code"].split("-")[0]
        weights[code] += unit["ev"]
        regions.setdefault(code, unit["region"])
    stages = tuple(Stage(w["name"], tuple(Contest(c, weights[c], regions[c]) for c in w["codes"]), w["survivors"], w["momentum"])
                   for w in calendar["windows"])
    return stages, calendar["lane_region"]


STAGES, LANE_REGION = load_calendar()


@dataclass(frozen=True)
class Candidate:
    id: str
    party: str
    lane: str
    strength: float
    p_run: float
    general: float
    defers_to: str | None = None
    defer_prob: float = 0.0
    home: str | None = None


@dataclass(frozen=True)
class State:
    code: str
    ev: int
    lean: float  # points left of the nation in 2024
    region: str


@dataclass(frozen=True)
class Game:
    candidates: tuple
    env_mean: float
    env_sd: float
    ec_bias: float  # only used when there's no state map, as in small test games
    states: tuple = ()


def load_game(path: Path = RATINGS) -> Game:
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = tuple(Candidate(
        id=c["id"], party=c["party"], lane=c["lane"], strength=math.log(c["poll"] / 10) + c["adj"],
        p_run=c["p_run"], general=c["general"], defers_to=c.get("defers_to"), defer_prob=c.get("defer_prob", 0.0),
        home=c.get("home"),
    ) for c in data["candidates"])
    env = data["national_environment"]
    return Game(candidates, env["mean"], env["sd"], data["electoral_college_bias"], load_states())


def load_states(path: Path = STATES) -> tuple:
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(State(u["code"], u["ev"], u["pres_2024"] - data["national_2024_margin"], u["region"]) for u in data["units"])


def with_changes(game: Game, p_run: dict | None = None, strength_shift: dict | None = None,
                 env_shift: float = 0.0) -> Game:
    """A copy of the game with some candidates' chances changed. Used for turns and what-ifs."""
    p_run, strength_shift = p_run or {}, strength_shift or {}
    # Someone certain to run isn't deferring to anyone.
    changed = tuple(replace(c, p_run=p_run.get(c.id, c.p_run), strength=c.strength + strength_shift.get(c.id, 0.0),
                            defer_prob=0.0 if p_run.get(c.id) == 1.0 else c.defer_prob)
                    for c in game.candidates)
    return replace(game, candidates=changed, env_mean=game.env_mean + env_shift)


def draw_field(rng: random.Random, candidates: list) -> list:
    running = {}
    # Candidates who defer must decide after the person they defer to.
    for c in sorted(candidates, key=lambda c: c.defers_to is not None):
        p = c.p_run * (1 - c.defer_prob) if running.get(c.defers_to) else c.p_run
        running[c.id] = rng.random() < p
    return [c for c in candidates if running[c.id]]


def play_window(rng: random.Random, stage: Stage, active: list, scores: dict, people: dict, delegates: Counter,
                tracker: Counter | None) -> dict:
    """Vote every state in one window. Returns each candidate's share of the window's vote."""
    party = people[active[0]].party
    regional = LANE_REGION.get(party, {})
    window_votes = Counter()
    for contest in stage.contests:
        votes = {}
        for i in active:
            person = people[i]
            score = scores[i] + regional.get(person.lane, {}).get(contest.region, 0) + rng.gauss(0, CONTEST_NOISE)
            if person.home == contest.code:
                score += HOME_PRIMARY_EDGE
            votes[i] = math.exp(score)
        total = sum(votes.values())
        # Democrats split delegates in proportion. Republican rules reward the leader, so squaring
        # the shares is a rough stand-in for winner-take-more states.
        power = 1 if party == "D" else 2
        delegate_total = sum((v / total) ** power for v in votes.values())
        for i, v in votes.items():
            window_votes[i] += contest.weight * v / total
            delegates[i] += contest.weight * (v / total) ** power / delegate_total
        if tracker is not None:
            tracker[("state", contest.code, max(votes, key=votes.get))] += 1
    total_weight = sum(c.weight for c in stage.contests)
    return {i: window_votes[i] / total_weight for i in active}


def run_primary(rng: random.Random, field: list, tracker: Counter | None = None) -> Candidate:
    """Run one party's primary. `tracker` counts who survives each window, if given."""
    people = {c.id: c for c in field}
    scores = {c.id: c.strength + rng.gauss(0, STRENGTH_SD) for c in field}
    delegates = Counter()
    active = list(scores)
    early_winner = None
    for number, stage in enumerate(STAGES):
        if number:
            for i in active:
                scores[i] += rng.gauss(0, STAGE_DRIFT)
        shares = play_window(rng, stage, active, scores, people, delegates, tracker)
        ranked = sorted(active, key=shares.get, reverse=True)
        scores[ranked[0]] += stage.momentum
        if len(ranked) > 1:
            scores[ranked[1]] += stage.momentum / 3
        for dropped in ranked[stage.survivors:]:
            for i in ranked[:stage.survivors]:
                if people[i].lane == people[dropped].lane:
                    scores[i] += LANE_TRANSFER * shares[dropped]
        active = ranked[:stage.survivors]
        if tracker is not None:
            tracker.update((number, i) for i in active)
            if number == 0:
                early_winner = ranked[0]
    nominee = people[max(active, key=lambda i: delegates[i])]
    if tracker is not None:
        tracker[("won_early", early_winner)] += 1
        tracker[("won_early_and_nomination", early_winner)] += nominee.id == early_winner
    return nominee


def electoral_college(rng: random.Random, states: tuple, margin: float, dem: Candidate, rep: Candidate) -> tuple:
    """Vote every state. Returns Democratic electoral votes, each state's margin, and the tipping state."""
    regions = {}
    results = []
    votes = 0
    for s in states:
        if s.region not in regions:
            regions[s.region] = rng.gauss(0, REGION_NOISE)
        result = s.lean + margin + regions[s.region] + rng.gauss(0, STATE_NOISE)
        if s.code == dem.home:
            result += HOME_STATE_EDGE
        if s.code == rep.home:
            result -= HOME_STATE_EDGE
        results.append((result, s))
        if result > 0:
            votes += s.ev
    # The tipping state is the one that takes the winner past 270, counting from their safest.
    results.sort(key=lambda r: r[0], reverse=votes >= EV_TO_WIN)
    running = 0
    tipping = None
    for _, s in results:
        running += s.ev
        if running >= EV_TO_WIN:
            tipping = s.code
            break
    return votes, results, tipping


def simulate(game: Game, runs: int = SIMULATIONS, seed: int = SEED, keep_draws: bool = False) -> dict:
    rng = random.Random(seed)
    dems = [c for c in game.candidates if c.party == "D"]
    reps = [c for c in game.candidates if c.party == "R"]
    ran, nominated, won = Counter(), Counter(), Counter()
    margins, draws, dem_wins = [], [], 0
    state_wins, tipping_states, ev_counts, stages = Counter(), Counter(), Counter(), Counter()
    matchups, matchup_wins = Counter(), Counter()
    split_results = close_margin_total = close_races = 0
    for _ in range(runs):
        environment = rng.gauss(game.env_mean, game.env_sd)
        dem_field, rep_field = draw_field(rng, dems), draw_field(rng, reps)
        ran.update(c.id for c in dem_field + rep_field)
        dem, rep = run_primary(rng, dem_field, stages), run_primary(rng, rep_field, stages)
        nominated.update((dem.id, rep.id))
        margin = environment + dem.general - rep.general + rng.gauss(0, GENERAL_NOISE)
        if game.states:
            votes, results, tipping = electoral_college(rng, game.states, margin, dem, rep)
            dem_won = votes >= EV_TO_WIN
            state_wins.update(s.code for result, s in results if result > 0)
            tipping_states[tipping] += 1
            ev_counts[votes // 10 * 10] += 1
            split_results += (margin > 0) != dem_won
            if abs(votes - EV_TO_WIN) <= 15:
                close_margin_total += margin
                close_races += 1
        else:
            dem_won = margin > game.ec_bias
        dem_wins += dem_won
        won[dem.id if dem_won else rep.id] += 1
        matchups[(dem.id, rep.id)] += 1
        matchup_wins[(dem.id, rep.id)] += dem_won
        margins.append(margin)
        if keep_draws:
            draws.append((environment, margin, dem_won))
    result = {
        "runs": runs, "seed": seed,
        "party": {"D": dem_wins / runs, "R": 1 - dem_wins / runs},
        "ran": {c.id: ran[c.id] / runs for c in game.candidates},
        "nominee_d": {c.id: nominated[c.id] / runs for c in dems},
        "nominee_r": {c.id: nominated[c.id] / runs for c in reps},
        "winner": {c.id: won[c.id] / runs for c in game.candidates},
        "win_if_nominated": {c.id: won[c.id] / nominated[c.id] for c in game.candidates if nominated[c.id] >= runs * 0.01},
        "margin_mean": sum(margins) / runs,
        "states_won": {c.id: sum(v for key, v in stages.items() if key[0] == "state" and key[2] == c.id) / runs
                       for c in game.candidates},
        "primary_states": primary_state_odds(stages, game, runs),
        "matchups": [{"dem": d, "rep": r, "share": count / runs, "dem_win": matchup_wins[(d, r)] / count}
                     for (d, r), count in matchups.most_common(12)],
        "stages": {c.id: {
            "past_early": stages[(0, c.id)] / runs, "past_super": stages[(1, c.id)] / runs,
            "won_early": stages[("won_early", c.id)] / runs,
            "nominee_if_won_early": (stages[("won_early_and_nomination", c.id)] / stages[("won_early", c.id)]
                                     if stages[("won_early", c.id)] >= runs * 0.005 else None),
        } for c in game.candidates},
    }
    if game.states:
        result["electoral"] = {
            "states": {s.code: state_wins[s.code] / runs for s in game.states},
            "tipping": {code: count / runs for code, count in tipping_states.most_common(10)},
            "ev_histogram": {k: v / runs for k, v in sorted(ev_counts.items())},
            "split_result": split_results / runs,
            "bias": close_margin_total / close_races if close_races else None,
        }
    if keep_draws:
        result["draws"] = draws
    return result


def primary_state_odds(stages: Counter, game: Game, runs: int) -> dict:
    """The two likeliest winners of each state's primary, for each party."""
    party_of = {c.id: c.party for c in game.candidates}
    table = {"D": {}, "R": {}}
    for key, count in stages.items():
        if key[0] == "state":
            table[party_of[key[2]]].setdefault(key[1], []).append((key[2], count / runs))
    return {party: {code: sorted(rows, key=lambda r: -r[1])[:2] for code, rows in states.items()}
            for party, states in table.items()}


def what_if_out(game: Game, base: dict, runs: int = 5000, count: int = 4) -> list:
    """Remove each party's likeliest nominees one at a time: who gains, and does the party's
    chance change? This shows how much of the race rests on one player's decision."""
    rows = []
    for market, party in (("nominee_d", "D"), ("nominee_r", "R")):
        top = sorted((c for c in base[market] if not c.startswith("field")), key=base[market].get, reverse=True)[:count]
        for candidate in top:
            result = simulate(with_changes(game, p_run={candidate: 0.0}), runs=runs)
            gains = {c: result[market][c] - base[market][c] for c in result[market] if c != candidate}
            rows.append({"out": candidate, "party": party, "party_odds": result["party"][party],
                         "party_change": result["party"][party] - base["party"][party],
                         "biggest_gainer": max(gains, key=gains.get), "gain": max(gains.values())})
    return rows


def main() -> None:
    game = load_game()
    result = simulate(game)
    print(f"Democrats {result['party']['D']:.1%}, Republicans {result['party']['R']:.1%}, "
          f"average margin D {result['margin_mean']:+.1f}")
    for market in ("nominee_d", "nominee_r", "winner"):
        top = sorted(result[market].items(), key=lambda kv: -kv[1])[:9]
        print(f"\n{market}: " + ", ".join(f"{k} {v:.1%}" for k, v in top))


if __name__ == "__main__":
    main()
