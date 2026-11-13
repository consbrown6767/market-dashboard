# Earnings-week premium: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the tests below was run. Committed so the date and contents are on
record. Changes after results go at the bottom and don't count.*

## The idea

Stocks tend to rise around the days they report earnings, more than on other days. The usual
explanation is that announcements carry risk that can't be diversified away (every company reporting
tells you something about the economy), so investors are paid for holding it.

- **Beaver (1968)**, and **Chari, Jagannathan & Ofer (1988)**: higher returns around announcements.
- **Frazzini & Lamont (2007), "The Earnings Announcement Premium and Trading Volume"**: stocks earn
  more in months they're expected to announce (US data 1972-2004).
- **Barber, De George, Lehavy & Trueman (2013), "The Earnings Announcement Premium Around the Globe"**
  (Journal of Financial Economics): a premium over the few days around the announcement, in many
  countries.
- **Savor & Wilson (2016), "Earnings Announcements and Systematic Risk"** (Journal of Finance):
  announcers earn more, and the premium is a reward for market-wide risk.

**After publication:** everything here (2016-2026) is after all four papers.

## Data

- **Announcement dates:** `earnings_dates` (Yahoo, with before-open / after-close timing).
- **Prices:** `daily_bars_adj` (Alpaca, adjusted for splits and dividends), 2016-01 to 2026-10.
- **Index members:** `shared/sp500_history.json` (the real S&P 500 list at the start of each year).
- **Yardstick:** SPY (dividend-adjusted, `SPY_ADJ`). T-bill: French 1-month.

**A known gap.** Yahoo only gave dates for **today's** 500 members. Stocks that left the index since
2016 have none (in 2016, 313 of 504 members have dates; in 2026, 473 of 500). Those that stayed
did better than those that left, so any portfolio built only from them looks too good. To keep this
from deciding anything:
- The main test compares the **same stocks** on announcement days against non-announcement days (the
  survivor bias is in both sides and cancels).
- The money comparison with SPY is reported, but against an **equal-weight portfolio of the same
  stocks** as well, which carries the same bias.

## The reaction day

For an announcement before the open (or during the day), the reaction day **E** is that trading day.
After the close, E is the next trading day. Companies in the S&P 500 set their dates weeks ahead, so
the date is public before the window starts.

## The strategies (fixed)

Each day, the universe is that year's S&P 500 members that have both prices and announcement dates.

- **A. Announcement window (main):** each stock is held on trading days **E−1, E and E+1** (the
  three-day window in Barber et al.). Equal weight across all stocks in a window that day. Bought at
  the close of E−2, sold at the close of E+1. On a day with no stock in a window, T-bills.
  Costs: 0.05% of each dollar traded, each trade.
- **B. Pre-announcement only (information):** days E−5 to E−1, the run-up before the news.
- **Robustness, no knowledge of the real date (information):** the date is predicted as the same
  quarter's date a year earlier + 364 days (the Frazzini-Lamont method), held on the 11 trading days
  centered on it.

**Compared with:**
- **EW:** equal weight in every stock of the same universe, every day (no cost: a proxy).
- **SPY.**

## Pass rules

**The premium is real** if, 2016-2026:
1. the average daily return of stocks in their window, minus the same day's EW return, is positive,
   **with t ≥ 2** (Newey-West), before costs; **and**
2. it stays positive in both halves (2016-2020, 2021-2026).

**A beats SPY** if, after costs, A ends with more money **and** a better Sharpe ratio than both SPY
**and** EW (the comparison that carries the same survivor bias).

## Also (information only)

- Each year; the premium by before-open vs after-close; by sector; trades per year.
- The break-even cost per trade.

## Changes after results

(none yet)
