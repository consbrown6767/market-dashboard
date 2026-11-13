# Constant leverage: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the tests below was run. Committed so the date and contents are on
record. Changes after results go at the bottom and don't count.*

## The idea

Instead of timing the market, always hold a fixed multiple of it, for example 1.5x or 2x, and keep
that multiple through good and bad years.

- **Ayres & Nalebuff (2008, 2010), "Lifecycle Investing"**, and **(2013) "Diversification Across Time"**
  (Journal of Portfolio Management): young savers should hold about 2x stocks early in life. Their
  claim is that, in US history since 1871, this beat 100% stocks for almost every generation, with
  a smaller risk of a bad outcome.
- **Kelly (1956)**; **Thorp**: the leverage that grows wealth fastest is about (market return − T-bill)
  ÷ variance. Above it, more leverage makes *less* money over time, because big losses compound.
- **Cheng & Madhavan (2009), "The Dynamics of Leveraged and Inverse ETFs"**: funds that reset to 2x
  every day lose to "2x over a long period" when markets are choppy.

**Leverage can't raise the Sharpe ratio:** it scales return and risk together, and borrowing costs more
than T-bills. So this is not a "better per unit of risk" test. It asks two things. Does a fixed
multiple make more money over long stretches? And how bad were the crashes?

## Data

- **US market:** French daily value-weighted market return and T-bill, 1926-07 to 2026-09.
- **Real funds:** Yahoo dividend-adjusted SSO (2x S&P 500, from 2006-06), UPRO (3x, from 2009-06) and
  SPY. Their fees and financing are already in the prices.

## The strategies (fixed)

Leverage **L** = 1.25, 1.5, 1.75, 2, 2.5, 3 (and 1 = the market).
- **Daily reset** (what a leveraged fund does): each day, L × the market's return, minus borrowing on
  (L − 1) at the T-bill + 1% a year. Rebalancing costs 0.05% of each dollar traded.
- **Monthly reset** (what a margin account does): set to L at each month's start, then let it drift.
  Same borrowing cost and trading cost. If the account's value reaches zero, it's wiped out for good.

## Pass rules

**2x (monthly reset) is worth holding long-term** only if all of these hold:
1. more money than the market over 1927-2026, **and** over 2009-2026 (after publication);
2. ahead of the market in at least 80% of 20-year stretches (one starting each January, 1927 to
   2006);
3. never wiped out, and its worst drop is no worse than −80%.

**Real funds:** SSO and UPRO held throughout, against SPY, from each fund's start. More money is
reported, not judged (they start after 2008's crash, so it's one lucky stretch).

## Also (information only)

- The same three rules for every L, both resets.
- The best fixed L in hindsight. The Kelly L estimated each year from past data only.
- 10-year stretches. Worst years. The 1929-1932 and 2007-2009 crashes.
- **A saver** (Ayres & Nalebuff's setting): the same amount every month for 40 years, starting each
  January 1927-1986. Ending money for 1x; 2x throughout; and 2x for the first 20 years, then 1x.

## Changes after results

(none yet)
