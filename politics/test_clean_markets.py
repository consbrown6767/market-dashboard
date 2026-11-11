"""Tests for clean_markets.py, using small made-up markets."""

import json
import tempfile
import unittest
from pathlib import Path

from clean_markets import (clean_market, hours_apart, latest_view, load_candidates, load_kalshi,
                           load_polymarket, midpoint, name_lookup, party_check, win_if_nominated)

CANDIDATES = [
    {"id": "jd-vance", "name": "J.D. Vance", "party": "R",
     "polymarket": ["JD Vance", "J.D. Vance"], "kalshi": ["J.D. Vance"]},
]


def quotes(**mids):
    return {name: {"bid": None, "ask": None, "mid": mid} for name, mid in mids.items()}


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class CleaningTests(unittest.TestCase):
    def test_midpoint_uses_bid_and_ask(self):
        self.assertAlmostEqual(midpoint(0.2, 0.3, fallback=0.9), 0.25)

    def test_midpoint_falls_back_when_there_is_no_bid(self):
        self.assertEqual(midpoint(None, 0.002, fallback=0.001), 0.001)

    def test_market_over_100_is_scaled_down(self):
        result = clean_market(quotes(a=0.6, b=0.6))
        self.assertAlmostEqual(result["odds"]["a"], 0.5)
        self.assertEqual(result["unlisted"], 0)

    def test_market_under_100_keeps_prices_and_reports_the_gap(self):
        result = clean_market(quotes(a=0.5, b=0.4))
        self.assertEqual(result["odds"]["a"], 0.5)
        self.assertAlmostEqual(result["unlisted"], 0.1)

    def test_latest_view_uses_the_newest_hour(self):
        book = {"winner": {"2026-11-04T01": quotes(a=0.1), "2026-11-04T02": quotes(a=0.2)}}
        self.assertEqual(latest_view(book)["winner"]["odds"]["a"], 0.2)

    def test_hours_apart(self):
        self.assertEqual(hours_apart("2026-11-04T23", "2026-11-05T02"), 3)


class CheckTests(unittest.TestCase):
    view = {
        "winner": {"odds": {"a": 0.2, "b": 0.1, "c": 0.01, "x": 0.05}},
        "nominee_d": {"odds": {"a": 0.4, "c": 0.02}},
        "nominee_r": {"odds": {"b": 0.5}},
        "party": {"odds": {"D": 0.6, "R": 0.4}},
    }

    def test_win_if_nominated(self):
        result = win_if_nominated(self.view)
        self.assertAlmostEqual(result["a"], 0.5)
        self.assertAlmostEqual(result["b"], 0.2)

    def test_tiny_nominee_prices_are_skipped(self):
        self.assertNotIn("c", win_if_nominated(self.view))

    def test_party_check_adds_up_candidates(self):
        sums = party_check(self.view, {"a": "D", "c": "D", "b": "R", "x": None})["candidates"]
        self.assertAlmostEqual(sums["D"], 0.21)
        self.assertAlmostEqual(sums["R"], 0.1)
        self.assertAlmostEqual(sums["unassigned"], 0.05)


class LoadingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_both_spellings_become_one_person_and_unknown_names_are_reported(self):
        write_jsonl(self.dir / "poly_markets.jsonl", [
            {"id": "1", "event_id": "31552", "label": "JD Vance"},
            {"id": "2", "event_id": "30829", "label": "New Person"},
            {"id": "3", "event_id": "31875", "label": "J.D. Vance"},
        ])
        row = {"fetched_utc": "2026-11-04T01:05:00+00:00", "best_bid": 0.1, "best_ask": 0.2, "price": 0.15}
        write_jsonl(self.dir / "poly_snapshots.jsonl", [
            {**row, "market_id": "1"}, {**row, "market_id": "2"}, {**row, "market_id": "3"}])
        book, unmapped = load_polymarket(self.dir, name_lookup(CANDIDATES, "polymarket"))
        self.assertIn("jd-vance", book["winner"]["2026-11-04T01"])
        self.assertIn("jd-vance", book["nominee_r"]["2026-11-04T01"])
        self.assertEqual(unmapped, {"New Person"})

    def test_later_kalshi_snapshot_in_the_same_hour_wins(self):
        rows = [{"fetched_at": f"2026-11-04T01:{minute}:00+00:00", "event_ticker": "KXPRESPERSON-28",
                 "label": "J.D. Vance", "yes_bid": bid, "yes_ask": bid} for minute, bid in (("05", 0.1), ("50", 0.3))]
        write_jsonl(self.dir / "snapshots-2026-11.jsonl", rows)
        book, _ = load_kalshi(self.dir, name_lookup(CANDIDATES, "kalshi"))
        self.assertEqual(book["winner"]["2026-11-04T01"]["jd-vance"]["mid"], 0.3)


class LiveDataTests(LoadingTests):
    def test_live_rows_override_older_rows_in_the_same_hour(self):
        live = self.dir / "live"
        live.mkdir()
        write_jsonl(self.dir / "poly_markets.jsonl", [{"id": "1", "event_id": "31552", "label": "JD Vance"}])
        row = {"market_id": "1", "fetched_utc": "2026-11-04T01:05:00+00:00", "best_bid": 0.1, "best_ask": 0.1, "price": 0.1}
        write_jsonl(self.dir / "poly_snapshots.jsonl", [row])
        write_jsonl(live / "poly_snapshots.jsonl", [{**row, "fetched_utc": "2026-11-04T01:30:00+00:00", "best_bid": 0.3, "best_ask": 0.3}])
        book, _ = load_polymarket(self.dir, name_lookup(CANDIDATES, "polymarket"), live)
        self.assertEqual(book["winner"]["2026-11-04T01"]["jd-vance"]["mid"], 0.3)


class CandidateFileTests(unittest.TestCase):
    def test_real_file_has_unique_ids_and_labels(self):
        candidates = load_candidates()
        self.assertEqual(len({c["id"] for c in candidates}), len(candidates))
        for venue in ("polymarket", "kalshi"):
            labels = [label for c in candidates for label in c[venue]]
            self.assertEqual(len(set(labels)), len(labels))


if __name__ == "__main__":
    unittest.main()
