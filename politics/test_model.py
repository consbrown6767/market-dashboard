"""Tests for model.py on simple games where the right answer is known."""

import json
import random
import unittest
from pathlib import Path

from model import Candidate, Game, State, draw_field, electoral_college, load_game, load_states, simulate, with_changes


def person(id, party="D", strength=0.0, p_run=1.0, general=0.0, lane="a", **extra):  # noqa
    return Candidate(id=id, party=party, lane=lane, strength=strength, p_run=p_run, general=general, **extra)


def game(*candidates, env_mean=0.0, env_sd=5.0, ec_bias=0.0):
    return Game(candidates, env_mean, env_sd, ec_bias)


BASIC = (person("d1"), person("r1", party="R"))


class ModelTests(unittest.TestCase):
    def test_one_candidate_per_party_wins_every_nomination(self):
        result = simulate(game(*BASIC), runs=200)
        self.assertEqual(result["nominee_d"]["d1"], 1)
        self.assertEqual(result["nominee_r"]["r1"], 1)

    def test_even_race_is_about_even(self):
        self.assertAlmostEqual(simulate(game(*BASIC), runs=4000)["party"]["D"], 0.5, delta=0.03)

    def test_same_seed_gives_the_same_answer(self):
        self.assertEqual(simulate(game(*BASIC), runs=300), simulate(game(*BASIC), runs=300))

    def test_nominee_odds_add_up_to_100(self):
        field = (person("d1"), person("d2", strength=1.0), person("d3", p_run=0.5), person("r1", party="R"))
        self.assertAlmostEqual(sum(simulate(game(*field), runs=500)["nominee_d"].values()), 1)

    def test_stronger_candidate_wins_more_often(self):
        field = (person("weak"), person("strong", strength=1.5), person("r1", party="R"))
        result = simulate(game(*field), runs=2000)
        self.assertGreater(result["nominee_d"]["strong"], result["nominee_d"]["weak"])

    def test_candidate_who_is_out_never_wins(self):
        field = (person("in"), person("out", p_run=0.0), person("r1", party="R"))
        self.assertEqual(simulate(game(*field), runs=300)["winner"]["out"], 0)

    def test_better_environment_helps_democrats(self):
        low = simulate(game(*BASIC, env_mean=-3), runs=2000)["party"]["D"]
        high = simulate(game(*BASIC, env_mean=3), runs=2000)["party"]["D"]
        self.assertGreater(high, low)

    def test_electoral_college_bias_hurts_democrats(self):
        fair = simulate(game(*BASIC), runs=2000)["party"]["D"]
        biased = simulate(game(*BASIC, ec_bias=2), runs=2000)["party"]["D"]
        self.assertLess(biased, fair)

    def test_deferring_candidate_stays_out_when_rival_runs(self):
        leader = person("leader")
        follower = person("follower", p_run=1.0, defers_to="leader", defer_prob=1.0)
        rng = random.Random(1)
        ids = [c.id for c in draw_field(rng, [follower, leader])]
        self.assertEqual(ids, ["leader"])

    def test_with_changes_leaves_the_original_alone(self):
        original = game(*BASIC)
        changed = with_changes(original, p_run={"d1": 0.0}, strength_shift={"r1": 1.0}, env_shift=2.0)
        self.assertEqual(original.candidates[0].p_run, 1.0)
        self.assertEqual(changed.candidates[0].p_run, 0.0)
        self.assertEqual(changed.candidates[1].strength, 1.0)
        self.assertEqual(changed.env_mean, 2.0)


class ElectoralCollegeTests(unittest.TestCase):
    states = (State("A", 300, 0.0, "x"), State("B", 238, 0.0, "x"))

    def test_real_map_adds_up_to_538(self):
        self.assertEqual(sum(s.ev for s in load_states()), 538)

    def test_blowout_wins_every_state(self):
        votes, _, tipping = electoral_college(random.Random(1), self.states, 100, person("d"), person("r"))
        self.assertEqual((votes, tipping), (538, "A"))

    def test_home_state_edge_helps_its_candidate(self):
        plain = simulate(game(*BASIC, ec_bias=0), runs=1)
        with_home = (person("d1", home="A"), person("r1", party="R"))
        state_game = Game(with_home, 0.0, 5.0, 0.0, self.states)
        neutral_game = Game(BASIC, 0.0, 5.0, 0.0, self.states)
        self.assertGreater(simulate(state_game, runs=3000)["party"]["D"], simulate(neutral_game, runs=3000)["party"]["D"])
        self.assertNotIn("electoral", plain)

    def test_state_map_results_are_reported(self):
        result = simulate(Game(BASIC, 0.0, 5.0, 0.0, self.states), runs=200)["electoral"]
        self.assertEqual(set(result["states"]), {"A", "B"})
        self.assertAlmostEqual(sum(result["ev_histogram"].values()), 1)


class RatingsFileTests(unittest.TestCase):
    def test_every_rated_person_is_in_the_candidate_table(self):
        known = {c["id"] for c in json.loads(Path("candidates.json").read_text(encoding="utf-8"))}
        rated = {c.id for c in load_game().candidates if not c.id.startswith("field")}
        self.assertEqual(rated - known, set())

    def test_defers_to_names_a_real_candidate(self):
        ids = {c.id for c in load_game().candidates}
        for c in load_game().candidates:
            if c.defers_to:
                self.assertIn(c.defers_to, ids)


if __name__ == "__main__":
    unittest.main()
