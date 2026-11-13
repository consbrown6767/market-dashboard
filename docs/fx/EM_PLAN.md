# Emerging-market currency strategies: the plan, fixed before any EM data was loaded

*Written 2026-11-13, after the G10 study failed in its vault (`README.md`, part 1) and before any emerging-market
exchange rate or interest rate was downloaded. Changes go at the bottom and don't count.*

## Why emerging markets

The G10 currency premiums faded after 2008, partly because rich-country interest rates converged near zero.
Emerging-market rates stayed far apart (Brazil, Turkey and South Africa high; Czechia, Israel and Korea low), and
the research finds bigger currency premiums there:
- Burnside, Eichenbaum, Kleshchelski & Rebelo (2011);
- Lustig, Roussanov & Verdelhan (2011), whose sample includes EM;
- Gilmore & Hayashi (2011), "Emerging Market Currency Excess Returns";
- Della Corte, Riddiough & Sarno (2016).

This is fresh data for this project: none of these currencies has been looked at.

## Currencies (each against the US dollar) and data

| Currency | Spot rate | Interest rate (OECD via FRED: 3-month interbank, else call money) | From |
|---|---|---|---|
| Mexico, Korea, South Africa, Brazil, India | FRED H.10 daily | MX, KR, ZA 3-month; BR, IN call money | 2004 (all have data) |
| Hungary, Poland, Czechia, Israel, Chile, Indonesia, Russia | Yahoo `USDxxx=X` daily (from 2003-12) | 3-month (Russia: 3-month, else call money) | 2004 |
| Turkey | Yahoo (from 2005) | call money (its 3-month ends 2008) | 2005 |

- **Russia** drops out after 2022-02: sanctions made the ruble untradeable for a US investor.
- **CPI** for value: OECD monthly (`XXXCPIALLMINMEI`) where FRED has it; a currency without CPI is left out of value
  only.
- **Known limit:** for the Indian rupee, Korean won, Brazilian real, Chilean peso and Indonesian rupiah, a US
  investor would really use non-deliverable forwards. Their implied rates can differ from onshore rates. Using
  onshore rates may overstate their carry, especially in 2004-2010.

## The versions (9, all counted; same mechanics as `fx_research.py`)

| # | Version | Signal (month-end, for next month) |
|---|---|---|
| E1 | Carry | Rate minus US rate; long top third, short bottom third |
| E2 | EM carry, long only | Long the top half by rate, equal weights, against the dollar (total 1x) |
| E3 | All EM vs dollar (dollar carry) | Long every currency if EM rates average above the US rate; otherwise short all |
| E4 | Trend per currency | Sign of each currency's 12-month excess return, 1/n each |
| E5 | Momentum, 12 months | Top vs bottom third |
| E6 | Value (PPP) | 5-year fall in the real exchange rate (CPI two months old); top vs bottom third |
| E7 | Carry, VIX filter | E1, but cash when the VIX's month-end is above its 12-month average |
| E8 | EM carry long only, VIX filter | E2 with the same filter |
| E9 | Combination | E1, E5, E6, each scaled to 8% volatility (36 months), averaged |

**Costs (double the G10 costs):** 0.10% per dollar traded, plus 0.02% a month per dollar held.

## Sandbox and vault

- **Sandbox: 2004-01 to 2013-12** (includes the 2008 crash and the 2013 "taper tantrum").
- **Vault: 2014-01 to 2026-10.** It's locked in code until `EM_FINALISTS.md` is committed. Finalists: the top
  three Sharpe ratios in the sandbox, as long as they're at least 0.3.

## Pass rules in the vault ("worth live testing")

1. SPY + the overlay (1x) has **more money and a better Sharpe ratio** than SPY over 2014-01 to 2026-10.
2. The overlay made money in **both halves**: 2014-2019 and 2020-2026.

Anything that passes both goes into the live paper record as a new rule (owner already asked for something worth
live testing). It's reported with its crashes and its bootstrap range.

## Changes

- 2026-11-13, before the sandbox was run (only a data check had been done): Yahoo's rupiah shows +16.7% in
  2013-11 and −20.8% in 2013-12, a bad price (the real move was a few percent). For Yahoo series only, days more
  than 8% away from the median of the surrounding 11 days are dropped before taking month-end values.
