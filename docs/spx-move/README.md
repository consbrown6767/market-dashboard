# S&P 500 move-size model

*Built 2026-11-09. Live from the prediction for Tuesday 2026-11-10 (made Monday evening). Code:
`collectors/spx_move.py`. Scored in the prediction ledger and shown on the Scorecard tab.*

## In one paragraph

Every weekday evening, after the close, the model says how big the next trading day's S&P 500 move
is likely to be, as a range: "90% chance between −1.3% and +1.2%, 50% chance between −0.5% and +0.6%."
It doesn't try to call the direction, since that's close to a coin flip. It uses five things known at
the close: recent moves, the VIX, dealer gamma, whether the market just fell, and whether tomorrow has
a Fed decision, inflation report or jobs report. Over 12½ years of backtest (3,151 days, each predicted
using only earlier days), its ranges were **about 4% more accurate than either simple guess**, and its
90% ranges caught **90.3%** of days. That's a modest edge, but it's solid and well calibrated.

## What it predicts, and when

- **Target:** the S&P 500 index's close-to-close % change for the next trading day (the overnight gap
  plus the day), as five quantiles: 5%, 25%, 50%, 75%, 95%.
- **Made:** after the close. The job runs at 4:50 pm, then retries at 6:20 and 8:50 pm and 8:05 am, but it
  only predicts once.
- **The window** opens at 9:30 the next morning, when the index next prints. The ledger refuses a
  prediction logged after that. Futures trade overnight and could tell a person more by morning, but
  the model never looks at them.
- **Resolved:** the next evening, from the closing level (Yahoo, cross-checked against
  SqueezeMetrics).

## What goes in (all fixed at the close)

| Input | What it is | Source |
|---|---|---|
| Recent moves | Today's, the last 5 days' and the last 22 days' realized variance, from each day's high-low range plus the opening gap | S&P 500 daily bars, Yahoo `^GSPC`, 1990 on |
| VIX | The options market's own expected move for the next 30 days | Cboe's free daily file, 1990 on |
| Dealer gamma | SqueezeMetrics GEX from the trading day before: whether it's negative, and where it ranks in the past year. Today's figure may not be out by the evening, so it's never used | `market_gamma`, 2011 on |
| Down day | How far the index fell today (0 if it rose). Drops raise volatility more than rallies do | S&P bars |
| Scheduled news (#5) | Whether tomorrow is a Fed decision day (2:00 pm), a CPI day (8:30 am) or a jobs-report day (8:30 am) | Fed calendar from federalreserve.gov (parser fixed 2026-11-13: 5 meetings spanning two months, 2013-2019, had been missed). CPI and jobs dates from BLS, which blocks scripts, so they were read in a browser into `shared/release_dates.json`. Past dates are the days reports actually came out, including the 2013 and 2025 shutdown delays. Schedule known through Dec 2027 |

Only scheduled news counts. Surprise Fed moves (Jan 2008, March 2020) and the cancelled March 2020
meeting are left out, because nobody knew about them the day before.

## Methods

You asked whether this would be econometrics, statistics or financial engineering. It's all three,
each doing a different job.

**Econometrics: the core model.**
- A **HAR regression** (heterogeneous autoregressive model; Corsi, 2009), the standard workhorse for
  volatility. The log of each day's realized variance is explained by yesterday's, last week's and
  last month's, plus the VIX, dealer gamma, down days and news days.
- **Realized variance** comes from the daily high-low range (the Parkinson estimator) plus the opening
  gap, which is much less noisy than squared daily moves alone.
- **The down-day term** captures the "leverage effect": falls raise volatility more than equal rises.
- **GJR-GARCH(1,1)**, the classic model built from returns alone, was run as a cross-check (see the
  comparison below).

**Financial engineering: reading the options market.**
- **The VIX becomes a one-day move** by dividing by √252 (VIX 25 ≈ a 1.6% typical day).
- **The VIX usually overstates real moves** (the "variance risk premium": option buyers pay for
  insurance). The regression learns how much to discount it: the VIX weight is about 0.79 rather than
  1, so a doubling of VIX means about a 73% wider range.
- **Ranges come from real past surprises.** Each past move is divided by the forecast made for it,
  and the 5% and 95% points of those ratios set the range. Fat tails and the small upward drift come
  through as they really happened, rather than from a bell-curve assumption.

**Statistics and data science: honest testing.**
- **Walk-forward:** the model is refit every day on every day since May 2012 (the first date with a
  year of dealer gamma), then predicts one day ahead. It never sees the future.
- **Proper scoring:** the quantile (pinball) loss rewards ranges that are both tight and right, and
  punishes ranges that are too wide as well as too narrow.
- **Calibration:** whether 90% ranges catch 90%.
- **Paired tests** compare the model with each simple guess day by day. Their error bars allow for
  streaks (Newey-West), because stormy weeks are stormy for every model.
- **A machine-learning challenger** (gradient-boosted quantile trees, refit monthly) was tested on
  the same days.
- **Pre-commitment:** version 1 is exactly the design you approved before any test was run. The
  comparisons below were run afterwards and don't change v1. Anything they suggest is a v2, for you to
  OK.

## How it did: the v1 backtest

3,151 trading days, Apr 30, 2014 to Nov 6, 2026. Each day was predicted at the close using only earlier days.

| | Average loss (lower is better) | vs the model | 90% ranges caught | 50% ranges caught | Average 90% width |
|---|---|---|---|---|---|
| **The model (v1)** | **0.2249** | | **90.3%** | **50.5%** | 3.05 pts |
| Recent moves (21-day standard deviation, bell curve) | 0.2340 | model 3.9% better | 87.7% | 54.0% | 3.01 pts |
| VIX at face value (VIX ÷ √252, bell curve) | 0.2344 | model 4.0% better | 96.1% | 64.8% | 3.75 pts |

Both gaps are 8 to 11 times their error bars, so the ledger calls them "Beats it."

- **It's sharper than VIX and still right.** Its 90% ranges are about 20% narrower than VIX's on
  average, yet catch exactly 90%. VIX at face value caught 96%: too cautious.
- **Its misses are balanced:** 156 below the range and 150 above. VIX's misses lean down (89 below,
  35 above). VIX is roughly right about crashes but far too wide on the upside.
