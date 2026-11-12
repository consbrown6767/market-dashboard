# Stock direction model

*Built 2026-11-11. Plan fixed before any result: `PLAN.md` (same folder, in git with its dates).
Code: `collectors/stock_direction.py`, tests `collectors/test_stock_direction.py`. Scored in the
prediction ledger and shown on the Scorecard tab. Live from Tuesday 2026-11-17 (first predictions for
Wednesday 11-18 to Wednesday 11-25). Fresh test on the other 400 S&P 500 stocks and five more signals:
2026-11-12.*

## In one paragraph

Every week, for each S&P 100 stock, the model gives the chance that it beats the S&P 500 (SPY) over
the next week. It reads what options traders are paying for: calls against puts, crash protection,
and how those prices just changed. It also uses last week's move against the stock's sector.
**The honest result: no version reliably beats the simple base rate.** "Each stock has about a 49.5%
chance" is as good as anything we built, in 2024-25 and in the sealed 2026 test. One input, the price
of crash protection, pointed the right way in both periods but not strongly enough to rule out luck.
The fresh test on the other 400 S&P 500 stocks (2026-11-12) backed that one input up: crash
protection pointed the right way there too, in both periods, and alone it scored lower than both
baselines in 2026 (still within noise). Of five more research signals, none clearly worked.
Three versions log live predictions, because it costs nothing and the live record is the only fair
judge from here.

## What it predicts, and when

- **Target:** 1 if the stock's total return (dividends included) beats SPY's from one Wednesday's
  close to the next Wednesday's close, else 0. Each prediction is a probability.
- **Made:** Tuesday evening (6:40 pm job), from data through Tuesday's close. One day is skipped
  before the window opens, as in the research, so option and stock closing prices can't overlap.
  Holiday weeks shift by a day.
- **Universe:** the 100 S&P 100 companies (`shared/sp100.json`), about 90 a week with enough options
  trading. ETFs are not predicted.

## The inputs

Each from a published paper. Weekly values come from the 5 days Tuesday to Tuesday.

| Input | What it is | Points to "beats SPY" when | Source |
|---|---|---|---|
| Call-vs-put gap | Call minus put implied volatility, same strike and expiry, volume-weighted | Calls are pricier | Cremers & Weinbaum (2010) |
| Crash protection | Out-of-the-money put volatility minus at-the-money call volatility | Protection is cheap | Xing, Zhang & Zhao (2010) |
| Change in call and put prices | At-the-money call and put volatility now against 4 weeks ago | Calls got pricier, puts cheaper | An, Ang, Bali & Cakici (2014) |
| Last week against its sector | Stock's weekly return minus its sector ETF's | It beat its sector (keeps going) | Medhat & Schmeling (2022) |

Implied volatility is worked out by us from each option's average traded price that day against the
stock's average price. History: Feb 2024 to now, from Alpaca's free trade data. It uses dividends,
the T-bill rate, and a binomial tree for American puts (within 0.1 volatility point of an exact tree
in tests). Options count only with 5+ trades that day, 10-60 days to expiry, and at least 10% of the
price as time value.

## How we tested it

1. **Plan first.** Inputs, directions, timing, baselines and pass rules were written and committed
   before any outcome was looked at. Four fixes made before results are listed in `PLAN.md`.
2. **Building period** (outcomes through 2025-12-31, 95 weeks, ~8,500 predictions): fit the
   probability curves; look around with the answer key.
