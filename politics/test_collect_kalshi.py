"""Tests for collect_kalshi.py. They use fake responses and never call Kalshi."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_kalshi
from collect_kalshi import collect, parse_event


def market(ticker="T-A", status="active", **changes):
    row = {
        "ticker": ticker, "status": status, "yes_sub_title": "Candidate A",
        "yes_bid_dollars": "0.2100", "yes_ask_dollars": "0.2200", "last_price_dollars": "0.2200",
        "volume_fp": "100.50",
    }
    row.update(changes)
    return row


def response(*markets):
    return {"event": {"markets": list(markets)}}


class ParseTests(unittest.TestCase):
    def test_reads_prices_as_numbers(self):
        row = parse_event(response(market()), "EV", "time")[0]
        self.assertEqual((row["yes_bid"], row["yes_ask"], row["volume"]), (0.21, 0.22, 100.5))

    def test_missing_optional_field_is_saved_as_empty(self):
        self.assertIsNone(parse_event(response(market()), "EV", "time")[0]["open_interest"])

    def test_skips_closed_markets(self):
        rows = parse_event(response(market(), market("T-B", status="finalized")), "EV", "time")
        self.assertEqual([r["ticker"] for r in rows], ["T-A"])

    def test_missing_price_field_is_an_error(self):
        broken = market()
        del broken["yes_bid_dollars"]
        with self.assertRaises(KeyError):
            parse_event(response(broken), "EV", "time")

    def test_price_in_cents_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_event(response(market(yes_ask_dollars="22")), "EV", "time")

    def test_no_open_markets_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_event(response(), "EV", "time")


class CollectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_saves_every_event_and_appends_on_the_next_run(self):
        with patch.object(collect_kalshi, "fetch_event", return_value=response(market())):
            collect(self.dir)
            status = collect(self.dir)
        lines = (self.dir / status["file"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2 * len(collect_kalshi.EVENTS))

    def test_one_failed_event_saves_nothing_and_records_the_error(self):
        results = [response(market()), OSError("network down")]
        with patch.object(collect_kalshi, "fetch_event", side_effect=results):
            with self.assertRaises(OSError):
                collect(self.dir)
        self.assertEqual(list(self.dir.glob("snapshots-*.jsonl")), [])
        self.assertFalse(json.loads((self.dir / "last_run.json").read_text())["ok"])


if __name__ == "__main__":
    unittest.main()
