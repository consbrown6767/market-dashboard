"""Checks for the level maths in strategy_collector.py. Run from collectors/: python -m unittest test_strategy_collector"""

import unittest
from datetime import date

import strategy_collector as sc

SHORT_CALLS = sc.DEALER_VIEWS["short_calls_long_puts"]
LONG_CALLS = sc.DEALER_VIEWS["long_calls_short_puts"]


class Walls(unittest.TestCase):
    day = date(2026, 11, 9)

    def test_most_open_interest_across_expirations_in_the_window(self):
        rows = [("2026-11-13", 200, 100, 50), ("2026-11-20", 200, 100, 50), ("2026-11-20", 210, 150, 500)]
        got = sc.walls(rows, self.day, 30)
        self.assertEqual((got["call_wall"], got["call_wall_oi"]), (200, 200))
        self.assertEqual((got["put_wall"], got["put_wall_oi"]), (210, 500))

    def test_ignores_expired_and_far_away_contracts(self):
        rows = [("2026-11-06", 150, 9999, 9999), ("2027-01-15", 300, 9999, 9999), ("2026-11-20", 200, 10, 10)]
        self.assertEqual(sc.walls(rows, self.day, 30)["call_wall"], 200)

    def test_expiring_today_still_counts(self):
        self.assertEqual(sc.walls([("2026-11-09", 190, 10, 10)], self.day, 30)["call_wall"], 190)

    def test_nothing_in_the_window(self):
        self.assertEqual(sc.walls([("2027-06-18", 200, 10, 10)], self.day, 30), {})


class GammaFlip(unittest.TestCase):
    # Calls at 110 and puts at 90 of equal size: call gamma wins high up, put gamma low down.
    contracts = [(True, 110, 0.1, 0.3, 1000), (False, 90, 0.1, 0.3, 1000)]

    def test_flip_sits_between_the_two_piles(self):
        flip = sc.gamma_flip(self.contracts, 100, SHORT_CALLS)
        self.assertGreater(flip, 95)
        self.assertLess(flip, 105)

    def test_the_dealer_view_never_moves_the_flip(self):
        self.assertAlmostEqual(sc.gamma_flip(self.contracts, 100, SHORT_CALLS), sc.gamma_flip(self.contracts, 100, LONG_CALLS))

    def test_the_dealer_view_flips_the_sign(self):
        self.assertAlmostEqual(sc.net_gamma(self.contracts, 105, SHORT_CALLS), -sc.net_gamma(self.contracts, 105, LONG_CALLS))

    def test_short_calls_means_short_gamma_near_the_calls(self):
        self.assertLess(sc.net_gamma(self.contracts, 110, SHORT_CALLS), 0)

    def test_one_sided_positioning_has_no_flip(self):
        self.assertIsNone(sc.gamma_flip([(True, 100, 0.1, 0.3, 1000)], 100, SHORT_CALLS))

    def test_no_contracts(self):
        self.assertIsNone(sc.gamma_flip([], 100, SHORT_CALLS))


if __name__ == "__main__":
    unittest.main()
