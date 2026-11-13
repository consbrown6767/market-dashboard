# Round 4 and the tournament (2026-11-12)

*Plan fixed before any result: `PLAN.md` (commit `4f227f4`). Code: `collectors/tournament.py`.
Full results: `~/MarketData/tournament/backtest-2026-11-12.json`.*

## The answer

**By the rules set beforehand, no strategy beats SPY.** "Best for beating SPY" (T1) has no
qualifier, so the answer is SPY itself. "Best risk-adjusted" (T2) is the **10-month trend rule**:
the same rule as `docs/classic-strategies/`, holding the market only while it's above its 10-month
average. From 2006 to 2025 it made 10.0% a year against SPY's 10.9%, with a worst drop of −18%
against −51%. Its better Sharpe ratio is within noise; its crash protection is the solid part.

**The closest thing to a winner is leveraged trend** (Gayed & Bilello 2016): hold 2x the market
while it's above its 200-day average, else T-bills. It made the most money of all 24 strategies in
every period: since 2016 18.5% a year against 14.9%, and since 1928 far more. Over 98 years its
better Sharpe ratio is beyond noise. It failed its rule because after publication (2016-2026) its
Sharpe ratio was lower than SPY's (0.75 vs 0.83), and its worst drop was deeper (−29% vs −25%).

## Round 4: the nine new strategies

$10k from each one's after-publication start, after costs, against its yardstick (the US market
for 10-14, the S&P 500 total return for 15-18):

| # | Strategy | From | Strategy | Yardstick | Sharpe | Worst drop | 100-year gap t | Verdict |
|---|---|---|---|---|---|---|---|---|
| 10 | Leveraged trend, 2x above 200-day average | 2016 | **$61.9k** | $44.5k | 0.75 vs 0.83 | −29% vs −25% | **4.86** | Fail (Sharpe) |
| 11 | Dual momentum | 2012 | $27.6k | $78.3k | 0.47 vs 0.93 | −29% vs −25% | −0.46 | Fail |
| 12 | Four-factor mix | 2012 | $72.1k | $78.3k | 0.87 vs 0.93 | −22% vs −25% | **3.35** | Fail |
| 13 | Industry momentum with trend (my idea) | 2006 | $63.3k | $92.4k | 0.58 vs 0.66 | −22% vs −50% | 0.67 | Fail |
| 14 | Small value with trend (my idea) | 2006 | $45.8k | $92.4k | 0.42 vs 0.66 | −40% vs −50% | 1.09 | Fail |
| 15 | Put-selling (CBOE PUT) | 2007 | $35.6k | $72.8k | 0.53 vs 0.65 | −33% vs −51% | −2.35 | Fail |
| 16 | Covered calls (CBOE BXM) | 2002 | $41.1k | $111.5k | 0.44 vs 0.63 | −36% vs −51% | −2.91 | Fail |
| 17 | Protective puts (CBOE PPUT) | 2008 | $43.6k | $73.8k | 0.59 vs 0.67 | −32% vs −46% | −4.40 | Fail |
| 18 | Collar (CBOE CLL) | 2008-09 | $30.6k | $83.2k | 0.45 vs 0.74 | −22% vs −36% | −3.16 | Fail |

- **Option strategies all lost to SPY** on money and on Sharpe, using real option prices. Selling
  insurance (puts, calls) gave up too much in rallies. Buying insurance (protective puts, collar)
  cost too much: protective puts made 3 points a year less than the S&P 500 since 1988. This matches
  Israelov's "Pathetic Protection".
- **The four-factor mix** beat the market over 1963-2026 (t 3.35) but not since 2012.
- **My two trend-filtered near misses** cut crashes but lost money since 2006. They couldn't
  have won anyway (rule T3).

## The tournament: every strategy tested today, 2006-01 to 2025-09, after costs