- **The biggest days are where every range misses.** Of the 12 biggest moves since 2014 (mostly
  March 2020 and April 2025), 4 landed inside the model's 90% range and 2 inside VIX's. Several of the
  model's misses were close: Apr 9, 2025's +9.5% against a range up to +6.5%; Mar 24, 2020's +9.4%
  against +9.2%.
- **Shocks out of calm get missed.** On Nov 5, 2026 (−4.36%) the range was −1.5% to +1.4%, because VIX
  was 16.6 going in. VIX at face value said ±1.7%, so it missed too. On Apr 3, 2025 (−4.8%, the
  tariff announcement after the close the day before), the range was −2.2% to +1.9%.

**It held up in every period.** Average loss by period (lower is better):

| Period | Days | Model | Recent moves | VIX at face value |
|---|---|---|---|---|
| 2014–2019 (calm, with the 2015 and 2018 shocks) | 1,429 | 0.181 | 0.190 | 0.190 |
| 2020–2022 (Covid crash, 2022 bear market) | 756 | 0.330 | 0.342 | 0.341 |
| 2023–2026 (AI rally, April 2025 tariffs, this month) | 966 | 0.207 | 0.216 | 0.216 |

**What each input taught us:**
- **Dealer gamma is real, and VIX misses it.** On the 302 days after a negative-gamma reading, actual
  moves averaged 1.09× what VIX implied. On positive-gamma days they averaged 0.73×. So VIX understates
  moves when dealers are short gamma and overstates them otherwise. In the model, negative gamma widens
  the range about 9%, and going from the year's lowest gamma to its highest narrows it about 21%.
- **Scheduled news matters, but less than you'd think.** The average move on Fed days was 0.78%, on
  jobs days 0.84% and on CPI days 0.76%, against 0.70% on days with no scheduled news. The model widens
  its range about 24% for a Fed day, 17% for a jobs day and 8% for a CPI day. Its 90% ranges caught
  95% of Fed days (a bit too wide), 88% of CPI days (a bit too narrow) and 90% of jobs days.
- **Down days:** the model widens its range about 8% for every 1% the index fell that day.

## Comparing methods (run after v1 was fixed; nothing here changed v1)

The same 3,151 days, each variant trained on the same past days (from May 2012). "Gap vs v1" is how much
worse (+) or better (−) each did than v1, with its error bar in brackets. A gap more than about twice
its error bar is a real difference.

