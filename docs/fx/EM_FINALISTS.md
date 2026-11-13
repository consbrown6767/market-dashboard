# Emerging-market FX finalists, fixed before the vault was opened

*Written 2026-11-13 after the sandbox run (`~/MarketData/fx/em-explore-2026-11-13.json`, 2004-2013 only), before
any data from 2014 on was loaded. Chosen by the plan's rule: the three best Sharpe ratios, all at least 0.3.*

| Version | Sandbox: per year | Sharpe | t | Worst drop | Sep 2008 - Feb 2009 |
|---|---|---|---|---|---|
| E6 Value (PPP) | 6.6% | 0.84 | 2.2 | −10% | +15% |
| E2 EM carry, long only | 5.2% | 0.51 | 1.8 | −27% | −25% |
| E8 EM carry, long only, VIX filter | 3.5% | 0.49 | 1.8 | −11% | −7% |

**Caution, written now:**
- Value needs 5 years of history, so its sandbox is only 2009-2013 (60 months).
- None of the three has t above 2.5. The deflated chances of being real are 0.84, 0.53 and 0.51.

## The three (code: `collectors/fx_em.py`, mechanics in `fx_research.py`)

- finalist: E6_value_ppp
- finalist: E2_em_carry_long_only
- finalist: E8_em_carry_long_only_vix

**Currencies:** Mexican peso, Korean won, South African rand, Brazilian real, Indian rupee, Hungarian forint,
Polish zloty, Czech koruna, Israeli shekel, Chilean peso, Indonesian rupiah, Russian ruble (to 2022-02) and
Turkish lira, each against the dollar. All rules are monthly, decided at month-end and held for the next month.

- **E6 Value:** for each currency, the real exchange rate is spot × local CPI ÷ US CPI (CPI two months old).
  Rank the currencies by how much their real exchange rate fell over 5 years. Long the third that fell most
  (cheap), short the third that fell least (dear), equal weights. Longs add to 1, shorts to −1.
- **E2 EM carry, long only:** long the half of the currencies with the highest interest rates (n ÷ 2, rounded
  down), equal weights, total 1x, against the dollar.
- **E8:** E2, but in cash for any month whose previous month-end VIX was above the average of its last 12
  month-ends.

**Costs:** 0.10% per dollar traded, plus 0.02% a month per dollar held.

## The vault test (from `EM_PLAN.md`)

2014-01 to 2026-10. **Worth live testing** only if (1) SPY plus the overlay (1x) has more money and a better
Sharpe ratio than SPY, **and** (2) the overlay made money in 2014-2019 **and** 2020-2026.
