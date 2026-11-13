# Global government bond strategies (tested 2026-11-13: failed)

*Plan: `PLAN.md` (commit `ebd1ce5`). Finalists: `FINALISTS.md` (commit `8683e56`). Code: `collectors/bonds.py`.
Results: `~/MarketData/bonds/explore-2026-11-13.json`, `holdout-2026-11-13.json`. Not live.*

## In one paragraph

Eight bond strategies across 10 countries' 10-year government bonds (hedged to the dollar, as overlays) were run
on 1980-2005:
- **Carry, value and the yield level:** the yield curve's slope, real yields, and the plain level of yields.
- **Momentum, trend and their combination.**
- **Global duration timing.**
- **A Taylor rule.**

The bond premiums were much weaker than the currency ones even in the sandbox. Only global duration timing
(hold all bonds while the average curve is unusually steep) cleared the bar. In 2006-2026 it added a little to SPY
($96.5k vs $89.4k), but it lost money from 2016 on, including −12% in 2022. **Not worth live testing.**

## Data caution (and the two defences)

The free international yields are **monthly averages**, which smooth returns and blur timing:
- **Timing:** each decision was scored on the return starting a full month later.
- **Hidden risk:** measured on US bonds, where daily yields exist. Averages hid 15% of the real volatility
  (k = 1.15), and the vault results were scaled up by that.

## Sandbox, 1980-2005 (overlay returns after costs)

| Version | Per year | Sharpe (raw) | Sharpe (corrected) | t | Worst drop |
|---|---|---|---|---|---|
| **Global duration timing** | 1.6% | 0.51 | **0.445** | 1.8 | −15% |
| Value (real yield) | 1.8% | 0.34 | 0.2997, just under 0.3 | 1.7 | −18% |
| Carry (term spread) | 1.7% | 0.28 | 0.25 | 1.3 | −30% |
| Combination | 0.8% | 0.27 | 0.24 | 1.1 | −14% |
| Yield level | 1.5% | 0.27 | 0.23 | 1.4 | −21% |
| Trend per country | 1.0% | 0.25 | 0.22 | 1.1 | −17% |
| Taylor rule | −0.8% | −0.11 | −0.10 | −0.6 | −35% |
| Momentum, 12 months | −2.6% | −0.32 | −0.28 | −1.6 | −54% |

Value showed 0.300 in the rounded output, and the code's rounded check let it through. The exact figure is
0.2997, so by the rule as written it wasn't a finalist. It was left out before the vault was opened.

## The vault, 2006-01 to 2026-09 (smoothing-corrected; SPY: 11.1% a year, Sharpe 0.66, $10k → $89.4k)

| | Overlay per year | Sharpe | 2006-15 | 2016-26 | SPY + overlay | Verdict |
|---|---|---|---|---|---|---|
| Global duration timing | +0.4% | 0.14 | +2.6% | **−1.6%** | $96.5k, Sharpe 0.68 | **fails rule 2** |

It held bonds in 2010-11, 2014-15, 2021-22 and 2025-26, and was flat otherwise. The gains came from 2011 (+12%)
and 2014 (+12%); 2022 cost 12%. The Sharpe gain from adding it to SPY, +0.01 (95% range −0.11 to +0.19), is noise.

## What this means

Government bond premiums across countries were thin even before 2006. Momentum lost money even then (bond
markets mean-revert over a year). The one survivor is a slow bet on steep curves, and it rests on two good years.
