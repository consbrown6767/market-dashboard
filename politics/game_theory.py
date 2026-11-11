#!/usr/bin/env python3
"""The strategic layer: the decisions where players really do react to each other.

1. ENTRY. Whether to run depends on who else runs. Each candidate's payoff is their rough
   nomination chance minus a personal cost. Costs are solved so that today's p_run values are
   already an equilibrium, which adds no new opinions about who wants to run. The game then
   answers one question: when one player's decision changes, how do the others respond?

2. CONSOLIDATION. Two candidates in a lane can split its voters. Staying is better for each
   unless their own chance falls below what they'd get by exiting, such as a VP slot or cabinet
   post. That is a prisoner's-dilemma shape, and it shows which lanes are under pressure.

3. VP PICK. Each likely nominee picks the running mate who helps the ticket most.

Everything uses a quick formula, not the full simulation, so these are rough and meant
for comparing choices. Results are only applied to the model in explicit what-if scenarios.

Usage: python3 game_theory.py
"""

from __future__ import annotations

import math

from model import Game, load_game, simulate, with_changes

SENSITIVITY = 8.0  # how sharply entry responds to payoffs; higher means more rational players
SAME_LANE_WEIGHT = 1.5  # a rival in your lane hurts more than one elsewhere
EXIT_VALUE = 0.05  # what a graceful exit is worth, as if it were this chance of the nomination
ITERATIONS = 200
SWING_STATE_PEOPLE = {"josh-shapiro", "jon-ossoff", "mark-kelly", "gretchen-whitmer", "ruben-gallego", "raphael-warnock",
                      "brian-kemp", "marco-rubio", "ron-desantis", "glenn-youngkin"}


def logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def nomination_chance(me, party: list, entry: dict) -> float:
    """Rough chance of winning the nomination if I run, given everyone else's chance of running."""
    rivals = sum(entry[c.id] * math.exp(c.strength) * (SAME_LANE_WEIGHT if c.lane == me.lane else 1.0)
                 for c in party if c.id != me.id)
    return math.exp(me.strength) / (math.exp(me.strength) + rivals)


def solve_costs(party: list) -> dict:
    """The personal costs that make the current p_run values a resting point."""
    entry = {c.id: c.p_run for c in party}
    return {c.id: nomination_chance(c, party, entry) - logit(c.p_run) / SENSITIVITY for c in party}


def respond(party: list, fixed: dict) -> dict:
    """Everyone re-decides until no one wants to change. `fixed` holds decisions already made."""
    costs = solve_costs(party)
    entry = {c.id: fixed.get(c.id, c.p_run) for c in party}
    for _ in range(ITERATIONS):
        for c in party:
            if c.id not in fixed and not c.id.startswith("field"):
                target = sigmoid(SENSITIVITY * (nomination_chance(c, party, entry) - costs[c.id]))
                entry[c.id] += 0.5 * (target - entry[c.id])  # half-steps stop the updates oscillating
    return entry


def entry_shocks(game: Game, players: list, decision: float = 0.0) -> list:
    """If each named player's decision is settled, who else changes their mind?"""
    rows = []
    for player in players:
        me = next(c for c in game.candidates if c.id == player)
        party = [c for c in game.candidates if c.party == me.party]
        after = respond(party, {player: decision})
        moves = sorted(((c.id, after[c.id] - c.p_run) for c in party if c.id != player and not c.id.startswith("field")),
                       key=lambda kv: -abs(kv[1]))[:3]
        rows.append({"player": player, "party": me.party, "decision": "in" if decision else "out",
                     "responses": [{"id": i, "before": next(c.p_run for c in party if c.id == i), "change": d} for i, d in moves],
                     "new_p_run": after})
    return rows


def strategic_what_if(game: Game, shock: dict, base: dict, runs: int = 5000) -> dict:
    """Compare a simple what-if (others don't react) with a strategic one (they do)."""
    party = [c for c in game.candidates if c.party == shock["party"]]
    simple = simulate(with_changes(game, p_run={shock["player"]: 0.0 if shock["decision"] == "out" else 1.0}), runs=runs)
    strategic = simulate(with_changes(game, p_run={c.id: shock["new_p_run"][c.id] for c in party}), runs=runs)
    side = shock["party"]
    return {"simple": simple["party"][side] - base["party"][side], "strategic": strategic["party"][side] - base["party"][side]}


def lane_pressure(game: Game, nominee_odds: dict) -> list:
    """For the two strongest players in each lane: is either better off leaving?"""
    rows = []
    for party_code in ("D", "R"):
        party = [c for c in game.candidates if c.party == party_code and not c.id.startswith("field")]
        for lane in sorted({c.lane for c in party}):
            mates = sorted((c for c in party if c.lane == lane), key=lambda c: -nominee_odds.get(c.id, 0))[:2]
            if len(mates) < 2:
                continue
            first, second = mates
            everyone_in = {c.id: 1.0 if c.id in (first.id, second.id) else c.p_run for c in party}
            stay = nomination_chance(second, party, everyone_in)
            leader_alone = nomination_chance(first, party, {**everyone_in, second.id: 0.0})
            leader_split = nomination_chance(first, party, everyone_in)
            rows.append({"party": party_code, "lane": lane, "leader": first.id, "chaser": second.id,
                         "chaser_chance": stay, "leader_gain_if_chaser_exits": leader_alone - leader_split,
                         "chaser_should_exit": stay < EXIT_VALUE})
    return rows


def vp_scores(game: Game, nominee_odds: dict, nominees_per_party: int = 2, picks: int = 3) -> list:
    """Best running mates for each likely nominee: electability, balance, and a swing state."""
    rows = []
    for party_code, market in (("D", "nominee_d"), ("R", "nominee_r")):
        party = [c for c in game.candidates if c.party == party_code and not c.id.startswith("field")]
        leaders = sorted(party, key=lambda c: -nominee_odds[market].get(c.id, 0))[:nominees_per_party]
        for nominee in leaders:
            options = []
            for mate in party:
                if mate.id == nominee.id:
                    continue
                score = 0.3 * mate.general + (0.3 if mate.lane != nominee.lane else 0)
                score += 0.4 if mate.id in SWING_STATE_PEOPLE else 0
                options.append({"id": mate.id, "score": round(score, 2)})
            rows.append({"nominee": nominee.id, "party": party_code,
                         "picks": sorted(options, key=lambda o: -o["score"])[:picks]})
    return rows


def main() -> None:
    game = load_game()
    base = simulate(game)
    players = ["kamala-harris", "gavin-newsom", "alexandria-ocasio-cortez", "jon-ossoff", "jd-vance", "marco-rubio"]
    print("If this player is OUT, who changes their mind?")
    for shock in entry_shocks(game, players):
        moves = ", ".join(f"{r['id']} {r['before']:.0%} {r['change']:+.0%}" for r in shock["responses"])
        print(f"  {shock['player']:26} {moves}")
    print("\nLane pressure")
    for row in lane_pressure(game, {**base["nominee_d"], **base["nominee_r"]}):
        print(f"  {row['party']} {row['lane']:14} {row['leader']} / {row['chaser']}: chaser {row['chaser_chance']:.0%}, "
              f"leader gains {row['leader_gain_if_chaser_exits']:+.0%} if chaser exits")
    print("\nVP picks")
    for row in vp_scores(game, base):
        print(f"  {row['nominee']:26} " + ", ".join(p["id"] for p in row["picks"]))


if __name__ == "__main__":
    main()