3. **Tuning** (owner's request): 16 variants, each learned on one of 2024 and 2025 and scored on the
   other. Adopted only if better than v1 in both years.
4. **Sealed test** (2026-01-07 to 2026-11-11, 45 weeks, 4,092 predictions): v1 and the tuned v2, run
   once (commit `fcb3925`).

**Baselines:** the base rate (49.5% for every stock, the share that beat SPY in 2024-25) and
"last week's move only".

**Scores:** Brier score (0.25 = always saying 50%; lower is better), compared week by week, with
noise allowing for streaks.

## Results

Gaps are in Brier points × 10,000; negative = better than the baseline. "±" is one unit of noise.
A real edge would need a gap about twice its noise.

### Each input alone (average weekly rank correlation with next week's result vs SPY)

| Input | 2024-25 | 2026 (sealed test) | Verdict |
|---|---|---|---|
| Crash protection | +0.021 (t 1.2) | **+0.032 (t 1.4, right in 62% of weeks)** | Right way both times, not proven |
| Call-vs-put gap | −0.006 | −0.018 | Wrong way both times |
| Change in call/put prices | −0.008 | −0.009 | Wrong way both times |
| Last week against sector | −0.011 | −0.022 | Slight bounce-back both times (not "keeps going") |

### The sealed 2026 test

| Version | vs base rate | vs last-week-only | Plan's verdict |
|---|---|---|---|
| v1, equal weights | −0.01 ± 0.24 | +1.07 ± 1.49 | **Fail** (it simply says ~49.5% for everyone) |
| v1, learned weights | −2.57 ± 2.79 | −1.49 ± 2.27 | **Lean pass** (lower than both, well within noise) |
| v2, equal weights, last week reverses | −0.82 ± 1.03 | +0.26 ± 1.19 | **Fail** |

- Top fifth minus bottom fifth (v1 equal weights): +0.06% a week, t 0.15. Nothing.
- The learned weights (fitted on 2024-25): crash protection +0.13, change −0.60, gap −0.01, last week
  −0.08. Most of its small edge comes from betting **against** the change signal, which ran backwards
  in 2024-25 and again in 2026. No research supports that direction, so treat it as probably luck.
- Robustness (v1 equal weights, each vs base rate): minimum trades 1 or 10, closest-option crash
  protection, Tuesday only, weekly mean, change against its own wobble. All within ±1 point of zero.

### The tuning log (2024-25 only; 16 variants)

Gap vs base rate when learned on 2024 and scored on 2025 / learned on 2025 and scored on 2024. v1:
+1.48 / +1.48.

| Variant | 2025 / 2024 | Beat v1 both years? |
|---|---|---|
| Weekly mean instead of median | +0.72 / +0.30 | yes |
| Weekly mean without highest and lowest day | +1.03 / +0.93 | yes |
| Half median, half mean | +1.25 / +0.93 | yes |
| A third each of median, mean, trimmed | +1.13 / +0.89 | yes |
| Tuesday only | +2.69 / +3.19 | no |
| Minimum trades 1 | +4.21 / +3.00 | no |
| Minimum trades 10 | +2.32 / +2.94 | no |
| Crash protection from the single closest options | +0.28 / +1.31 | yes |
| Change against own 26-week wobble | +13.19 / +4.68 | no |
| **Last week reverses instead of continuing** | **−0.22 / −0.25** | yes (the only one better than the base rate in both years) |
| Drop the gap | +2.92 / +2.57 | no |
| Drop crash protection | −0.37 / +0.46 | yes |
| Drop the change | +2.10 / +1.76 | no |
| Drop last week | +0.57 / +0.15 | yes |
| Learned weights | +4.99 / +0.36 | no |

The best of each group combined did worse than v1 in both years (+1.60 / +2.04). So, by the rule,
v2 = the single best change (last week reverses). On the owner's question about the median: every
average-type measure beat the median in both years, the plain mean most. But the differences were
under one unit of noise.

## What went live, and why

The owner's instruction was to put a version live if it passed and cost nothing. Three versions log
predictions every Tuesday. No trading, and the job uses only free data (options history for the S&P
500, a few GB a year on this Mac, not in the backup):

- **1-learned:** v1 with learned weights. It goes live because the plan's pre-set rule says a lean
  pass goes live. Expect it to look like the base rate.
- **3-skew:** crash protection alone, Xing, Zhang & Zhao's original signal and the only input that
  pointed the right way both times. **It was chosen after seeing the 2026 results**, so 2026 can't
  judge it: its 2026 gap (−2.09 ± 1.41) is reported only as a hint. In the 2024-25 years it was mixed
  (+2.45 / −0.16). Only its live record counts.

Both are listed in `shared/stock_direction_live.json`. On the Scorecard they appear as
"Stock direction" with their versions. - **3-skew@sp400** (live from 2026-11-12): crash protection alone on the 400 other S&P 500 stocks,
  fitted on their 2024-25 weeks. It passed the pre-registered fresh test (lean pass), so by the stage 3
  rule the live universe grows to these stocks. About 150 predictions a week. Together with `3-skew`
  that's ~240 crash-protection predictions a week, which is the point: more predictions, sooner verdict.

Not live, though they lean-passed on the 400: v1 learned weights on the 400 (it mostly re-bets the same
crash-protection signal), post-earnings drift (failed on the S&P 100 in 2026, and live use would need
weekly earnings data from an unofficial Yahoo feed), and the reversed lottery signal (runs against its
research; looks like a 2024-26 fashion). Each could be switched on later as a new version.

All three are listed in `shared/stock_direction_live.json`. On the Scorecard they appear as
"Stock direction" with their versions. A real edge this small would take a year or more of live
predictions to show clearly.

## Stage 3: the fresh test on 400 other stocks (2026-11-12)

The S&P 100's 2026 results had been seen, so crash protection alone couldn't be judged on them. The
other 400 S&P 500 stocks' results had not. Same code, same versions, fitted on their 2024-25 weeks,
tested once on 2026 (commit `0986c0f`, file `fresh-sp400-2026-11-12.json`). About 130 of the 400 have
enough options trading each week (thinly traded options are left out by the same rules as before), so
the test has 45 weeks and 5,951 predictions. 49.4% beat SPY.

| Version | vs base rate | vs last-week-only | Two-year check (2025 / 2024) | Verdict |
|---|---|---|---|---|
| v1, equal weights | −0.13 ± 0.34 | +0.30 ± 1.28 | +0.18 / −0.07 | Fail |
| v1, learned weights | −2.11 ± 3.25 | −1.67 ± 3.24 | +0.02 / −5.25 | Lean pass |
| **Crash protection alone (`3-skew`)** | **−2.68 ± 2.75** | **−2.24 ± 3.08** | +0.64 / −2.81 | **Lean pass** |

Each input alone on the 400 (2024-25 / 2026):

| Input | 2024-25 | 2026 | Same as on the S&P 100? |
|---|---|---|---|
| Crash protection | **+0.028 (t 2.1)** | **+0.035 (t 1.6, right in 60% of weeks)** | Yes: right way again, a bit stronger |
| Call-vs-put gap | −0.003 | 0.000 | Nothing |
| Change in call/put prices | −0.005 | +0.011 | Nothing |
| Last week against sector | −0.014 | −0.006 | Slight bounce-back again |

**What it means:** crash protection has now pointed the right way in all four looks (two groups of
stocks, two periods), and the fresh one was decided in advance. That is the best evidence this project
has for any input. It is still a small effect: a 0.03 rank correlation, which moves each probability
only a couple of points away from the base rate (on the 400 for the week from 2026-11-11: 45.8% to 50.7%).
Not proven, but no longer likely to be pure luck.

## Stage 4: five more research signals (2026-11-12)

Picked from the research before any was computed (`PLAN.md`). Tested first on the S&P 100
(discovery), then on the 400 (confirmation). Rank correlation with next week's result, oriented so
positive = the paper's direction:

| Signal | Paper | S&P 100: 2024-25 / 2026 | 400: 2024-25 / 2026 | Verdict |
|---|---|---|---|---|
| Option-to-stock volume (low wins) | Johnson & So 2012 | −0.025 / −0.008 | −0.010 / +0.007 | Nothing |
| Earnings week (reporters win) | Frazzini & Lamont 2007 | −0.007 / −0.038 | −0.009 / 0.000 | Nothing; slightly the wrong way |
| Post-earnings drift (beats keep winning) | Bernard & Thomas 1989 | **+0.033 (t 2.3)** / −0.006 | **+0.026 (t 2.6)** / +0.015 | Worked in 2024-25, faded in 2026 |
| Realized minus implied volatility (low wins) | Bali & Hovakimian 2009 | −0.017 / −0.018 | +0.004 / +0.005 | Nothing |
| Lottery stocks (big recent jumpers lose) | Bali, Cakici & Whitelaw 2011 | −0.042 / −0.034 | −0.034 / −0.021 | **Opposite**, all four times: big jumpers kept winning |

As versions, scored against the base rate (2026 test):

| Version | S&P 100 | 400 |
|---|---|---|
| Option-to-stock volume | +3.93 ± 5.88 | +0.76 ± 2.59 |
| Earnings week | 0.00 ± 0.00 | −0.02 ± 0.22 |
| Post-earnings drift | +3.21 ± 2.94 | −1.28 ± 1.86 (lean pass) |
| Realized minus implied | −0.36 ± 1.26 | +0.37 ± 1.10 |
| Lottery | −1.31 ± 6.93 (lean pass) | −0.74 ± 5.64 (lean pass) |
| All six (crash protection plus the five) | +0.47 ± 2.21 | −0.26 ± 0.52 |

The lottery version's passes come from its curve learning the **reverse** of the paper (bet on recent
jumpers). That fits 2024-26, when the biggest movers (AI and chip stocks) kept running, but nothing in
the research says it should last, and its noise is the largest of all. Post-earnings drift passed on the
400 but failed on the S&P 100 in 2026. Neither goes live: see below.

