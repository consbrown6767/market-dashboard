# Pairs trading model (tested 2026-11-12: failed)

*Plan fixed before any result: `PLAN.md` (commit `ec4a63b`). Code: `collectors/pairs_model.py`.
Full results: `~/MarketData/pairs/backtest-2026-11-12.json`. Not live.*

## In one paragraph

Each month, the model finds the 20 pairs of S&P 500 stocks in the same sector whose prices moved most
closely together over the past year. Over the next 6 months, when a pair drifts 2 standard
deviations apart, it buys the laggard and shorts the leader, then closes when they meet. This is
Gatev, Goetzmann & Rouwenhorst's (2006) method exactly, using the companies that were actually in
the index at the time. **From 2017 to Oct 2026 it earned nothing.** It made −0.5% a year after
costs, +0.2% a year before costs (both relative to T-bills), and was above T-bills in 5 of 10
years. It was truly market-neutral (beta 0.01), but with no profit to show for it.

## Results (Jan 2017 to Oct 2026, 118 months)

| | Per year | Sharpe | Worst drop | $10k becomes |
|---|---|---|---|---|
| Pairs (T-bill interest plus pair profits, after costs) | 2.0% | −0.27 | −3% | $12,100 |
| SPY | 14.9% | 0.82 | −24% | $39,200 |

- **Profit beyond T-bills:** −0.54% a year after costs (t −0.9); +0.16% before costs (t 0.3).
- **Year by year** (beyond T-bills): 2017 −3.5%, 2018 +0.4%, 2019 −1.9%, 2020 +2.4%, 2021 −2.4%,
  2022 +1.8%, 2023 +1.0%, 2024 −2.6%, 2025 −2.7%, 2026 (to Oct) +1.9%.
- **Activity:** 2,964 trades over 118 portfolios. **Only 42% of opened trades converged**; the rest
  were still apart at the end of the 6 months (or a stock left).

### Pass rules

| Rule | Result |
|---|---|
| 1. Makes money beyond T-bills, t ≥ 2 | **Fail** (−0.54% a year) |
| 2. Better Sharpe than SPY | **Fail** (−0.27 vs 0.82) |
| 3. Above T-bills in 6 of 10 years | **Fail** (5 of 10) |

### Variants (information only)

| Version | Beyond T-bills, per year | Converged |
|---|---|---|
| Plan (same sector, 20 pairs, costs) | −0.54% | 42% |
| No costs | +0.16% | 42% |
| Any sector (Gatev's original) | −0.50% | 42% |
| 10 pairs | −0.66% | 44% |
| 50 pairs | −0.34% | 39% |

## Checks on my own work

- **The engine works:** on made-up prices where the gap between two stocks snaps back, it made
  $0.53 per $1 over 6 months; on random pairs, about zero; a delisted stock closes the trade on its
  last day.
- **No survivorship bias to speak of:** members come from Wikipedia's list as it stood each
  year-end (edit history, `shared/sp500_history.json`). Alpaca had prices for 747 of the 766
  companies that were members at some point from 2015 to 2026. 492-501 were usable each year. The 19
  missing are mostly companies bought in 2015-16 or old tickers of renamed companies.
- **Ticker reuse:** a stock's series ends at its first missing day, so a later security reusing an
  old ticker can't leak in.
- **No look-ahead:** pairs and their normal gap come from the 12 months before; trades act at the
  next day's close.

## What this means

The classic pairs trade was a real edge from 1962 to about 2000 (Gatev et al.). Do & Faff found it
fading after 2002, and in S&P 500 stocks over the last ten years it's gone. Pairs that drift apart
now usually keep drifting: fewer than half come back within 6 months. Almost certainly that's
because quant funds have traded the edge away. Fancier versions (cointegration, machine learning)
are what professionals moved to. The research review (Krauss 2017) finds they do better, but mostly
on data before costs and before 2015.

## Sources

- Gatev, E., Goetzmann, W. & Rouwenhorst, K. G. (2006). Pairs Trading: Performance of a Relative-Value Arbitrage Rule. Review of Financial Studies 19(3).
- Do, B. & Faff, R. (2010). Does Simple Pairs Trading Still Work? Financial Analysts Journal 66(4).
- Do, B. & Faff, R. (2012). Are Pairs Trading Profits Robust to Trading Costs? Journal of Financial Research 35(2).
- Krauss, C. (2017). Statistical Arbitrage Pairs Trading Strategies: Review and Outlook. Journal of Economic Surveys 31(2).

## Upkeep

None: nothing live. Rerun: `pairs_model.py members` (Wikipedia, slow on purpose), `prices`, `backtest`.
