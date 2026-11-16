# The signal stack: the plan, fixed before any result

*Written 2026-11-16, before any signal was computed or any return looked at for this study. Changes
go at the bottom and don't count. Status: **plan only. Nothing is built or run yet.***

## The idea

Professional quant funds don't rely on one strong signal. They combine many weak ones, each barely
better than a coin flip, across hundreds of stocks (Grinold's "fundamental law"; Gu, Kelly & Xiu 2020;
Jensen, Kelly & Pedersen 2023). This is the one approach the project hasn't tried properly.

**How it avoids fitting noise:** every signal's direction comes from its original paper, fixed below.
Signals are combined with equal weights. Nothing is tuned on the data, so the backtest is one test,
not a search.

## Stocks, timing, costs

- **Stocks:** S&P 500 members at the time (`shared/sp500_history.json`), prices from `daily_bars_adj`.
- **Weekly:** signals from Tuesday's close, positions from Wednesday's close to the next Wednesday's
  close (the one-day gap the stock direction model uses).
- **Scoring a signal:** each week, rank the stocks on it from −0.5 (worst) to +0.5 (best), in the
  direction below. A stock missing a signal gets 0 for it. A signal is used in a week only if at
  least 80% of stocks have it.
- **Costs:** 0.05% per dollar traded; 0.5% a year to borrow shorted stock.
- **Period:** 2017-01 to 2026-10 (the first year of prices builds the signals).

## The signals

Direction: **+** means higher is expected to do better, **−** worse.

| # | Family | Signal | Dir | Source |
|---|---|---|---|---|
| 1 | Momentum | Return over months 12 to 2 | + | Jegadeesh & Titman 1993 |
| 2 | Momentum | Return over months 6 to 2 | + | Jegadeesh & Titman 1993 |
| 3 | Momentum | Return over months 12 to 7 | + | Novy-Marx 2012 |
| 4 | Momentum | Price ÷ its 52-week high | + | George & Hwang 2004 |
| 5 | Momentum | Months 12 to 2 return after removing the market's part (by beta) | + | Blitz, Huij & Martens 2011 |
| 6 | Momentum | Price ÷ its 200-day average | + | Han, Yang & Zhou 2013 |
| 7 | Momentum | Its sector's 6-month return (if a sector map covers the stocks) | + | Moskowitz & Grinblatt 1999 |
| 8 | Reversal | Last week's return | − | Lehmann 1990 |
| 9 | Reversal | Last month's return | − | Jegadeesh 1990 |
| 10 | Reversal | Return over months 36 to 13 (from 2019) | − | De Bondt & Thaler 1985 |
| 11 | Low risk | Volatility of daily returns, 12 months | − | Blitz & van Vliet 2007 |
| 12 | Low risk | Volatility left after removing the market, 1 month | − | Ang, Hodrick, Xing & Zhang 2006 |
| 13 | Low risk | Beta to the market, 12 months | − | Frazzini & Pedersen 2014 |
| 14 | Low risk | Biggest one-day gain in the last month ("lottery") | − | Bali, Cakici & Whitelaw 2011 |
| 15 | Trading | Price impact per dollar traded (Amihud), 3 months | + | Amihud 2002 |
| 16 | Trading | Dollars traded per day, 3 months | − | Brennan, Chordia & Subrahmanyam 1998 |
| 17 | Trading | Last week's volume ÷ its 3-month average | + | Gervais, Kaniel & Mingelgrin 2001 |
| 18 | Calendar | Its average return in this calendar month in past years (from 2018) | + | Heston & Sadka 2008 |
| 19 | Calendar | An earnings report is due in the week | + | Barber, De George, Lehavy & Trueman 2013 |
| 20 | Calendar | A dividend is expected in the month (if dividend data covers the stocks) | + | Hartzmark & Solomon 2013 |
| 21 | Earnings | Return over the 3 days around its last report, held 60 days | + | Chan, Jegadeesh & Lakonishok 1996 |
| 22 | Options* | Price of crash protection (out-of-the-money put volatility − at-the-money call) | − | Xing, Zhang & Zhao 2010 |
| 23 | Options* | Call volatility − put volatility, same strike | + | Cremers & Weinbaum 2010 |
| 24 | Options* | Change in call volatility, 4 weeks | + | An, Ang, Bali & Cakici 2014 |
| 25 | Options* | Change in put volatility, 4 weeks | − | An, Ang, Bali & Cakici 2014 |
| 26 | Options* | Implied volatility − actual volatility | + | Bali & Hovakimian 2009 |
| 27 | Options* | Option volume ÷ stock volume | − | Johnson & So 2012 |

