# Global government bond strategies: the plan, fixed before any result was seen

*Written 2026-11-13, before any bond data was turned into returns. Changes go at the bottom and don't count.*

## The idea

The bond version of the currency ideas, across 10 countries' 10-year government bonds, each hedged to the dollar.
A hedged bond earns the bond's return minus its own country's cash rate.
- **The expectations hypothesis fails** (Fama & Bliss 1987; Campbell & Shiller 1991). Steep yield curves predict
  higher bond returns, not just rising rates. That is **bond carry** (Koijen, Moskowitz, Pedersen & Vrugt 2018,
  "Carry").
- **Value:** high real yields predict higher returns (Asness, Moskowitz & Pedersen 2013, "Value and Momentum
  Everywhere").
- **Momentum and trend:** AMP (2013), cross-country; Moskowitz, Ooi & Pedersen (2012), per country.
- **Monetary policy:** central banks cut when inflation is low and unemployment high, which lifts bond prices.
  A Taylor-rule gap that says "should cut" favours that country's bonds (the bond side of Molodtsova & Papell 2009).
- **Bond-yield timing:** a steep global curve predicts global bond returns (Cochrane & Piazzesi 2005, simplified).

A real version uses government bond futures (one-month trading, margin only), so each strategy is an **overlay**.

## Data (FRED / OECD, already partly stored in `macro_series`)

- **10-year government yields** (`IRLTLT01xxM156N`): US, Germany (for the euro area), Japan (from 1989), UK,
  Switzerland, Canada, Australia, New Zealand, Norway (from 1985), Sweden (from 1987).
- **3-month rates, CPI, unemployment:** as in `docs/fx/PLAN.md`.
- **US daily 10-year yield** (FRED `DGS10`, already in `rates_daily`): used only to measure the smoothing
  (below).

**Bond return:** a par bond bought at last month's yield (coupon = that yield, paid twice a year), priced a month
later at this month's yield with 10 years less a month to run, plus a month of coupon. Minus the country's 3-month
rate ÷ 12.

### Two defences against the monthly-average yields

1. **A one-month gap.** A decision made at the end of month t is scored on the return from month t+1's average
   yield to month t+2's. The scored return then starts after the decision, never before.
2. **A smoothing correction.** Averaged yields hide part of the real swings. In the sandbox, measure US bond
   returns two ways: from month-end daily yields (`DGS10`), and from the monthly averages. Their volatility ratio
   is k. **In the vault, each overlay's monthly deviations from its own mean are multiplied by k** before
   scoring. The average return is unchanged; the risk is made honest. Both raw and corrected numbers are
   reported, and the pass rules use the corrected ones.

## The versions (8, all counted)

Cross-sectional versions: long the top third, short the bottom third (max(2, n÷3) each side, equal weights,
longs total 1 and shorts −1).

| # | Version | Signal at each month-end |
|---|---|---|
| B1 | Bond carry | Term spread: 10-year yield minus 3-month rate. Long the steepest |
| B2 | Bond value | Real yield: 10-year yield minus 12-month CPI inflation (CPI two months old). Long the highest |
| B3 | Momentum, 12 months | Last 12 months' hedged excess return. Long the best |
| B4 | Trend per country | Each country long if its 12-month excess return is positive, short if not, 1/n each |
| B5 | Combination | B1, B2, B3, each scaled to 5% volatility (36 months), averaged |
| B6 | Global duration timing | Long all countries equally (total 1x) when the average term spread is above its average of the last 120 months; otherwise flat |
| B7 | Yield level | Long the highest 10-year yields, short the lowest |
| B8 | Taylor rule | Score 1.5 × inflation gap + 0.5 × unemployment gap against the cross-country average (data two months old). Long the lowest scores ("should cut"), short the highest |

**Costs:** 0.03% per dollar traded, plus 0.01% a month per dollar held (rolling futures).

## Sandbox and vault

- **Sandbox: 1980-01 to 2005-12** (7 countries in 1980, 10 by 1989).
- **Vault: 2006-01 to 2026-09.** It's locked in code until `FINALISTS.md` is committed. Finalists: the top three
  sandbox Sharpe ratios, as long as they're at least 0.3.

## Pass rules in the vault ("worth live testing"), on smoothing-corrected returns

1. SPY + the overlay (1x) has **more money and a better Sharpe ratio** than SPY.
2. The overlay made money in **both halves** (2006-2015 and 2016-2026).

Anything that passes goes to the live paper record (the owner asked for that). It's reported with its crashes,
correlation with SPY and bootstrap range.

## Changes

(none yet)
