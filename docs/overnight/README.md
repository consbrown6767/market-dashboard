# Overnight-only investing (tested 2026-11-13: failed)

*Plan fixed before any result: `PLAN.md` (commit `13e14d6`). Code: `collectors/overnight.py`.
Full results: `~/MarketData/overnight/backtest-2026-11-13.json`. Not live.*

## In one paragraph

Hold SPY from each close to the next open; cash during the trading day. **The pattern is real but
can't be traded.** Before costs, overnight hours delivered 94% of SPY's gains from 1993 to 2026. The
trading day itself lost 4% a year in QQQ's and IWM's case, and earned close to nothing for SPY. But
buying and selling every day, even at just 0.01% per trade, turned it into 4.6% a year against SPY's
10.8%. And since 2009 the pattern has faded: daytime hours have made money again, and even with zero
costs overnight-only earned 8.7% a year against 14.7%.

## Results (after costs of 0.01% per trade, two trades a day)

| | Overnight only | Daytime only | Buy and hold |
|---|---|---|---|
| **SPY 1993-2026** | 4.6% a year, Sharpe 0.27, $45k | −4.3%, $2.3k | **10.8%, Sharpe 0.60, $314k** |
| SPY 2009-2026 | 3.3%, 0.24 | 0.4% | **14.7%, 0.91** |
| QQQ 2009-2026 | 7.0%, 0.55 | 1.7% | **20.3%, 1.05** |
| IWM 2009-2026 | 7.6%, 0.53 | −6.1% | **11.7%, 0.59** |

**Without any costs** (impossible in practice), SPY overnight-only: 10.0% a year with Sharpe 0.82
(1993-2026), against 10.8% and 0.60; since 2009, 8.7% and 0.75 against 14.7% and 0.91. **Break-even
cost per trade:** below zero for SPY. It loses even when trading is free, because daytime hours
also made money. QQQ: 0.006% (1993 on), below zero since 2009. IWM: 0.009%, 0.003% since 2009.

**Pass rules:** SPY whole period **fail**; SPY since 2009 **fail**; QQQ and IWM since 2009 **fail**.

## Checks on my own work

- The overnight and daytime pieces multiply back to each day's total return (largest gap 0.03%, from
  dividends falling on the ex-date morning). Their total over 2007-2025 matches Yahoo's dividend-adjusted
  SPY (×6.853 vs ×6.849).
- Dividends are credited to the overnight holder, who owns the fund going into the ex-date.
- Conservative: cash earns nothing during the day.

## What this means

One of the best-known oddities in market research is real in the data: most gains came overnight.
But it is too small per trade to survive trading twice a day. And since about 2009 it has weakened:
daytime hours earned SPY about half its return (2016: +16% daytime vs −3% overnight; 2023: +19% vs
+6%).

## Sources

- Cooper, M., Cliff, M. & Gulen, H. (2008). Return Differences between Trading and Non-trading Hours: Like Night and Day. SSRN.
- Kelly, M. & Clark, S. (2011). Returns in Trading Hours versus Non-trading Hours: The Difference is Day and Night. Journal of Asset Management 12(2).
- Lou, D., Polk, C. & Skouras, S. (2019). A Tug of War: Overnight versus Intraday Expected Returns. Journal of Financial Economics 134(1).
- Data: Yahoo daily open and close and dividends for SPY, QQQ, IWM.
