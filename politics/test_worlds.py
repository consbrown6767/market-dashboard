"""Tests for worlds.py: gap-filling rules, and whether a fitted world is still the same game."""

import unittest

import house
import worlds
from model import load_game, simulate, with_changes

PARTIES = {"a": "D", "b": "D", "x": "R", "y": "R"}
RAW = {"nominee_d": {"a": 0.5, "b": 0.5}, "nominee_r": {"x": 0.5, "y": 0.5}, "winner": {"a": 0.3, "b": 0.3, "x": 0.2, "y": 0.2}}


class GapFillingTests(unittest.TestCase):
    def test_quoted_prices_stay_and_only_the_leftover_is_shared(self):
        result = worlds.share_leftover({"a": 0.6}, {"a"}, {"b": 0.3, "c": 0.1}, ["a", "b", "c"])
        self.assertEqual(result["a"], 0.6)
        self.assertAlmostEqual(result["b"], 0.3)
        self.assertAlmostEqual(result["c"], 0.1)

    def test_win_odds_add_up_to_the_party_price(self):
        nominee = {"a": 0.5, "b": 0.5, "x": 0.5, "y": 0.5}
        wins = worlds.win_targets({"a": 0.2, "b": 0.2, "x": 0.3, "y": 0.3}, {"a", "b", "x", "y"}, nominee, RAW, 0.6, PARTIES)
        self.assertAlmostEqual(wins["a"] + wins["b"], 0.6)
        self.assertAlmostEqual(wins["x"] + wins["y"], 0.4)

    def test_nobody_wins_more_often_than_they_are_nominated(self):
        nominee = {"a": 0.1, "b": 0.9, "x": 0.5, "y": 0.5}
        wins = worlds.win_targets({"a": 0.3, "b": 0.3, "x": 0.2, "y": 0.2}, {"a", "b", "x", "y"}, nominee, RAW, 0.6, PARTIES)
        self.assertLess(wins["a"], nominee["a"])

    def test_unquoted_win_odds_use_the_raw_chance_if_nominated(self):
        nominee = {"a": 0.2, "b": 0.8, "x": 0.5, "y": 0.5}
        wins = worlds.win_targets({"b": 0.48, "x": 0.2, "y": 0.2}, {"b", "x", "y"}, nominee, RAW, 0.6, PARTIES)
        self.assertAlmostEqual(wins["a"], 0.12 * 0.6 / 0.6)  # 0.2 nominee times raw 60% if nominated

    def test_house_uses_kalshi_conditionals_weighted_by_the_party_price(self):
        power = {label: 0.0 for label in house.POWER_LABELS.values()}
        power["Democratic Sweep"] = 0.8  # House always Democratic if the president is
        power["R-House, R-Senate, D-President"] = 0.0
        power["D-House, R-Senate, R-President"] = 0.1  # half the time if the president is Republican
        power["Republican Sweep"] = 0.1
        self.assertAlmostEqual(worlds.house_from_power(power, 0.6), 0.6 * 1.0 + 0.4 * 0.5)
        self.assertAlmostEqual(worlds.power_president(power), 0.8)

    def test_missing_power_market_means_no_answer_rather_than_a_guess(self):
        self.assertIsNone(worlds.house_from_power({}, 0.6))
        self.assertIsNone(worlds.power_president({}))

    def test_pool_lands_between_its_inputs_and_nearer_the_market(self):
        self.assertTrue(0.3 < worlds.pool(0.7, 0.3) < 0.5)


class FitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = load_game()
        # A hidden "true" game, so the fit has targets it can reach exactly.
        cls.hidden = with_changes(cls.game, p_run={"jd-vance": 0.7}, env_shift=-1.0,
                                  strength_shift={"gavin-newsom": 0.6, "jon-ossoff": -0.5})
        truth = simulate(cls.hidden, runs=20000)
        cls.truth = truth
        cls.targets = {"party_d": truth["party"]["D"], "nominee_d": truth["nominee_d"], "nominee_r": truth["nominee_r"],
                       "winner": truth["winner"], "run": {"jd-vance": truth["ran"]["jd-vance"]}}
        cls.fitted = worlds.fit_game(cls.game, cls.targets, rounds=10, runs=6000)
        cls.result = simulate(cls.fitted, runs=20000, seed=99)

    def test_fit_reproduces_the_targets(self):
        self.assertAlmostEqual(self.result["party"]["D"], self.truth["party"]["D"], delta=0.02)
        self.assertAlmostEqual(self.result["ran"]["jd-vance"], self.truth["ran"]["jd-vance"], delta=0.02)
        for market in ("nominee_d", "nominee_r", "winner"):
            for name, odds in self.truth[market].items():
                self.assertAlmostEqual(self.result[market].get(name, 0), odds, delta=0.025, msg=name)

    def test_a_fitted_world_is_the_same_game(self):
        same = [(c.id, c.party, c.lane, c.home, c.defers_to, c.defer_prob) for c in self.game.candidates]
        self.assertEqual([(c.id, c.party, c.lane, c.home, c.defers_to, c.defer_prob) for c in self.fitted.candidates], same)
        self.assertEqual(self.fitted.states, self.game.states)
        self.assertEqual(self.fitted.env_sd, self.game.env_sd)

    def test_unpriced_chances_of_running_are_left_alone(self):
        before = {c.id: c.p_run for c in self.game.candidates}
        for c in self.fitted.candidates:
            if c.id != "jd-vance":
                self.assertEqual(c.p_run, before[c.id])

    def test_declaring_ends_any_deferring(self):
        game = with_changes(self.game, p_run={"marco-rubio": 1.0})
        self.assertAlmostEqual(simulate(game, runs=3000)["ran"]["marco-rubio"], 1.0)


if __name__ == "__main__":
    unittest.main()
