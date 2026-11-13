# Round 4 and the tournament: the plan, fixed before any result was seen

*Written 2026-11-12, before any of the new strategies below was run, and before the common-window
table was built. Committed to git so the date and contents are on record. Changes after results go
under "Changes after results" and don't count toward the verdict.*

## Why these candidates

The first three rounds (`docs/vol-managed/`, `docs/classic-strategies/`, `docs/risk-budget/`,
`docs/pairs/`, `docs/macro-timing/`) found one durable thing: the trend rule lowers crashes, and with
them risk, at a small cost in return. The candidates below either turn that lower risk into
return (leverage), apply it to other assets, or come from strategies built on real option prices.

## New candidates (each fixed)

| # | Name | Rule | Source (its data) | After publication |
|---|---|---|---|---|
| 10 | **Leveraged trend** | Each day: if the US market's level is above its 200-day average at the close, hold **2x** the market the next day (rebalanced daily); else T-bills. | Gayed & Bilello (2016), "Leverage for the Long Run" (1928-2015) | 2016-01 |
| 11 | **Dual momentum** | Each month: of US and Developed ex US stocks, hold the one with the higher 12-month return; if that return is below the T-bill's, hold 10-year Treasuries instead. | Antonacci (2012/2014) (1974-2011) | 2012-01 |
| 12 | **Four-factor mix** | 25% each in French's small value, momentum (top tenth), profitability (top fifth) and low volatility (lowest fifth), rebalanced monthly. | Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere" (to 2011) | 2012-01 |
| 13 | **Industry momentum with trend** | Strategy 6 (top 10 of 49 industries) only while the market is above its 10-month average; else T-bills. | **My idea after seeing round 2.** No paper | none (see below) |
| 14 | **Small value with trend** | Strategy 8 (small value) the same way. | **My idea after seeing round 2.** No paper | none |
| 15 | **Put-selling** | CBOE PUT index: sells 1-month at-the-money S&P 500 puts each month, fully backed by T-bills. | Whaley (2002); Israelov & Nielsen (2014) | 2007-07 (index launch) |
| 16 | **Covered calls** | CBOE BXM: S&P 500 plus selling 1-month at-the-money calls. | Whaley (2002) | 2002-05 |
| 17 | **Protective puts** | CBOE PPUT: S&P 500 plus buying 1-month 5% out-of-the-money puts. | Israelov (2017), "Pathetic Protection" | 2008-01 |
| 18 | **Collar** | CBOE CLL: S&P 500, buy 5% out-of-the-money puts, sell 10% out-of-the-money calls (quarterly puts, monthly calls). | CBOE | its whole history (from 2008-09) |

Strategies 13 and 14 have no clean out-of-sample period: I designed them after seeing both halves
work. They are judged on the same rules but **can't be the tournament's winner** (rule T3).

**Data:**
- French daily and monthly US, Developed ex US and portfolios (as before).
- FRED 10-year Treasury yields (bond returns as in `risk_budget.py`).
- CBOE's daily history of PUT, BXM, PPUT and CLL: real option prices, dividends included.
- S&P 500 total return (Yahoo `^SP500TR`, 1988 on).

**Costs:**
- 10: 0.05% per dollar traded on each switch; borrowing T-bill + 1% a year on the extra 1x
  (similar to a 2x fund's fee plus financing).
- 11: 0.05% per dollar on switches.
- 12: each sleeve's monthly cost from round 2.
- 13-14: round 2's costs plus switches.
- 15-18: 0.40% a year (typical fee of funds that run these indices). SPY's 0.09% is charged on the
  S&P 500 yardstick in the tournament.

## Pass rules for 10-18 (as in round 2)

**Beats the market:** in its after-publication period, more money **and** a better Sharpe ratio
than the market. Over its full period, a gap over the market with t ≥ 3 (Newey-West). The yardstick
is the French US market for 10-14 and the S&P 500 total return for 15-18. For 13-14, "after
publication" is replaced by 2006-2026.

**Safer, not better:** better Sharpe ratio **and** smaller worst drop than the market, in both its
full and its after-publication period.

## The tournament

**Common window: 2006-01 to 2025-09.** It's after publication for most strategies, includes 2008,
2020 and 2022, and every series has data in it except pairs (from 2017) and the collar (from
2008-09). Those two are shown on their own shorter windows.

**Every strategy tested today** is run through it, after its own costs, monthly:
- vol-managed (both versions);
- the nine classic strategies;
- the risk budget model at 10% and 15%;
- macro timing;
- 10-18.

**Yardstick:** the S&P 500 total return minus SPY's 0.09% fee ("SPY").

**Reported for each:** per year, Sharpe ratio, worst drop, $10k becomes, and the gap over SPY.

**Choosing the winners:**

- **T1. Best for beating SPY:** the most money in the common window among strategies that (a)
  passed "beats the market" in their own plan and (b) beat SPY on both money and Sharpe in the
  common window. **If none qualifies, the answer is "SPY itself".**
- **T2. Best risk-adjusted:** the highest Sharpe ratio in the common window among strategies that
  passed "beats" or "safer" in their own plan. It must also have a smaller worst drop than SPY.
- **T3.** Strategies 13 and 14 (designed after seeing results) can't win T1 or T2. They are shown
  for information.
- **T4. Luck check:** the deflated Sharpe ratio (Bailey & López de Prado) for T1's or T2's winner's
  gap over SPY. It counts every strategy and version tested today as a try, at least 25. A
  winner whose chance of being real is under 50% is reported as "probably luck".

## Changes after results

(none yet)
