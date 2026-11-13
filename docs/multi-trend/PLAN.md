# Trend across many markets: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the tests below was run. Committed to git so the date and contents are on
record. Changes after results go at the bottom and don't count.*

## The idea

Our trend tests so far used US stocks alone, and since 2010 they lost to SPY: no long crash came, and
the switch only paid for its false alarms. Research on trend-following uses **many markets at once**:
stocks, bonds, real estate, commodities. In any year, some are trending. This tests that.

## Research

- **Faber (2007), "A Quantitative Approach to Tactical Asset Allocation"**: five asset classes (US
  stocks, foreign stocks, 10-year Treasuries, real estate, commodities), 20% each, each held only while
  above its 10-month average, else T-bills. Data to 2005, so **everything here is after publication**.
- **Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum"** (data to 2009), and **Hurst, Ooi &
  Pedersen (2017), "A Century of Evidence on Trend-Following"**: in each market, go long if its last 12
  months beat T-bills and short if not, each sized to the same risk. This is what managed-futures funds
  do. Famous for making money in 2008 and 2022.

## Data: real funds (Yahoo, dividend-adjusted closes, fund fees already inside the prices)

SPY (US stocks), EFA (foreign developed stocks), IEF (7-10 year Treasuries), VNQ (US real estate), DBC
(commodities futures, a fund with total return including the roll). DBC starts 2006-02, so scoring
runs **2007-03 to 2026-10** (12 months of history needed first). T-bill: French 1-month (carried
forward after 2026-09). One commodity fund isn't the GSCI index Faber used. It's the closest real fund
with a long record.

## The strategies (fixed)

Each month's positions are decided from data through the last trading day of the month before, and
take effect at the **next day's close** (so they could really be traded).

- **A. Trend across five (Faber):** 20% in each fund whose month-end price is above its average of the
  last 10 month-ends; that 20% is in T-bills otherwise. Costs 0.05% per dollar traded.
- **B. Long/short trend across five (Moskowitz, Ooi & Pedersen):** for each fund, +1 if its last
  12-month return beat the T-bill, −1 if not. Weight = that sign × 40% ÷ the fund's volatility (last
  126 trading days, yearly terms) ÷ 5, at most 2x per fund. The money not tied up sits in T-bills. Costs
  0.05% per dollar traded, 0.5% a year to borrow what's shorted, and 0.85% a year (a typical
  managed-futures fund fee).
- **C. Half SPY, half B**, rebalanced monthly: what an investor would actually hold.

**Compared with:**
- SPY.
- The same five funds, 20% each, rebalanced monthly (diversification without trend).
- 60% SPY / 40% IEF.

## Pass rules

- **A beats SPY:** more money and a better Sharpe ratio over 2007-03 to 2026-10. **Safer, not better:**
  better Sharpe and smaller worst drop over the whole window **and** from 2013-01 (after the
  long/short paper).
- **B works:** return above T-bills with t ≥ 2 (Newey-West) over the whole window, **and** a gain in
  both 2008 and 2022.
- **C beats SPY:** more money and a better Sharpe ratio over the whole window. **Safer, not better:** as
  for A.

## Also (information only, never changing a verdict)

- A longer check, 1994-2026, on French data: US and foreign stocks, plus the 10-year Treasury computed
  from yields. Three assets, no real estate or commodities.
- Each year; crashes (2008, 2020, 2022); trades per year.

## Changes after results

(none yet)
