# Nine classic strategies against the market (tested 2026-11-12)

*Plan fixed before any result: `PLAN.md` (commit `dfaee9a`). Code: `collectors/classic_strategies.py`.
Full results (every year, decade and crash): `~/MarketData/classic_strategies/backtest-2026-11-12.json`.
Data: Kenneth French's library (CRSP; includes every stock that ever traded, so no survivorship
bias), US 1926-2026, four other markets 1990-2026.*

## In one paragraph

Nine famous published strategies, all long-only, all doable with ordinary funds, were tested
against simply holding the whole US market, after costs. The main test was the years after each
paper came out. **None passed the plan's "beats the market" bar.** Three came close: industry
momentum, small value and stock momentum each made more money than the market over 100 years. But
each edge shrank by a third to two-thirds after publication, and none was strong enough to rule
out luck. One passed the plan's other bar, **"safer, not better": the 10-month trend rule**. It
made a little less than the market but with much smaller crashes, in the US and abroad.

## The scorecard

$10,000 after each strategy's publication date, to Sept 2026, after costs:

| # | Strategy (paper) | After publication from | Strategy | Market | Sharpe, strategy vs market | Worst drop, strategy vs market | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Trend, 10-month (Faber 2007) | 2006 | $68k | $92k | **0.76** vs 0.66 | **−18%** vs −50% | **Safer, not better** |
| 2 | Trend, 12-month (Moskowitz, Ooi & Pedersen 2012) | 2010 | $47k | $92k | 0.67 vs 0.87 | −28% vs −25% | Fail |
| 3 | Halloween, Nov-Apr only (Bouman & Jacobsen 2002) | 1999 | $65k | $112k | 0.48 vs 0.51 | −30% vs −50% | Fail |
| 4 | Turn of the month (Lakonishok & Smidt 1988) | 1987 | $105k | $710k | 0.44 vs 0.58 | −18% vs −50% | Fail |
| 5 | Stock momentum, top tenth (Jegadeesh & Titman 1993) | 1990 | **$670k** | $461k | 0.51 vs 0.59 | −53% vs −50% | Fail |
| 6 | Industry momentum, top 10 of 49 (Moskowitz & Grinblatt 1999) | 1996 | **$384k** | $221k | **0.63** vs 0.57 | −47% vs −50% | Fail (near miss) |
| 7 | Low volatility, lowest fifth (Ang et al. 2006) | 2001 | $91k | $101k | **0.64** vs 0.54 | −37% vs −50% | Fail |
| 8 | Small value (Fama & French 1992) | 1991 | **$809k** | $491k | 0.59 vs 0.63 | −62% vs −50% | Fail (near miss) |
| 9 | Profitability, top fifth (Novy-Marx 2013) | 2011 | **$86k** | $79k | **0.92** vs 0.87 | −24% vs −25% | Fail |

Each row's market column covers the same months as that strategy, so the rows have different
starting points.

### Each pass rule

| Strategy | 1. After publication: more money and better Sharpe | 2. 100-year edge t ≥ 3 | 3. Ahead in 60% of decades | 4. Ahead in 3 of 4 other markets |
|---|---|---|---|---|
| Trend 10-month | no (less money) | no (−1.0) | no (3 of 9) | **yes (3 of 4)** |
| Trend 12-month | no | no (−1.0) | no (3 of 9) | no (1 of 4) |
| Halloween | no | no (−2.0) | no (3 of 9) | **yes (4 of 4)** |
| Turn of the month | no | no (−2.0) | no (3 of 9) | no (0 of 4) |
| Stock momentum | no (lower Sharpe) | **yes (3.07)** | **yes (6 of 9)** | no (0 of 4) |
| Industry momentum | **yes** | no (**2.99**) | **yes (6 of 9)** | no data |
| Low volatility | no (less money) | no (−0.9) | **yes (3 of 5)** | no data |
| Small value | no (lower Sharpe) | no (**2.91**) | **yes (7 of 9)** | **yes (4 of 4)** |
| Profitability | **yes** | no (1.3) | **yes (4 of 5)** | no (1 of 4) |

## What stands out

**Every edge shrank after publication**, as McLean & Pontiff found across 97 predictors. Gap over the
market, per year:

| Strategy | Before publication | After |
|---|---|---|
| Stock momentum | +4.8% | +2.3% |
| Industry momentum | +3.6% | +2.1% |
| Small value | +6.5% | +2.3% |
| Profitability | +0.8% | +0.5% |
| Trend 10-month | −1.2% | −2.1% |
| Turn of the month | −1.8% | −5.8% |

