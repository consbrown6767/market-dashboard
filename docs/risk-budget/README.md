# Risk budget model (tested 2026-11-12: failed)

*Plan fixed before any result: `PLAN.md` (commit `8f9a2bc`). Code: `collectors/risk_budget.py`.
Full results: `~/MarketData/risk_budget/backtest-2026-11-12.json`. Not live.*

## In one paragraph

You pick a risk level (5%, 10%, 15% or 20% swings a year). The model splits money between US
stocks and 10-year Treasuries so each carries equal risk (Asness, Frazzini & Pedersen 2012). It drops
either one while it's in a downtrend (Faber's 10-month rule) and scales the mix to your risk level,
borrowing up to 2x. It never forecasts returns (DeMiguel, Garlappi & Uppal 2009). Tested 1965-2026
after costs, **it lost to the simplest alternative at every risk level**: SPY mixed with T-bills
to the same risk ("A"). At 15% risk: $10k became $1.40M against A's $2.73M, and since 2011 8.4% a
year against 11.6%. Its one strength was crashes. It made money in 2000-02 (+32% vs −35%) and
2008 (+4% vs −42%), because bonds rallied while the trend rule had moved it out of stocks. It
lost heavily whenever interest rates rose (1965-81, 2021-23).

## Results after costs (1965-07 to 2026-09)