## What we learned

- Options signals that worked in the 1996-2011 research don't show up for the 100 biggest US stocks
  in 2024-26, with our data. That fits the later research: these effects faded after publication
  (McLean & Pontiff), and much of what was left was about stocks that are costly to borrow
  (Muravyev, Pearson & Pollet). Our stocks are cheap to borrow.
- Last week's move bounced back slightly rather than continuing, against Medhat & Schmeling. Small,
  and in both periods.
- Crash protection is the one thread worth following, and the fresh 400 backed it up.
- Of five more published signals, none held in 2026. Post-earnings drift was the strongest in
  2024-25 and then faded. Recent big jumpers kept winning, the reverse of the lottery research.

## Limits

- No option quotes, only trades. Daily average prices from different moments of the day add noise,
  most on big-move days.
- No open interest history, so the papers' open-interest weights became volume weights.
- About 2¾ years of options data. Only effects about as strong as the original papers' could have
  shown.
- Today's S&P 100 and S&P 500 members are used for the whole past (survivorship).
- On the 400, only about a third of the stocks (the ones with busier options) get predictions in a
  given week, so "the 400" really means the more-traded part of it.
- BNY's options before its 2025 ticker change aren't included. GEV and SNDK start when they were
  listed.

## Upkeep

- Job `direction`, weekdays 6:40 pm. On a week's last trading day (normally Tuesday) it downloads the
  S&P 500 stocks' options (about an hour, under the free-plan request limit), recomputes the last 50
  days of implied volatility, and predicts. Each live version names its stock list (`universe`, default
  the S&P 100) in `shared/stock_direction_live.json`. On other days it refreshes prices and resolves predictions
  whose window has closed.
- Commands, from `collectors/`:
  - `stock_direction.py live --dry-run 2026-11-10`: what it would predict that day; logs nothing.
  - `stock_direction.py iv [SYMBOLS]`: recompute implied volatility.
  - `stock_direction.py explore`: the answer-key look at 2024-25.
  - `stock_direction.py tune`: the tuning log.
  - `stock_direction.py signals`: stage 4 on the S&P 100. `stock_direction.py --universe sp400 fresh`:
    the stage 3/4 fresh test (already run once; rerunning it is no longer a fair test).
  - `stock_direction.py earnings [SYMBOLS]`: refresh earnings dates from Yahoo.
- The 2026 test can't be rerun as a fair test: it's been seen. Any new version is judged live.
- S&P 100 membership changes: edit `shared/sp100.json`, run `backfill_alpaca.py NEWSYMBOL` and
  `stock_direction.py iv NEWSYMBOL`, then `install.sh`. That's a new version.
- Ideas not built:
  - Crash protection held for a month, not a week. Xing et al. found it lasts up to 6 months, and a
    longer hold suits its slow drift.
  - Option-implied borrowing cost (Muravyev, Pearson & Pollet).
