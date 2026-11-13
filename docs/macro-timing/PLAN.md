# Macro timing model: the plan, fixed before any result was seen

*Written 2026-11-12, before the model was run on any data. Committed to git so the date and
contents are on record. Changes after results go under "Changes after results" and don't count
toward the verdict.*

## The idea in plain English

An algorithm that reads only the economy and the market's valuation, never price charts. Each
month it estimates next month's stock return beyond T-bills from 14 economic indicators. It then
holds more stocks when that estimate is high and fewer when it's low.

## Research

- **Goyal & Welch (2008), Review of Financial Studies**, "A Comprehensive Look at the Empirical
  Performance of Equity Premium Prediction": 14 well-known indicators (dividend yield, earnings
  yield, interest rates, credit spreads, inflation...). Each one alone predicts **worse than the
  plain historical average** when used in real time. The data, updated by Goyal through 2025, is
  what this test uses.
- **Campbell & Thompson (2008), Review of Financial Studies**: with common-sense limits (never
  predict a negative stock premium), the predictions beat the average slightly, enough to help an
  investor a little.
- **Rapach, Strauss & Zhou (2010), Review of Financial Studies**, "Out-of-Sample Equity Premium
  Prediction: Combination Forecasts": **averaging the 14 single-indicator forecasts** beats the
  historical average reliably out of sample (1947-2005) and earns a real gain for a
  mean-variance investor. **This is the model.**
- **Known before testing:** Goyal, Welch & Zafirov (2024) report that most of these signals have
  performed poorly since 2005. This test checks for ourselves.

## Data

Goyal's monthly file (1871-2025): S&P 500 level, dividends and earnings (12-month sums), book-to-
market, T-bill, long-term government yield and return, AAA and BAA corporate yields, corporate bond
return, net equity issuance, stock variance, inflation, and CRSP S&P 500 returns with dividends.

## The 14 indicators (Goyal & Welch's definitions)

Dividend-price (log dividends − log price), dividend yield (log dividends − log last month's price),
earnings-price, dividend payout (log dividends − log earnings), stock variance, book-to-market, net
equity issuance, T-bill rate, long-term yield, long-term bond return, term spread (long yield −
T-bill), default yield spread (BAA − AAA), default return spread (corporate − government bond
return), inflation.

**Real-time lags**, so nothing is used before it was public: inflation one extra month (Rapach et
al.), and earnings-based indicators (earnings-price, payout) three extra months, since companies
report a quarter's earnings up to about three months later.

## The model (v1, fixed)

Each month-end t, using only data through t:

1. For each indicator, fit (by ordinary least squares, on all months from 1927-01 to t) next
   month's stock return above the T-bill on this month's indicator value. Predict next month.
2. **Combine:** the plain average of the 14 predictions (Rapach, Strauss & Zhou). If it's below zero,
   use zero (Campbell & Thompson).
3. **Invest:** stocks share = prediction ÷ (3 × variance of monthly stock returns over the last 60
   months), kept between 0 and 1.5 (Rapach et al.'s risk aversion of 3 and limits). The rest is in
   T-bills; borrowing beyond 1x costs the T-bill rate + 1%. Trading costs 0.05% per dollar traded.

**Benchmarks:**
- **Buy and hold** the market (CRSP S&P 500 with dividends), always 100%. The one to beat.
- **Historical average**: the same investing rule, but the prediction is the average past return.
  This is the "no information" version.

## Periods

- **Out of sample:** 1947-01 to 2025-12 (as in Rapach et al.; 20 years of learning first).
- **After publication:** 2006-01 to 2025-12 (Rapach et al.'s data ended in 2005).
- Decades 1950s-2010s, plus 2020-25.

## Pass rules

1. **After publication:** more money and a better Sharpe ratio than buy and hold.
2. **1947-2025:** prediction accuracy better than the historical average (out-of-sample R² above 0,
   Clark & West test one-sided p < 0.05), and a better Sharpe ratio than both buy and hold and the
   historical-average version.
3. **After publication:** out-of-sample R² above 0.
4. **Decades:** better Sharpe ratio than buy and hold in at least 5 of the 8.

## Always reported

- Each indicator alone (R² and its investing result), before and after publication.
- Without the real-time lags (as in the papers); risk aversion 2 and 5; limits 0 to 1; one-month
  delay. Information only.
- Crashes and every year.

## Changes after results

(none yet)
