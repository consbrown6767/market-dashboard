# Math exploration (2026-11-13): one finalist passed the vault, weakly

*Plan fixed before any data: `PLAN.md` (commit `26eca5e`). Finalists fixed before the vault opened:
`FINALISTS.md` (commit `25fa708`). Code: `collectors/exploration.py`. Results:
`~/MarketData/exploration/explore-2026-11-13.json` and `holdout-2026-11-13.json`. Not live.*

## In one paragraph

Eight methods from the research literature were run on 1946-2005 only, 15 versions in all. The
2006-2026 data stayed locked in a "vault" that the code would not open:
- **Covariance math:** eigenvalues (the absorption ratio), Mahalanobis distance (turbulence), and random-matrix
  and Ledoit-Wolf cleaning for minimum-variance portfolios.
- **Hidden-state and regression models:** a hidden Markov model of calm and stormy markets, lasso regression
  across industries, and boosted trees.
- **Market measures:** the variance risk premium from options prices, and a fractal (variance-ratio) trend filter.

**Most failed already in the sandbox,** and none cleared the luck test there. The rule then sent the top three
to the vault, where two failed. The third passed:
- **Variance risk premium:** hold more SPY when options are expensive compared with how much the market has
  actually moved.
- **The result:** more money than SPY ($127k vs $89k) and a slightly better Sharpe ratio (0.70 vs 0.66),
  with a much smaller worst drop (−37% vs −51%).
- **The catch:** the Sharpe edge is well within luck (95% range −0.24 to +0.34). After the paper's 2009
  publication it made more money but had a *lower* Sharpe ratio than SPY and a bigger worst drop. Most of its
  edge came from 2008-09.

## Sandbox, 1946-2005 (US market: 11.2% a year, Sharpe 0.50, worst drop −46%)

| Version | Per year | Sharpe | Worst drop | Sharpe gap | Chance it's real* |
|---|---|---|---|---|---|
| 6b Minimum variance, Ledoit-Wolf | 11.6% | **0.58** | −35% | **+0.08** | 0.02 |
| 6a Minimum variance, random-matrix clipping | 11.5% | 0.57 | −38% | +0.07 | 0.02 |
| 4b Variance risk premium, regression (1993-2005) | 12.2% | 0.54 | −38% | +0.04 | 0.14 |
| 7a Boosted trees on industries | **13.1%** | 0.53 | −49% | +0.04 | 0.01 |
| 3b Hidden Markov, monthly | 10.4% | 0.51 | −32% | +0.01 | 0.00 |
| 8a Variance-ratio trend filter | 10.3% | 0.50 | −36% | +0.00 | 0.00 |
| 5a Lasso lead-lag, timing | 11.1% | 0.49 | −46% | 0.00 | 0.00 |
| 5b Lasso lead-lag, rotation | 11.7% | 0.47 | −57% | −0.02 | 0.00 |
| 7b Ridge on industries | 11.4% | 0.44 | −57% | −0.06 | 0.00 |
| 4a Variance risk premium, above median (1990-2005) | 8.2% | 0.45 | −21% | −0.06 | 0.07 |
| 3a Hidden Markov, daily | 8.9% | 0.41 | −36% | −0.09 | 0.00 |
| 1b Absorption ratio, daily | 7.4% | 0.30 | −29% | −0.20 | 0.00 |
| 2a Turbulence, monthly | 7.0% | 0.28 | −30% | −0.22 | 0.00 |
| 1a Absorption ratio, monthly | 7.1% | 0.27 | −32% | −0.23 | 0.00 |
| 2b Turbulence, daily | 1.4% | −0.25 | −72% | −0.74 | 0.00 |

*Deflated Sharpe (Bailey & López de Prado) of the gap, allowing for 15 tries. 0.95 would be convincing.

**What failed, and why:**
- **The "fragility" warnings** (absorption ratio, turbulence) were out of the market 30-43% of the time, and paid
  for it in missed gains. Daily turbulence flipped 68 times a year, and trading costs ate it. The papers report
  improvements, but here they cost 4% a year.
- **Flaw in my turbulence version:** the distance grows with the number of industries, which grew from 43 to 49.
  A corrected version (divided by the number of industries, checked afterwards) is still far behind: Sharpe 0.35
  vs 0.50.
- **Boosted trees made the most money** (13.1% a year) but with a deeper worst drop, and its edge is within luck.
- **The hidden Markov model** found real calm and stormy states, but switching on them was no better than holding.

## The vault, 2006-01 to 2026-09 (opened once; SPY: 11.1% a year, Sharpe 0.66, worst drop −51%, $10k → $89k)

