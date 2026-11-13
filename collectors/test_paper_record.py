"""Tests for the live paper record's write-first and never-edit rules (no network)."""

import sqlite3
import unittest
from datetime import datetime, timedelta

import paper_record as pr


def fresh():
    db = sqlite3.connect(":memory:")
    pr.ensure(db)
    return db


class Rules(unittest.TestCase):
    def setUp(self):
        self.real_now = pr._now
        pr._now = lambda: datetime(2026, 11, 13, 9, 10, tzinfo=pr.ET)

    def tearDown(self):
        pr._now = self.real_now

    def test_refuses_after_the_trade_time(self):
        db = fresh()
        with self.assertRaises(ValueError):
            pr.log_position(db, "lev-trend", "2026-11-12", datetime(2026, 11, 13, 9, 0, tzinfo=pr.ET), {"hold": "SSO"}, {})
        self.assertIsNotNone(pr.log_position(db, "lev-trend", "2026-11-12", datetime(2026, 11, 13, 16, 0, tzinfo=pr.ET),
                                             {"hold": "SSO", "trade_date": "2026-11-13"}, {}))

    def test_logs_once(self):
        db = fresh()
        t = datetime(2026, 11, 13, 16, 0, tzinfo=pr.ET)
        self.assertIsNotNone(pr.log_position(db, "trend10", "2026-11-12", t, {"hold": "SPY"}, {}))
        self.assertIsNone(pr.log_position(db, "trend10", "2026-11-12", t, {"hold": "cash"}, {}))

    def test_chain_catches_an_edit_and_a_removal(self):
        db = fresh()
        t = datetime(2026, 11, 13, 16, 0, tzinfo=pr.ET)
        for i, d in enumerate(("2026-11-10", "2026-11-11", "2026-11-12")):
            pid = pr.log_position(db, "lev-trend", d, t + timedelta(days=i), {"hold": "SSO"}, {})
            pr.add_mark(db, "lev-trend", d, pid, "SSO", 0.01 * (i + 1), 0.005, 0.0, {"rf": 0.0001})
        self.assertTrue(pr.verify(db)["ok"])
        db.execute("UPDATE paper_marks SET ret = 0.5 WHERE id = 2")
        self.assertFalse(pr.verify(db)["ok"])
        db = fresh()
        for i, d in enumerate(("2026-11-10", "2026-11-11", "2026-11-12")):
            pr.log_position(db, "lev-trend", d, t + timedelta(days=i), {"hold": "SSO"}, {})
        db.execute("DELETE FROM paper_positions WHERE id = 2")
        self.assertFalse(pr.verify(db)["ok"])

    def test_summary_compounds_against_spy(self):
        db = fresh()
        pid = pr.log_position(db, "lev-trend", "2026-11-12", datetime(2026, 11, 13, 16, 0, tzinfo=pr.ET), {"hold": "SSO"}, {})
        pr.add_mark(db, "lev-trend", "2026-11-16", pid, "SSO", 0.10, 0.05, 0.0, {"rf": 0.0})
        pr.add_mark(db, "lev-trend", "2026-11-17", pid, "SSO", -0.10, -0.05, 0.0, {"rf": 0.0})
        e = pr.summary(db)["strategies"][0]
        self.assertAlmostEqual(e["rule_10k"], 9900.0)
        self.assertAlmostEqual(e["spy_10k"], 9975.0)
        self.assertEqual(e["verdict"], "too early")


if __name__ == "__main__":
    unittest.main()
