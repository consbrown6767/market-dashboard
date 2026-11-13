# Country stock-market rotation: the plan, fixed before any country data was loaded

*Written 2026-11-13, before any country fund's prices were downloaded. Changes go at the bottom and don't count.*

## The idea

Choose among national stock markets rather than stocks. The research finds cheap countries and countries with
strong past returns tend to beat the rest:
- **Momentum:** Richards (1997), "Winner-Loser Reversals in National Stock Market Indices"; Bhojraj &
  Swaminathan (2006).
- **Value:** Asness, Liew & Stevens (1997), "Parallels between the Cross-sectional Predictability of Stock and
  Country Returns"; Keimling (2016).
- **Value and momentum together:** Asness, Moskowitz & Pedersen (2013). The two work best combined, because they
  tend to fail at different times.
- **Low volatility across countries:** Blitz & van Vliet (2007).

Everything here is after those papers. It's tested as a **long-short overlay on SPY**: long the best third of
countries, short the worst third, through the real iShares country funds.

## Data (Yahoo, real funds: fees are already in the prices)

- **From 1996-03:** EWA Australia, EWC Canada, EWD Sweden, EWG Germany, EWH Hong Kong, EWI Italy, EWJ Japan,
  EWK Belgium, EWL Switzerland, EWM Malaysia, EWN Netherlands, EWO Austria, EWP Spain, EWQ France, EWS Singapore,
  EWU UK, EWW Mexico, and SPY (US).
- **Added when they start:** EWY Korea, EWT Taiwan, EWZ Brazil (2000), EZA South Africa (2003).
- **Prices:** monthly returns from dividend-adjusted closes.
- **Dividend yield:** dividends paid over the last 12 months ÷ the unadjusted price.

## The versions (8, all counted)

Ranked at each month-end, held the next month. Long the top max(2, n÷3) countries, short the bottom ones; longs
total 1, shorts −1.

| # | Version | Rank by |
|---|---|---|
| C1 | Momentum 12-1 | Return over months t−11 to t−1 (skipping the last month) |
| C2 | Momentum 6 months | Return over the last 6 months |
| C3 | Short-term reversal | Last month's return (long the losers) |
| C4 | Value | Trailing 12-month dividend yield (long the highest) |
| C5 | Low volatility | Volatility of daily returns over the last 12 months (long the calmest) |
| C6 | Value + momentum | Average of the C1 and C4 ranks |
| C7 | Trend across countries | Long-only: equal weight in countries above their 10-month average, the rest in cash. **Against SPY directly, not as an overlay** |
| C8 | Momentum with a market filter | C1, but flat whenever the equal-weight average of all countries is below its own 10-month average |

**Costs:** 0.10% per dollar traded, plus 0.5% a year to borrow what's shorted.

## Sandbox and vault

- **Sandbox: 1997-04 to 2010-12** (12 months of history needed first).
- **Vault: 2011-01 to 2026-10.** It's locked in code until `FINALISTS.md` is committed. Finalists: the top three
  sandbox Sharpe ratios of at least 0.3 (C7: the Sharpe of its returns over T-bills).

## Pass rules in the vault ("worth live testing")

- **Overlays (C1-C6, C8):** SPY + the overlay (1x) has more money **and** a better Sharpe ratio than SPY, **and**
  the overlay made money in both halves (2011-2018 and 2019-2026).
- **C7:** more money and a better Sharpe ratio than SPY, **or** "safer, not better": a better Sharpe ratio and a
  smaller worst drop. Either way, in both halves.

## Changes

(none yet)
