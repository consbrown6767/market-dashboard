# Macro timing model (tested 2026-11-12: failed)

*Plan fixed before any result: `PLAN.md` (commit `ec4a63b`). Code: `collectors/macro_timing.py`.
Full results: `~/MarketData/macro_timing/backtest-2026-11-12.json`. Not live.*

## In one paragraph

Each month, the algorithm predicts next month's stock return above T-bills from 14 economic
indicators: valuations, interest rates, credit spreads, inflation, share issuance (Goyal & Welch's
data). It averages the 14 predictions (Rapach, Strauss & Zhou 2010), never predicts below zero
(Campbell & Thompson 2008), and holds between 0 and 1.5x in stocks depending on the prediction.
**It worked before the research was published and failed after.** 1947-2005: 14.1% a year against
11.9% for buy-and-hold, with predictions measurably better than the plain average. 2006-2025:
8.7% a year against 11.1%, and predictions worse than the plain average. Its worst moment was 2008.
Valuations looked cheap, so it was holding 1.5x stocks into the crash: −67% against −50%.

## Results after costs

| | Per year | Sharpe | Worst drop | $10k becomes |
|---|---|---|---|---|
| **1947-2005 (before publication)** | | | | |
| Model | **14.1%** | **0.60** | −43% | **$24.4M** |
| Same rule, plain historical average | 13.3% | 0.52 | −58% | $15.5M |
| Buy and hold | 11.9% | 0.54 | −44% | $7.5M |
| **2006-2025 (after publication)** | | | | |
| Model | 8.7% | 0.47 | −67% | $52,600 |
| Same rule, plain historical average | 10.1% | 0.53 | −66% | $67,800 |
| **Buy and hold** | **11.1%** | **0.67** | −50% | **$82,400** |
| **1947-2025 (all)** | | | | |
| Model | 12.7% | 0.568 | −67% | $128M |
| Buy and hold | 11.7% | 0.572 | −50% | $61M |

Over the whole span the model made more money only because it held 1.15x stocks on average. Per unit
of risk it tied buy-and-hold (0.568 vs 0.572).

**Prediction accuracy** (out-of-sample R², improvement over the plain average; Clark & West test):

| Period | R² | p |
|---|---|---|
| 1947-2005 | **+0.92%** | 0.001 |
| 2006-2025 | **−0.38%** | 0.87 |
| 1947-2025 | +0.56% | 0.004 |

A monthly R² of about 1% is what the papers report. That's the scale of "predictable" here.

### Pass rules

| Rule | Result |
|---|---|
| 1. 2006-2025: more money and better Sharpe than buy and hold | **Fail** ($52.6k vs $82.4k) |
| 2. 1947-2025: beats the average (passes, p 0.004) and better Sharpe than buy and hold and the average version | **Fail** (Sharpe 0.568 vs 0.572) |
| 3. 2006-2025: R² above 0 | **Fail** (−0.38%) |
| 4. Better Sharpe than buy and hold in 5 of 8 decades | **Fail** (2 of 8: the 1980s and 1990s) |

### Crashes

| | Model | Buy and hold |
|---|---|---|
| 1973-74 | −43% | −43% |
| 1987 | −19% | −21% |
| 2000-02 | **−31%** | −44% |
| **2008** | **−67%** | −50% |
| Covid 2020 | −29% | −19% |
| 2022 | −17% | −18% |

Valuation signals said "cheap" during the 2008 and 2020 falls, so the model bought more on the way down.

### Each indicator alone (R², %; above 0 = better than the plain average)

| Indicator | 1947-2005 | 2006-2025 |
|---|---|---|
| Dividend-price | −0.01 | −1.66 |
| Dividend yield | −0.76 | −2.03 |
| Earnings-price | +0.01 | −2.53 |
| Payout | −0.54 | −0.08 |
| Stock variance | −0.51 | −0.78 |
| Book-to-market | −2.48 | −1.83 |
| Net share issuance | +0.04 | −2.50 |
| T-bill rate | +0.23 | **+0.16** |
| Long-term yield | −0.54 | **+0.53** |
| Long-term bond return | −0.55 | −0.04 |
| Term spread | +0.35 | −1.02 |
| Default yield spread | −0.18 | −0.63 |
| Default return spread | −0.23 | −0.64 |
| Inflation | +0.17 | −0.49 |

As Goyal & Welch found, alone almost none beat the average. Averaging them helped before 2006
because their errors partly cancel. Since 2006, nearly all point the wrong way at once.

## Checks on my own work

- **Data check:** CRSP S&P 500 total return 2008 −36.5% (published about −37%), 2022 −18.2%
  (published −18.1%).
- **Reproduces the paper:** before 2006 the combination beats the average with p = 0.001, as Rapach
  et al. found on quarterly data.
- **No look-ahead:** each prediction is fitted only on months already known. Inflation lagged an
  extra month and earnings three, for publication delays. Without those lags the result barely
  changes (2006-2025: 8.6% a year).
- **Sensitivity** (2006-2025, buy and hold 11.1%, Sharpe 0.67): risk aversion 2: 12.5% a year
  (Sharpe 0.60, only by holding more stocks); 5: 5.2%; limit 0 to 1x: 9.5% (0.62); one-month delay:
  9.1% (0.49). None beats buy and hold on Sharpe.
- **Limit:** Goyal's file is assembled after the fact. Some values (earnings, book value) may differ
  slightly from what was printed at the time.

## What this means

The best-known academic macro timing method stopped working once it was published. That's
consistent with Goyal, Welch & Zafirov (2024) and with McLean & Pontiff's "published edges shrink".
Economic data does carry a little information about next month's stocks, but only about 1% of the
monthly swings, and that little has disappeared since 2006.

## Sources

- Goyal, A. & Welch, I. (2008). A Comprehensive Look at the Empirical Performance of Equity Premium Prediction. Review of Financial Studies 21(4). Data: Amit Goyal's website, updated to 2025.
- Campbell, J. & Thompson, S. (2008). Predicting Excess Stock Returns Out of Sample: Can Anything Beat the Historical Average? Review of Financial Studies 21(4).
- Rapach, D., Strauss, J. & Zhou, G. (2010). Out-of-Sample Equity Premium Prediction: Combination Forecasts and Links to the Real Economy. Review of Financial Studies 23(2).
- Clark, T. & West, K. (2007). Approximately Normal Tests for Equal Predictive Accuracy in Nested Models. Journal of Econometrics.
- Goyal, A., Welch, I. & Zafirov, A. (2024). A Comprehensive 2022 Look at the Empirical Performance of Equity Premium Prediction. Review of Financial Studies.

## Upkeep

None: nothing live. Rerun: `macro_timing.py data`, `macro_timing.py backtest`.
