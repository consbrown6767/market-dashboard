# Constant leverage (tested 2026-11-13: 2x fails the safety rules; more money, ruinous crashes)

*Plan fixed before any result: `PLAN.md` (commit `a16794b`). Code: `collectors/constant_leverage.py`.
Full results: `~/MarketData/constant_leverage/backtest-2026-11-13.json`. Not live.*

## In one paragraph

Always holding 2x the US market made more money over 100 years: 12.4% a year against 10.2%. In
hindsight, 2x was the best fixed level. **But it fails two of the three rules.** It lost 98.7% of
its value in 1929-1932, against 84% for the market. Someone who held 2x through the Depression
needed about 77 times their money back to break even. And over 20-year stretches it was ahead only
72% of the time. Starting in 1929, it ended with 21 cents for every dollar the market ended with.
**The surprise is the saver.** Someone adding the same amount every month for 40 years did better
at 2x than at 1x in **every one** of 60 starting years since 1927. Crashes hit while the balance is
still small, and the later years compound on a bigger base. That's Ayres & Nalebuff's point, and
it held.

## Results: $10,000 held, 1927-01 to 2026-09 (borrowing at T-bill + 1%, trading 0.05%)

Monthly reset (a margin account):

| Leverage | Per year | Sharpe | Worst drop | 1929-32 | 2007-09 | Ahead in 20-yr stretches | Worst 20-yr vs market |
|---|---|---|---|---|---|---|---|
| **1x (market)** | 10.2% | **0.45** | −84% | −84% | −50% | n/a | n/a |
| 1.25x | 11.2% | 0.44 | −91% | −91% | −59% | 84% | 0.81 |
| 1.5x | 11.8% | 0.43 | −95% | −95% | −67% | 80% | 0.59 |
| 1.75x | 12.2% | 0.43 | −97% | −97% | −73% | 74% | 0.38 |
| **2x** | **12.4%** | 0.42 | **−98.7%** | −98.7% | −79% | **72%** | **0.21** |
| 2.5x | 11.7% | 0.42 | −99.8% | −99.8% | −87% | 69% | 0.04 |
| 3x | 9.3% | 0.41 | −100.0% | −100.0% | −92% | 60% | 0.00 |

- **Past 2x, more leverage makes less money.** 3x ends with less than 1.5x, because the crashes
  compound. This is the Kelly limit. Estimated from past data alone it was 0.8x in 1937, about 2x
  from 1970 on, and 2.4x today. Real investors should stay well under it, because the estimate is
  noisy and going over it is costly.
- **Daily reset (a 2x fund) is about the same:** 12.8% a year, worst drop −98.4%, ahead in 75% of
  20-year stretches.
- **Since 2009 (after publication)**, with no big crash: 2x made 25.9% a year against 15.0%, and 3x
  made 34%. This stretch is what makes leverage look easy.

**Real funds** (held throughout, against SPY):

| | Per year | Sharpe | Worst drop | 2020 Covid | 2022 | $10k → |
|---|---|---|---|---|---|---|
| SSO (2x), 2006-07 to 2026-10 | 15.3% | 0.57 | −81% (2007-09) | −41% | −39% | $181k |
| SPY, same | 11.2% | **0.67** | −51% | −19% | −18% | $86k |
| UPRO (3x), 2009-07 to 2026-10 | 32.1% | 0.83 | −63% | −60% | −57% | $1.25M |
| SPY, same | 14.9% | **0.95** | −24% | −19% | −18% | $112k |

**The saver** (the same amount every month for 40 years, 60 starting years from 1927 to 1986):

| | Median ending money per $1 saved | Worst | Beat 1x |
|---|---|---|---|
| 1x | $15.7 | $9.0 | n/a |
| **2x throughout** | **$39.4** | **$12.4** | **60 of 60 (100%)** |
| 2x for 20 years, then 1x | $26.0 | $9.4 | 48 of 60 (80%) |

The worst saver at 2x started in 1969 and finished in 2008's crash: still 1.13x what 1x ended with.
The best started in 1929 (7.3x): buying at 2x through the Depression lows.

**Pass rules for 2x (monthly reset):** (1) more money, whole period and since 2009: **pass**. (2)
Ahead in 80% of 20-year stretches: **fail** (72%). (3) Never wiped out and worst drop better than
−80%: **fail** (−98.7%). **Verdict: not worth holding as a lump sum.**

## Checks on my own work

- **The model matches the real fund.** 2x daily reset on French's market, 2006-07 to 2026-09: 16.0% a
  year, Sharpe 0.58, worst drop −80%. The real SSO: 15.5%, 0.57, −81%. Monthly correlation 0.995. The
  0.7% a year gap is about SSO's 0.89% fee.
- 1x reproduces the market exactly ($10k → $164M over 1927-2026, 10.2% a year).
- **Not modeled:** margin calls. A broker would force a 2x account to sell after about a third of its
  value is gone, so the real 1929-32 outcome at 2x could have been worse (sold near the bottom).
  Individual borrowing usually costs more than T-bill + 1%, so the results here flatter margin.
  Leveraged funds avoid margin calls; their cost is the fee.

## What this means

- **As a lump sum, 2x isn't safe.** It made more money in most 20-year stretches. But a 1929-type crash
  takes 99% of it, and the Sharpe ratio is always a bit lower than holding the market. It's the
  same bet, made bigger, at a cost.
- **For a monthly saver early in life, the history strongly supports some leverage.** At 2x, every
  starting year since 1927 ended ahead. That matches Ayres & Nalebuff. The catch is living
  through it: the 2x saver watched their account fall 79% in 2008 and 98% in 1929-32.
- This links to the tournament's leveraged trend: 2x only while the market is above its 200-day
  average. On the same 1927-2026 data (checked after these results, for comparison only), it lost
  39% in 1929-32 instead of 98.7%, and its worst drop was −56% instead of −98.7%. It made 17.4% a
  year with a Sharpe of 0.64, against 0.45 for the market. The trend rule is what makes 2x
  survivable. Its cost is the whipsaws in quick-rebound years, which made it lag since 2010.

## Sources

- Ayres, I. & Nalebuff, B. (2010). Lifecycle Investing. Basic Books. Also (2013) Diversification Across Time, Journal of Portfolio Management 39(2).
- Kelly, J. (1956). A New Interpretation of Information Rate. Bell System Technical Journal 35(4).
- Cheng, M. & Madhavan, A. (2009). The Dynamics of Leveraged and Inverse Exchange-Traded Funds. Journal of Investment Management 7(4).
- Data: Kenneth French daily market and T-bill; Yahoo dividend-adjusted SPY, SSO, UPRO.
