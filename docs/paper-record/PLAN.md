# Live paper record: the plan, fixed before the first position was logged

*Written 2026-11-13, before the record started. The owner said yes to it the same day. Nothing is traded:
positions are written down ahead of time and scored afterwards from real prices. Changes go at the bottom,
and any change to a rule is a new version, scored on its own.*

## Why

Three rules looked promising in testing, but they were tested on history that had already been seen. Only
prices that come after today can't have been tuned on. This record collects them.

## The three rules (version 1 of each)

| Name | Rule | Holds | Tested in |
|---|---|---|---|
| **lev-trend** | Each evening: if SPY's close is above its average of the last 200 closes, hold the 2x fund SSO; otherwise cash. Traded at the **next** trading day's close. | SSO or cash | `docs/tournament/` (confirmation test) |
| **trend10** | On the last trading day of each month: if SPY's close is above its average of the last 10 month-end closes, hold SPY; otherwise cash. Traded at the next trading day's close. | SPY or cash | `docs/classic-strategies/`, `docs/tournament/` |
| **fed-drift** | Before each scheduled Fed decision: buy SPY at 2:00 pm the trading day before (the 1:59 pm minute bar's close), sell at 1:59 pm on decision day. Otherwise nothing. | SPY for ~24 hours, 8 times a year | `docs/fed-drift/` (intraday check) |

**Details, fixed:**
- **Prices:** Alpaca, SPY and SSO adjusted for splits and dividends (`adjustment=all`), daily bars
  for the two trend rules and SIP minute bars for fed-drift. The free plan only serves bars ending at
  least 16 minutes ago, so the evening job reads today's closes.
- **Cash** earns the 3-month T-bill (FRED DTB3, the latest rate known that day, ÷ 360 per calendar day).
- **Costs:** 0.05% of the money moved at each switch for the two trend rules (as in their tests), and
  0.01% per trade for fed-drift (two trades per meeting).
- **Written first:** a trend position is logged on the signal evening, and the job refuses to log it
  once the trade close has passed. A fed-drift position is logged days ahead, and never after 2 pm
  the day before. Each logged row carries a hash of itself and of the row before it, so a changed
  or deleted row shows up. The marks (daily results) are hashed too.
- **Missed evenings:** if the Mac was asleep on a signal evening, the job catches up the next morning
  (before the trade close) from the same closing prices. If it misses the trade close too, that
  signal is skipped and the old position stays. Every skip is listed.
- **Start:** the record starts 2026-11-13. Each trend rule's first position is its current state (lev-trend
  from the 2026-11-12 close, trend10 from the October month-end), bought at the first close after it's logged.
  The record and SPY's both start from that close.
- **Calendar:** trading days from Alpaca's market calendar. Fed meetings from `econ_calendar`; if a
  meeting is moved after its position was logged, that position is marked void, not scored.

## The yardstick (SPY, held throughout the same days)

- **lev-trend and trend10:** $10,000 in the rule against $10,000 in SPY, from the first day each held
  a position. Also the Sharpe ratio and the worst drop.
- **fed-drift:** the average return per meeting window against SPY's average day over the same
  stretch. Also "SPY plus the Fed windows layered on top" (SPY held always, plus an extra 1x during
  each window) against SPY.

## When a verdict is allowed

- **Trend rules:** none before **3 years** of record (2029-11). Before that the panel says "too early",
  because one crash or none decides everything. After 3 years: beats SPY only with more money **and**
  a better Sharpe ratio.
- **fed-drift:** none before **30 meetings** (about 4 years, end of 2030). Then: the windows' average
  beats SPY's average day with t ≥ 2.

## Changes

(none yet. Note for the record: this file was written before the first positions were logged at
9:26 am on 2026-11-13 and committed shortly after; only this note was added.)
