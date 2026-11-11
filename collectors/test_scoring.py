"""Tests for scoring.py. Run: python3 -m unittest test_scoring"""

import itertools
import unittest
from datetime import date, datetime, time, timedelta

from scoring import (
    Bar, EventKind, GradeStatus, SectorData, StockDay, evaluate_day, grade_prediction,
)

DAY = date(2026, 10, 21)
WALL = 100.0
BAR_VOLUME_NORMAL = 1000.0
# 20-day average cumulative volume: 1000 per bar, keyed by bar end time
BASELINE = {
    (datetime.combine(DAY, time(9, 30)) + timedelta(minutes=5 * k)).time(): BAR_VOLUME_NORMAL * k
    for k in range(1, 79)
}


def make_bars(closes, volume=2000.0, start=time(9, 35), day=DAY, open_=None):
    first = datetime.combine(day, start)
    return [Bar(first + timedelta(minutes=5 * i), open_ or c, c, volume) for i, c in enumerate(closes)]


def sector(up=True, n=78):
    # opens at 100 (= previous close), then trades at 101 (up) or 99 (down)
    return SectorData(prev_close=100.0, bars=make_bars([101.0 if up else 99.0] * n, volume=0, open_=100.0))


def stock_day(closes, volume=2000.0, sector_up=True, gamma_flip=95.0, shorts=None, prev_close=99.0, bars=None):
    return StockDay(
        symbol="TEST", prev_close=prev_close, bars=bars or make_bars(closes, volume),
        call_wall=WALL, gamma_flip=gamma_flip, avg_cum_volume=BASELINE,
        sector=sector(sector_up) if sector_up is not None else None, shorts_crowded=shorts,
    )


# 3 bars below, break at bar 4 (09:50), hold through bar 10 (10:20)
BREAK_AND_HOLD = [99.0] * 3 + [101.0] * 7


class CombinationTable(unittest.TestCase):
    def test_every_combination(self):
        # (volume ok, sector up, above gamma flip) -> prediction iff volume and score >= 1
        for v, s, g in itertools.product([True, False], repeat=3):
            with self.subTest(volume=v, sector=s, gamma=g):
                day = stock_day(
                    BREAK_AND_HOLD, volume=2000.0 if v else 1200.0,
                    sector_up=s, gamma_flip=95.0 if g else 105.0,
                )
                [event] = evaluate_day(day).events
                self.assertEqual(event.score, int(s) + int(g))
                expected = EventKind.PREDICTION if v and (s or g) else EventKind.NO_PREDICTION
                self.assertEqual(event.kind, expected)
                self.assertEqual(event.strong, expected is EventKind.PREDICTION and s and g)

    def test_volume_plus_shorts_is_a_prediction(self):
        day = stock_day(BREAK_AND_HOLD, sector_up=False, gamma_flip=105.0, shorts=True)
        [event] = evaluate_day(day).events
        self.assertEqual(event.kind, EventKind.PREDICTION)
        self.assertEqual(event.score, 1)

    def test_all_three_points_is_strong(self):
        [event] = evaluate_day(stock_day(BREAK_AND_HOLD, shorts=True)).events
        self.assertEqual(event.score, 3)
        self.assertTrue(event.strong)

    def test_volume_exactly_1_5x_fails(self):
        [event] = evaluate_day(stock_day(BREAK_AND_HOLD, volume=1500.0)).events
        self.assertAlmostEqual(event.volume_ratio, 1.5)
        self.assertEqual(event.kind, EventKind.NO_PREDICTION)

    def test_missing_volume_baseline_means_no_prediction(self):
        day = stock_day(BREAK_AND_HOLD)
        day = StockDay(**{**day.__dict__, "avg_cum_volume": {}})
        [event] = evaluate_day(day).events
        self.assertEqual(event.kind, EventKind.NO_PREDICTION)
        self.assertIsNone(event.volume_ratio)

    def test_missing_data_is_noted_and_scores_zero(self):
        day = stock_day(BREAK_AND_HOLD, sector_up=None, gamma_flip=None)
        [event] = evaluate_day(day).events
        self.assertEqual(event.score, 0)
        self.assertIn("no sector data", event.notes)
        self.assertIn("no gamma flip", event.notes)
        self.assertIn("no short-interest data", event.notes)


