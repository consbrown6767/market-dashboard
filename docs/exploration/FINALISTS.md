# Math exploration: finalists, fixed before the vault was opened

*Written 2026-11-13 after the exploration (`~/MarketData/exploration/explore-2026-11-13.json`, data up to
2005-12-30 only), and before any data from 2006 on was loaded. Chosen by the plan's rule: the three versions
with the largest positive Sharpe gap over the market. Two are near-twins (the same idea with two ways to clean
the covariance). The rule was fixed in advance, so both go in as they are.*

**Warning written in advance:** none of the 15 versions cleared the luck test in exploration. The deflated
chance that the gap is real was 0.021, 0.017 and 0.137 for these three. So the expected answer in the vault
is "fails".

## The three (exact rules, code in `collectors/exploration.py`)

- finalist: 6b_minvar_ledoit_wolf
- finalist: 6a_minvar_rmt_clip
- finalist: 4b_vrp_regression

**6b. Minimum variance, Ledoit-Wolf.**
- *Rule:* at each month-end, take the last 250 trading days of the 49 French industries (those with no gaps)
  and estimate the covariance with Ledoit-Wolf shrinkage. Find the long-only minimum-variance weights, at
  most 10% each. Hold them for the next month.
- *Costs:* 0.10% per dollar traded, plus 0.20% a year for fund fees.
- *Exploration, 1946-2005:* 11.6% a year, Sharpe 0.58 vs the market's 11.2% and 0.50. Worst drop −35% vs −46%.

**6a. Minimum variance, random-matrix clipping.**
- *Rule:* the same, but the covariance is cleaned by replacing the correlation matrix's eigenvalues
  below the Marchenko-Pastur edge (1 + √(N/T))² with their average.
- *Exploration:* 11.5%, Sharpe 0.57, worst drop −38%.

**4b. Variance risk premium, regression weight.**
- *Signal:* at each month-end, VRP = (VIX ÷ 100)² ÷ 12 minus the sum of the month's squared daily S&P 500
  log returns.
- *Forecast:* a straight-line regression, fitted on all past months (from 1990, at least 36 of them),
  of the next month's market excess return on VRP.
- *Rule:* weight in SPY = forecast ÷ (3 × the variance of the market's last 120 monthly excess returns),
  kept between 0 and 1.5. The rest is in T-bills, and borrowing above 1x costs the T-bill rate (as in
  the exploration).
- *Costs:* 0.05% per dollar traded.
- *Exploration, 1993-2005:* 12.2% a year, Sharpe 0.54 vs 10.3% and 0.50. Worst drop −38% vs −45%.

## The vault test (from the plan)

2006-01 to 2026-09, against SPY (dividends in). Market timing (4b) holds SPY itself. The industry
portfolios (6a, 6b) use French's industry returns less the fee and costs above.
- **Beats SPY:** more money **and** a better Sharpe ratio.
- **Safer, not better:** a better Sharpe ratio **and** a smaller worst drop.
- Bootstrap range of the Sharpe gap reported.

The vault is opened once, by `exploration.py holdout`, which refuses to run unless this file is committed
and unchanged.
