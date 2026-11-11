"""Tests for snapshot_polymarket.py, using fake responses."""

import json
import tempfile
import unittest
from pathlib import Path

from snapshot_polymarket import parse_event, snapshot


def market(id, label, active=True):
    return {"id": id, "groupItemTitle": label, "active": active, "closed": False, "bestBid": 0.1, "bestAsk": 0.2,
            "outcomePrices": '["0.15", "0.85"]'}


EVENT = {"id": 7, "markets": [market(1, "JD Vance"), market(2, "Person AI", active=False)]}


class SnapshotTests(unittest.TestCase):
    def test_inactive_placeholders_are_skipped(self):
        markets, snapshots = parse_event(EVENT, "time")
        self.assertEqual([m["label"] for m in markets], ["JD Vance"])
        self.assertEqual(snapshots[0]["best_ask"], 0.2)

    def test_runs_append_snapshots_but_keep_one_market_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            snapshot(out, lambda slug: EVENT)
            snapshot(out, lambda slug: EVENT)
            self.assertEqual(len((out / "poly_markets.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((out / "poly_snapshots.jsonl").read_text().splitlines()), 10)

    def test_a_failed_event_saves_nothing(self):
        def fetch(slug):
            raise OSError("down")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                snapshot(Path(tmp), fetch)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
