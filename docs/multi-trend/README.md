# Trend across many markets (tested 2026-11-13: failed)

*Plan fixed before any result: `PLAN.md` (commit `f9498de`). Code: `collectors/multi_trend.py`.
Full results: `~/MarketData/multi_trend/backtest-2026-11-13.json`. Not live.*

## In one paragraph

Faber's trend rule was applied to five real funds: US stocks (SPY), foreign stocks (EFA), Treasuries
(IEF), real estate (VNQ) and commodities (DBC). Two versions: long-only (A), and the long/short version
managed-futures funds run (B). A third (C) held half SPY, half B. 2007-2026, after costs, trading a
day after each signal. **All three failed.** The long-only version cut the worst drop to −12%, but made
4.8% a year against SPY's 10.9%. The long/short version made money in 2008 (+52%) and 2022 (+3%), but lost
heavily in 2018 (−30%) and 2020 (−30%). Its return above T-bills wasn't reliable (t 1.6). Half SPY,
half long/short matched SPY's return per unit of risk over the whole period (0.656 vs 0.653) with half
the worst drop. But since 2013 it fell well behind (0.68 vs 0.92).

## Results (2007-03 to 2026-10, $10k, after costs)

| | Per year | Sharpe | Swings a year | Worst drop | $10k becomes |
|---|---|---|---|---|---|
| A. Trend across five, long-only | 4.8% | 0.50 | 6.8% | −12% | $25.2k |
| B. Long/short trend across five | 6.8% | 0.34 | 21.3% | −55% | $36.3k |
| C. Half SPY, half B | 9.8% | **0.656** | 13.2% | **−26%** | $62.6k |
| Five funds, 20% each, no trend | 6.1% | 0.42 | 12.3% | −43% | $32.1k |
| 60% SPY / 40% IEF | 8.2% | **0.72** | 9.5% | −29% | $47.4k |
| **SPY** | **10.9%** | 0.653 | 15.4% | −51% | **$76.9k** |

**Since 2013:** SPY 14.7% a year (Sharpe 0.92); A 5.5% (0.62); B 4.7% (0.24); C 10.5% (0.68); 60/40 9.5% (0.84).

| Pass rule | Result |
|---|---|
| A beats SPY / safer | **Fail / fail** (Sharpe 0.50 vs 0.65) |
| B: above T-bills with t ≥ 2, and up in 2008 and 2022 | **Fail** (t 1.57; it was up in both years) |
| C beats SPY / safer | **Fail / fail** (since 2013, Sharpe 0.68 vs 0.92) |

**Crashes (A / B / C / SPY):** 2008 crisis −5% / +72% / −5% / −51%. Covid crash −2% / −2% / −11% / −19%.
2022: −6% / +3% / −6% / −18%.

**B by year vs SPY:** 2008 +52% vs −37%; 2014 +51% vs +14%; 2017 +45% vs +22%; 2021 +38% vs +29%;
but 2009 −17% vs +26%; 2016 −15% vs +12%; 2018 −30% vs −5%; 2020 −30% vs +18%; 2023 −4% vs +26%;
2024 −10% vs +25%.

## Checks on my own work

- The engine reproduces SPY exactly when told to hold 100% SPY. Each fund's 2008 and 2022 returns
  match the published ones (IEF 2008 +17.9%, DBC 2022 +19.3%).
- Positions follow the rule. In 2020, B was long stocks into the February-March crash, then short
  stocks into the April rebound. That's the classic whipsaw.
- **Why B is so jumpy:** sizing each market to 40% risk is the paper's setting for 58 markets, where
  the swings average out. With five funds, four of them stocks or stock-like, they don't. B swung 21% a
  year, more than SPY. Real managed-futures funds trade 50-100 markets. A five-fund copy is not that.

## Longer check, 1994-2026 (French data, three assets, information only)

US stocks, Developed ex US stocks, 10-year Treasury: half US stocks, half long/short trend made 13.3% a
year against 11.0% for US stocks, with Sharpe 0.69 vs 0.60 and worst drop −27% vs −50%. That longer
stretch includes 2000-02, when trend shone. The same pattern as every trend test: **it earns its keep
in long crashes, and there hasn't been one since 2009.**

## What this means

Spreading trend across five markets didn't fix the problem since 2010. It worked in 2008 and 2022 and
lost in the quick-rebound years. The most surprising line is the plain **60/40**: over 2007-2026 it had
a better return per unit of risk (0.72) than SPY or any trend version, though it made less money.

## Sources

- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation. Journal of Wealth Management.
- Moskowitz, T., Ooi, Y. H. & Pedersen, L. H. (2012). Time Series Momentum. Journal of Financial Economics.
- Hurst, B., Ooi, Y. H. & Pedersen, L. H. (2017). A Century of Evidence on Trend-Following Investing. Journal of Portfolio Management.
- Data: Yahoo dividend-adjusted closes of SPY, EFA, IEF, VNQ, DBC; French; FRED DGS10.
