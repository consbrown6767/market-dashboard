# Live paper record

*Started 2026-11-13. Rules: `PLAN.md`. Code: `collectors/paper_record.py` (job `paper`). Shown on the
Scorecard tab ("Live paper record · trading rules"). Nothing is traded.*

## How it works

- **Weekdays at 4:40 pm** (retry 8:40 pm): reads the day's adjusted closes of SPY and SSO from Alpaca.
  Logs each trend rule's position for the **next** day's close, and marks the finished day: the rule's
  return and SPY's, with T-bills for cash days and 0.05% per switch.
- **Fed windows** are logged up to 14 days ahead (never after 1:59 pm the day before) and marked on
  decision day from the 1:59 pm minute bars, less 0.01% per trade.
- **9:10 am** catches up an evening the Mac slept through, as long as the trade close hasn't passed.
  Otherwise the signal is listed as skipped and the old position stays.
- Every position and every mark is chained to the row before it (`paper_record.py verify`). The job
  stops with a failed run, and the watchdog alerts, if the chain doesn't check out.

## First positions (2026-11-13, 9:26 am)

| Rule | From | Why |
|---|---|---|
| Leveraged trend | SSO from the 11-13 close | SPY 757.12 vs 200-day average 728.98 |
| 10-month trend | SPY from the 11-13 close | October month-end 755.72 vs 10-month-end average 725.56 |
| Pre-Fed drift | First window Dec 8 2 pm to Dec 9 2 pm | Logged from about Nov 24 |

## Checked before going live

- A simulation of October 2026 (job run at chosen times on a copy of the tables) logged, skipped and
  marked as designed. Its Fed window for Oct 27-28 came out at +0.20%, the backtest's +0.22% less
  costs.
- Unit tests: refusing late positions, logging once, and catching an edited or deleted row
  (`test_paper_record.py`).
