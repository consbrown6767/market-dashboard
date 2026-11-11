"""Checks for the prediction ledger. Run from collectors/: python -m unittest test_ledger"""

import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest import mock

import ledger

T0 = datetime(2026, 11, 9, 17, 0, tzinfo=ledger.ET)
RANGE = {"q": {"0.05": -1.5, "0.25": -0.5, "0.5": 0.0, "0.75": 0.5, "0.95": 1.5}}
WIDE = {"q": {"0.05": -3.0, "0.25": -1.0, "0.5": 0.0, "0.75": 1.0, "0.95": 3.0}}


def fresh() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    ledger.ensure(db)
    return db


def at(t):
    return mock.patch.object(ledger, "_now", return_value=t)


def log_live(db, target, forecast=RANGE, baselines=None, kind="quantiles", now=T0, opens=None):
    with at(now):
        return ledger.log(db, model="m", version="1", mode="live", target=target, kind=kind,
                          opens_at=opens or now + timedelta(hours=16), resolves_at=now + timedelta(hours=23),
                          forecast=forecast, baselines={"wide": WIDE} if baselines is None else baselines)


class Writing(unittest.TestCase):
    def test_live_prediction_is_stamped_and_chained(self):
        db = fresh()
        a, b = log_live(db, "day 1"), log_live(db, "day 2")
        rows = db.execute("SELECT id, made_at, prev_hash, hash FROM predictions ORDER BY id").fetchall()
        self.assertEqual([r[0] for r in rows], [a, b])
        self.assertEqual(rows[0][1], "2026-11-09T17:00:00-05:00")
        self.assertIsNone(rows[0][2])
        self.assertEqual(rows[1][2], rows[0][3])

    def test_refuses_a_prediction_after_its_window_opens(self):
        with self.assertRaisesRegex(ValueError, "too late"):
            log_live(fresh(), "day 1", opens=T0 - timedelta(minutes=1))

    def test_live_predictions_cannot_be_backdated(self):
        with self.assertRaisesRegex(ValueError, "stamped"):
            ledger.log(fresh(), model="m", version="1", mode="live", target="x", kind="quantiles", made_at=T0,
                       opens_at=T0 + timedelta(hours=1), resolves_at=T0 + timedelta(hours=2), forecast=RANGE, baselines={"w": WIDE})

    def test_needs_a_baseline_and_a_sane_forecast(self):
        with self.assertRaisesRegex(ValueError, "baseline"):
            log_live(fresh(), "x", baselines={})
        with self.assertRaisesRegex(ValueError, "rise"):
            log_live(fresh(), "x", forecast={"q": {"0.05": 1.0, "0.95": -1.0}})
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            log_live(fresh(), "x", kind="probability", forecast={"p": 1.2}, baselines={"half": {"p": 0.5}})

    def test_same_target_twice_is_skipped_not_overwritten(self):
        db = fresh()
        first = log_live(db, "day 1")
        self.assertIsNone(log_live(db, "day 1", forecast=WIDE))
        self.assertEqual(db.execute("SELECT forecast FROM predictions WHERE id = ?", (first,)).fetchone()[0],
                         ledger._json(RANGE))

    def test_cannot_resolve_early_or_twice(self):
        db = fresh()
        pid = log_live(db, "day 1")
        with at(T0 + timedelta(hours=1)), self.assertRaisesRegex(ValueError, "before"):
            ledger.resolve(db, pid, 0.3, "test")
        with at(T0 + timedelta(days=1)):
            self.assertEqual([p["id"] for p in ledger.due(db, "m")], [pid])
            ledger.resolve(db, pid, 0.3, "test")
            self.assertEqual(ledger.due(db, "m"), [])
            with self.assertRaisesRegex(ValueError, "already"):
                ledger.resolve(db, pid, 0.4, "test")

    def test_clearing_a_backtest_leaves_live_rows(self):
        db = fresh()
        log_live(db, "day 1")
        for i in range(3):
            made = T0 - timedelta(days=10 - i)
            pid = ledger.log(db, model="m", version="1", mode="backtest", target=f"past {i}", kind="quantiles", made_at=made,
                             opens_at=made + timedelta(hours=16), resolves_at=made + timedelta(hours=23),
                             forecast=RANGE, baselines={"wide": WIDE})
            ledger.resolve(db, pid, 0.1, "test")
        self.assertEqual(ledger.clear_backtest(db, "m", "1"), 3)
        self.assertEqual(db.execute("SELECT mode, COUNT(*) FROM predictions GROUP BY mode").fetchall(), [("live", 1)])
        self.assertTrue(ledger.verify(db)["ok"])


