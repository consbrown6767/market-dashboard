# Fed-day drift and the Fed cycle (tested 2026-11-13: both failed on the plan's rules)

*Plan fixed before any result: `PLAN.md` (commit `9719e42`). Code: `collectors/fed_drift.py`.
Full results: `~/MarketData/fed_drift/backtest-2026-11-13.json`. Not live.*

## In one paragraph

Two famous findings say US stocks make much of their money around Fed meetings. **Both worked before
they were published, and both faded after.**
- **Fed-day drift:** from 2002 to 2011, SPY's close on decision day averaged +0.46%, more than the
  market's whole excess return over that stretch. Since 2012 it's +0.10%, no different from any
  other day.
- **Fed cycle:** "hold stocks only in even weeks after a meeting" beat SPY from 2002 to 2016 (Sharpe 0.85
  vs 0.44). Since 2017 it made 5.5% a year against SPY's 15.0%.

**One thing survived.** Measured the way Lucca & Moench actually defined it (2 pm the day before
to just before the 2 pm decision), SPY still rose +0.20% on average across 86 meetings in 2016-2026
(t 2.9). That's three times an ordinary day. The gain is given back after the announcement, which
is why the close-to-close test misses it. This was an information-only check, not a pass rule.

## Results

**A. Fed-day drift** (SPY's return over T-bills, decision-day close vs the close before):

| | Meetings | Decision day | Other days | t | Up |
|---|---|---|---|---|---|
| 2002-2011 (before publication) | 80 | **+0.46%** | 0.00% | 2.91 | 65% |
| **2012-2026 (after: the test)** | 118 | **+0.10%** | +0.05% | **0.50** | 49% |
| *2 pm to 2 pm, 2016-2026 (information)* | 86 | *+0.20%* | *+0.06% avg day* | *2.92 vs 0* | *62%* |

The intraday drift by period: 2016-2020 +0.10%, 2021-2026 +0.30% (2022 alone +0.94%). Median +0.10%;
without the 3 best meetings, +0.14%.

**B. Fed cycle**: average daily return over T-bills by week after the meeting (basis points; 1 bp = 0.01%):

| Week | 0 | 1 | 2 | 3 | 4 | 5 | 6 | Even − odd | t |
|---|---|---|---|---|---|---|---|---|---|
| 2002-2016 | **8.6** | −1.7 | **7.1** | −5.3 | **10.5** | −1.5 | 2.5 | **+11.2** | 2.82 |
| 2017-2026 | −0.9 | 11.6 | 8.1 | 7.9 | 1.5 | 2.6 | −3.7 | **−4.3** | −0.94 |

The pattern flipped: since 2017, week 1 (odd) was the best week.

**$10,000 invested** (costs 0.01% per dollar traded; B switches about 49 times a year):

| 2017-01 to 2026-10 | Per year | Sharpe | Worst drop | $10k → |
|---|---|---|---|---|
| B. Fed cycle (even weeks only) | 5.5% | 0.31 | −16% | $17.0k |
| B with costs 0.05% | 3.5% | 0.14 | −17% | $14.0k |
| A. Decision days only | 2.6% | 0.05 | −4% | $12.9k |
| **SPY** | **15.0%** | **0.82** | −24% | **$39.4k** |

| 2002-01 to 2016-12 (before publication) | Per year | Sharpe | Worst drop | $10k → |
|---|---|---|---|---|
| **B. Fed cycle** | **11.0%** | **0.85** | −21% | **$48.0k** |
| A. Decision days only | 4.1% | 0.81 | −3% | $18.2k |
| SPY | 6.7% | 0.44 | −51% | $26.4k |

**Pass rules:** A, the drift is real after 2012 **fail** (t 0.5). B beats SPY after 2017 **fail**.

## Checks on my own work

- **The Fed calendar had a gap.** The stored calendar (`econ_calendar`, used by the S&P 500 move-size
  model too) is missing five meetings that spanned two months: 2013-05-01, 2017-02-01, 2017-11-01,
  2018-08-01, 2019-05-01. The Fed's history pages write these as "April/May 30-1", which the parser in
  `spx_move.py` doesn't read. They were added in this test's code, as the plan said. Also dropped
  2003-09-15: the Fed's page lists both the 15th and 16th, and the decision came on the 16th. The
  stored table itself was not changed (see "Open question" below).
- **Replication:** the pre-2012 drift (+0.46% a day, all of the market's excess return) is close to
  Lucca & Moench's +0.49%. The 2002-2016 cycle pattern matches Cieslak et al.'s even-week finding.
  So the code reproduces the papers. The later failure is in the market, not in the code.
- Every rule uses only the published meeting calendar, which is set a year ahead.

## What this means

Fed meetings still matter for the hours before the decision. But on daily closes, the edge either
disappeared after publication or gets given back after 2 pm. The intraday drift (+0.20% per meeting)
would be tradable in principle: buy at 2 pm the day before, sell just before 2 pm on decision day,
8 times a year. That adds about 1.4% a year after costs if layered on top of an SPY holding. But it was an
information-only look at already-seen data, so it can't count as a pass. The honest next step is a
**live paper record** going forward. It's free, but it's a new daily job, so it needs the owner's OK.

## Open question for the owner

The calendar gap also affects the history the S&P 500 move-size model (v1) learns from: five Fed
days are marked as ordinary days. v1 refits on all past days each evening, so its Fed-day effect is
estimated from about 195 Fed days instead of 200 (a small effect). Upcoming meetings are flagged
correctly, because 2026-2027 have none that span two months. Fixing the parser changes v1's training
data, so it waits for the owner's decision.

## Sources

- Lucca, D. & Moench, E. (2015). The Pre-FOMC Announcement Drift. Journal of Finance 70(1).
- Cieslak, A., Morse, A. & Vissing-Jorgensen, A. (2019). Stock Returns over the FOMC Cycle. Journal of Finance 74(5).
- Data: federalreserve.gov meeting calendars; Yahoo dividend-adjusted SPY; Alpaca SPY minute bars (SIP).
