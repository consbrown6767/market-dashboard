# Risk budget model: the plan, fixed before any result was seen

*Written 2026-11-12, before the model was run on any data. Committed to git so the date and
contents are on record. Changes after results go under "Changes after results" and don't count
toward the verdict.*

## The question

**You pick how much risk you'll accept. The model picks the mix that earns the most for it.**
Risk here means how much the portfolio swings in a year (volatility). SPY swings about 15-16% a
year. The model is tested at four risk levels: **5%, 10%, 15% and 20%**. At each level it must
earn more than the simple ways of taking the same risk.

## What the research says, and how the model uses it

- **Don't trust return forecasts.** DeMiguel, Garlappi & Uppal (2009, Review of Financial Studies):
  textbook "optimal" portfolios (Markowitz), built from estimated returns, lose out of sample to
  simply splitting money evenly, because return estimates are mostly noise. → **The model never
  forecasts returns.** It uses only risk (volatility), which can be measured far more reliably.
- **Balance risk, not dollars.** Asness, Frazzini & Pedersen (2012, Financial Analysts Journal),
  "Leverage Aversion and Risk Parity": stocks carry most of the risk in a 60/40 portfolio. Giving
  stocks and bonds equal *risk*, then scaling up to the desired level, earned more per unit of
  risk than stocks or 60/40 from 1926 to 2010. → **Step 1.**
- **Step aside in downtrends.** Faber (2007); Hurst, Ooi & Pedersen (2017), "A Century of Evidence
  on Trend-Following Investing": trend rules cut crashes across a century and many markets. Our own
  test (`docs/classic-strategies/`) confirmed the 10-month rule is safer for stocks. → **Step 2.**
- **Hit the risk level you asked for.** Harvey et al. (2018), "The Impact of Volatility
  Targeting": scaling by recent volatility keeps risk near target and trims the worst tails.
  → **Step 3.**
- **Known danger:** risk parity rode a 40-year bond rally (1981-2020). The test periods include
  the 1965-1981 bond bear market and 2022, so that luck can't hide.

## Data (free)

- US stocks: French's daily market return and 1-month T-bill (`ff_daily`, 1926-2026), compounded to months.
- US 10-year Treasury: FRED DGS10 daily yields (1962-2026), month-end values. The monthly return
  of a 10-year Treasury is worked out from the yields (a par bond bought at last month's yield,
  priced at this month's, plus a month of interest). This is a standard method. It will be checked
  against known years (2008, 2022) before any model is run.
- Scored from 1965-07 onward, so 36 months of history exist.

## The model (v1, fixed)

At each month-end, using only data up to that day:

1. **Equal risk:** each asset (US stocks, 10-year Treasuries) gets a weight of 1 ÷ its volatility over
   the last 36 months of excess returns (Asness, Frazzini & Pedersen). Normalized to sum to 1.
2. **Trend filter:** an asset whose total-return level is below its average of the last 10
   month-ends is dropped for the month (its share goes to T-bills).
3. **Scale to your risk level:** the kept mix is scaled so that its volatility, estimated from the
   last 36 months of the two assets' swings and how they move together, equals the chosen level.
   Total exposure is capped at **2x** (borrowing up to as much again as the portfolio).
4. Hold a month. Cash sits in T-bills. Borrowing costs the T-bill rate + 1% a year. Trading costs
   0.05% per dollar traded.

## What it must beat, at the same risk level

- **A. SPY at your risk level:** stocks and T-bills in a fixed proportion: chosen level ÷ the stock
  market's volatility over **all** past years (expanding, so no look-ahead). Capped at 2x.
- **B. 60/40 at your risk level:** 60% stocks, 40% Treasuries, scaled the same way.
- **Plain SPY** (100% stocks) for reference.
- **Steps on the way, to see which part helps:** stocks only with trend + scaling (no bonds);
  equal-risk stocks and bonds + scaling (no trend).

## Periods

- **Full:** 1965-07 to 2026-09.
- **After publication:** 2011-01 to 2026-09 (the risk parity paper's data ended 2010).
- **Rising rates:** 1965-07 to 1981-09, and 2021-01 to 2023-10. **Falling rates:** 1981-10 to 2020-12.
- **Decades:** the 1970s through the 2010s, plus 2020-26.

## Pass rules

At the **10% and 15%** levels (the two an ordinary investor would use), the model passes only if all
of these hold:

1. **Full period:** better Sharpe ratio and more money than A and B, and a smaller worst drop than A.
2. **After publication:** better Sharpe ratio and more money than A and B.
3. **Beyond luck:** the monthly gap over A has a t-statistic of at least 3 over the full period
   (Harvey, Liu & Zhu; Newey-West).
4. **Rising rates:** better Sharpe ratio than A in both rising-rate stretches (the bond-luck test).
5. **Decades:** better Sharpe ratio than A in at least 4 of the 6.
6. **It controls risk:** the actual volatility, full period, is within 3 points of the chosen level.

## Always reported (never changing the verdict)

- All four risk levels; crashes (1973-74, 1987, 2000-02, 2008, 2020, 2022); every year.
- Rolling 10-year windows: the share in which the model beats A.
- Block bootstrap (12-month blocks, 2,000 draws): a 95% range for the Sharpe gap over A.
- Sensitivity: volatility window 12/24/60 months, trend 6/12 months, cap 1.5x/3x, double costs,
  borrowing at T-bill + 2%, a one-month delay. Information only; nothing is picked from these.
- Bond-math check against known years.

## If it passes

Propose to the owner a live paper record (monthly amounts in stocks, bonds and cash, logged before
each month). Nothing is traded.

## Changes after results

(none yet)