class TamperCheck(unittest.TestCase):
    def setUp(self):
        self.db = fresh()
        self.ids = [log_live(self.db, f"day {i}") for i in range(3)]
        with at(T0 + timedelta(days=1)):
            ledger.resolve(self.db, self.ids[0], 0.2, "test")

    def test_clean_chain_passes(self):
        self.assertEqual(ledger.verify(self.db), {"live_predictions": 3, "ok": True, "problems": []})

    def test_changed_forecast_is_caught(self):
        self.db.execute("UPDATE predictions SET forecast = ? WHERE id = ?", (ledger._json(WIDE), self.ids[1]))
        self.assertIn("contents changed", " ".join(ledger.verify(self.db)["problems"]))

    def test_removed_row_is_caught(self):
        self.db.execute("DELETE FROM predictions WHERE id = ?", (self.ids[1],))
        self.assertIn("doesn't follow", " ".join(ledger.verify(self.db)["problems"]))

    def test_changed_outcome_is_caught(self):
        self.db.execute("UPDATE prediction_outcomes SET outcome = 9 WHERE prediction_id = ?", (self.ids[0],))
        self.assertIn("outcome of prediction", " ".join(ledger.verify(self.db)["problems"]))


class Scoring(unittest.TestCase):
    def test_brier(self):
        self.assertAlmostEqual(ledger.brier({"p": 0.7}, 1), 0.09)
        self.assertAlmostEqual(ledger.brier({"p": 0.5}, 0), 0.25)

    def test_pinball(self):
        # Median 0, outcome 1: loss 0.5 at the median. 90% level at 2, outcome 1: (0.9-1)*(1-2) = 0.1.
        self.assertAlmostEqual(ledger.pinball({"q": {"0.5": 0.0}}, 1.0), 0.5)
        self.assertAlmostEqual(ledger.pinball({"q": {"0.9": 2.0}}, 1.0), 0.1)
        self.assertAlmostEqual(ledger.pinball({"q": {"0.5": 0.0, "0.9": 2.0}}, 1.0), 0.3)

    def test_coverage(self):
        got = ledger.coverage([(RANGE, 0.2), (RANGE, 1.0), (RANGE, 2.0)])
        self.assertEqual(got["5-95%"]["inside"], 2)
        self.assertEqual(got["25-75%"]["inside"], 1)
        self.assertAlmostEqual(got["5-95%"]["expected"], 0.9)

    def test_verdicts_need_enough_predictions_and_a_clear_gap(self):
        self.assertEqual(ledger.compare([0.1] * 5, [0.3] * 5)["verdict"], "too few")
        n = ledger.MIN_RESOLVED
        self.assertEqual(ledger.compare([0.1, 0.12] * n, [0.3, 0.31] * n)["verdict"], "better")
        self.assertEqual(ledger.compare([0.3, 0.31] * n, [0.1, 0.12] * n)["verdict"], "worse")
        noisy_model, noisy_base = [0.1, 0.5] * n, [0.5, 0.11] * n
        self.assertEqual(ledger.compare(noisy_model, noisy_base)["verdict"], "no clear difference")

    def test_summary_scores_model_and_baseline_on_the_same_outcomes(self):
        db = fresh()
        for i, y in enumerate([0.1, -0.2, 0.4]):
            made = T0 - timedelta(days=5 - i)
            pid = ledger.log(db, model="m", version="1", mode="backtest", target=f"d{i}", kind="quantiles", made_at=made,
                             opens_at=made + timedelta(hours=16), resolves_at=made + timedelta(hours=23),
                             forecast=RANGE, baselines={"wide": WIDE})
            ledger.resolve(db, pid, y, "test")
        log_live(db, "tomorrow")
        rows = {r["mode"]: r for r in ledger.summary(db)}
        bt = rows["backtest"]
        self.assertEqual((bt["logged"], bt["resolved"]), (3, 3))
        self.assertLess(bt["model_loss"], bt["baselines"]["wide"]["baseline_loss"])  # tighter range, small moves
        self.assertEqual(bt["baselines"]["wide"]["verdict"], "too few")
        self.assertEqual(bt["coverage"]["5-95%"]["share"], 1.0)
        self.assertEqual((rows["live"]["logged"], rows["live"]["resolved"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
