# Roadmap

*Written 2026-11-16 after a review of the whole project. Agreed with the owner the same day. Update
this file when a step is finished or the plan changes.*

## Where the project stood at the review

- **Data collection** is the strongest part: 17 background jobs, about 2,200 runs, almost all clean.
- **Research:** 19 studies and about 107 versions, each planned before its results. One trading rule
  survived (leveraged trend), plus a safer one (10-month trend) and a few weak leads. The full list is
  on the Research tab (`shared/research.json`).
- **Live tests** are all too young to judge, and most need months or years.
- **The dashboard** had no home page, a cluttered Scorecard, and none of the research in it.

## What the review concluded

The stated goal was a model that beats SPY at similar risk. After the research, the odds of that with
free data and published ideas look low (a rough estimate: 10-15%), and proving a weak edge would take
3-4 years of live results. Two findings are more useful:

1. **Risk can be predicted even though direction can't.** The S&P move-size model beat both of its
   simple guesses in its backtest.
2. **More risk, taken while the trend is up, has paid over 100 years** (leveraged trend), with a worst
   drop of 56%. That's a risk choice, not skill.

So the project's future is as a **decision-support and forecasting tool**, with the hunt for an edge
continuing as one bet at a time rather than the main purpose.

## The plan

### Step 1. Set the goal (open: needs the owner)

Decide what decisions the project should serve (investing, understanding events, work), and how many
hours a week it deserves. This sets the order of step 3.

### Step 2. Consolidate, build nothing new

| Item | State |
|---|---|
| Today tab: one home screen (market now, live tests, top stories, betting-market moves, calendar, data health) | Done 2026-11-16 |
| Research tab: every idea tested, its verdict and takeaway | Done 2026-11-16 |
| Scorecard: live records first, backtests behind a button | Done 2026-11-16 |
| Tidy `reference.md` (short header, change log at the end, current "where things stand") | Done 2026-11-16 |

### Step 3. Add the decision layer (next, each needs the owner's OK before building)

| Item | What it gives |
|---|---|
| Risk panel: trend state, expected move size, odds of a big drop | When risk is high or low, without claiming to know direction |
| "What's priced in" panel: options, rate markets and Polymarket on one screen | The market's own view of the Fed, elections and big events |
| Savings-path simulator on the 100 years of data | How savings rate, time and leverage drive outcomes |
| Forecast journal: the owner's own predictions, scored like the models | Calibration practice with results in weeks |
| Fast event forecasts scored against Polymarket (leadership votes, Fed meetings, confirmations) | Quick feedback; the Dec 1 2026 Senate leader vote could be the first |
| Recession and inflation gauges | Context for big personal decisions, not for timing stocks (macro timing failed its test) |

### Step 4. One research bet at a time

- **The 50-signal stack:** about 50 published signals on S&P 500 stocks (prices, options, company
  accounts from SEC filings, earnings events), signs fixed from the papers, equal weights, one backtest,
  then the live paper record. Needs the owner's OK and a contact email for the SEC's download rules.
- **Polymarket bias test:** are long shots overpriced? Uses data already collected.
- Review every quarter. Retire anything that isn't earning its place (the gamma tracker makes about one
  prediction a week, so its 30-prediction verdict is more than six months away).

### Stop doing

- More backtests on data that's already been looked at.
- New tabs for new data sources.

## Not advice

These are research tools. Nothing here trades, and what the owner does with their money is their own
decision.
