# Currency (FX) strategies: results

*Plan: `PLAN.md` (commit `d77b118`). Finalists: `FINALISTS.md` (commit `55a0914`). Code: `collectors/fx_research.py`.
Results: `~/MarketData/fx/explore-2026-11-13.json`, `holdout-2026-11-13.json`. Not live.*

## Part 1: the major currencies (G10 against the dollar)

**In one paragraph:** 11 strategies from international monetary theory were run on 1980-2005:
- **Interest-rate strategies:** carry, dollar carry, real carry, the Taylor rule, and carry with a VIX or a trend
  filter.
- **Price and value strategies:** momentum, value (PPP), trend per currency, and a combination.

In that sandbox they looked strong, much stronger than any stock strategy tested here. Dollar carry had a Sharpe of
0.99 (t 5.2), and three versions had a deflated chance of being real above 90%. **All three finalists then failed
in 2006-2026.** The currency premiums that held for decades largely disappeared after 2008, when the major central
banks pinned rates near zero and rate gaps between countries shrank. That matches what the research literature
reports after publication.

### Sandbox, 1980-2005 (overlay returns, after costs)

| Version | Per year | Sharpe | t | Worst drop | Deflated chance real |
|---|---|---|---|---|---|
| **Dollar carry** | 7.2% | **0.99** | 5.2 | −12% | 0.997 |
| **Trend per currency** | 4.9% | 0.76 | 4.0 | −16% | 0.939 |
| **Combination** | 3.7% | 0.76 | 3.5 | −12% | 0.922 |
| Carry | 5.6% | 0.61 | 2.9 | −30% | 0.781 |
| Taylor rule | 5.4% | 0.60 | 3.2 | −30% | 0.772 |
| Carry, trend filter | 3.8% | 0.50 | 2.1 | −29% | 0.627 |
| Value (PPP) | 4.2% | 0.48 | 2.9 | −19% | 0.582 |
| Real carry | 2.5% | 0.33 | 1.4 | −34% | 0.306 |
| Momentum, 12 months | 2.0% | 0.25 | 1.5 | −32% | 0.179 |
| Carry, VIX filter (1991-2005) | 1.0% | 0.19 | 0.7 | −34% | 0.173 |
| Momentum, 1 month | 0.8% | 0.13 | 0.6 | −37% | 0.059 |

### The vault, 2006-01 to 2026-10 (SPY: 11.0% a year, Sharpe 0.66, $10k → $88.6k)

| Finalist | Overlay per year | Sharpe | 2006-15 | 2016-26 | SPY + overlay | Verdict |
|---|---|---|---|---|---|---|
| Dollar carry | −0.6% | −0.04 | −2.7% | +1.3% | $75.7k, Sharpe 0.54 | fails |
| Trend per currency | −1.4% | −0.18 | −1.3% | −1.5% | $69.1k, 0.58 | fails |
| Combination | +0.4% | 0.12 | −0.2% | +1.0% | $92.4k, 0.62 | fails |

- **Dollar carry** was long foreign currencies going into 2008 and lost 16% from September 2008 to February 2009.
  It also lost 10% in 2014 and 8% in 2015 as the dollar surged.
- **Trend per currency** did what trend does in 2008 (+7%), but lost in most other years.
- **The combination** came closest (+0.4% a year), but adding it to SPY still lowered SPY's Sharpe ratio.

**Not checked:** the real carry fund (Invesco DB G10 Currency Harvest, DBV) has been delisted, and Yahoo no
longer has its history.
