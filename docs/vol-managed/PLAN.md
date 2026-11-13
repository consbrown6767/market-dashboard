# Volatility-managed market model: the plan, fixed before any result was seen

*Written 2026-11-12, before the backtest was run or any outcome looked at. Committed to git so the
date and contents are on record. Anything changed after the results are in must be listed under
"Changes after results" at the bottom, with the reason. Changes there don't count toward the verdict.*

## The idea in plain English

When the stock market has been calm, hold more of it; when it has been wild, hold less. Each month,
the amount held is set by how jumpy the market was last month: half as jumpy means twice as much
(up to a limit), twice as jumpy means half as much.

**Why it might work:** wild stretches tend to stay wild for a while (volatility clusters), but
investors are not paid proportionally more for sitting through them. So cutting back in wild months
gives up little return and avoids much of the pain, and the calm months can be held more heavily.

**Source:** Moreira & Muir (2017), "Volatility-Managed Portfolios", Journal of Finance 72(4).
US data 1926-2015. Related: Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert (2018), "The
Impact of Volatility Targeting", Journal of Portfolio Management. **The main critique:** Cederburg,
O'Doherty, Wang & Yan (2020), Journal of Financial Economics, find that real-time versions (no use
of future data) mostly fail across 103 strategies. The market itself is the case where the evidence
holds up best (Barroso & Detzel 2021 find costs wipe out the gains everywhere except the market).
This test is built to settle it for the market with our own honest real-time version.

**Known before testing:** I (Claude) know the published results for the US market up to about 2015.
I have not seen this rule's results for 2016-2026 or for the other markets below. That is why the
2016-2026 US period and the other markets are the ones that count most.

## Data (all free)

- **US market, 1926-07 to 2026-09:** Kenneth French's data library (Dartmouth), daily "Mkt-RF"
  (all US stocks, value-weighted, from CRSP, dividends included, minus the T-bill) and "RF"
  (1-month T-bill). This is what the paper used. It tracks the S&P 500 closely but is not identical.
- **Other markets, 1990-07 to 2026-09:** French's daily Developed ex US, Europe, Japan, and Asia
  Pacific ex Japan markets (US dollars, dividends included, minus the US T-bill).
- **49 US industries, 1926 to 2026:** French's daily value-weighted industry returns.
- **S&P 500 itself, 1990 to today:** `index_daily` SPX closes (price only, no dividends). A check on
  the actual index and the most recent weeks.

## The rule (v1, fixed)

At the close of the last trading day of each month:

1. **Jumpiness:** the variance of the market's daily excess returns during that month, scaled to a
   22-day month (Moreira & Muir's measure).
2. **Raw amount:** c / jumpiness, where c is set so that, over all months **up to now only**, the
   managed returns would have been exactly as volatile as simply holding the market. (The paper
   picks c using the whole sample, which uses the future. This is the honest real-time version, as
   in Cederburg et al.) The first 10 years of each market are warm-up only, never scored.
3. **Limit:** two versions, both scored:
   - **"Up to 1.5x":** hold between 0 and 1.5 times the portfolio in stocks (borrowing up to half).
   - **"Never borrow":** hold between 0 and 1 times the portfolio in stocks; the rest earns the T-bill.
4. Hold that amount for the next month; the rest (or the borrowing) sits at the T-bill rate.

**Costs:** 0.05% of every dollar traded at each month-end rebalance (from the weight the month's
moves left you at to the new one). Borrowing costs the T-bill rate plus 1% a year. Sensitivity
checks at 0.20% trading and T-bill + 3% borrowing.

## What it's compared with

- **Buy and hold the market**, always 100% invested. This is "SPY", the thing to beat.
- **Shuffled timing (placebo):** the same set of monthly amounts, in random order, 1,000 times. If
  the real timing doesn't beat about 95% of the shuffles, the gain comes from the average amount
  held, not from knowing when.

## Periods

- **US full, 1937-01 to 2026-09:** after the 10-year warm-up.
- **US 2016-01 to 2026-09:** after the paper's data ended. Unseen by the authors and by me.
- **Decades:** 1940s through 2010s, plus 2020-26.
- **Other markets:** 2000-07 to 2026-09 (after a 10-year warm-up from 1990-07).
- **49 industries:** each one managed on its own jumpiness, 1937 to 2026.

## Pass rules (the verdict)

The **"Up to 1.5x" version beats buying and holding the market** if all of these hold:

1. **US 2016-2026:** it ends with more money and has the better return per unit of risk (Sharpe ratio).
2. **US full period:** the better Sharpe ratio, with the gain clearly more than noise (a 95% range
   from a block bootstrap, 12-month blocks, 2,000 draws, that stays above zero), and more money at the end.
3. **Decades:** better Sharpe in at least 6 of the 9.
4. **Other markets:** better Sharpe in at least 3 of the 4.
5. **Placebo:** beats at least 95% of the shuffled-timing runs (US full, Sharpe ratio).

The **"Never borrow" version** holds less than 100% on average, so it isn't expected to end with
more money. It passes as **a safer way to hold the market** if it has a better Sharpe ratio and a
smaller worst drop in the US full period and 2016-2026, and better Sharpe in 3 of the 4 other markets.

Also reported, never changing the verdict:
- Every year's result against buy-and-hold, worst drops, and the big crashes (1987, 2000-02, 2008,
  2020, 2022).
- **One-day delay:** trading at the next day's close instead of the month-end close.
- **Variants** (information only, not picked from): jumpiness over 1 week, 3 months or 6 months;
  1/volatility instead of 1/variance (Harvey et al.); downside variance only (Wang & Yan 2021).
- 49 industries: in how many the managed version has the better Sharpe ratio.
- The S&P 500 price-only check, 2000 to today.

## If it passes

Propose a live paper record to the owner: each month-end, log the amount the rule says to hold
for the next month, before the month starts, and score it against SPY. Nothing is traded.

## Changes after results

(none yet)