\* Options history starts in February 2024, so these join the stack from then.

**Known going in, and left as the papers say:** in this project's own earlier tests on 2024-2026,
signal 14 ran the wrong way, signal 19 showed nothing, signal 21 faded in 2026, and signal 22 pointed
the right way. Flipping or dropping any of them now would be fitting to data already seen.

**Stage 2, not in this plan's test:** about 15 signals from company accounts (profitability, earnings
quality, asset growth, share issuance, value and others) need point-in-time filings from the SEC's
EDGAR service. The SEC asks automated downloaders for a contact email, so this waits for the owner.
Adding them is a new version with its own plan.

## Versions (4, all counted)

| Version | How signals are combined | Portfolio |
|---|---|---|
| **A1 (main)** | Average within each family, then average the families | Long-only: the top fifth of stocks, equal amounts |
| A2 | Same | Long the top fifth, short the bottom fifth (an overlay on SPY) |
| B1 | Plain average of all signals | Long-only top fifth |
| B2 | Same | Long-short overlay |

To hold down trading, a stock stays in the top (or bottom) fifth until it drops out of the top (or
bottom) two-fifths.

## Yardsticks

- **SPY**, in dollars and Sharpe ratio.
- **All the stocks in equal amounts**, rebalanced weekly at the same cost. This matters: a long-only
  basket of S&P 500 stocks can beat or trail SPY just by not being weighted toward the giants.

## Pass rules ("worth a live paper record")

- **Long-only (A1, B1):** more money **and** a better Sharpe ratio than SPY **and** than the
  equal-amounts basket, over the whole period **and** in each half (2017-2021, 2022-2026).
- **Overlay (A2, B2):** the long-short return is positive with a block-bootstrap 95% range above zero,
  it's positive in both halves, **and** SPY plus the overlay beats SPY in money and Sharpe ratio.
- Also reported, not part of the rule: each signal's own weekly rank correlation with next week's
  return, so it's clear which ones are alive.

## Honest limits, written now

- **These years aren't untouched.** Earlier studies here looked at S&P 500 prices for 2017-2026 (pairs)
  and at options signals for 2024-2026 (stock direction). Fixing every direction from the papers keeps
  this to one test, but only a live record is fully clean.
- Large stocks after 2016 are where published signals are weakest. A small edge or none is the likely
  result.
- A signal this weak needs about 3-4 years of live results to prove.
- Shorting costs and trading costs for a small account can be higher than assumed.

## Changes

All three were made on 2026-11-16 **before any strategy result was looked at**. The first run's output was
opened only for its mechanics: how many weeks each signal was used, the number of stocks, and SPY's own return.

1. **Coverage rule: 80% changed to 30%.** With 80%, all six options signals, the dividend signal and most weeks
   of the earnings signals were never used, because options trade actively enough in only about half the stocks
   and the earnings and dividend tables cover today's members, not past ones. A stock missing a signal still
   gets 0 (neutral) for it, so low coverage only waters a signal down.
2. **Options data:** days with 5 or more trades per option, as in the stock direction model. The plan didn't say.
3. **Signal 21** is measured against SPY's return over the same three days, as in the paper, since stocks
   report on different days.
