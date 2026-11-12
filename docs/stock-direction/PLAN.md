# Stock direction model: the plan, fixed before any result was seen

*Written 2026-11-11, before the backtest was run or any outcome looked at. Agreed in conversation
with the owner. Committed to git so the date and contents are on record. Anything changed after the
results are in must be listed under "Changes after results" at the bottom, with the reason. Changes
there don't count toward the verdict; they would need a v2 and a fresh test.*

## The question

Every week, for each S&P 100 stock: **what's the chance it beats the S&P 500 (SPY) over the next
week?** One probability per stock per week, scored with the Brier score like the rest of the ledger.

## Universe

- The 100 companies in the S&P 100 (components table on Wikipedia, as of 2026-09-21, read
  2026-11-11; `shared/sp100.json`). GOOG left out, since it's the same company as GOOGL.
- Sector of each stock: its GICS sector from the same table, matched to that sector's SPDR ETF
  (XLK, XLV, XLF, XLY, XLP, XLC, XLI, XLE, XLU, XLB, XLRE). That's a fixed rule, not a judgment.
- A stock is in a week's ranking only if all four inputs exist for it that week. GEV (spun off
  April 2024), SNDK (Feb 2025) and BNY (renamed from BK in 2025; options under the new ticker only) join
  when their data starts.
- **Known bias:** today's members are used for the whole past (survivorship). Stocks that joined
  after big runs (PLTR, ANET, GEV, SNDK, DELL...) are in the past data although nobody knew in 2024
  they'd be members. This flatters anything that rewards recent winners (input 4).
- ETFs are not predicted. The research is on individual stocks, and ETF options are mostly bought as
  portfolio insurance, so the same signals would mean something else.

## Data

- Options: daily trade bars per contract from Alpaca (`option_bars_daily`): each day's volume-weighted
  average price (VWAP), volume and number of trades. History from 2024-02-01. Only Friday-ending
  expirations, strikes within 10% of the stock's range, the 45 days before each expiration (how
  `backfill_alpaca.py` downloads). No quotes, no open interest.
- Stocks: Alpaca daily bars (`stock_bars_daily`, raw), with each day's VWAP. Returns use
  `stock_bars_split_adj` plus cash dividends (total return).
