"""Tests for news_scan.py, using a made-up feed."""

import unittest

from news_scan import classify, parse_feed, rank

FEED = """<rss><channel>
<item><title>Ossoff won't run in 2028, aides say</title><link>https://example.com/a</link>
<pubDate>Wed, 04 Nov 2026 12:00:00 GMT</pubDate><source>Paper</source></item>
<item><title>No link here</title><link>javascript:alert(1)</link></item>
</channel></rss>"""


class NewsTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify("Newsom launches campaign"), "entry")
        self.assertEqual(classify("Harris rules out a run"), "exit")
        self.assertEqual(classify("New poll shows tight race"), "poll")
        self.assertEqual(classify("Weather today"), "other")

    def test_feed_tags_candidates_and_drops_unsafe_links(self):
        items = parse_feed(FEED, {"jon-ossoff": r"\bOssoff\b"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["candidates"], ["jon-ossoff"])
        self.assertEqual(items[0]["kind"], "exit")

    def test_rank_removes_repeats_and_puts_exits_first(self):
        base = {"link": "x", "published": "2026", "candidates": []}
        items = [{**base, "title": "A poll", "kind": "poll"}, {**base, "title": "A poll", "kind": "poll"},
                 {**base, "title": "B out", "kind": "exit"}]
        self.assertEqual([i["title"] for i in rank(items)], ["B out", "A poll"])


if __name__ == "__main__":
    unittest.main()
