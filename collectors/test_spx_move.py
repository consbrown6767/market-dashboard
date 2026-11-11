"""Tests for the S&P 500 move-size model (spx_move.py): no peeking, inputs from the right day, the Fed
calendar parser, and the evening guard against half-finished bars. Synthetic data, no database or network.

Run from collectors/:  ~/MarketData/.venv/bin/python -m unittest test_spx_move
"""

import unittest
from datetime import datetime

import numpy as np
import pandas as pd

import spx_move as m
from options_collector import ET


def synthetic(days: int = 1100, seed: int = 1) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=days).strftime("%Y-%m-%d")
    vol = 0.6 + 0.5 * np.abs(np.sin(np.arange(days) / 60))  # % per day, drifting calm and stormy spells
    ret = rng.standard_normal(days) * vol / 100
    close = 2000 * np.cumprod(1 + ret)
    prev = np.concatenate([[2000], close[:-1]])
    open_ = prev * (1 + rng.standard_normal(days) * vol / 300)
    spread = np.abs(rng.standard_normal(days)) * vol / 100 * close
    high, low = np.maximum(open_, close) + spread / 2, np.minimum(open_, close) - spread / 2
    vix = vol * np.sqrt(252) * 1.15 + rng.standard_normal(days)
    gex = rng.standard_normal(days) * 3e9 + 1e9
    events = pd.DataFrame({"date": [dates[i] for i in range(20, days, 21)], "event": "cpi"})
    return {
        "spx": pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low, "close": close}),
        "vix": pd.DataFrame({"date": dates, "vix": vix, "vix_source": "cboe"}),
        "vix9d": pd.DataFrame({"date": dates, "vix9d": vix * 0.95}),
        "vix3m": pd.DataFrame({"date": dates, "vix3m": vix * 1.05}),
        "gex": pd.DataFrame({"date": dates, "gex": gex}),
        "events": events,
    }


def forecast(inp, i):
    f = m.build_frame(inp)
    fit = m.Fit(m.Design(f, m.SPEC[m.VERSION]), i)
    assert fit.ready, "synthetic history too short to fit"
    return fit.quantiles()


class NoPeeking(unittest.TestCase):
    def test_changing_anything_after_the_day_changes_nothing(self):
        inp, i = synthetic(), 1000
        before = forecast(inp, i)
        day = inp["spx"].date[i]
        later = synthetic(seed=2)  # completely different future...
        for k in inp:
            if k == "events":
                continue
            future = (inp[k].date > day) if k != "gex" else (inp[k].date >= day)  # ...and that day's own gamma
            inp[k].loc[future, inp[k].columns[1:]] = later[k].loc[future, later[k].columns[1:]].to_numpy()
        self.assertEqual(forecast(inp, i), before)

    def test_changing_the_past_does_change_it(self):
        inp, i = synthetic(), 1000
        before = forecast(inp, i)
        inp["vix"].loc[i, "vix"] *= 2  # today's VIX is an input
        self.assertNotEqual(forecast(inp, i), before)

    def test_gamma_is_from_an_earlier_day(self):
        f = m.build_frame(synthetic())
        known = f.gex_date.notna()
        self.assertTrue((f.gex_date[known] < f.date[known]).all())
        self.assertEqual(f.gex_date.iat[500], f.date.iat[499])

    def test_events_mark_the_day_before(self):
        inp = synthetic()
        f = m.build_frame(inp)
        cpi_day = inp["events"].date.iat[3]
        i = int(f.index[f.date == cpi_day][0])
        self.assertEqual(f.cpi.iat[i - 1], 1.0)  # the evening before CPI
        self.assertEqual(f.cpi.iat[i], 0.0)

    def test_live_row_gets_its_next_day(self):
        inp = synthetic()
        last = inp["spx"].date.iat[-1]
        inp["events"] = pd.concat([inp["events"], pd.DataFrame({"date": ["2099-01-02"], "event": ["fomc"]})])
        f = m.build_frame(inp, next_day="2099-01-02")
        self.assertEqual((f.date.iat[-1], f.next_day.iat[-1], f.fomc.iat[-1]), (last, "2099-01-02", 1.0))
        self.assertTrue(np.isnan(f.r_next.iat[-1]))


class Forecasts(unittest.TestCase):
    def test_quantiles_rise_and_baselines_are_centred(self):
        inp = synthetic()
        f = m.build_frame(inp)
        q = forecast(inp, 1000)["q"]
        self.assertEqual(list(q.values()), sorted(q.values()))
        for b in m.baselines(f.iloc[1000]).values():
            self.assertEqual(b["q"]["0.5"], 0.0)
            self.assertAlmostEqual(b["q"]["0.05"], -b["q"]["0.95"])

    def test_ranges_are_about_right_on_known_data(self):
        f = m.build_frame(synthetic(days=1600))
        fits = m.walk_forward(f, m.SPEC[m.VERSION])
        y = f.r_next.to_numpy()
        inside = [fit.sigma * fit.qz[0] <= y[i] <= fit.sigma * fit.qz[4] for i, fit in fits.items()]
        self.assertGreater(len(inside), 300)
        self.assertAlmostEqual(np.mean(inside), 0.9, delta=0.05)

    def test_needs_two_years_of_training(self):
        f = m.build_frame(synthetic())
        self.assertFalse(m.Fit(m.Design(f, m.SPEC[m.VERSION]), 400).ready)


class Data(unittest.TestCase):
    def test_fed_parser_keeps_only_scheduled_decisions(self):
        html = """<div class="panel"><div class="panel-heading"><h4>2027 FOMC Meetings</h4></div>
          <div class="fomc-meeting"><div class="fomc-meeting__month">Jan/Feb</div><div class="fomc-meeting__date">31-1</div></div>
          <div class="fomc-meeting"><div class="fomc-meeting__month">March</div><div class="fomc-meeting__date">16-17*</div></div>
          <div class="fomc-meeting"><div class="fomc-meeting__month">August</div><div class="fomc-meeting__date">22 (notation vote)</div></div></div>
          <h5>January 31-February 1 Meeting - 2012</h5><h5>March 2 (unscheduled) Meeting - 2020</h5>
          <h5>March 17-18 (cancelled) Meeting - 2020</h5><h5>October 15 Conference Call - 2008</h5><h5>June 9-10 Meeting - 2020</h5>"""
        self.assertEqual(m.fed_meetings(html), {"2027-02-01": "", "2027-03-17": "with projections",
                                                "2012-02-01": "", "2020-06-10": ""})

    def test_todays_bar_waits_for_the_close(self):
        h = pd.DataFrame({"Close": [1.0, 2.0]}, index=["2026-11-06", "2026-11-09"])
        self.assertEqual(list(m.complete_bars(h, datetime(2026, 11, 9, 15, 59, tzinfo=ET)).index), ["2026-11-06"])
        self.assertEqual(len(m.complete_bars(h, datetime(2026, 11, 9, 16, 20, tzinfo=ET))), 2)
        self.assertEqual(len(m.complete_bars(h, datetime(2026, 11, 10, 8, 5, tzinfo=ET))), 2)

    def test_stamps_open_after_they_are_made(self):
        made, opens, resolves = m.stamps("2026-11-06", "2026-11-09")
        self.assertTrue(made < opens < resolves)
        self.assertEqual((opens.hour, opens.minute, opens.day), (9, 30, 9))


if __name__ == "__main__":
    unittest.main()
