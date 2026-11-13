# Options fear premium (VRP): confirmation tests, fixed before any of them was run

*Written 2026-11-13, after the vault result (`README.md`) and the owner's request to "try it over different time
periods ... during other bear markets that aren't 2008 crash level". Changes after results go at the bottom and
don't count.*

**What has already been seen:** SPY 2006-2026 (the vault), and 1993-2005 (the sandbox). Tests 1 and 3 below reuse
that S&P 500 history, cut new ways, so they describe the rule more than confirm it. **Test 2 uses four markets
the rule has never seen** and is the real confirmation.

## The rule (unchanged: finalist 4b)

- **Each month-end:** VRP = (fear index ÷ 100)² ÷ 12, minus the sum of the month's squared daily log returns
  of the same market.
- **Forecast:** a straight-line regression, on all past months (at least 36), of the next month's excess return
  on VRP.
- **Holding:** forecast ÷ (3 × the variance of the last 120 monthly excess returns), kept between 0 and 1.5x. The
  rest is in T-bills; borrowing costs the T-bill rate.
- **Costs:** 0.05% per dollar traded. The weight is fixed for the month, so daily results apply it to each
  day's return.

## Test 1: every S&P 500 decline of 10% or more

- **Market:** the S&P 500 with dividends (Cboe/S&P `SP500TR`). The rule runs from 1993-02, after 3 years of VIX.
- **Declines:** found from daily closes. A decline starts at a record high, bottoms at its lowest close before
  the old high is regained, and counts if that bottom is at least 10% down. Each one is scored on two stretches:
  1. **Peak to bottom:** did VRP lose less than the market?
  2. **Peak to 12 months after the bottom:** which ended with more money (did it miss the rebound)?
- **Pass:** leaving out 2007-2009, VRP loses less in **at least two thirds** of the declines, **and** ends the
  peak-to-12-months stretch ahead in **at least half**.

## Test 2: four fresh markets (the real test)

The same rule, using each market's own fear index and its own returns:

| Market | Fear index | Held | Runs from (after 36 months) |
|---|---|---|---|
| Nasdaq-100 | VXN (Yahoo, 2001) | QQQ, dividends in | about 2004 |
| Dow Jones | VXD (Yahoo, 2005-11) | DIA, dividends in | about 2009 |
| Russell 2000 | RVX (Cboe, 2009-09) | IWM, dividends in | about 2012 |
| Europe | VSTOXX (STOXX, 1999) | French's European market (US dollars, dividends in) | about 2002 |

Daily returns for the realized variance: the index (^NDX, ^DJI, ^RUT) or, for Europe, French's European market.
For Europe that return includes currency moves while VSTOXX doesn't, so its VRP is noisier. T-bill: US (French)
throughout.

**Pass:** a Sharpe ratio at least as high as buying and holding the same market in **at least 3 of the 4**.

## Test 3: time periods on the S&P 500

Sharpe ratio of VRP vs the market in six stretches: 1993-1999, 2000-2005, 2006-2009, 2010-2015, 2016-2020,
2021-2026. **Pass:** higher in **at least 4 of 6**.

## Verdict

**Confirmed** only if all three tests pass. Otherwise **not confirmed**. Either way, it's reported in plain terms.

## Information only (never changing the verdict)

- Rolling 5-year windows (monthly steps): the share where VRP has more money and the share where it has a
  better Sharpe ratio.
- Sensitivity of the S&P result: risk aversion 2, 3, 5; a cap of 1.0x, 1.5x, 2.0x; a rolling 10-year regression
  instead of all past months.
- 1990's bear market can't be tested (the rule needs 3 years of VIX first).

## Changes after results

(none yet)