**The best after-publication result could be luck.** The deflated Sharpe ratio test (Bailey & López de
Prado) asks whether the best of the nine is better than you'd expect from picking the luckiest of
nine coin-flippers. For the best one (industry momentum), the chance its edge is real is **11%**.

**The near misses:**
- **Industry momentum** passed rule 1 and missed rule 2 by a hair (t 2.99 against 3). It's
  doable with sector funds. Costs are the risk: it trades about 61% of the portfolio a month, and
  its edge after publication vanishes at 0.39% per dollar traded.
- **Small value** made more money after publication ($809k vs $491k) and won in all four other
  markets by a lot (Developed ex US: $126k vs $46k from 2000). It failed because the ride was
  rougher: lower Sharpe since 1991, −62% worst drop, and it lagged the market in the 1990s and 2010s.
- **Stock momentum** made the most over 100 years ($10k → $3.0 billion vs $164 million). But since
  2000 it lost to the market in all four other markets, and it would need costs under 0.44% a month.
  Real costs for a top-decile momentum portfolio are in that range (Novy-Marx & Velikov).

**The safe one:**
- **Trend, 10-month:** hold the market while it's above its 10-month average, else T-bills.
  Since 2006: 9.7% a year vs 11.3%, but the worst drop was −18% against −50%. In the 2008 crisis it
  lost 3% against the market's 50%. Over 100 years its worst drop was −44% against −84%.
  It also made more money than the market from 2000 in 3 of 4 other markets. The cost is missing
  sharp rebounds: Apr-Dec 2020, +29% vs +55%.

## Costs used

Switches in and out (strategies 1-4): 0.05% of the dollars traded. Industry baskets: 0.10% per dollar
traded, from the actual trades. French portfolios (trades not visible), a fixed amount a month:
momentum 0.25%, small value and low volatility 0.05%, profitability 0.03%. Break-even monthly cost
after publication: momentum 0.44%, small value 0.24%, profitability 0.07%.

## Checks on my own work

- No look-ahead: every signal is fixed at the month-end before it's used. French builds its
  portfolios from data through the month before, too.
- French's portfolios include delisted stocks, so the past isn't limited to today's survivors.
- The decade rule counts only whole decades (the 1930s through the 2010s).
- Limits: French portfolios are paper portfolios. Real funds (e.g. momentum or small-value ETFs)
  charge fees and trade differently. The other markets start in 1990, so they cover 26 years.

## What this means for "beat SPY"

1. **No classic long-only strategy clears an honest bar.** The ones that beat the market over 100
   years did it mostly before they were published, and they have had long bad stretches since
   (small value in the 2010s, momentum in the 2000s).
2. **A real, durable finding: trend-following cuts crashes**, in every market and period we have, for
   a modest cost in return. That's a risk tool, not a way to beat SPY.
3. Possible next tests, each needing its own plan before results: trend applied to the
   near-miss strategies (industry momentum or small value only while the market is above its
   10-month average), and industry momentum with sector ETFs at real ETF costs.

## Sources

- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation. Journal of Wealth Management.
- Moskowitz, T., Ooi, Y. H. & Pedersen, L. H. (2012). Time Series Momentum. Journal of Financial Economics.
- Bouman, S. & Jacobsen, B. (2002). The Halloween Indicator. American Economic Review.
- Lakonishok, J. & Smidt, S. (1988). Are Seasonal Anomalies Real? Review of Financial Studies.
- Jegadeesh, N. & Titman, S. (1993). Returns to Buying Winners and Selling Losers. Journal of Finance.
- Moskowitz, T. & Grinblatt, M. (1999). Do Industries Explain Momentum? Journal of Finance.
- Ang, A., Hodrick, R., Xing, Y. & Zhang, X. (2006). The Cross-Section of Volatility and Expected Returns. Journal of Finance.
- Fama, E. & French, K. (1992). The Cross-Section of Expected Stock Returns. Journal of Finance.
- Novy-Marx, R. (2013). The Other Side of Value: The Gross Profitability Premium. Journal of Financial Economics.
- On testing: McLean & Pontiff (2016), Journal of Finance; Harvey, Liu & Zhu (2016), Review of Financial
  Studies; Bailey & López de Prado (2014), Journal of Portfolio Management; Novy-Marx & Velikov (2016),
  Review of Financial Studies.

## Upkeep

None: nothing live. Rerun: `vol_managed.py data`, `classic_strategies.py data`, `classic_strategies.py backtest`.
