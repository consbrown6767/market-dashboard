"""Tests for backfill_history.py, using made-up candles."""

import unittest

from backfill_history import candle_quote, daily_points, hourly_rows

CANDLE = {"end_period_ts": 1793854800, "yes_bid": {"close_dollars": "0.2100"}, "yes_ask": {"close_dollars": "0.2200"}}
EMPTY = {"end_period_ts": 1793858400, "yes_bid": {}, "yes_ask": {"close_dollars": "0.2200"}}
MARKET = {"event": "KXPRESPERSON-28", "ticker": "T", "label": "Jon Ossoff"}


class CandleTests(unittest.TestCase):
    def test_reads_closing_quotes(self):
        self.assertEqual(candle_quote(CANDLE), (0.21, 0.22))

    def test_an_empty_side_gives_nothing(self):
        self.assertEqual(candle_quote(EMPTY), (None, None))

    def test_hourly_rows_match_the_live_format_and_skip_empty_hours(self):
        rows = hourly_rows(MARKET, [CANDLE, EMPTY])
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {"fetched_at", "event_ticker", "ticker", "label", "yes_bid", "yes_ask"})

    def test_daily_points_use_the_midpoint(self):
        self.assertEqual(list(daily_points([CANDLE]).values()), [0.215])


if __name__ == "__main__":
    unittest.main()
