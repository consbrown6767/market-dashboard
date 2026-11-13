# FX finalists, fixed before the vault was opened

*Written 2026-11-13 after the sandbox run (`~/MarketData/fx/explore-2026-11-13.json`, data 1980-2005 only), before any
data from 2006 on was loaded. Chosen by the plan's rule: the three best Sharpe ratios, all above 0.3.*

| Version | Sandbox: per year | Sharpe | t | Worst drop | Deflated chance real (11 tries) |
|---|---|---|---|---|---|
| Dollar carry | 7.2% | 0.99 | 5.2 | −12% | 0.997 |
| Trend per currency | 4.9% | 0.76 | 4.0 | −16% | 0.939 |
| Combination (carry + 12-month momentum + value) | 3.7% | 0.76 | 3.5 | −12% | 0.922 |

**Caution, written now:** these papers' own samples overlap the vault's first years. Lustig, Roussanov &
Verdelhan's dollar carry used data to 2010, so 2006-2010 isn't fully after publication. The vault is still data
this code has never seen.

## The three (code: `collectors/fx_research.py`)

- finalist: 2_dollar_carry
- finalist: 10_trend_per_currency
- finalist: 11_combination

**Currencies:** pound, yen (from 1985), Swiss franc, Canadian, Australian and New Zealand dollars, Norwegian
and Swedish krone, euro (from 1999), each against the US dollar. All are monthly, decided from month-end data
and held for the next month.

**2. Dollar carry.**
- *Signal:* at each month-end, average the 3-month interest rate of every available currency, minus the US
  3-month rate.
- *Rule:* if the gap is positive, go long every currency equally (1/n each, total 1x) against the dollar. If
  negative, go short every currency equally.

**10. Trend per currency.** Each currency's excess return over the last 12 months (spot change plus the interest
gap). Long it against the dollar if positive, short if negative, with 1/n each.

**11. Combination.** The carry (top third minus bottom third by interest rate), 12-month momentum (top minus
bottom third) and value (5-year fall in the real exchange rate, top minus bottom third) portfolios. Each is scaled
to 8% yearly volatility using its last 36 months, then the three are averaged.

**Costs (all):** 0.05% per dollar traded, plus 0.01% a month per dollar held.

## The vault test (from the plan)

2006-01 to 2026-10. A finalist is **worth live testing** only if:
1. SPY plus the overlay (1x) has more money **and** a better Sharpe ratio than SPY;
2. the overlay made money in 2006-2015 **and** in 2016-2026;
3. the same rule on emerging-market currencies (listed in `PLAN.md`; costs doubled) has a positive return
   and a Sharpe ratio of at least 0.2.

The vault is opened once, by `fx_research.py holdout`, which refuses unless this file is committed and unchanged.
