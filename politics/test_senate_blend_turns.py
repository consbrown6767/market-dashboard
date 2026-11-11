"""Tests for senate.py, blend.py and turns.py, using small made-up cases."""

import tempfile
import unittest
from pathlib import Path

import house
import turns
from blend import align_to_model, blend_odds
from model import Candidate, Game, load_game
from senate import dem_controls, load_map, rating, simulate_senate


def tiny_map(not_up_d=50, lean=0.0):
    return {"national_2024_margin": 0.0, "not_up_in_2028": {"D": not_up_d, "R": 49}, "uncalled_2026": {"seats": []},
            "seats": [{"code": "AA", "state": "A", "party": "D", "pres_2024": lean, "edge": 0}]}


class SenateTests(unittest.TestCase):
    def test_tie_goes_to_the_vice_presidents_party(self):
        self.assertTrue(dem_controls(50, True))
        self.assertFalse(dem_controls(50, False))
        self.assertTrue(dem_controls(51, False))

    def test_ratings(self):
        self.assertEqual([rating(p) for p in (0.99, 0.5, 0.01)], ["Safe D", "Toss-up", "Safe R"])

    def test_very_blue_seat_is_safe(self):
        result = simulate_senate(tiny_map(lean=40), [(0, 0, False)] * 500)
        self.assertEqual(result["seats"][0]["p_dem"], 1)
        self.assertEqual(result["control_d"], 1)

    def test_environment_moves_seats(self):
        bad = simulate_senate(tiny_map(), [(-10, -10, False)] * 500)["seats"][0]["p_dem"]
        good = simulate_senate(tiny_map(), [(10, 10, True)] * 500)["seats"][0]["p_dem"]
        self.assertLess(bad, good)

    def test_real_map_adds_up_to_100_senators(self):
        data = load_map()
        total = sum(data["not_up_in_2028"].values()) + len(data["uncalled_2026"]["seats"]) + len(data["seats"])
        self.assertEqual(total, 100)

    def test_no_state_is_listed_twice(self):
        codes = [s["code"] for s in load_map()["seats"]]
        self.assertEqual(len(codes), len(set(codes)))


class HouseTests(unittest.TestCase):
    def test_good_environment_wins_the_house(self):
        draws = [(15, 15, True)] * 200
        result = house.simulate_house(draws, [True] * 200)
        self.assertEqual(result["control_d"], 1)
        self.assertEqual(result["outcomes"]["Democratic Sweep"], 1)

    def test_all_eight_outcomes_add_up_to_100(self):
        draws = [(e, e, e > 0) for e in range(-20, 20)] * 20
        result = house.simulate_house(draws, [e[2] for e in draws])
        self.assertAlmostEqual(sum(result["outcomes"].values()), 1)
        self.assertEqual(len(house.POWER_LABELS), 8)


class BlendTests(unittest.TestCase):
    raw, market = {"a": 0.6, "b": 0.4}, {"a": 0.2, "b": 0.8}

    def test_weight_zero_is_the_market(self):
        self.assertAlmostEqual(blend_odds(self.raw, self.market, 0)["a"], 0.2)

    def test_weight_one_is_the_model(self):
        self.assertAlmostEqual(blend_odds(self.raw, self.market, 1)["a"], 0.6)

    def test_blend_lands_in_between_and_sums_to_100(self):
        result = blend_odds(self.raw, self.market, 0.25)
        self.assertTrue(0.2 < result["a"] < 0.6)
        self.assertAlmostEqual(sum(result.values()), 1)

    def test_unrated_names_and_the_gap_go_to_the_field(self):
        view = {"nominee_d": {"odds": {"a": 0.5, "unrated": 0.3}, "unlisted": 0.2}}
        aligned = align_to_model(view, "nominee_d", {"a", "field-d"}, {})
        self.assertEqual(aligned["a"], 0.5)
        self.assertAlmostEqual(aligned["field-d"], 0.5)


class TurnTests(unittest.TestCase):
    game = Game((Candidate("a", "D", "x", 0.0, 0.5, 0.0), Candidate("b", "R", "x", 0.0, 1.0, 0.0)), 0.0, 5.0, 0.0)

    def test_status_and_multiplier_and_environment_all_apply(self):
        turn = {"changes": {"multipliers": {"b": 2.0}, "statuses": {"a": "running"}, "env_shift": 1.5}}
        result = turns.apply_turns(self.game, [turn])
        self.assertEqual(result.candidates[0].p_run, 1.0)
        self.assertGreater(result.candidates[1].strength, 0.6)
        self.assertEqual(result.env_mean, 1.5)

    def test_turns_stack(self):
        out = {"changes": {"multipliers": {}, "statuses": {"a": "out"}, "env_shift": 1.0}}
        result = turns.apply_turns(self.game, [out, out])
        self.assertEqual((result.candidates[0].p_run, result.env_mean), (0.0, 2.0))

    def test_oversized_multiplier_is_refused(self):
        with self.assertRaises(SystemExit):
            turns.check_changes(self.game, {"a": 5.0}, {})

    def test_unknown_candidate_is_refused(self):
        with self.assertRaises(SystemExit):
            turns.check_changes(self.game, {}, {"nobody": "out"})

    def test_empty_log_means_the_starting_ratings(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = turns.current_game(Path(tmp) / "none.jsonl")
        self.assertEqual(current, load_game())


if __name__ == "__main__":
    unittest.main()
