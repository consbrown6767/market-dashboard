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
| Risk panel: trend state, expected move size, odds of a big drop | **Done 2026-11-16** (Today tab, "Risk right now"): how often the S&P 500 fell 5% or 10% within a month after days like today, by trend and VIX band, since 1990. History, not a tested forecast |
| "What's priced in" panel: options, rate markets and Polymarket on one screen | **Done 2026-11-16** (Today tab): SPY's options-implied move for about a week, a month and two months, and the busiest macro, politics and geopolitics betting markets |
| Savings-path simulator on the 100 years of data | **Done 2026-11-16** (Research tab, "Savings paths"): a monthly saving replayed from every start month since 1928, in T-bills, the market, 2x always and leveraged trend. Series from `collectors/savings_paths.py` |
| Forecast journal: the owner's own predictions, scored like the models | **Done 2026-11-16** (backend): a forecast file with `"who": "owner"` goes to the ledger as "Your forecast journal". Tell Claude the event and your chance; no entry form on the page, because the server is read-only |
| Fast event forecasts scored against Polymarket (leadership votes, Fed meetings, confirmations) | **Done 2026-11-16**: `collectors/event_forecast.py`, evidence files in `docs/event-forecasts/`. First forecast: Van Hollen wins the Dec 1 Senate leader vote, 3% against the market's 9.3%. **Resolve by hand after Dec 1** (`event_forecast.py due`, then `resolve`) |
| Recession and inflation gauges | **Done 2026-11-16** (Today tab, "Economy gauges"): Sahm recession rule, yield curve, unemployment, jobless claims, inflation, the Fed rate against inflation, junk-bond stress. New daily job `gauges` (`collectors/macro_gauges.py`, 09:12) |

### Step 4. One research bet at a time

- **The signal stack, stage 1: done 2026-11-16, failed** (`docs/signal-stack/`). 27 signals from prices, trading, calendar, earnings and options; all four versions trailed SPY and the equal-amounts basket. Stage 2 (about 15 company-accounts signals from SEC filings) is not built: it needs a contact email for the SEC and would be a third look at the same years, so it's only worth doing if the owner wants it.
- **Original description of the stack:** about 50 published signals on S&P 500 stocks (prices, options, company
  accounts from SEC filings, earnings events), signs fixed from the papers, equal weights, one backtest,
  then the live paper record. Needs the owner's OK and a contact email for the SEC's download rules.
- **Polymarket bias test:** **done 2026-11-16, failed** (`docs/polymarket-bias/`). Prices were close to fair; both trading rules made about nothing after costs. A clean rerun is possible in six months on markets first seen after 2026-11-16.
- Review every quarter. Retire anything that isn't earning its place (the gamma tracker makes about one
  prediction a week, so its 30-prediction verdict is more than six months away).

### Stop doing

- More backtests on data that's already been looked at.
- New tabs for new data sources.

## Not advice

These are research tools. Nothing here trades, and what the owner does with their money is their own
decision.
