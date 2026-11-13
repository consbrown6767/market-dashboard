# Country stock-market rotation (tested 2026-11-13: failed)

*Plan: `PLAN.md` (commit `54f14a2`). Finalists: `FINALISTS.md` (commit `2e50009`). Code: `collectors/countries.py`.
Results: `~/MarketData/countries/explore-2026-11-13.json`, `holdout-2026-11-13.json`. Not live.*

## In one paragraph

Eight ways to choose among 22 national stock markets (real iShares country funds plus SPY) were run on
1997-2010: momentum, reversal, value (dividend yield), low volatility, value + momentum, trend, and filtered
momentum. Most did nothing even there. The two finalists, trend across countries and momentum with a market
filter, **both failed in 2011-2026 by a wide margin**. Their bootstrap ranges are entirely below zero. US stocks
led the world from 2011, so anything that spread money across countries fell far behind SPY. And country momentum
reversed instead of persisting.

## Sandbox, 1997-04 to 2010-12 (SPY: 5.5% a year, Sharpe 0.23, worst drop −51%)

| Version | Result |
|---|---|
| **Trend across countries (long only)** | 10.7% a year, Sharpe 0.64, worst drop −21% |
| **Momentum with a market filter** | +4.7% a year overlay, Sharpe 0.42, t 1.3 |
| Momentum 6 months | +1.2%, Sharpe 0.15 |
| Momentum 12-1 | −0.4%, 0.06 |
| Value + momentum | −0.6%, 0.02 |
| Value (dividend yield) | −1.7%, −0.12 |
| Low volatility | −4.6%, −0.19 |
| Reversal 1 month | −4.0%, −0.26 |

## The vault, 2011-01 to 2026-10 (SPY: 14.0% a year, Sharpe 0.90, worst drop −24%, $10k → $79.2k)

| Finalist | Result | Sharpe gap vs SPY, 95% range | Verdict |
|---|---|---|---|
| Trend across countries | 4.4% a year, Sharpe 0.34, worst drop −19%, $19.8k | −0.55 (−0.99 to −0.13) | fails |
| Momentum with a market filter | overlay −2.9% a year; SPY + overlay $50.3k, Sharpe 0.62 | −0.28 (−0.48 to 0.00) | fails |

## What this means

Spreading money across countries was a winning idea in the decade when the US lagged, and a losing one in the
decade it led. Country momentum, value and low volatility, all well documented before 2000, did nothing or worse.
