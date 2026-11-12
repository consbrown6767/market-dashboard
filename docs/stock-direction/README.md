# Stock direction model

*Built 2026-11-11. Plan fixed before any result: `PLAN.md` (same folder, in git with its dates).
Code: `collectors/stock_direction.py`, tests `collectors/test_stock_direction.py`. Scored in the
prediction ledger and shown on the Scorecard tab. Live from Tuesday 2026-11-17 (first predictions for
Wednesday 11-18 to Wednesday 11-25).*

## In one paragraph

Every week, for each S&P 100 stock, the model gives the chance that it beats the S&P 500 (SPY) over
the next week. It reads what options traders are paying for: calls against puts, crash protection,
and how those prices just changed. It also uses last week's move against the stock's sector.
**The honest result: no version reliably beats the simple base rate.** "Each stock has about a 49.5%
chance" is as good as anything we built, in 2024-25 and in the sealed 2026 test. One input, the price
of crash protection, pointed the right way in both periods but not strongly enough to rule out luck.
Two versions log live predictions anyway, because it costs nothing and the live record is the only
fair judge from here.

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

## What went live (2026-11-11), and why

The owner's instruction was to put a version live if it passed and cost nothing. Two versions log
predictions every Tuesday. No trading, and the job uses only free data (about 1.5 GB a year of
options history on this Mac, not in the backup):

- **1-learned:** v1 with learned weights. It goes live because the plan's pre-set rule says a lean
  pass goes live. Expect it to look like the base rate.
- **3-skew:** crash protection alone, Xing, Zhang & Zhao's original signal and the only input that
  pointed the right way both times. **It was chosen after seeing the 2026 results**, so 2026 can't
  judge it: its 2026 gap (−2.09 ± 1.41) is reported only as a hint. In the 2024-25 years it was mixed
  (+2.45 / −0.16). Only its live record counts.

Both are listed in `shared/stock_direction_live.json`. On the Scorecard they appear as
"Stock direction" with their versions. With about 90 predictions a week, the ledger can give a
verdict after a few weeks. A real edge this small, though, would take a year or more to show.

## What we learned

- Options signals that worked in the 1996-2011 research don't show up for the 100 biggest US stocks
  in 2024-26, with our data. That fits the later research: these effects faded after publication
  (McLean & Pontiff), and much of what was left was about stocks that are costly to borrow
  (Muravyev, Pearson & Pollet). Our stocks are cheap to borrow.
- Last week's move bounced back slightly rather than continuing, against Medhat & Schmeling. Small,
  and in both periods.
- Crash protection is the one thread worth following.

## Limits

- No option quotes, only trades. Daily average prices from different moments of the day add noise,
  most on big-move days.
- No open interest history, so the papers' open-interest weights became volume weights.
- About 2¾ years of options data. Only effects about as strong as the original papers' could have
  shown.
- Today's S&P 100 members are used for the whole past (survivorship).
- BNY's options before its 2025 ticker change aren't included. GEV and SNDK start when they were
  listed.

## Upkeep

- Job `direction`, weekdays 6:40 pm. On a week's last trading day (normally Tuesday) it downloads the
  100 stocks' options (about 10-15 minutes, under the free-plan request limit), recomputes the last 50
  days of implied volatility, and predicts. On other days it refreshes prices and resolves predictions
  whose window has closed.
- Commands, from `collectors/`:
  - `stock_direction.py live --dry-run 2026-11-10`: what it would predict that day; logs nothing.
  - `stock_direction.py iv [SYMBOLS]`: recompute implied volatility.
  - `stock_direction.py explore`: the answer-key look at 2024-25.
  - `stock_direction.py tune`: the tuning log.
- The 2026 test can't be rerun as a fair test: it's been seen. Any new version is judged live.
- S&P 100 membership changes: edit `shared/sp100.json`, run `backfill_alpaca.py NEWSYMBOL` and
  `stock_direction.py iv NEWSYMBOL`, then `install.sh`. That's a new version.
- Ideas not built:
  - Crash protection with more stocks (the S&P 500), for more statistical power.
  - Crash protection held for a month, not a week. Xing et al. found it lasts up to 6 months, and a
    longer hold suits its slow drift.
  - Option-implied borrowing cost (Muravyev, Pearson & Pollet).