| Finalist | Per year | Sharpe | Worst drop | $10k → | Sharpe gap, 95% range | Verdict |
|---|---|---|---|---|---|---|
| 6b Minimum variance, Ledoit-Wolf | 8.9% | 0.61 | −40% | $58.6k | −0.06 (−0.26 to +0.16) | fails |
| 6a Minimum variance, random-matrix | 9.1% | 0.62 | −39% | $61.3k | −0.04 (−0.24 to +0.19) | fails |
| **4b Variance risk premium** | **13.0%** | **0.70** | **−37%** | **$126.8k** | +0.03 (−0.24 to +0.34) | **beats SPY (by the rule)** |

## Looking harder at the one that passed (after the vault; information only)

| Check | VRP | SPY |
|---|---|---|
| Average weight in SPY (0 to 1.5x) | **0.99x**: no extra leverage on average | 1x |
| Same average weight, but held constant (0.99x) | n/a | $88.4k, Sharpe 0.66 |
| Borrowing at T-bill + 1% above 1x | $121.8k, Sharpe 0.69 | $89.4k, 0.66 |
| Capped at 1x (never borrows) | $77.7k, Sharpe **0.70**, worst drop **−30%** | $89.4k, 0.66, −51% |
| **After publication, 2010-2026** | $104.2k, Sharpe **0.80**, worst drop −33% | $91.9k, Sharpe **0.90**, −24% |
| Years ahead of SPY | 12 of 21 | |
| Without 2008-09 | $119.3k | $112.0k |

**Read it like this:** the timing really added something. At the same average exposure, holding SPY steadily
made $88k, and timing it made $127k. But most of the gain came from 2008-09: it held 0.58x through 2008 and
1.1x into the 2009 rebound. Since 2010 it has made a bit more money with more risk, and a lower Sharpe ratio.
It also hurt in some years: 2020 (+2% vs +18%, it was out for the rebound) and 2022 (−25% vs −18%, it was 1.3x
going in).

The weight mostly sat between the limits: 8% of months at 0, 20% at 1.5x, 71% in between.

## What this means

1. **The best idea from the whole exploration is the variance risk premium.** It's an economic idea, not a
   statistical pattern: option buyers overpay for protection, more so when fear is high. That makes it the most
   believable kind of signal. But the evidence is like leveraged trend's: it shines in one crisis and is
   ordinary otherwise.
2. **The right next step is a live paper record**, next to the three rules already running. The inputs (the
   S&P 500 and the VIX) are already collected every evening. It needs the owner's OK.
3. **Fancier math didn't help.** Eigenvalues, hidden Markov models, lasso and boosted trees all failed to beat
   the market by more than luck. The two minimum-variance portfolios did well before 2006 (the low-volatility
   effect) but lagged in 2006-2026.

## Sources

- Kritzman, M., Li, Y., Page, S. & Rigobon, R. (2011). Principal Components as a Measure of Systemic Risk. Journal of Portfolio Management 37(4).
- Kritzman, M. & Li, Y. (2010). Skulls, Financial Turbulence, and Risk Management. Financial Analysts Journal 66(5).
- Hamilton, J. (1989). A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle. Econometrica 57(2).
- Ang, A. & Bekaert, G. (2002). International Asset Allocation with Regime Shifts. Review of Financial Studies 15(4).
- Nystrup, P., Madsen, H. & Lindström, E. (2017). Long Memory of Financial Time Series and Hidden Markov Models with Time-Varying Parameters. Journal of Forecasting 36(8).
- Bollerslev, T., Tauchen, G. & Zhou, H. (2009). Expected Stock Returns and Variance Risk Premia. Review of Financial Studies 22(11).
- Hong, H., Torous, W. & Valkanov, R. (2007). Do Industries Lead Stock Markets? Journal of Financial Economics 83(2).
- Rapach, D., Strauss, J., Tu, J. & Zhou, G. (2019). Industry Return Predictability: A Machine Learning Approach. Journal of Financial Data Science 1(3).
- Laloux, L., Cizeau, P., Bouchaud, J.-P. & Potters, M. (1999). Noise Dressing of Financial Correlation Matrices. Physical Review Letters 83(7).
- Ledoit, O. & Wolf, M. (2004). Honey, I Shrunk the Sample Covariance Matrix. Journal of Portfolio Management 30(4).
- Gu, S., Kelly, B. & Xiu, D. (2020). Empirical Asset Pricing via Machine Learning. Review of Financial Studies 33(5).
- Lo, A. & MacKinlay, A. C. (1988). Stock Market Prices Do Not Follow Random Walks. Review of Financial Studies 1(1).
- Bailey, D. & López de Prado, M. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management 40(5).
- Data: Kenneth French daily US market and 49 industries; Cboe VIX; S&P 500; Yahoo dividend-adjusted SPY.