class HoldAndTiming(unittest.TestCase):
    def test_decision_is_made_at_end_of_hold(self):
        [event] = evaluate_day(stock_day(BREAK_AND_HOLD)).events
        self.assertEqual(event.breakout_time.time(), time(9, 50))
        self.assertEqual(event.decision_time.time(), time(10, 20))

    def test_fall_back_during_hold_then_rebreak_qualifies(self):
        closes = [99.0] * 3 + [101.0, 101.0, 99.5] + [101.0] * 7
        events = evaluate_day(stock_day(closes)).events
        self.assertEqual([e.kind for e in events], [EventKind.FAILED_HOLD, EventKind.PREDICTION])
        self.assertEqual(events[0].decision_time.time(), time(10, 0))

    def test_close_exactly_at_wall_does_not_fail_hold(self):
        closes = [99.0] * 3 + [101.0, 100.0] + [101.0] * 5
        [event] = evaluate_day(stock_day(closes)).events
        self.assertEqual(event.kind, EventKind.PREDICTION)

    def test_hold_still_in_progress(self):
        result = evaluate_day(stock_day([99.0] * 3 + [101.0] * 4))
        self.assertEqual(result.events, [])
        self.assertEqual(result.holding_since.end.time(), time(9, 50))

    def test_breakout_bar_ending_1530_counts(self):
        # bar 72 ends at 15:30, then 6 hold bars to 16:00
        [event] = evaluate_day(stock_day([99.0] * 71 + [101.0] * 7)).events
        self.assertEqual(event.breakout_time.time(), time(15, 30))
        self.assertEqual(event.decision_time.time(), time(16, 0))

    def test_breakout_after_1530_ignored(self):
        # break on the 15:35 bar
        result = evaluate_day(stock_day([99.0] * 72 + [101.0] * 6))
        self.assertEqual(result.events, [])
        self.assertIsNone(result.holding_since)

    def test_gap_up_through_wall_counts_as_breakout(self):
        [event] = evaluate_day(stock_day([101.0] * 7, prev_close=99.0)).events
        self.assertEqual(event.breakout_time.time(), time(9, 35))

    def test_already_above_wall_is_not_a_breakout(self):
        result = evaluate_day(stock_day([101.0] * 10, prev_close=101.0))
        self.assertEqual(result.events, [])

    def test_one_prediction_per_day(self):
        closes = BREAK_AND_HOLD + [99.0] + [101.0] * 7
        events = evaluate_day(stock_day(closes)).events
        self.assertEqual([e.kind for e in events], [EventKind.PREDICTION])

    def test_non_qualifying_hold_needs_new_break_to_retry(self):
        # low-volume first break, then volume surges and a second break qualifies
        bars = make_bars(BREAK_AND_HOLD, volume=1000.0) + make_bars(
            [99.0] + [101.0] * 7, volume=6000.0, start=time(10, 25))
        events = evaluate_day(stock_day(None, bars=bars)).events
        self.assertEqual([e.kind for e in events], [EventKind.NO_PREDICTION, EventKind.PREDICTION])

    def test_extended_hours_bars_ignored(self):
        premarket = make_bars([105.0] * 3, start=time(9, 0))
        bars = premarket + make_bars(BREAK_AND_HOLD)
        [event] = evaluate_day(stock_day(None, bars=bars)).events
        self.assertEqual(event.breakout_time.time(), time(9, 50))


class Grading(unittest.TestCase):
    def setUp(self):
        [self.pred] = evaluate_day(stock_day(BREAK_AND_HOLD)).events
        self.close = datetime.combine(DAY, time(16, 0))

    def test_held_to_close(self):
        after = make_bars([102.0] * 69, start=time(10, 25))
        grade = grade_prediction(self.pred, after, self.close)
        self.assertEqual(grade.status, GradeStatus.HELD)
        self.assertAlmostEqual(grade.pct_move, (102 / 101 - 1) * 100)

    def test_close_below_wall_is_wrong_even_if_it_recovers(self):
        after = make_bars([102.0] * 10 + [99.0] + [105.0] * 58, start=time(10, 25))
        grade = grade_prediction(self.pred, after, self.close)
        self.assertEqual(grade.status, GradeStatus.WRONG)
        self.assertEqual(grade.broke_below_at.time(), time(11, 15))

    def test_pending_before_checkpoint(self):
        after = make_bars([102.0] * 5, start=time(10, 25))
        self.assertEqual(grade_prediction(self.pred, after, self.close).status, GradeStatus.PENDING)

    def test_next_day_checkpoint(self):
        nxt = DAY + timedelta(days=1)
        after = make_bars([102.0] * 69, start=time(10, 25)) + make_bars([104.0] * 78, day=nxt)
        grade = grade_prediction(self.pred, after, datetime.combine(nxt, time(16, 0)))
        self.assertEqual(grade.status, GradeStatus.HELD)
        self.assertEqual(grade.price, 104.0)


if __name__ == "__main__":
    unittest.main()