- Dividends: Alpaca corporate actions (cash dividends, ex-date and amount).
- Interest rate: 3-month Treasury bill (FRED series DTB3, from the Fed's St. Louis bank).

## Implied volatility, each option each day

- Price: the option's VWAP that day, against the stock's VWAP that day (both day averages, so a late
  rally doesn't make a fake gap).
- Model: the stock price reduced by the present value of cash dividends going ex before expiration,
  and the T-bill rate. Calls: Black-Scholes (with dividends taken out, an American call is worth the
  European one). Puts: Black-Scholes plus the early-exercise premium from a Cox-Ross-Rubinstein binomial
  tree (what OptionMetrics, the papers' data, uses), worked out once on a grid and looked up. Tested
  against a 2,000-step tree: within 0.1 volatility point.
- Kept: options with at least **5 trades** that day, **10 to 60 days** to expiry (Xing, Zhang & Zhao),
  an implied volatility between 3% and 200% (extreme values dropped, as in the papers), and at least
  **10% of the price as time value** (judgment: a deep in-the-money option worth little more than its
  exercise value gives a volatility that's guesswork; in tests its error ran to several points).
- Moneyness = strike / stock price.

## The four inputs

All weekly values come from the daily values over the week, **Tuesday close to Tuesday close** (the 5
trading days ending Tuesday), as in Xing, Zhang & Zhao. They averaged the days; we take the **median
day** instead (see "Changes before results" below). A week needs at least 3 good days.

| # | Input | Exact definition | Direction (fixed in advance) | Source of definition and direction |
|---|---|---|---|---|
| 1 | Call-vs-put gap | Each day: every strike and expiry where both the call and the put qualify; call IV minus put IV, averaged with each pair weighted by its combined volume | Higher = more likely to beat | Cremers & Weinbaum (2010). They weighted by open interest; we have none, so volume |
| 2 | Crash-protection price (SKEW) | Each day: volume-weighted IV of out-of-the-money puts (moneyness above 0.80, below 0.95) minus volume-weighted IV of at-the-money calls (0.95 to 1.05) | Higher = less likely to beat | Xing, Zhang & Zhao (2010). Their volume-weighted version (their robustness check, which also worked: 19 basis points a week) |
| 3 | Change in call and put prices | ΔCVOL: this week's volume-weighted IV of at-the-money calls (0.95-1.05) minus the same 4 weeks earlier. ΔPVOL: the same for at-the-money puts. Input 3 = average of the rank of ΔCVOL and the rank of minus ΔPVOL | Calls rising = more likely; puts rising = less likely | An, Ang, Bali & Cakici (2014): monthly changes in at-the-money 30-day call and put IV, still significant among big stocks and in 2006-2011 |
| 4 | Last week compared with its sector | Stock's total return minus its sector ETF's, over the week ending Tuesday close | Higher = more likely to beat (keeps going) | Medhat & Schmeling (2022): among the largest, most heavily traded stocks, last month's winners keep winning. Measured against the sector because Hameed & Mian (2015) show sector-relative moves are the ones that reverse or persist on their own |

Input 5 (12-month trend) was proposed and then dropped by agreement: a months-long effect with little
to say about a single week, added without a reason tied to this model.

## The outcome

- Prediction made after Tuesday's close, from data through Tuesday.
- Outcome window: **Wednesday close to the next Wednesday close** (one day skipped, as in Xing, Zhang &
  Zhao, so option and stock closes don't overlap). If Wednesday is a holiday, the next trading day.
- Outcome = 1 if the stock's total return beat SPY's total return over that window, else 0.

## How a prediction is made

1. Each week, rank the stocks on each input from 0 to 1 (percentile), turned so that 1 always means
   "more likely to beat".
2. **Model E (equal weights):** score = average of the four ranks. Probability = a logistic curve of
   the score with two numbers (level and slope), fitted on the building period only.
3. **Model L (learned weights):** a logistic regression on the four ranks, fitted on the building
   period only (the answer-key fit), then frozen.
4. **Baseline "base rate":** the share of stock-weeks in the building period that beat SPY, every
   week, for every stock. This is the honest "coin flip": a model that knows nothing still learns the
   base rate. A plain 50% is also reported.
5. **Baseline "price only":** input 4 alone, through the same logistic curve, fitted on the building
   period. This checks whether options add anything beyond last week's move.

## Periods

- **Building:** weeks whose outcome window ends on or before 2025-12-31 (inputs exist from about
  March 2024). Used to fit the curves and weights, and for looking around with the answer key.
- **Test:** weeks whose outcome ends from 2026-01-01 to 2026-11-11 (about 45 weeks). Not looked at
  until the code and this plan are final; then run once.

## Scoring and the verdict

- Each week: each model's average Brier score over that week's stocks. Weeks are the independent
  units (stocks in the same week move together).
- Compare model and baseline week by week: average gap and its noise allowing for streaks (the
  ledger's own `compare`). **Clear pass:** better than a baseline by more than twice the noise.
  **Lean pass:** lower score, but within the noise.
- **Goes live if** E or L has a lower test score than both baselines (lean or clear). If both do, E,
  unless L is a clear pass against E. Going live only means logging predictions in the ledger (no
  trading), so the live record keeps judging it. If neither passes, the write-up says so and the
  model stops.

## Also reported (none of it changes the verdict)

- Each input on its own, building and test: average weekly rank correlation with the outcome and its
  t-statistic. This answers whether input 3 adds anything beyond input 1, and whether last week's move
  keeps going or bounces back.
- Calibration table: predicted bands against how often they came true.
- Top fifth minus bottom fifth: the average weekly return difference (paper only, no trading costs).
- Robustness, each run once: minimum trades 1 and 10 instead of 5; crash protection from the single
  options closest to 0.95 and 1.0 (Xing's main version) instead of volume-weighted; input 3 measured
  against each stock's own past 26 weekly changes (the owner's "normal wobble" idea); Tuesday only
  instead of the week's median; the week's average (Xing's way) instead of its median.

## Known weaknesses, stated in advance

- 2¾ years of options data, about 95 building and 45 test weeks: only an effect about as strong as
  the original papers' could stand out. A faded effect will look like noise.
- Published effects shrink by about 58% on average after publication (McLean & Pontiff 2016).
  Cremers & Weinbaum's own gap was no longer significant in 2001-2005.
- Muravyev, Pearson & Pollet (2022): once stock borrowing costs are counted, the gap and the skew stop
  predicting. Our stocks are cheap to borrow, so inputs 1 and 2 may carry little.
- Trade prices, not quotes; volume weights, not open interest; a stale option VWAP can still sit
  against a whole-day stock VWAP.
- Survivorship (above).

## Predictions, made before the results

1. Equal weights beat learned weights on the test (about 70% likely).
2. The options inputs add little beyond price only (about 70% likely).
3. Best single input: crash protection (low confidence).
4. Last week's move keeps going rather than bouncing back (low confidence; survivorship tilts this
   way too).
5. Most likely overall: everything within noise of the base rate. About 30% chance any version
   passes.

## Sources

- Cremers & Weinbaum (2010), JFQA 45(2): https://ideas.repec.org/a/cup/jfinqa/v45y2010i02p335-367_00.html
- Xing, Zhang & Zhao (2010), JFQA 45(3): https://ideas.repec.org/a/cup/jfinqa/v45y2010i03p641-662_00.html
- An, Ang, Bali & Cakici (2014), JF; NBER w19590: https://www.nber.org/papers/w19590
- Medhat & Schmeling (2022), RFS 35(3): https://econpapers.repec.org/RePEc:oup:rfinst:v:35:y:2022:i:3:p:1480-1526.
- Hameed & Mian (2015), JFQA 50(1-2): https://ideas.repec.org/a/cup/jfinqa/v50y2015i1-2p89-117_00.html
- Muravyev, Pearson & Pollet (2022), JF 77(3): https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:3:p:1787-1828
- Gonçalves-Pinto et al. (2020), Management Science 66(9): https://econpapers.repec.org/RePEc:inm:ormnsc:v:66:y:2020:i:9:p:3903-3926
- McLean & Pontiff (2016), JF: https://Www.Gwern.net/doc/economics/2016-mclean.pdf
- Bjerksund & Stensland (1993), "Closed-form approximation of American options", Scandinavian
  Journal of Management 9.

## Changes before results (no outcome had been looked at)

- 2026-11-11, pricing: the Bjerksund-Stensland 1993 formula first planned for puts was tested against an
  exact binomial tree and overstated in-the-money put volatility by 0.2-0.4 points, enough to bias the
  call-vs-put gap. Replaced by the binomial tree's own early-exercise premium on a grid.
- 2026-11-11, the 10% time-value rule (above), from the same tests.
- 2026-11-11, weekly median instead of mean: on AAPL, the daily call-vs-put gap's day-to-day spread rose
  from 0.6 points on calm days to 2.6-3.9 points on days with a 2-5% intraday range, because an option's
  average price and the stock's average price then come from different moments. On 2025-04-09 (AAPL up
  15% intraday) the gap read -13 points. The median of 5 days ignores one or two such days. This is a
  weakness of our data (no quotes), not a choice in the research; the mean is kept as a robustness check.
- 2026-11-11, a week counts only if at least 10 stocks have every input (judgment: ranks among a
  handful of stocks mean little). Only affects thin early weeks, if any.
- 2026-11-11, windows: the outcome window starts at the first trading day after the prediction day and
  ends at the first trading day after the next week's prediction day (normally Wednesday to Wednesday).
  When a Wednesday is a holiday this moves to Thursday, so a day is always skipped after the inputs.

## Stage 2: tuning, then one final test (added 2026-11-11, before any result)

The owner asked for the models to be compared, changed on what's seen, and tested again. To keep the
2026 test fair, every change is chosen on 2024-25 only:

- **Two folds inside the building period:** learn on 2024 and score 2025, then learn on 2025 and score
  2024. Same fitting as the main plan, just on one year.
- **Variants tried, one at a time from v1:**
  - weekly value: mean, trimmed mean (the average without the week's highest and lowest day), half
    median and half mean, a third each of median, mean and trimmed (all the owner's suggestions), and
    Tuesday only;
  - minimum trades 1 and 10;
  - crash protection from the single closest options;
  - change measured against the stock's own normal wobble;
  - last week's move reversing instead of continuing;
  - each input dropped in turn;
  - learned weights instead of equal.
- **Adoption rule:** a change is adopted only if it beats v1 in **both** folds (scored on the stock-weeks
  both versions have). Within a group, the one with the best average gain. One change per group, then
  combined into v2. If the combination doesn't beat v1 in both folds, v2 is the single best change.
  If nothing beats v1 in both folds, there is no v2.
- **Final test:** v1 (as planned above) and v2 each run once on 2026, fitted on all of 2024-25.
  Same pass rules. v2 also has to beat v1 there to replace it. Every variant tried is listed in the
  write-up, so the number of tries is on record.
- **Going live** (owner's OK, 2026-11-11, as long as it costs nothing): the version that passes goes
  into the ledger as a live model with a weekly job. If none passes, nothing goes live.

## Changes after results

(none yet)
