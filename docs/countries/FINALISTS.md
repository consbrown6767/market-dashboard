# Country rotation finalists, fixed before the vault was opened

*Written 2026-11-13 after the sandbox (`~/MarketData/countries/explore-2026-11-13.json`, 1997-04 to 2010-12 only),
before any data from 2011 on was loaded. Rule: the top three Sharpe ratios of at least 0.3. Only two qualified.*

| Version | Sandbox | Note |
|---|---|---|
| C7 Trend across countries (long only) | 10.7% a year, Sharpe 0.64, worst drop −21%, vs SPY 5.5%, 0.23, −51% | Sandbox included the US "lost decade" and an emerging-market boom |
| C8 Momentum with a market filter (overlay) | 4.7% a year, Sharpe 0.42, t 1.3, worst drop −37% | Weak evidence |

**Caution, written now:** 1997-2010 was unusually bad for US stocks against the rest of the world. Since 2011 it has
been the opposite. C7 will be judged against SPY in a stretch where US stocks led.

- finalist: C7_trend_long_only
- finalist: C8_momentum_market_filter

## The rules (code: `collectors/countries.py`)

Funds: 22 iShares country funds plus SPY (list in `PLAN.md`), monthly, decided at month-end and held next month.

- **C7 Trend across countries:** each fund whose month-end price (with dividends) is above its average of the last
  10 month-ends gets 1/n, where n is the number of funds with data that month. The rest sits in T-bills. Costs are
  0.10% per dollar traded.
- **C8 Momentum with a market filter:**
  - *Ranking:* rank the funds by their return over months t−11 to t−1. Long the top third, short the bottom third.
    Longs total 1, shorts −1.
  - *Filter:* flat whenever the equal-weight average of all funds is below its own 10-month average.
  - *Costs:* 0.10% per dollar traded, plus 0.5% a year on shorts.

## The vault test (from `PLAN.md`), 2011-01 to 2026-10

- **C7:** worth live testing if it beats SPY (more money and a better Sharpe ratio) or is "safer, not better" (a
  better Sharpe ratio and a smaller worst drop), the same way in **both** halves (2011-2018, 2019-2026).
- **C8:** SPY plus the overlay has more money **and** a better Sharpe ratio than SPY, **and** the overlay made money
  in both halves.
