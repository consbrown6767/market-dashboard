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

## Part 2: emerging-market currencies

*Plan: `EM_PLAN.md` (commit `9f450ed`; one data-cleaning change before the sandbox, commit after it). Finalists:
`EM_FINALISTS.md` (commit `6a0d5fc`). Code: `collectors/fx_em.py`. Results: `~/MarketData/fx/em-explore-2026-11-13.json`,
`em-holdout-2026-11-13.json`.*

**In one paragraph:** 13 currencies (Mexico, Korea, South Africa, Brazil, India, Hungary, Poland, Czechia, Israel,
Chile, Indonesia, Russia to 2022, Turkey), with costs doubled. Nine versions were run on 2004-2013. Value and
long-only EM carry led, but none had t above 2.5. **All three finalists failed in 2014-2026.**
- Long-only EM carry earned about 1% a year, too little for its risk. Adding it to SPY gave more money, but a lower
  Sharpe ratio, because it falls with stocks (correlation 0.5).
- The VIX filter halved that correlation, but lost money in 2014-2019.
- Value lost 4.8% a year from 2020.

### Sandbox, 2004-2013

| Version | Per year | Sharpe | t | Worst drop | Sep 2008 - Feb 2009 |
|---|---|---|---|---|---|
| **Value (PPP)** (from 2009 only) | 6.6% | **0.84** | 2.2 | −10% | n/a |
| **EM carry, long only** | 5.2% | 0.51 | 1.8 | −27% | −25% |
| **EM carry, long only, VIX filter** | 3.5% | 0.49 | 1.8 | −11% | −7% |
| All EM vs dollar | 4.1% | 0.46 | 1.7 | −26% | −23% |
| Carry (top vs bottom third) | 2.7% | 0.37 | 1.3 | −18% | −6% |
| Combination (from 2012 only) | 0.9% | 0.28 | 0.8 | −3% | n/a |
| Carry, VIX filter | 0.7% | 0.15 | 0.5 | −14% | −4% |
| Momentum, 12 months | −1.5% | −0.14 | −0.3 | −39% | −17% |
| Trend per currency | −1.6% | −0.17 | −0.5 | −35% | −1% |

### The vault, 2014-01 to 2026-10 (SPY: 13.5% a year, Sharpe 0.82, $10k → $50.6k)

| Finalist | Overlay per year | Sharpe | 2014-19 | 2020-26 | SPY + overlay | Verdict |
|---|---|---|---|---|---|---|
| Value (PPP) | −1.8% | −0.18 | +1.8% | **−4.8%** | $40.4k, Sharpe 0.63 | fails |
| EM carry, long only | +1.2% | 0.17 | +0.6% | +1.6% | **$53.7k**, Sharpe 0.65 | fails (lower Sharpe) |
| EM carry, long only, VIX filter | +0.2% | 0.07 | **−1.3%** | +1.7% | **$51.2k**, Sharpe 0.73 | fails |

## What all this means

1. **Currency premiums were real for decades and largely faded after 2008.** In 1980-2005 the G10 versions had
   Sharpe ratios up to 0.99 with t up to 5. In 2006-2026 the best made 0.4% a year. In emerging markets, carry
   still pays a little, but not enough for its crash risk.
2. **The research's own reasons fit:**
   - Rich-country rates converged near zero after 2008, so there was little carry to earn.
   - The strategies became crowded once published and offered as funds. The real G10 carry fund (DBV) was closed
     and delisted.
   - Currency crashes coincide with stock crashes, so carry adds risk to SPY exactly when it hurts.
3. **20 versions and two clean vaults, six finalists: none worth live testing by the rules fixed in advance.**
