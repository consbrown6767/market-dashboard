"""Tests for game_theory.py on small fields where the direction of the answer is known."""

import unittest

from game_theory import entry_shocks, lane_pressure, nomination_chance, respond, vp_scores
from model import Candidate, Game


def person(id, lane="a", strength=0.0, p_run=0.5, general=0.0, party="D"):
    return Candidate(id=id, party=party, lane=lane, strength=strength, p_run=p_run, general=general)


TRIO = [person("big", strength=1.0, p_run=0.8), person("rival", p_run=0.4), person("other", lane="b", p_run=0.4)]


class EntryTests(unittest.TestCase):
    def test_todays_odds_are_already_a_resting_point(self):
        settled = respond(TRIO, {})
        for c in TRIO:
            self.assertAlmostEqual(settled[c.id], c.p_run, places=3)

    def test_rival_is_likelier_to_run_when_the_favorite_is_out(self):
        self.assertGreater(respond(TRIO, {"big": 0.0})["rival"], 0.4)

    def test_lane_mate_gains_more_than_someone_elsewhere(self):
        after = respond(TRIO, {"big": 0.0})
        self.assertGreater(after["rival"] - 0.4, after["other"] - 0.4)

    def test_settled_decision_is_not_changed(self):
        self.assertEqual(respond(TRIO, {"big": 0.0})["big"], 0.0)

    def test_field_candidate_never_changes(self):
        field = [*TRIO, person("field-d", p_run=1.0)]
        self.assertEqual(respond(field, {"big": 0.0})["field-d"], 1.0)

    def test_shock_lists_the_biggest_responses_first(self):
        game = Game(tuple(TRIO), 0, 5, 0)
        responses = entry_shocks(game, ["big"])[0]["responses"]
        self.assertEqual(responses[0]["id"], "rival")


class LaneTests(unittest.TestCase):
    def test_stronger_rivals_lower_my_chance(self):
        me = TRIO[1]
        weak = nomination_chance(me, TRIO, {"big": 0.0, "rival": 1.0, "other": 1.0})
        strong = nomination_chance(me, TRIO, {"big": 1.0, "rival": 1.0, "other": 1.0})
        self.assertGreater(weak, strong)

    def test_leader_gains_when_the_chaser_exits(self):
        game = Game(tuple(TRIO), 0, 5, 0)
        row = lane_pressure(game, {"big": 0.5, "rival": 0.2})[0]
        self.assertEqual((row["leader"], row["chaser"]), ("big", "rival"))
        self.assertGreater(row["leader_gain_if_chaser_exits"], 0)


class VpTests(unittest.TestCase):
    def test_pick_from_another_lane_beats_an_equal_lane_mate(self):
        game = Game(tuple(TRIO), 0, 5, 0)
        picks = vp_scores(game, {"nominee_d": {"big": 0.9}, "nominee_r": {}}, nominees_per_party=1)[0]["picks"]
        self.assertEqual(picks[0]["id"], "other")


if __name__ == "__main__":
    unittest.main()
