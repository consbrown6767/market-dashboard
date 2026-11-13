# Math exploration: the plan, fixed before any data was looked at

*Written 2026-11-13, before any of the methods below was run. Committed so the date and contents are on
record. Changes go at the bottom and don't count.*

## The idea

Hunt for patterns with more advanced tools: linear algebra, hidden-state models, machine learning,
covariance cleaning. Stick to rules that trade at most daily (no high-frequency trading).

**The danger:** try enough things and one will look good by luck. **The guard:** split the history in
two before looking.

- **Exploration (the "sandbox"):** everything **up to 2005-12-31**. Try every method below, count
  every version, and keep the scores.
- **Holdout (the "vault"):** **2006-01 to 2026-09.** The code refuses to load it during exploration.
  After exploration, up to three finalists get exact rules written into `FINALISTS.md` and
  committed. Only then is the vault opened, **once**, for those three.

## The methods (15 versions, all counted)

Data: Kenneth French daily returns for the US market and 49 industries (from 1926), T-bill; S&P 500 and
VIX (from 1990). Signals use only data up to each decision. Daily rules act the next day; monthly
rules act the next month.

| # | Method (research) | The math | Versions |
|---|---|---|---|
| 1 | **Absorption ratio**: Kritzman, Li, Page & Rigobon (2011), "Principal Components as a Measure of Systemic Risk" | Eigenvalues of the 49 industries' covariance (500 days): the share of variance in the top 1/5 of eigenvectors. When it jumps (15-day vs 1-year average, more than 1 standard deviation up), markets are fragile → T-bills | (a) monthly, (b) daily |
| 2 | **Financial turbulence**: Kritzman & Li (2010), "Skulls, Financial Turbulence, and Risk Management" | Mahalanobis distance of today's 49 industry returns from their past mean and covariance: how unusual the day is. Above its 80th percentile of the past → T-bills | (a) monthly (21-day average), (b) daily |
| 3 | **Hidden Markov regimes**: Hamilton (1989); Ang & Bekaert (2002); Nystrup et al. (2017) | A 2-state Gaussian hidden Markov model of daily market returns (Baum-Welch, refit each year on all past days). Hold the market while the filtered chance of the calm state is above 50% | (a) daily, (b) monthly |
| 4 | **Variance risk premium**: Bollerslev, Tauchen & Zhou (2009) | VIX² ÷ 12 minus last month's realized variance: what option buyers pay for protection. High → higher returns ahead. *Exploration 1990-2005 only (VIX starts 1990)* | (a) hold the market when above its past median, (b) weight from an expanding regression, 0 to 1.5 |
| 5 | **Industry lead-lag**: Hong, Torous & Valkanov (2007); Rapach, Strauss, Tu & Zhou (2019) | Lasso regression (L1 penalty, chosen by time-ordered cross-validation) of next month's returns on all 49 industries' last-month returns | (a) market timing: hold if the forecast is positive, (b) rotation: the 10 industries with the best forecasts |
| 6 | **Random-matrix covariance cleaning**: Laloux, Cizeau, Bouchaud & Potters (1999); Ledoit & Wolf (2004) | Minimum-variance portfolio of the 49 industries (long only, at most 10% each) from a cleaned covariance (250 days) | (a) eigenvalue clipping (Marchenko-Pastur), (b) Ledoit-Wolf shrinkage |
| 7 | **Machine learning on industries**: Gu, Kelly & Xiu (2020) | Gradient-boosted trees on an industry-month panel. Features: returns over the last 1, 3, 6, 12 months, volatility, market beta, biggest daily move, the market's own last month. Retrained each year on all past data; buy the top 10 forecasts | (a) boosted trees, (b) ridge regression (the linear benchmark) |
| 8 | **Fractal trend filter**: Lo & MacKinlay (1988) variance ratio; Hurst | Variance ratio of 10-day to 1-day returns over the last 250 days. Above 1 (the market is trending): follow the 10-month trend rule. Otherwise hold the market | (a) one version |

**Costs:** 0.05% per dollar traded for switching between the market and T-bills; 0.10% per dollar
traded for industry portfolios (rebalanced monthly).

## How exploration is scored (1946-01 to 2005-12; VRP 1990-02 to 2005-12)

For each version: growth of $10k, Sharpe ratio and worst drop against the US market over the same months.
Also the **deflated** chance that its Sharpe gap over the market is real, given 15 tries (Bailey & López de
Prado).

## Picking finalists

The **three versions with the largest Sharpe gap over the market** in exploration, as long as the gap is
positive, become finalists. Their exact rules go into `FINALISTS.md` before the vault opens. If none
has a positive gap, nothing goes to the vault and the answer is "nothing found".

## Pass rules in the vault (2006-01 to 2026-09)

Yardstick: **SPY** (dividends in). Market-timing finalists are applied to SPY itself; industry
portfolios use French's industries less 0.20% a year (a typical industry-fund fee) plus trading costs.

- **Beats SPY:** more money **and** a better Sharpe ratio.
- **Safer, not better:** a better Sharpe ratio **and** a smaller worst drop, but less money.
- Also reported: the bootstrap range of the Sharpe gap (block bootstrap, 12-month blocks).

## Changes

(none yet)
