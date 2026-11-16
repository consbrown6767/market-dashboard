# The signal stack: results

*Run on 2026-11-16 by the plan in `PLAN.md` (committed first, with three changes logged before any
result was read). Code: `collectors/signal_stack.py`. Raw output: `~/MarketData/signal_stack/`.
Research only.*

## In one paragraph

Twenty-seven published signals on S&P 500 stocks, each pointed the way its paper says and combined
with equal weights, **lost to SPY and to simply holding every stock in equal amounts**, over
2017-2026 and in both halves. The long-short version lost about 5% a year. **All four versions fail.
Nothing goes to a live test.** A few single signals pointed the right way, but too weakly to trust.

## The test

- 512 weeks, January 2017 to October 2026. About 497 stocks a week: S&P 500 members at the time.
- 18 to 27 signals in use each week (options signals join in February 2024).
- Costs: 0.05% per dollar traded, 0.5% a year to borrow shorted stock.

## Long-only: the top fifth of stocks by combined score

| | Whole period | 2017-2021 | 2022-2026 | Sharpe (whole) | Worst drop | $10,000 became |
|---|---|---|---|---|---|---|
| **SPY** | **15.0% a year** | 17.5% | 12.4% | **0.79** | −30% | **$39,500** |
| Every stock, equal amounts | 12.1% | 15.9% | 8.4% | 0.59 | −36% | $30,800 |
| A1: families balanced (main) | 9.7% | 13.4% | 6.0% | 0.53 | −32% | $24,900 |
| B1: plain average | 10.5% | 13.0% | 8.0% | 0.60 | −30% | $26,800 |

Both stacks trail SPY by about 5 points a year, and trail the equal-amounts basket too, so the
shortfall isn't only from not owning the giant companies.

## Long-short overlay: top fifth minus bottom fifth

| | Overlay, a year | 2017-2021 | 2022-2026 | 95% range | SPY + overlay became |
|---|---|---|---|---|---|
| A2 | −5.7% | −7.1% | −4.2% | −14.8% to +3.3% | $23,200 (SPY alone $39,500) |
| B2 | −4.5% | −7.7% | −1.1% | −14.6% to +6.0% | $25,300 |

## Each signal on its own

Weekly rank correlation with the next week's return. Positive means the signal pointed the way its
paper says. A "t" near 2 or more would be worth noticing; near 3 would be convincing.

| Signal | Weeks | Correlation | t |
|---|---|---|---|
| Price of crash protection (options) | 142 | +0.021 | +2.1 |
| Earnings drift | 362 | +0.010 | +2.0 |
| Momentum, months 12 to 7 | 512 | +0.014 | +1.7 |
| Momentum, months 12 to 2 | 512 | +0.016 | +1.6 |
| Momentum net of the market | 512 | +0.015 | +1.6 |
| Last week reverses | 512 | +0.013 | +1.6 |
| Earnings report due | 492 | +0.005 | +1.3 |
| The other 17 | | −0.010 to +0.009 | −1.0 to +1.0 |
| Less-traded stocks do better (price impact) | 512 | −0.015 | −2.2 |
| Dividend month | 147 | −0.010 | −2.4 |
| Less-traded stocks do better (dollar volume) | 512 | −0.015 | −2.7 |

## What it means

- **Why it lost:** the signals that say "smaller, quieter, less-traded stocks do better" were badly
  wrong in these years. The most heavily traded giants led the market. Those signals dragged the
  whole stack down, and the momentum signals weren't strong enough to offset them.
- **Nothing here is strong enough to stand alone.** With 27 signals, one or two reaching a t of 2 is
  about what luck produces.
- **Crash protection pointed the right way again.** That's the fifth look in a row across this
  project. It's already on a live test in the stock direction model, which is the right place to
  judge it.
- **This matches the research.** The big studies find combined signals earn most of their return in
  small, hard-to-trade stocks and on the short side. In large stocks after 2016 there was little left.

## What was not tested

- **Company-accounts signals** (profitability, earnings quality, asset growth and others). They need
  SEC filings, which need a contact email from the owner. Quality signals did better than most in
  these years in published work, so this is a real gap, but it would be a new version on years that
  have now been looked at twice.
- **Small stocks**, where the research says the edge is largest. Free data on stocks that later
  delisted is incomplete, which would flatter a backtest.
- **Fitted weights.** Deliberately: fitting which signals to trust on these same years would be
  choosing the winners after the fact.

## Honesty notes

- **Three plan changes** were written and committed before any result was read (`PLAN.md`, Changes).
- **Both sets of results were seen.** The rerun after those changes crashed on a typing error, so the
  first results read were by accident the original plan's (the 80% coverage rule, with no options
  signals). Under that rule: A1 9.4% a year, B1 10.2%, overlays −5.2% and −4.3%. All four fail there
  too, so the changes made no difference to the verdict. Kept as
  `results-2026-11-16-original-80pct-rule.json`.
- These years had been looked at before by other studies here, as the plan says.
- A stock that stops trading keeps its last price for up to 10 days, so a bankruptcy would be
  understated. That's rare among S&P 500 members and would only make the result worse.
