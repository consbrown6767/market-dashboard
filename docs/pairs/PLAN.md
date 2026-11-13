# Pairs trading model: the plan, fixed before any result was seen

*Written 2026-11-12, before any price was downloaded for it or any result looked at. Committed to
git so the date and contents are on record. Changes after results go under "Changes after
results" and don't count toward the verdict.*

## The idea in plain English

Find two stocks that have moved almost in lockstep for a year, like two oil majors. When they
drift apart, buy the one that fell behind and short the one that ran ahead, betting they snap back
together. Close the bet when they meet again. Each pair is long one stock and short the other, so
the market's ups and downs mostly cancel out.

## Research

- **Gatev, Goetzmann & Rouwenhorst (2006), Review of Financial Studies**, "Pairs Trading:
  Performance of a Relative-Value Arbitrage Rule". The standard method, used here exactly: pairs
  chosen by the smallest distance between their normalized price paths over 12 months, traded over
  the next 6 months, opened at a 2-standard-deviation gap, closed when the prices cross. US stocks
  1962-2002: profitable, even after estimated costs.
- **Do & Faff (2010, Financial Analysts Journal)**, "Does Simple Pairs Trading Still Work?": the
  profits fell sharply after about 2002. Pairs from the same industry held up best. **Do & Faff
  (2012)**: after trading costs, mostly unprofitable since 1989, except the most similar pairs.
- **Krauss (2017, Journal of Economic Surveys)**, review of pairs trading: the simple distance
  method is the benchmark every fancier method gets compared with.
- **Known before testing:** the published results point to small or no profits in recent years.
  This test checks 2017-2026 for ourselves, after costs.

## Data

- **Who was in the S&P 500, when:** the Wikipedia list "List of S&P 500 companies" as it stood at
  each year-end, 2014-2025 (from the page's edit history), with each company's GICS sector at the
  time. A stock can be paired in a year only if it was a member at the start of that year. That
  keeps companies that later dropped out or were bought, which removes most of the survivorship bias.
- **Prices:** Alpaca's full-market daily bars, adjusted for splits and dividends (`daily_bars_adj`),
  2016-01 to today. Companies Alpaca has no data for are counted and reported.
- **T-bill:** French's 1-month T-bill (`ff_daily`).

## The rule (v1, fixed)

A new portfolio starts at the beginning of every month, and each runs for 6 months, so 6 portfolios
are open at once. The strategy's monthly return is their average.

1. **Formation (the 12 months before the start):** stocks that were members, with a price every
   trading day. Each stock's total-return price is set to 1 on the first day.
2. **Pairs:** within the same GICS sector, the **20 pairs with the smallest sum of squared
   differences** between their normalized prices. A stock may be in more than one pair.
3. **Trading (the next 6 months):** prices are set to 1 again at the start. When the gap between a
   pair's prices exceeds **2 standard deviations** of its gap during formation, buy $1 of the
   lower one and short $1 of the higher one. **Trades happen at the next day's close** (Gatev's
   "wait one day" version, which avoids the bounce between buy and sell prices). Close when the
   prices cross, also at the next day's close, or on the last day. A pair may reopen.
4. **Delistings:** if a stock stops trading (bought out, bankrupt), the pair is closed at its last price.
5. **Returns:** the profit on all 20 pairs ÷ 20 ("return on committed capital", Gatev's main
   measure). The money set aside also earns the T-bill rate.
6. **Costs:** 0.05% of each dollar traded, each leg, opening and closing (0.2% a round trip per
   pair); 0.5% a year to borrow the shorted stock while open.

Scored months: 2017-01 (first trading start) to 2026-10.

## Pass rules

1. **It makes money:** monthly return above the T-bill, after costs, with a t-statistic of at least
   2 (Newey-West; about 10 years of data).
2. **Worth holding:** better Sharpe ratio than SPY over the same months.
3. **Steady:** return above the T-bill in at least 6 of the 10 calendar years.

## Always reported

- The same without costs; the any-sector version (Gatev's original); 10 and 50 pairs. Information only.
- How much it moves with the market (beta to SPY), worst drop, trades per pair, the share of
  opened pairs that converge, and how many members had no Alpaca data.

## Changes after results

(none yet)