SPY (S&P 500 total return minus SPY's fee): **10.9% a year, Sharpe 0.65, worst drop −51%, $10k → $77.2k.**

| Strategy | Own test | Per year | Sharpe | Worst drop | $10k becomes | vs SPY, per year |
|---|---|---|---|---|---|---|
| Leveraged trend (2x above 200-day average) | fail | **12.9%** | 0.58 | −37% | **$109.0k** | +3.2 |
| Profitability (top fifth) | fail | 12.6% | 0.76 | −43% | $104.3k | +1.5 |
| Industry momentum (top 10 of 49) | fail | 11.3% | 0.60 | −47% | $83.5k | +0.8 |
| Low volatility (lowest fifth) | fail | 11.2% | 0.79 | −37% | $81.0k | −0.2 |
| **SPY** | | **10.9%** | **0.65** | **−51%** | **$77.2k** | |
| Four-factor mix | fail | 10.4% | 0.60 | −48% | $69.9k | −0.4 |
| **Trend, 10-month** | **safer** | 10.0% | **0.79** | **−18%** | $65.6k | −1.4 |
| Industry momentum with trend (my idea) | fail | 9.8% | 0.62 | −22% | $62.8k | −1.3 |
| Trend, 12-month | fail | 8.8% | 0.62 | −28% | $52.5k | −2.4 |
| Macro timing | fail | 8.6% | 0.47 | −67% | $51.4k | −1.6 |
| Stock momentum (top tenth) | fail | 8.5% | 0.42 | −53% | $49.7k | −1.3 |
| Volatility-managed, up to 1.5x | fail | 8.0% | 0.72 | −16% | $46.0k | −3.4 |
| Protective puts | fail | 7.9% | 0.56 | −39% | $45.1k | −3.2 |
| Risk budget, 15% risk | fail | 7.9% | 0.61 | −17% | $45.1k | −3.3 |
| Small value | fail | 7.6% | 0.37 | −62% | $42.5k | −1.6 |
| Halloween | fail | 7.6% | 0.56 | −30% | $42.4k | −3.6 |
| Small value with trend (my idea) | fail | 7.5% | 0.42 | −40% | $41.9k | −2.9 |
| Volatility-managed, never borrow | fail | 7.4% | 0.77 | −12% | $41.1k | −4.1 |
| Risk budget, 10% risk | fail | 7.1% | 0.67 | −13% | $38.4k | −4.4 |
| Dual momentum | fail | 7.0% | 0.46 | −29% | $37.9k | −4.0 |
| Put-selling (from 2007-02) | fail | 6.3% | 0.48 | −33% | $31.4k | −4.6 |
| Collar (from 2008-09) | fail | 6.3% | 0.46 | −22% | $28.5k | −5.9 |
| Covered calls | fail | 5.4% | 0.39 | −36% | $28.3k | −5.7 |
| Turn of the month | fail | 2.0% | 0.09 | −15% | $14.9k | −9.3 |
| Pairs trading (from 2017) | fail | 1.6% | −0.37 | −3% | $11.5k | −13.8 |

French-based strategies use the whole US market, so their gap over SPY includes the
small difference between the whole market and the S&P 500.

**Three beat SPY on money in this window:** leveraged trend, profitability and industry
momentum. None did it after passing its own test. Each failed for the reasons in its write-up:
profitability and industry momentum were not beyond luck over 100 years and failed abroad;
leveraged trend had a lower Sharpe ratio after publication.

**Luck check (rule T4, as written):** profitability had the best gap over SPY per unit of
risk, but its chance of being real, after 25 tries, is 32%. Rule T4 applied to the T2 winner gives
0.2%, because that rule measures the gap over SPY, which a "safer" strategy gives up on purpose. See below.

## After the results (information only; recorded in PLAN.md)

**Is the 10-month trend's better Sharpe ratio real?** Block bootstrap 95% ranges for the Sharpe gap:
1927-2026 vs the market +0.10 (−0.08 to +0.30); 2006-2025 vs SPY +0.14 (−0.29 to +0.65);
1989-2026 vs SPY +0.06 (−0.22 to +0.37). **All include zero: not proven.** Its smaller crashes are
consistent across every period and market we have (round 2): the 2008 crisis −3% vs −50%, worst
drop over 100 years −44% vs −84%.

**Leveraged trend, stress-tested** (French US market, per year and Sharpe):

| Version | 1928-2026 | 2016-2026 | 2006-2025 |
|---|---|---|---|
| Plan (2x, trade at the signal close) | 17.0%, 0.63 | 18.5%, 0.75 | 12.9%, 0.58 |
| One more day of delay | 15.1%, 0.57 | 18.9%, 0.77 | 12.6%, 0.57 |
| Borrowing T-bill + 3% | 15.3%, 0.57 | 16.6%, 0.68 | 11.1%, 0.51 |
| 0.2% per dollar on switches | 15.0%, 0.56 | 16.7%, 0.68 | 10.7%, 0.49 |
| 1.5x | 14.2%, 0.64 | 15.1%, 0.76 | 10.8%, 0.59 |
| 3x | 21.7%, 0.63 | 24.1%, 0.73 | 15.9%, 0.56 |
| Market (buy and hold) | 10.2%, 0.45 | 14.9%, 0.83 | |

On the S&P 500 total return itself: 1989-2026 **$1.84M vs $571k**, Sharpe 0.61 vs 0.61, worst drop
−39% vs −51%. 2006-2025: $140k vs $77k, Sharpe 0.65 vs 0.65. 2016-2026: $64.4k vs $44.1k, Sharpe
0.77 vs 0.84, worst drop −30% vs −24%. By year since 2016, strategy vs SPY: 2017 +46% vs +22%; 2021
+61% vs +29%; 2022 −28% vs −18%; 2024 +45% vs +25%. It switches about 5 times a year.

1928-2026 Sharpe gap over the market: +0.19 (95% range +0.03 to +0.36), beyond noise over 98 years,
though not since 2016. Its volatility is 25% a year against the market's 18%. What it does is
**take more risk than the market in calm uptrends and none in downtrends.** Per unit of risk it has
roughly matched the S&P 500 since 1989, while being in cash for the worst of 2000-02 and 2008.

## What this means

1. **Nothing tested today reliably beats SPY on return per unit of risk** in the years after its
   research came out. That covers 24 strategies, from 20+ papers: timing, factors, options, pairs,
   macro, risk parity.
2. **The trend rule is the one thing that keeps working, as crash control.** At 1x it gives up a
   little return for much smaller crashes. At 2x (leveraged trend) it turns that into more money than
   SPY at roughly SPY's return per unit of risk, with smaller crashes except in sharp ones like 2020
   and 2022.
3. If you want to beat SPY in dollars and accept more swings, leveraged trend is the only candidate
   with a 98-year record behind it. It is not proven since 2016 by our rules. It loses badly in
   choppy years (2022: −28% vs −18%), it needs leverage (a 2x fund or margin), and its cost
   assumptions matter. The honest next step is a live paper record.

## Sources (new in round 4)

- Gayed, M. & Bilello, C. (2016). Leverage for the Long Run. SSRN (Dow Award 2016).
- Antonacci, G. (2014). Dual Momentum Investing. McGraw-Hill; (2012) Risk Premia Harvesting Through Dual Momentum. SSRN.
- Asness, C., Moskowitz, T. & Pedersen, L. H. (2013). Value and Momentum Everywhere. Journal of Finance 68(3).
- Whaley, R. (2002). Return and Risk of CBOE Buy Write Monthly Index. Journal of Derivatives 10(2).
- Israelov, R. & Nielsen, L. (2014). Covered Call Strategies: One Fact and Eight Myths. Financial Analysts Journal 70(6).
- Israelov, R. (2017). Pathetic Protection: The Elusive Benefits of Protective Puts. Journal of Alternative Investments.
- Bailey, D. & López de Prado, M. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management.
- Data: CBOE index history (PUT, BXM, PPUT, CLL); Yahoo ^SP500TR; French; FRED.

## Upkeep

None: nothing live. Rerun: `tournament.py data` then `tournament.py backtest` (needs the data
commands of the earlier rounds).

## Confirmation test of leveraged trend (2026-11-12): confirmed, with clear caveats

*Plan fixed first: `CONFIRM_PLAN.md` (commit `a25d9e3`). Results: `~/MarketData/tournament/confirm-2026-11-12.json`.*

**1. Four fresh markets, 1991-05 to 2026-09** ($10k, in US dollars):

| Market | Leveraged trend | Buy and hold | Sharpe | Worst drop |
|---|---|---|---|---|
| Developed ex US | **$510k** (11.7% a year) | $96k (6.6%) | **0.51** vs 0.33 | −39% vs −56% |
| Europe | **$471k** (11.5%) | $158k (8.1%) | **0.47** vs 0.40 | −45% vs −59% |
| Asia Pacific ex Japan | **$1.83M** (15.8%) | $193k (8.7%) | **0.58** vs 0.40 | −39% vs −60% |
| **Japan** | **$10.9k (0.2%)** | $34k (3.5%) | 0.05 vs 0.14 | **−86%** vs −58% |

3 of 4: pass. Japan shows the danger: a market that goes sideways for 35 years, with many false
signals, whipsawed the 2x version into an −86% drop.

**2. The real 2x fund (SSO), signal on SPY, trading a day after the signal, 2007-05 to 2026-10:**
$90.7k against SPY's $72.8k (12.0% vs 10.7% a year). It had a lower Sharpe ratio (0.55 vs 0.64),
more swings (22% vs 15% a year) and a smaller worst drop (−38% vs −51%). It switched 5.5 times a year.
Holding SSO all the time: $137k, but a −81% drop. Data checked: SSO's 2008 (−67.9%) and 2022
(−39.0%) match its published returns.

Bad years, strategy vs SPY: 2007 (May-Dec) −26% vs 0% (17 switches in 8 months); 2010 −9% vs
+15%; 2011 −11% vs +2%; 2015 −19% vs +1%; 2022 −34% vs −18%. Good years: 2008 −3% vs −37%;
2013 +71% vs +32%; 2021 +61% vs +29%; 2024 +44% vs +25%.

**3. Every 10-year stretch, 1928-2026 (US):** ahead in **79 of 89 (89%)**. Worst: 1998-2007, ×1.12
against the market's ×1.85.

**Information:** 100-, 150- and 250-day averages give 16.7-17.1% a year over 1928-2026 (the 200-day
gives 17.0%), so the result doesn't hinge on 200. Their worst drops are deeper (−66% to −73%).

**Verdict by the plan: confirmed.** In plain terms: in markets that trend (US, Europe, Asia,
developed ex US), it has made far more money than buying and holding, with smaller crashes. It
fails in markets that chop sideways (Japan; the US in 2007, 2010-11 and 2015). Since 2007 on the
real fund it took more risk than SPY and earned less per unit of it. The extra money came from
leverage plus dodging 2008, not from higher efficiency. It is the strongest candidate found, not
a sure thing.
