"""Tests for read_polymarket.py. They use a small fake database, never the real one."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from read_polymarket import extract, to_utc


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "options.db"
        self.out = Path(self.tmp.name) / "out"
        db = sqlite3.connect(self.db)
        for statement in (
            "CREATE TABLE poly_events (id TEXT, title TEXT, grp TEXT, volume REAL)",
            "CREATE TABLE poly_markets (id TEXT, event_id TEXT, label TEXT)",
            "CREATE TABLE poly_snapshots (fetched_at TEXT, market_id TEXT, price REAL)",
            "INSERT INTO poly_events VALUES ('1', 'Presidential Election Winner 2028', 'politics', 10)",
            "INSERT INTO poly_events VALUES ('2', 'Next Chancellor before 2028?', 'geopolitics', 5)",
            "INSERT INTO poly_markets VALUES ('a', '1', 'Candidate A')",
            "INSERT INTO poly_markets VALUES ('b', '2', 'Candidate B')",
            # 01:30 EST is later than 01:45 EDT, though it sorts earlier as plain text.
            "INSERT INTO poly_snapshots VALUES ('2026-11-01T01:30:00-05:00', 'a', 0.2)",
            "INSERT INTO poly_snapshots VALUES ('2026-11-01T01:45:00-04:00', 'a', 0.1)",
            "INSERT INTO poly_snapshots VALUES ('2026-11-01T02:00:00-05:00', 'b', 0.9)",
        ):
            db.execute(statement)
        db.commit()
        db.close()

    def read(self, name):
        with open(self.out / name, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_keeps_only_2028_politics(self):
        manifest = extract(self.db, self.out)
        self.assertEqual((manifest["events"], manifest["markets"]), (1, 1))
        self.assertEqual({s["market_id"] for s in self.read("poly_snapshots.jsonl")}, {"a"})

    def test_snapshots_sort_correctly_across_the_clock_change(self):
        extract(self.db, self.out)
        self.assertEqual([s["price"] for s in self.read("poly_snapshots.jsonl")], [0.1, 0.2])

    def test_database_is_not_changed(self):
        before = self.db.read_bytes()
        extract(self.db, self.out)
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_database_stops_with_a_clear_error(self):
        with self.assertRaises(SystemExit):
            extract(self.db.with_name("nope.db"), self.out)

    def test_to_utc(self):
        self.assertEqual(to_utc("2026-11-01T01:30:00-05:00"), "2026-11-01T06:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
