# Bond finalists, fixed before the vault was opened

*Written 2026-11-13 after the sandbox (`~/MarketData/bonds/explore-2026-11-13.json`, 1980-2005 only), before any
data from 2006 on was loaded.*

**Smoothing:** in 1980-2005, US bond excess returns had a volatility of 8.97% a year when measured from month-end
daily yields, against 7.80% from monthly averages.
- k: 1.15

**The rule:** the top three sandbox Sharpe ratios, after the smoothing correction, as long as they're at least 0.3.
- **Global duration timing:** 0.445. Qualifies.
- **Value, real yield:** 0.2997. It shows as 0.300 after rounding, and the code's rounded check let it in. By the
  rule as written it falls short, so it is **not** a finalist.
- **Carry (term spread):** 0.246. Below the bar.

So one finalist:

- finalist: B6_global_duration_timing

**Caution, written now:** its sandbox evidence is modest: 1.6% a year, raw Sharpe 0.51, t 1.8, deflated chance of
being real 0.72 given 8 tries.

## The rule (code: `collectors/bonds.py`)

- **Countries:** US, Germany (euro area), Japan (from 1989), UK, Switzerland, Canada, Australia, New Zealand,
  Norway (from 1985), Sweden (from 1987). Each is a 10-year government bond hedged to the dollar (its return minus
  its own 3-month rate).
- **Each month-end:** the average across countries of (10-year yield − 3-month rate).
- **If it's above its average of the last 120 month-ends:** long every country's bond equally (total 1x).
  **Otherwise:** flat.
- **Scored with the one-month gap:** a decision at the end of month t earns month t+2's return, measured from
  average yields. Costs are 0.03% per dollar traded plus 0.01% a month per dollar held.

## The vault test (from `PLAN.md`), on smoothing-corrected returns (k above)

2006-01 to 2026-09. **Worth live testing** only if (1) SPY plus the overlay (1x) has more money and a better Sharpe
ratio than SPY, **and** (2) the overlay made money in 2006-2015 **and** 2016-2026.
