# Volatility-managed market model (tested 2026-11-12: failed)

*Plan fixed before any result: `PLAN.md` (commit `f2fb47a`). Code: `collectors/vol_managed.py`.
Full results: `~/MarketData/vol_managed/backtest-2026-11-12.json`. Not live: it failed its pass rules.*

## In one paragraph

The idea (Moreira & Muir 2017, Journal of Finance): hold more of the stock market after calm months
and less after wild ones. We tested it on 100 years of US data (Kenneth French's library, the same
data the paper used), four other markets, 49 industries and the S&P 500 itself, using only what
was known at each moment. **It does not beat buying and holding.** The version allowed to borrow up
to 1.5x ended 1937-2026 with about a third of the money ($10k → $30M against $94M) and a slightly
lower return per unit of risk. Since 2016 (after the paper) it made 9.3% a year against 14.9%.
It did one thing well: in every big crash it lost far less (2008: −11% against −50%). But it then
missed most of the recoveries (April-December 2020: +5% against +55%), and over time that cost more
than the crashes saved. The paper's own result rests almost entirely on 1926-1936. From 1937 on,
even the paper's own setup, which peeks at the future, only ties the market.

## The rule tested (fixed in the plan)

At each month-end: measure how jumpy the market was that month (variance of daily returns). Hold
c ÷ jumpiness of the market next month. c is set from past data only, so the managed version would
have been as volatile as the market. The first 10 years are warm-up. Two versions: up to 1.5x
(borrowing at the T-bill rate + 1%) and never borrowing (the rest in T-bills). Costs: 0.05% per
dollar traded.

## Results against buying and holding

US market (French, all US stocks, dividends in), after costs:

| Period | Version | Per year | Return per unit of risk (Sharpe) | Worst drop | $10k becomes |
|---|---|---|---|---|---|
| 1937-2026 | Up to 1.5x | 9.3% | 0.47 | −66% | $30.3M |
| | Never borrow | 8.6% | 0.50 | −47% | $16.5M |
| | **Buy and hold** | **10.7%** | **0.52** | −50% | **$94.4M** |
| 2016-2026 (after the paper) | Up to 1.5x | 9.3% | 0.71 | −16% | $25,900 |
| | Never borrow | 8.8% | 0.80 | −10% | $24,800 |
| | **Buy and hold** | **14.9%** | **0.83** | −25% | **$44,500** |

The pass rules, up to 1.5x version:

| Rule | Result |
|---|---|
| 1. 2016-2026: more money and better Sharpe | **Fail** (less money, 0.71 vs 0.83) |
| 2. 1937-2026: better Sharpe, clearly beyond noise, more money | **Fail** (0.47 vs 0.52; 95% range of the gap −0.18 to +0.10) |
| 3. Better Sharpe in 6 of 9 decades | **Fail** (2 of 9: the 1980s and 2000s; also behind in 1937-39) |
| 4. Better Sharpe in 3 of 4 other markets | **Fail** (0 of 4) |
| 5. Beats 95% of shuffled timings | **Fail** (85%) |

**Never-borrow version as a safer way to hold:** also fails. Its Sharpe was a hair lower over
1937-2026 (0.50 vs 0.52) and since 2016 (0.80 vs 0.83), and lower in all 4 other markets. It did
have smaller worst drops in every period.

### Crashes and recoveries (up to 1.5x; average amount held in brackets)

| Stretch | Managed | Buy and hold |
|---|---|---|
| 1987 crash (Aug-Dec) | −5% (0.56x) | −22% |
| 2000-02 tech bust | −15% (0.31x) | −45% |
| 2008 crisis (Nov 07-Feb 09) | −11% (0.22x) | −50% |
| Covid crash (Feb-Mar 2020) | −8% (0.48x) | −20% |
| **Covid rebound (Apr-Dec 2020)** | **+5% (0.37x)** | **+55%** |
| 2022 bear year | −4% (0.19x) | −20% |

The pattern: markets stay jumpy for a while after a crash, so the rule stays mostly out, and the
biggest up months come in exactly those jumpy stretches.

### Other markets (2000-07 to 2026-09, US dollars), Sharpe, managed (up to 1.5x) vs buy and hold

Developed ex US 0.28 vs 0.33, Europe 0.28 vs 0.32, Japan 0.21 vs 0.23, Asia Pacific ex Japan
0.31 vs 0.40. Worst drops were much smaller everywhere (Europe −32% vs −59%).

### 49 US industries

