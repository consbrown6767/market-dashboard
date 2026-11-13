# Fed-day drift and the Fed cycle: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the tests below was run. Committed so the date and contents are on
record. Changes after results go at the bottom and don't count.*

## The idea

Two well-known findings say US stocks earn much of their return around Federal Reserve meetings.

- **Lucca & Moench (2015), "The Pre-FOMC Announcement Drift"** (Journal of Finance; first circulated
  2011, data 1994-2011): the S&P 500 rose on average about 0.5% in the 24 hours before scheduled Fed
  decisions. That was most of the market's excess return in their sample.
- **Cieslak, Morse & Vissing-Jorgensen (2019), "Stock Returns over the FOMC Cycle"** (Journal of
  Finance; data 1994-2016): counting weeks from each Fed meeting, stocks earned their excess return
  almost entirely in **even weeks** (0, 2, 4, 6), and nothing in odd weeks.

**After publication:** the drift from 2012, the cycle from 2017.

## Data

- **Fed decision days:** scheduled meetings in `econ_calendar` (from federalreserve.gov), 2002-2026,
  unscheduled calls excluded. **Corrections:** the stored calendar misses five meetings that spanned two
  months (the Fed's pages write them "April/May 30-1"). They are added here from the same Fed
  pages: 2013-05-01, 2017-02-01, 2017-11-01, 2018-08-01, 2019-05-01. Also, 2003-09-15 is dropped:
  the Fed's 2003 page lists both September 15 and 16, but the decision was announced on the 16th.
- **SPY:** daily dividend-adjusted closes (`SPY_ADJ`, Yahoo), 2002-2026. T-bill: French 1-month.
- **Intraday (information only):** Alpaca SPY minute bars around each meeting, 2016-2026, for Lucca
  & Moench's exact window (2 pm the day before to just before the 2 pm decision).

## The strategies (fixed)

Day 0 is the decision day. The meeting calendar is published a year ahead, so every rule is known in
advance.

- **A. Pre-Fed drift:** hold SPY from the close the day before (day −1) to the close of day 0, T-bills
  otherwise. In the market 8 days a year, so it can't make SPY's money. The test is whether those
  days really earn more.
- **B. Fed cycle:** trading days are counted from the latest meeting. Week 0 is days −1 to +3, week 1 is
  +4 to +8, week 2 is +9 to +13, and so on (5 trading days each); the day before a meeting starts its
  week 0. Hold SPY in even weeks (0, 2, 4, 6, ...), T-bills in odd weeks.
- **Costs:** 0.01% per dollar traded (SPY, as in the overnight test). 0.05% also reported.

## Pass rules

- **A, the drift is real:** from 2012-01 to 2026-10, SPY's average return over T-bills on day 0 is
  above the average on all other days, **with t ≥ 2** (Welch t-test of day-0 returns against
  other days).
- **B beats SPY:** from 2017-01 to 2026-10, after costs, more money **and** a better Sharpe ratio than
  holding SPY.

## Also (information only)

- The same before publication: A 2002-2011, B 2002-2016.
- Average return in each cycle week (0 to 6).
- A on 2 pm to 2 pm intraday windows, 2016-2026.
- Each year.

## Changes after results

(none yet)