| Variant | Average loss | Better than recent moves by | 90% caught | Gap vs v1 |
|---|---|---|---|---|
| **v1: recent moves + VIX + gamma + down days + news** | **0.2249** | **3.9%** | 90.3% | |
| Recent moves only (plain HAR) | 0.2279 | 2.6% | 91.1% | +0.0030 (0.0007) worse |
| Recent moves + VIX | 0.2253 | 3.7% | 90.9% | +0.0004 (0.0005) no clear difference |
| Recent moves + VIX + down days + news (v1 without gamma) | 0.2256 | 3.6% | 90.9% | +0.0007 (0.0002) worse |
| VIX alone, rescaled | 0.2260 | 3.4% | 91.0% | +0.0011 (0.0005) worse |
| **v1 + VIX9D (9-day VIX)** | **0.2242** | **4.2%** | 89.9% | **−0.0007 (0.0003) better** |
| v1 + VIX term structure (VIX ÷ VIX3M) | 0.2244 | 4.1% | 89.9% | −0.0005 (0.0003) no clear difference |
| GJR-GARCH(1,1) (econometric cross-check) | 0.2273 | 2.9% | 89.1% | +0.0024 (0.0006) worse |
| Boosted trees (machine learning) | 0.2360 | −0.8% | 82.9% | +0.0111 (0.0022) worse |

What this says, plainly:
- **Most of the edge over "VIX at face value" comes from correcting VIX.** That means discounting its
  usual overstatement and using real tail shapes. VIX alone, rescaled this way, already gets most of
  the way. Recent moves add a little, and dealer gamma adds a little more on top: dropping gamma from v1
  makes it measurably worse (+0.0007, about 3½ times its error bar). So **gamma does add something VIX
  doesn't have**, which was the main question. The gain is small, about 0.3%.
- **Down days and news add little** to a model that already has VIX, because VIX already prices most
  of it. They're harmless and stay in v1, as agreed.
- **The 9-day VIX (VIX9D) is the one addition that clearly helps.** It better matches a one-day horizon,
  and it already prices a known event within the next week or so. It's the top v2 candidate.
- **GARCH** (returns only, no VIX) is clearly worse than v1. The options market knows things past
  returns don't.
- **Machine learning lost even to the simple guesses.** Its ranges were too narrow (they caught 83%,
  not 90%). It learned noise from about 3,000 days of history. With this little data, the simple
  regression is the better tool, so it was dropped, as planned.

## Limits, honestly

- **The edge is modest.** About 4% better than the simple guesses isn't a trading edge by itself.
  Its value is a calibrated, honest daily number for "how big could tomorrow be," for sizing and for
  judging whether a move was unusual.
- **It overreacts in extreme panics.** In March 2020 some 90% ranges reached ±25–32% for a single day,
  far wider than one day can realistically move. The log scale extrapolates too far when VIX is
  70–80. This costs it some score in those weeks. It's a known v2 fix (cap or shrink extreme inputs).
- **It can't see surprises coming.** A sudden shock out of calm (Nov 5, 2026; Apr 3, 2025) will land
  outside the range. That's what the 10% outside is for.
- **Sources are free and unofficial in places.** The S&P history comes from Yahoo. It matched
  SqueezeMetrics' closes on 3,903 of 3,904 days, and every run re-checks the last 10.
- **BLS dates need a yearly refresh** in a browser. The job warns when fewer than 60 days of schedule
  are left.

## Ideas for a version 2 (not built; needs your OK)

Each would be a new version, scored separately from v1, and v1 keeps running.

1. **Add VIX9D.** It's the only addition the comparison clearly supports, at about 0.3% better. The
   data is already collected.
2. **Cap extreme ranges.** Shrink the inputs in panics, so a single day's 90% range can't reach ±30%
   (March 2020).
3. **Separate tails for news days.** Fed-day ranges came out a bit too wide and CPI-day ranges a bit
   too narrow.
4. **A second target: the trading day alone** (open to close, without the overnight gap). That's the
   part the gamma breakout tracker cares about, and it could tell that tracker when a day is unusually
   calm or wild.

The ML challenger is not worth another try until there's far more data, for example with intraday bars.

## Where things are

- **Code:** `collectors/spx_move.py`; tests: `collectors/test_spx_move.py`.
- **Job:** `spxmove` (launchd, set up by `collectors/install.sh`), Mon–Fri at 16:50, 18:20, 20:50 and 08:05.
- **Data in `~/MarketData/options.db`:**
  - `index_daily`: SPX from Yahoo; VIX, VIX9D and VIX3M from Cboe; with a `source` column.
  - `econ_calendar`: Fed decisions, CPI days and jobs-report days.
  - `predictions` and `prediction_outcomes`: the ledger.
  - All of it goes into the nightly backup.
- **Commands** (from `collectors/` with the venv's Python):
  - `spx_move.py`: the job.
  - `spx_move.py backtest`: reruns the v1 backtest.
  - `spx_move.py research`: the comparison above.
- **On the dashboard:** the Scorecard tab shows tomorrow's range, its inputs, the next scheduled news
  and the last 120 ranges against what happened.
