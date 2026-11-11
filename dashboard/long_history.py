"""Older price history for the Spreads tab: Yahoo daily closes from 2000, joined onto Alpaca's.

Alpaca's free plan only goes back to 2016. Yahoo fills the years before, and only those: from the
first Alpaca day on, Alpaca stays the source. The Yahoo part is rescaled so it meets Alpaca exactly on
that first day (both are dividend- and split-adjusted, so only the level differs), which keeps the
ratio chart free of a jump at the join. Nothing is stored; fetched histories are kept in memory.
Yahoo is unofficial: if it fails, the series is returned unchanged and the reason is passed back.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from options_collector import http_get

START = 946684800  # 2000-01-01
TTL = 6 * 3600     # history before 2016 doesn't change; today's prices come from Alpaca anyway
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def yahoo_closes(sym: str) -> dict[str, float]:
    """{date: dividend-adjusted close} from 2000 (or the first trading day) to today."""
    with _lock:
        hit = _cache.get(sym)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    ysym = sym.replace(".", "-")  # BRK.B on Alpaca is BRK-B on Yahoo
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}"
           f"?period1={START}&period2=9999999999&interval=1d&events=div,split")
    m = json.loads(http_get(url, {"User-Agent": "Mozilla/5.0"}, attempts=2))["chart"]["result"][0]
    ind = m["indicators"]
    closes = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    off = timedelta(seconds=m["meta"].get("gmtoffset", 0))
    out = {(datetime.fromtimestamp(t, timezone.utc) + off).date().isoformat(): c
           for t, c in zip(m.get("timestamp") or [], closes) if c}
    with _lock:
        _cache[sym] = (time.time(), out)
    return out


def extend(sym: str, recent: dict[str, float]) -> tuple[dict[str, float], str | None, str | None]:
    """recent ({date: close} from Alpaca or the database) with Yahoo's earlier days put in front.
    Returns (series, join date or None if nothing was added, error or None)."""
    try:
        old = yahoo_closes(sym)
    except Exception as e:
        return recent, None, f"older history for {sym} unavailable (Yahoo: {e})"
    if not recent:
        return old, None, None
    first = min(recent)
    anchor = max((d for d in old if d <= first), default=None)
    earlier = [d for d in old if d < first]
    if not anchor or not earlier:
        return recent, None, None  # Yahoo has nothing older (the fund started after 2016)
    scale = recent[first] / old[anchor]
    merged = {d: old[d] * scale for d in earlier}
    merged.update(recent)
    return merged, first, None
