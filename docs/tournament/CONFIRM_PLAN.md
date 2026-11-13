# Leveraged trend, confirmation test: the plan, fixed before any result was seen

*Written 2026-11-12, after the tournament (`README.md`) and before any of the tests below was run.
Leveraged trend was picked as the lead **after** seeing results, so only evidence it couldn't have
been tuned on counts here. Changes after results go at the bottom and don't count.*

## The rule (unchanged from the tournament)

Each day at the close: if the market's level is above its 200-day average, hold 2x the market the
next day; else T-bills. Borrowing costs T-bill + 1% a year; each switch costs 0.05% per dollar traded.

## Tests

1. **Fresh markets.** The same rule on French's daily Developed ex US, Europe, Japan and Asia
   Pacific ex Japan markets (US dollars, dividends in), scored 1991-05 to 2026-09, against holding
   each market. Not looked at for this rule in any earlier round.
2. **A real 2x fund.** Signal: SPY's dividend-adjusted close against its 200-day average. Holding:
   the real ProShares Ultra S&P500 (SSO, 2x daily, actual price with its fees and financing). Else
   T-bills. Against SPY. Daily adjusted closes from Yahoo, from SSO's start (2006-06) to 2026-10.
   The signal acts at the next day's close here (a day later than the tournament version), so the
   trade can actually be placed. Switch cost 0.05% per dollar.
3. **Every 10-year stretch** (US, French market, 1928-2026, starting each January): the share in
   which leveraged trend ends with more money than holding the market, and the worst stretch.

## Verdict

**Confirmed** only if all of these hold:
- in test 1, more money than buy and hold in at least 3 of the 4 markets, **and** a Sharpe ratio at
  least as high in at least 3 of the 4;
- in test 2, more money than SPY over the whole period;
- in test 3, ahead in at least 70% of the 10-year stretches.

Otherwise **not confirmed**.

**Information only:** 100-, 150- and 250-day averages; 1.5x and 3x; worst years.

## If confirmed

Propose a live paper record to the owner. Nothing is traded.

## Changes after results

(none yet)
