# Earnings-week premium (tested 2026-11-13: failed)

*Plan fixed before any result: `PLAN.md` (commit `5f79c84`). Code: `collectors/earnings_premium.py`.
Full results: `~/MarketData/earnings_premium/backtest-2026-11-13.json`. Not live.*

## In one paragraph

Hold each S&P 500 stock only on the three trading days around its earnings announcement, the day
before, the reaction day and the day after. Research from 1968 to 2016 found stocks earn extra on
those days. **From 2016 to 2026 they didn't.** On those days the stocks did no better than the same
stocks on other days: −0.02% a day, t −0.4. A portfolio holding only those stocks swung wildly, at
34% a year volatility with a worst drop of −74%. It traded its whole value about twice a week. $10k
became $5.2k after costs, against $44.7k in SPY.

## Results, 2016-01 to 2026-10

**The premium** is the average daily return of stocks in their window, minus the same day's average
of all stocks in the universe.

| | Per day | t | Days |
|---|---|---|---|
| **Main: 3-day window (E−1 to E+1)** | **−0.017%** | **−0.43** | 2,522 |
| 2016-2020 | +0.014% | 0.24 | |
| 2021-2026 | −0.044% | −0.82 | |
| Before-open reporters | −0.048% | −1.02 | |
| After-close reporters | +0.022% | 0.42 | |
| Day before (E−1) | +0.014% | 0.55 | |
| Reaction day (E) | −0.033% | −0.36 | |
| Day after (E+1) | +0.053% | 1.66 | |
| *Run-up, 5 days before (information)* | *+0.035%* | *2.50* | |
| *Dates predicted from a year earlier (information)* | *+0.010%* | *0.86* | |

The premium changed sign from year to year: +0.19% a day in 2016, −0.26% in 2017, +0.15% in 2019,
−0.21% in 2025. No sector had t above 2 (the highest was Industrials, 1.9).

**$10,000 invested (costs 0.05% per dollar traded):**

| $10k → | Per year | Sharpe | Worst drop |
|---|---|---|---|
| Earnings windows, after costs: $5.2k | −5.8% | −0.07 | −74% |
| Earnings windows, no costs: $16.7k | 4.9% | 0.25 | −66% |
| Same stocks, equal weight: $47.5k | 15.5% | 0.84 | −25% |
| **SPY: $44.7k** | **14.8%** | **0.85** | −24% |

**Pass rules:** the premium is real **fail** (t −0.4, and negative in 2021-2026). Beats SPY and the
same stocks **fail**. Break-even cost: zero, because it loses even with free trading.

## Checks on my own work

- **Are the dates lined up?** Yes. The average absolute move on the reaction day was 4.0%, against
  1.35% on an ordinary day, 1.35% the day before and 1.7% the day after. A one-day slip would have
  shown up here.
- **Bad prices.** Only 6 stock-days moved more than 50% (for example EQT on its 2018 spin-off, and
  PG&E in its 2019 bankruptcy). Too few to change the answer.
- **Survivor bias.** Yahoo gave dates only for today's members, so the universe averages 394 stocks,
  not 500. That bias sits on both sides of the premium and cancels. It flatters the equal-weight
  line, which is why that line beat SPY.
- **The window is the right size.** On average 19 stocks were in a window each day, which matches four
  announcements a year × 3 days × 394 stocks ÷ 252 days.

## What this means

The earnings premium, measured on decades of data before 2007, is gone in large US stocks since 2016.
That fits McLean & Pontiff's finding that published effects shrink. And even where the premium
exists, holding only the ~19 stocks with news that day is a very risky portfolio.

The one hint is the **5-day run-up before announcements** (+0.035% a day, t 2.5, about 0.18% per
event). But it was one of several extra looks, below the t ≥ 3 bar a new idea needs. It is also
smaller than the round-trip cost of trading it (0.10%) plus the risk of holding a handful of stocks.
Noted, not pursued.

## Sources

- Beaver, W. (1968). The Information Content of Annual Earnings Announcements. Journal of Accounting Research 6.
- Chari, V., Jagannathan, R. & Ofer, A. (1988). Seasonalities in Security Returns: The Case of Earnings Announcements. Journal of Financial Economics 21(1).
- Frazzini, A. & Lamont, O. (2007). The Earnings Announcement Premium and Trading Volume. NBER Working Paper 13090.
- Barber, B., De George, E., Lehavy, R. & Trueman, B. (2013). The Earnings Announcement Premium Around the Globe. Journal of Financial Economics 108(1).
- Savor, P. & Wilson, M. (2016). Earnings Announcements and Systematic Risk. Journal of Finance 71(1).
- Data: Yahoo earnings dates; Alpaca adjusted daily bars; Wikipedia S&P 500 member lists.
