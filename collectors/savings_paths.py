"""Monthly return series for the savings-path simulator on the Research tab.

Writes ~/MarketData/savings/paths.json: one monthly return per month since 1928 for four ways of
holding US stocks, built with the same functions and costs as the studies that tested them:
  tbills      T-bills (the "kept it in cash" yardstick)
  market      the US stock market, 1x                      (French data library)
  lev2        2x the market, reset monthly                 (constant_leverage.py: 1% a year to borrow, 0.05% per trade)
  lev_trend   2x while above the 200-day average, else T-bills  (tournament.py)
The dashboard reads the file and the browser runs the what-ifs. This is history replayed, not a
forecast. Run by hand after the French data is refreshed:  savings_paths.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constant_leverage as cl  # noqa: E402
import tournament as tn  # noqa: E402
import vol_managed as vm  # noqa: E402

OUT = Path.home() / "MarketData" / "savings" / "paths.json"
START = pd.Period("1928-01", "M")  # the 200-day rule needs most of 1927


def main() -> int:
    db = sqlite3.connect(f"file:{Path.home() / 'MarketData' / 'options.db'}?mode=ro", uri=True)
    d = vm.load(db, "us")
    series = {
        "tbills": cl.monthly(d["rf"]),
        "market": cl.monthly(d["ex"] + d["rf"]),
        "lev2": cl.monthly_reset(d, 2.0)[0],
        "lev_trend": tn.lev_trend(d, 2.0),
    }
    frame = pd.DataFrame({k: v.loc[START:] for k, v in series.items()}).dropna()
    out = {"made": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
           "first": str(frame.index[0]), "last": str(frame.index[-1]),
           "names": {"tbills": "T-bills (cash)", "market": "US stock market", "lev2": "2x the market, always",
                     "lev_trend": "Leveraged trend (2x above the 200-day average, else cash)"},
           "months": [str(m) for m in frame.index],
           "returns": {k: [round(float(x), 6) for x in frame[k]] for k in frame}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out))
    for k in frame:
        print(f"{k:10s} {((1 + frame[k]).prod() ** (12 / len(frame)) - 1) * 100:5.1f}% a year, worst month {frame[k].min() * 100:6.1f}%")
    print(f"{len(frame)} months {out['first']}..{out['last']} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