At the **15%** risk level (close to SPY's own 15.6%):

| | Per year | Sharpe | Worst drop | $10k becomes | Since 2011, per year |
|---|---|---|---|---|---|
| **The model** | 8.4% | 0.35 | −30% | $1.40M | 8.4% |
| A: SPY + T-bills at the same risk | **9.6%** | **0.46** | −42% | **$2.73M** | **11.6%** |
| B: 60/40 at the same risk | 10.1% | 0.42 | −50% | $3.56M | 12.1% |
| Step: stocks only, trend + scaling | 9.9% | 0.47 | −27% | $3.28M | 9.3% |
| Step: equal risk, no trend | 8.7% | 0.36 | −38% | $1.68M | 7.8% |
| Plain SPY (risk 15.6%) | 10.8% | 0.46 | −50% | $5.32M | 14.0% |

Every risk level, model vs A, Sharpe: 5%: 0.39 vs 0.46. 10%: 0.36 vs 0.46. 15%: 0.35 vs 0.46.
20%: 0.36 vs 0.46.

### Pass rules (10% and 15% levels; both the same)

| Rule | Result |
|---|---|
| 1. Full period: better Sharpe and more money than A and B, smaller worst drop than A | **Fail** (smaller drop, but lower Sharpe and less money) |
| 2. Since 2011: better Sharpe and more money than A and B | **Fail** |
| 3. Gap over A, t ≥ 3 | **Fail** (−0.2 at 10%, −0.6 at 15%) |
| 4. Better Sharpe than A in both rising-rate stretches | **Fail** (1965-81: −0.41 vs +0.08; 2021-23: −0.40 vs +0.15) |
| 5. Better Sharpe than A in 4 of 6 decades | **Fail** (1 of 6: the 2000s) |
| 6. Actual risk within 3 points of the level | Pass (13.0% at 15%, 9.5% at 10%) |

### Crashes (15% level)

| | Model | A | 60/40 | SPY |
|---|---|---|---|---|
| 1973-74 bear market | −23% | −33% | −50% | −46% |
| 1987 crash | −21% | −16% | −17% | −22% |
| 2000-02 tech bust | **+32%** | −35% | −31% | −45% |
| 2008 crisis | **+4%** | −42% | −41% | −50% |
| Covid crash 2020 | **+8%** | −16% | −14% | −20% |
| 2022 (stocks and bonds both fell) | −10% | −16% | −28% | −20% |

Only 27 of 52 rolling 10-year windows beat A on money (15% level). The bootstrap 95% range for the
Sharpe gap over A runs from −0.35 to +0.16.

## Why it failed: bonds

Sharpe ratio (return above T-bills per unit of risk) of each piece, no costs:

| Period | Stocks | 10-year Treasuries | 60/40 | Equal risk |
|---|---|---|---|---|
| 1965-1981 (rates rising) | 0.09 | **−0.43** | −0.07 | −0.29 |
| 1981-2010 (rates falling) | 0.46 | **0.60** | 0.62 | **0.72** |
| 2011-2026 | 0.87 | **0.03** | 0.84 | 0.71 |
| 1965-2010 (the paper's years in our data) | 0.33 | 0.25 | 0.34 | 0.33 |

Equal risk gives bonds about 60% of the portfolio's risk, and borrows to do it. That paid off only in
the 30-year bond rally from 1981 to 2020. Since 2011, 10-year Treasuries have earned almost nothing
above T-bills, and borrowing at T-bill + 1% made it worse. On our data (from 1965), the risk parity
paper's advantage doesn't show up even in its own years; its 1926-2010 result relied on years
before ours plus the rally.

## Checks on my own work

- **Bond math against published yearly 10-year Treasury returns** (Damodaran's series, from memory,
  approximately): 2008 +20.4% vs about +20.1%; 2009 −10.1% vs −11.1%; 2022 −16.4% vs −17.8%;
  1994 −7.1% vs −8.0%; 2013 −8.5% vs −9.1%. 1982 is higher (+39% vs +33%), since monthly rolling
  gains more in a year of steep rate falls. Close enough not to change any conclusion.
- No look-ahead: weights are fixed at the month-end before, from past data only. The fixed mixes A
  and B use volatility from all past years, not the future.
- **Sensitivity** (15% level, Sharpe full / since 2011; A is 0.46 / 0.87): volatility window
  12/24/60 months 0.34-0.39 / 0.66-0.72; trend 6 or 12 months 0.33-0.38; cap 1.5x 0.38, 3x 0.34;
  double costs 0.33; borrowing T-bill + 2% 0.31; one-month delay 0.32. **Nothing comes close to A.**

## What this means

1. **"Optimize return for a given risk" mostly means "own stocks, scaled to your risk."** At every
   risk level, the plain SPY + T-bills mix had the best return per unit of risk. Adding bonds by risk
   weight did worse after 2010 and in every rising-rate stretch.
2. **The stocks-only trend version (one of the steps) is the interesting part.** Over 1965-2026 at
   15% risk it slightly beat A (Sharpe 0.47 vs 0.46, $3.28M vs $2.73M, worst drop −27% vs −42%). Since
   2011 it lost (9.3% vs 11.6% a year), the same pattern as the 10-month trend test in
   `docs/classic-strategies/`: it lowers crashes and costs return in strong bull markets. Not a pass;
   seen after the results; would need its own plan.
3. If you want less risk than SPY, the evidence-backed answer is the boring one: hold SPY and cash
   in the proportion that matches your risk. Hold 65% SPY and 35% T-bills for about 10% risk.
   Optionally add the 10-month trend rule if crash protection matters more to you than the last few
   points of return.

## Sources

- Asness, C., Frazzini, A. & Pedersen, L. H. (2012). Leverage Aversion and Risk Parity. Financial Analysts Journal 68(1).
- DeMiguel, V., Garlappi, L. & Uppal, R. (2009). Optimal Versus Naive Diversification. Review of Financial Studies 22(5).
- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation. Journal of Wealth Management.
- Hurst, B., Ooi, Y. H. & Pedersen, L. H. (2017). A Century of Evidence on Trend-Following Investing. Journal of Portfolio Management.
- Harvey, C. et al. (2018). The Impact of Volatility Targeting. Journal of Portfolio Management 45(1).
- Data: French data library (stocks, T-bills); FRED DGS10 (10-year Treasury yields, Federal Reserve).

## Upkeep

None: nothing live. Rerun: `vol_managed.py data`, `risk_budget.py data`, `risk_budget.py bondcheck`, `risk_budget.py backtest`.
