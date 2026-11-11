"""Tests for venue_check.py on made-up prices with known behavior."""

import unittest

from venue_check import paired_days, slope, summarize


class VenueTests(unittest.TestCase):
    def test_slope(self):
        self.assertAlmostEqual(slope([1, 2, 3], [2, 4, 6]), 2)

    def test_pairs_need_both_venues(self):
        days = {f"2026-01-{d:02}": 0.1 for d in range(1, 11)}
        markets = {"m": {"a": {"polymarket": days, "kalshi": {"2026-01-01": 0.2}}}}
        self.assertEqual(paired_days(markets), [])

    def test_polymarket_following_kalshi_is_detected(self):
        # Polymarket fully catches up to Kalshi every time, and Kalshi doesn't move.
        rows = [(0.2, 0.2 + g, 0.2 + g, 0.2 + g) for g in (0.02, 0.05, -0.03, -0.06, 0.04)]
        result = summarize(rows)
        self.assertAlmostEqual(result["polymarket_follows"], 1)
        self.assertAlmostEqual(result["kalshi_follows"], 0)
        self.assertAlmostEqual(result["gap_left_after"], 0)


if __name__ == "__main__":
    unittest.main()
