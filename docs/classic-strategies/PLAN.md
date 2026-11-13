# Nine classic strategies against the market: the plan, fixed before any result was seen

*Written 2026-11-12, before any of these strategies was run on our data. Committed to git so the
date and contents are on record. Changes after results go under "Changes after results" and don't
count toward the verdict.*

## The question

Does any well-known, published, long-only strategy beat simply holding the whole US market
("SPY") after costs, **in the years after it was published**? Every strategy here can be done by
an ordinary investor (index funds, sector or factor funds, or a stock basket), with no shorting
and no borrowing.

## Advice from the research on testing, and how this plan uses it

- **Results shrink after publication.** McLean & Pontiff (2016, Journal of Finance), 97 published
  predictors: returns are 26% lower just outside the paper's sample and 58% lower after
  publication. → **The main test is each strategy's after-publication period**, which no author
  could have tuned on.
- **Too many people have tried too many things.** Harvey, Liu & Zhu (2016, Review of Financial
  Studies): after hundreds of published factors, a new one needs a t-statistic of about 3, not 2.
  → Full-period edges must clear t ≥ 3.
- **Backtests overfit.** Bailey & López de Prado (2014, Journal of Portfolio Management), the
  "deflated Sharpe ratio": the best of N tries looks good by luck alone. → All 9 strategies are
  reported, and the best one is checked against the luck of picking the best of 9.
- **Costs kill high-turnover strategies.** Novy-Marx & Velikov (2016, Review of Financial
  Studies): momentum costs roughly 0.5% a month as a long-short; strategies trading more than half
  the portfolio a month rarely survive. → Costs charged as below; each strategy's break-even cost
  is reported.
- **Survivorship.** French's data (CRSP) includes every stock that ever traded, including the
  ones that died. That fixes the biggest flaw of our earlier stock tests.
- **One market can be luck.** → Repeat in other markets where French has the data.

## Data (all free, Kenneth French's data library, Dartmouth)

US market, T-bill, 49 industries (daily, 1926-07 to 2026-09; already in `ff_daily`); four other
markets (daily, 1990-07 on; in `ff_daily`); monthly sorted portfolios: 10 momentum deciles
(1927 on), small/big × value (1926 on), variance quintiles (1963 on), profitability quintiles
(1963 on); for other markets, 6 portfolios by size × momentum, size × value, size × profitability
(1990 on). Everything value-weighted, dividends included, in US dollars.

## The nine strategies (each fixed, with the paper's own settings)

"After publication" starts the January after the paper's data ended.

| # | Name | Rule | Paper (its data) | After publication |
|---|---|---|---|---|
| 1 | Trend, 10-month | Hold the market next month if its total-return level is above its average over the last 10 month-ends; else T-bills | Faber (2007) (to 2005) | 2006-01 |
| 2 | Trend, 12-month | Hold the market if its return over the last 12 months beat the T-bill's; else T-bills | Moskowitz, Ooi & Pedersen (2012) (to 2009) | 2010-01 |
| 3 | Halloween | Market from November through April, T-bills May through October | Bouman & Jacobsen (2002) (to Aug 1998) | 1999-01 |
| 4 | Turn of the month | Market only on the last trading day of each month and the first 3 of the next; else T-bills | Lakonishok & Smidt (1988) (to 1986) | 1987-01 |
| 5 | Stock momentum | French's top decile by return over months t-12 to t-2 (biggest winners) | Jegadeesh & Titman (1993) (1965-1989) | 1990-01 |
| 6 | Industry momentum | The 10 of 49 industries with the best last-6-month return, equal amounts, monthly | Moskowitz & Grinblatt (1999) (1963-1995) | 1996-01 |
| 7 | Low volatility | French's lowest-variance quintile (past 60 days' variance) | Ang, Hodrick, Xing & Zhang (2006) (1963-2000) | 2001-01 |
| 8 | Small value | French's small-cap, high book-to-market portfolio (2×3 sort) | Fama & French (1992) (1963-1990) | 1991-01 |
| 9 | Profitability | French's top quintile by operating profitability | Novy-Marx (2013) (1963-2010) | 2011-01 |

**Costs:**
- Strategies 1-4 and 6: 0.05% of each dollar traded (0.10% for 6, which trades baskets),
  computed from the actual trades.
- French portfolios, where we can't see the trades, are charged a fixed monthly cost: momentum
  0.25%, small value 0.05%, low volatility 0.05%, profitability 0.03%. These are my estimates from
  Novy-Marx & Velikov's ranges.

**Scoring start:** the first month every input exists (trend: after 12 months; industry momentum:
after 6), from 1927 on in the US.

## Pass rules: "beats the market"

A strategy **beats the market** only if all of these hold:

1. **After publication:** more money at the end **and** a better Sharpe ratio than holding the market.
2. **Full period:** the monthly gap over the market has a t-statistic of at least 3 (Harvey, Liu & Zhu).
3. **Decades:** more money than the market in at least 60% of the full decades it covers.
4. **Other markets** (strategies 1-5, 8, 9): more money than that market, 2000-2026, in at least 3 of
   the 4 (Developed ex US, Europe, Japan, Asia Pacific ex Japan). For 5, 8 and 9 abroad, the closest
   French portfolio: big winners, small value, big high-profitability.

Strategies 1-4 are in T-bills part of the time, so they may instead pass as **"safer, not
better"**: after publication **and** over the full period, a better Sharpe ratio and a smaller
worst drop than the market.

## Always reported (never changing a verdict)

- Each strategy's results before vs after publication (how much it shrank).
- Break-even cost: the monthly cost at which its after-publication edge would be zero.
- The deflated Sharpe ratio test for the best after-publication Sharpe ratio among the nine.
- Year-by-year and crash-by-crash results against the market.

## If one passes

Propose to the owner a live paper record. Nothing is traded.

## Changes after results

(none yet)
