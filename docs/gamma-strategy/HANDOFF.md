# Handoff: Gamma Breakout Prediction Tracker

Status: running since 2026-11-06 as the dashboard's Gamma tab. This is the original design, kept for
reference. The rules are `collectors/scoring.py`, the data side is `collectors/strategy_collector.py`,
and the README's Gamma section covers how it runs. (Handoff written 2026-10-21.)

## Goal
A local research dashboard that tests one idea: when a liquid large-cap stock breaks
above its options **call wall** and holds, dealer hedging flows push it further up.

This is **not** a trading bot. It makes predictions live, logs them, and checks later
whether they came true. No backtest is needed to start: testing forward on live data
is the plan.

## What it does
1. **Each morning:** pull option chains for about 20 large stocks and compute each one's
   call wall, put wall and gamma flip from the previous day's open interest.
2. **During the day:** watch 5-minute price bars. When a stock breaks above its call wall,
   start a 30-minute hold check.
3. **At the end of the hold:** check the requirements and the score below. If it
   qualifies, log a prediction ("keeps going up").
4. **Afterwards:** check each prediction at end of day, next day and 3 days later.
5. **Dashboard:** chart with today's levels, live breakouts, and a running scorecard.

## Prediction rules (deterministic)

### Requirements: all must be met, or there is no prediction
1. A 5-minute bar closes above the call wall.
2. None of the next six 5-minute bars (30 min) closes below the wall.
3. Volume so far today is more than 1.5× the stock's 20-day average volume by the same
   time of day.

### Score: ranks breakouts that meet every requirement
| Condition | Points |
|---|---|
| Sector ETF above both its open and its previous close | +1 |
| Price above the gamma flip | +1 |
| Crowded short sellers / expensive to borrow (only when data exists) | +1 |

### Decision
- All requirements met and score ≥ 1 → **prediction** (score 2–3 = "strong").
- All requirements met and score 0 → no prediction, logged quietly.
- Requirement failed → no prediction, logged quietly as a failed breakout.

### Edge cases
- **Falls back below the wall during the 30-minute hold:** that attempt is void (logged
  as a failed breakout). A fresh break later the same day can still qualify.
- **Falls back below the wall after a prediction:** the prediction is **wrong**. It is
  never thrown out.
- The breakout must happen by **3:30 pm ET** so the hold finishes before the close.
- At most **one prediction per stock per day**.
- The original rubric's "−2 for failing back below the wall" was removed. It can't apply
  at prediction time (failing the hold means no prediction), so it was replaced by
  requirement 2 plus the outcome check.

### Scoring a prediction
At each check (end of day, next day, 3 days later), record the % move from the
prediction price. It's **wrong** if any 5-minute bar closes back below the wall before
the check.

Log every breakout, including the ones that don't qualify, with their outcomes. After a
few weeks, compare high-score vs low-score vs no-prediction breakouts to see whether the
scoring actually helps.

## Definitions
- **Call wall:** the strike with the most call open interest, across expirations within
  the next 30 days, taken from the previous day's data.
- **Put wall:** the same, for puts. Shown on the chart, not used in the rules yet.
- **Gamma flip:** the price where total dealer gamma exposure changes sign. Assumes
  dealers are short the calls and long the puts that customers hold. Keep that
  assumption as a switchable setting and write it down in the docs.
  - Caution: common theory says that above the flip, dealers *dampen* moves. So +1 for
    being above it may point the wrong way. Kept as the user designed it; the logged
    data will settle it.

## Data
- **Start with:** Yahoo Finance (free, no API key, about 15 minutes delayed). It has
  open interest at each strike, which is what the walls need.
- **Later options:**
  - Alpaca: faster prices, and historical option prices back to Feb 2024 (an estimated
    "indicative" feed, not official OPRA quotes).
  - OCC: historical open interest. Check whether it's broken down by strike and
    expiration before relying on it for a backtest.
- **Short interest / borrow:** no good free daily source. Skip it until one is found.

## Caveats to show in the app
- Call and put walls are model estimates. Open interest does not show which side
  dealers are actually on.
- Delayed data means signals are about 15 minutes late. That's fine for checking
  predictions, not for trading.
- Moves outside regular hours are ignored.

## Not in the first version
CFTC positioning, prime-broker data, catalysts (just flag earnings dates), automated
trading, backtesting.

## Suggested next steps
1. Pick the ~20 tickers and map each to its sector ETF (e.g. AAPL → XLK).
2. Build the level calculations (call wall, put wall, gamma flip) with tests.
3. Build the intraday breakout and hold detector, plus the prediction log.
4. Build the dashboard: chart with levels, live breakouts, scorecard.
5. Write a README covering data assumptions, scoring rules and how to run it.
