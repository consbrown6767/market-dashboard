"""Tests for the stock direction model (stock_direction.py): option pricing against a slow exact method,
implied volatility round trips, week blocks, and ranks. Synthetic data, no database or network.

Run from collectors/:  ~/MarketData/.venv/bin/python -m unittest test_stock_direction
"""

import math
import unittest
from datetime import date

import numpy as np
import pandas as pd

import stock_direction as m


def crr_american_put(S, K, T, r, sig, steps=2000):
    """Cox-Ross-Rubinstein binomial tree: slow but exact in the limit."""
    dt = T / steps
    u = math.exp(sig * math.sqrt(dt))
    d = 1 / u
    p = (math.exp(r * dt) - d) / (u - d)
    disc = math.exp(-r * dt)
    prices = S * d ** np.arange(steps, -1, -1) * u ** np.arange(0, steps + 1)
    v = np.maximum(K - prices, 0)
    for i in range(steps, 0, -1):
        prices = prices[1:] / u
        v = np.maximum(disc * (p * v[1:] + (1 - p) * v[:-1]), K - prices)
    return float(v[0])


class Pricing(unittest.TestCase):
    def test_call_matches_black_scholes(self):
        # Textbook value: S=100, K=100, T=1, r=5%, sigma=20% -> 10.4506
        self.assertAlmostEqual(float(m.bs_call(np.array(100.), np.array(100.), np.array(1.), np.array(.05), np.array(.2))),
                               10.4506, places=3)

    def test_american_put_close_to_binomial(self):
        cases = [(100, 100, 30 / 365, 0.045, 0.30), (100, 92, 20 / 365, 0.05, 0.25), (100, 105, 45 / 365, 0.05, 0.35),
                 (100, 85, 55 / 365, 0.04, 0.6), (100, 110, 12 / 365, 0.05, 0.15)]
        for S, K, T, r, sig in cases:
            approx = float(m.american_put(*(np.array(float(x)) for x in (S, K, T, r, sig))))
            exact = crr_american_put(S, K, T, r, sig)
            self.assertLess(abs(approx - exact), 0.005, (S, K, T, r, sig, approx, exact))

    def test_american_put_at_least_european(self):
        S, K, T, r, sig = (np.array(x) for x in (100., 100., 30 / 365, .05, .3))
        european = float(m.bs_call(S, K, T, r, sig) - S + K * np.exp(-r * T))
        self.assertGreaterEqual(float(m.american_put(S, K, T, r, sig)), european)

    def test_implied_vol_round_trip(self):
        rng = np.random.default_rng(3)
        n = 400
        S = np.full(n, 100.0)
        K = rng.uniform(82, 118, n)
        T = rng.uniform(10, 60, n) / 365
        r = rng.uniform(0.03, 0.055, n)
        sig = rng.uniform(0.12, 0.9, n)
        is_call = rng.random(n) < 0.5
        price = np.where(is_call, m.bs_call(S, K, T, r, sig), m.american_put(S, K, T, r, sig))
        exercise = np.maximum(np.where(is_call, S - K * np.exp(-r * T), K - S), 0)
        priced = price - exercise >= m.MIN_TIME_VALUE * price     # the rule compute_iv applies
        iv = m.implied_vol(price[priced], S[priced], K[priced], T[priced], r[priced], is_call[priced])
        self.assertFalse(np.isnan(iv).any())
        self.assertLess(np.max(np.abs(iv - sig[priced])), 1e-6)

    def test_put_iv_from_exact_tree_prices(self):
        # Prices from a 2,000-step tree, priced back through the grid: within 0.1 vol point whenever
        # at least 10% of the price is time value (the rule compute_iv applies).
        worst = 0.0
        for K in (85, 95, 100, 103, 105, 110, 115, 120):
            for T in (10, 30, 60):
                for sig in (0.2, 0.35, 0.6):
                    t, r = T / 365, 0.05
                    price = crr_american_put(100, K, t, r, sig)
                    if price - max(K - 100, 0) < m.MIN_TIME_VALUE * price:
                        continue
                    iv = float(m.implied_vol(*(np.array([x]) for x in (price, 100., float(K), t, r)), np.array([False]))[0])
                    worst = max(worst, abs(iv - sig))
        self.assertLess(worst, 0.001)

    def test_price_below_exercise_value_has_no_iv(self):
        iv = m.implied_vol(np.array([5.0]), np.array([100.]), np.array([110.]), np.array([30 / 365]), np.array([.05]),
                           np.array([False]))
        self.assertTrue(np.isnan(iv[0]))


class Weeks(unittest.TestCase):
    def test_blocks_run_wednesday_to_tuesday(self):
        self.assertEqual(m._block(date(2026, 11, 4)), date(2026, 11, 4))   # Wednesday
        self.assertEqual(m._block(date(2026, 11, 10)), date(2026, 11, 4))  # Tuesday
        self.assertEqual(m._block(date(2026, 11, 11)), date(2026, 11, 11))
        self.assertEqual(m._block(date(2026, 11, 7)), date(2026, 11, 4))   # Saturday

    def test_split_by_outcome_end(self):
        p = pd.DataFrame({"end": [date(2025, 12, 31), date(2026, 1, 7), date(2026, 11, 11), date(2026, 11, 18)], "x": range(4)})
        b, t = m.split(p)
        self.assertEqual(list(b["x"]), [0])
        self.assertEqual(list(t["x"]), [1, 2])


class Ranks(unittest.TestCase):
    def test_ranks_point_the_planned_way(self):
        n = 12
        p = pd.DataFrame({"block": [date(2025, 1, 1)] * n, "stock": [f"S{i}" for i in range(n)],
                          "gap": np.arange(n), "skew": np.arange(n), "dcvol": np.arange(n), "dpvol": np.arange(n),
                          "rel_week": np.arange(n), "excess": 0.0, "y": 0})
        r = m.add_ranks(p).set_index("stock")
        self.assertEqual(r.at["S11", "r_gap"], 1.0)        # biggest call-vs-put gap: most likely to beat
        self.assertEqual(r.at["S11", "r_skew"], 0.0)       # steepest crash protection: least likely
        self.assertEqual(r.at["S11", "r_change"], 0.5)     # calls and puts both rose most: cancels
        self.assertEqual(r.at["S11", "r_rel_week"], 1.0)   # last week's sector-relative winner keeps going

    def test_weeks_with_few_stocks_dropped(self):
        p = pd.DataFrame({"block": [date(2025, 1, 1)] * 5, "stock": list("abcde"), "gap": range(5), "skew": range(5),
                          "dcvol": range(5), "dpvol": range(5), "rel_week": range(5), "excess": 0.0, "y": 0})
        self.assertTrue(m.add_ranks(p).empty)


if __name__ == "__main__":
    unittest.main()
