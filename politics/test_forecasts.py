"""Tests for forecasts.py, using made-up forecasts in a temporary folder."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forecasts import add_forecast, brier_by_source, chain_append, gap_results, read_log, record_gap, verify_log


class ChainTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "log.jsonl"
        for prob in (0.1, 0.2, 0.3):
            add_forecast("q", prob, "raw", "2027-12-31", path=self.path)

    def test_intact_log_verifies(self):
        self.assertIsNone(verify_log(self.path))

    def test_edited_entry_is_found(self):
        lines = self.path.read_text().splitlines()
        entry = json.loads(lines[1])
        entry["prob"] = 0.9
        lines[1] = json.dumps(entry)
        self.path.write_text("\n".join(lines) + "\n")
        self.assertEqual(verify_log(self.path), 2)

    def test_deleted_entry_is_found(self):
        lines = self.path.read_text().splitlines()
        self.path.write_text("\n".join([lines[0], lines[2]]) + "\n")
        self.assertEqual(verify_log(self.path), 2)

    def test_bad_probability_is_refused(self):
        with self.assertRaises(ValueError):
            add_forecast("q", 1.2, "raw", "2027-12-31", path=self.path)


class BrierTests(unittest.TestCase):
    def test_perfect_and_coin_flip_scores(self):
        forecasts = [{"question": "a", "prob": 1.0, "source": "good"}, {"question": "a", "prob": 0.5, "source": "flip"}]
        result = brier_by_source(forecasts, [{"question": "a", "outcome": True}])
        self.assertEqual(result["good"]["brier"], 0)
        self.assertEqual(result["flip"]["brier"], 0.25)

    def test_only_the_latest_forecast_counts(self):
        forecasts = [{"question": "a", "prob": 0.0, "source": "raw"}, {"question": "a", "prob": 1.0, "source": "raw"}]
        result = brier_by_source(forecasts, [{"question": "a", "outcome": True}])
        self.assertEqual(result["raw"], {"brier": 0, "questions": 1})

    def test_unresolved_questions_are_left_out(self):
        self.assertEqual(brier_by_source([{"question": "a", "prob": 0.5, "source": "raw"}], []), {})


class GapTests(unittest.TestCase):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def gap(self, raw=0.3, market=0.2):
        return {"at": self.start.isoformat(), "market": "m", "candidate": "c", "raw": raw, "market_price": market}

    def test_the_same_gap_twice_in_a_day_counts_once(self):
        result = gap_results([self.gap(), self.gap()], lambda *_: 0.25, self.start + timedelta(days=8))
        self.assertEqual(result[7]["toward"], 1)

    def test_small_gaps_are_not_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(record_gap("m", "c", 0.21, 0.2, path=Path(tmp) / "g.jsonl"))

    def test_market_moving_toward_raw_counts_as_toward(self):
        result = gap_results([self.gap()], lambda *_: 0.25, self.start + timedelta(days=8))
        self.assertEqual(result[7]["toward"], 1)

    def test_market_moving_away_counts_as_away(self):
        result = gap_results([self.gap()], lambda *_: 0.15, self.start + timedelta(days=8))
        self.assertEqual(result[7]["away"], 1)

    def test_checkpoints_not_reached_are_skipped(self):
        result = gap_results([self.gap()], lambda *_: 0.25, self.start + timedelta(days=8))
        self.assertEqual(sum(result[30].values()), 0)

    def test_missing_prices_are_counted(self):
        result = gap_results([self.gap()], lambda *_: None, self.start + timedelta(days=8))
        self.assertEqual(result[7]["no_data"], 1)


if __name__ == "__main__":
    unittest.main()