Managed on its own jumpiness, an industry had the better Sharpe in **7 of 49**.

### The S&P 500 itself (price only, 2000 to Oct 2026)

Up to 1.5x: Sharpe 0.46 vs 0.35 and worst drop −19% vs −53%, but slightly less money (6.1% vs 6.3% a
year). That stretch starts at the top of the 2000 bubble and has two −50% crashes, the best case
for this rule. Since 2016: 9.3% vs 12.9% a year, Sharpe 0.67 vs 0.73.

## Checks on my own work

- **Does the code reproduce the paper?** Yes. Using the paper's own setup (c chosen with the whole
  sample, no limit, no costs, 1926-2015), Sharpe 0.51 vs 0.42 and an extra 4.8% a year beyond
  market exposure (t = 3.05), matching the published figures.
- **Where the paper's edge comes from**, same setup, by period:

  | Period | Managed | Buy and hold |
  |---|---|---|
  | 1926-1936 | 0.88 | 0.29 |
  | 1937-2015 | 0.48 | 0.48 |
  | 2016-2026 | 0.63 | 0.83 |

  The Depression decade carries the result. An honest version has to spend those years learning c.
- **What hurts the honest version:** the real-time c on its own *lowers* Sharpe (1937-2026,
  uncapped, no costs: 0.44, with amounts up to 15x). The 1.5x limit helps (0.50). Costs take about
  0.03. None of it gets past the market's 0.52.
- **No look-ahead:** amounts computed on data cut at June 2008 are identical to the full run's up to
  then.
- **One-day delay** (trade the day after month-end): no real change (Sharpe 0.48).
- **High costs** (0.20% per dollar, borrowing T-bill + 3%): Sharpe 0.41.

## Variants (information only; none picked)

US 1937-2026, Sharpe (buy and hold 0.52), up to 1.5x / never borrow:

| Jumpiness measured as | 1937-2026 | 2016-2026 (buy and hold 0.83) |
|---|---|---|
| Last month, variance (the rule) | 0.47 / 0.50 | 0.71 / 0.80 |
| Last week | 0.32 / 0.35 | 0.54 / 0.54 |
| Last 3 months | 0.46 / 0.47 | 0.57 / 0.65 |
| Last 6 months | 0.47 / 0.49 | 0.59 / 0.58 |
| 1/volatility instead of 1/variance (Harvey et al.) | 0.51 / **0.54** | 0.81 / **0.85** |
| Down days only (Wang & Yan) | 0.44 / 0.47 | 0.62 / 0.69 |

The gentler 1/volatility version (never borrow) is the only one a little ahead of the market on
Sharpe in both periods. It still made less money (10.2% vs 10.7% a year; since 2016, 12.2% vs
14.9%). It was one of six tries, the gap is well within noise, and it wasn't the plan's rule, so it
counts for nothing. The last-week version's tiny amounts come from c: very calm weeks make 1/variance
huge, which pushes c, and so every other month's amount, close to zero.

## What this means

- **Holding less after wild months has not beaten the market since the 1930s**, in the US or
  abroad. The academic result is real for its sample but hangs on one decade.
- **It is a genuine drawdown cutter.** If the goal were "lose less in crashes" rather than "beat
  SPY", the never-borrow version roughly halves the worst drops for about 2 points a year less
  return. That is a trade-off, not an edge.
- This agrees with the main critique (Cederburg et al. 2020): honest, real-time versions don't hold up.

## Sources

- Moreira, A. & Muir, T. (2017). Volatility-Managed Portfolios. Journal of Finance 72(4).
- Cederburg, S., O'Doherty, M., Wang, F. & Yan, X. (2020). On the performance of volatility-managed
  portfolios. Journal of Financial Economics 138(1).
- Harvey, C., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M. & Van Hemert, O. (2018). The
  Impact of Volatility Targeting. Journal of Portfolio Management 45(1).
- Barroso, P. & Detzel, A. (2021). Do limits to arbitrage explain the benefits of volatility-managed
  portfolios? Journal of Financial Economics 140(3).
- Wang, F. & Yan, X. (2021). Downside risk and the performance of volatility-managed portfolios.
  Journal of Banking & Finance 131.
- Data: Kenneth R. French Data Library (Dartmouth), daily factors (CRSP through 2026-09).

## Upkeep

None: no job, nothing live. To rerun: `vol_managed.py data` (re-downloads French's files, updated
monthly) then `vol_managed.py backtest`.
