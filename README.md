# Market Dashboard

A local dashboard that gives a broader picture of the market: one tab per kind of
information, all reading from one database that background collectors keep filling.

Research only. Nothing here places trades.

## Open it

**http://127.0.0.1:8765** in any browser on this Mac. The server runs all the time as a
background job (`dashboard` below) and only listens on this machine. Pages refresh every minute.

| Tab | Shows | Data |
|---|---|---|
| Options | Click any symbol for its options detail: open interest by strike (calls up, puts down, price marked), today's volume by strike, implied volatility by strike, and per expiration: call/put OI and volume, put/call ratios, at-the-money IV and implied move (straddle ÷ price); filter to one expiration or all within 30 days. Also: what's being collected per symbol ("OCC series" = every strike × expiration OCC lists out to ~3 years; "in snapshot" = contracts priced hourly, ≤60 days and ±25%, so SPY/QQQ with daily expirations and $1 strikes show 4–8× more than a typical stock), S&P 500 dealer gamma (12 months), CFTC futures positioning. | `stock_snapshots`, `open_interest`, `option_quotes`, `market_gamma`, `cftc_net` |
| Gamma | The breakout tracker: each stock's call wall, put wall and gamma flip, a 5-minute chart with those levels, breakouts in their 30-minute hold, every breakout logged with its grades, and a scorecard comparing predictions with everything else. See "Gamma tab" below. | `strategy_levels`, `strategy_events`, `strategy_grades`, `strategy_state`, `strategy_bars_5m` |
| Politics | The political game machine: 2028 odds from the raw model, the markets and a blend, in seven sections (Overview, Play the game, President, Senate and House, Strategy, Ratings, Scorecard). See "Politics tab" below. | `~/MarketData/politics/outputs/data.json` |
| Scorecard | Every model's record in one place, each judged against a simple guess made at the same moment: predictions, resolved, result, verdict, tamper check. The S&P 500 move-size model's next-day range with its inputs, the next scheduled Fed/CPI/jobs news, and its last 120 ranges against what happened. Also whether range models' 90% ranges really catch 90%, and the latest predictions. See "Scorecard tab" and "S&P 500 move-size model" below. | `predictions`, `prediction_outcomes`, `econ_calendar`, plus the Gamma and Politics records |
| Options: watchlists | **Universal watchlist**: every stock with data in the database (options and/or spread prices), built from the data, so it grows on its own as collection grows. **My watchlists**: your own named lists made from it (New / Rename / Delete, + to add, × to remove), saved in `shared/watchlists.json` for later use (other tabs, the strategy, backtests). Click any ticker to open it in the options panels. Only stocks with data can be added; adding new tickers from the app comes later. `shared/watchlist.json` (what gets collected) is separate and unchanged. | `stock_snapshots`, `open_interest`, `daily_bars_adj`, `shared/watchlists.json` |
| Spreads | Relative-value pairs from `shared/pairs.json` (starts with RSP/SPY; add KO/PEP, CVX/XOM, …): ratio with 50/200-day averages, z-score and 1-year percentile, returns per leg and for the spread, both legs indexed to 100; any ticker, history to 2000, any time window | `daily_bars_adj` (+ Alpaca/Yahoo on demand) |
| News | Top stories (headlines from ~80 sources grouped by event, ranked by how many outlets carry them), latest headlines with topic filters and a search over everything stored, shipping through the 28 chokepoints (Hormuz, Bab el-Mandeb, Suez, …) against normal, with history to 2019, and the Fed and data calendar with Polymarket's odds for the next decision. See "News tab" below. | `news_stories`, `news_items`, `news_fts`, `chokepoint_daily`, `econ_calendar`, `poly_snapshots` |
| Events | Polymarket: groups (macro & Fed, geopolitics, business & tech, politics, crypto, sports & other), 24h movers, what resolves this week, every event with its outcomes; click one for all outcomes and price history | `poly_events`, `poly_markets`, `poly_snapshots` |
| Status | Every collector job's last run, status and detail; recent runs | `runs` |

**Price, chain and contract charts (Options tab):** click a symbol in the table, or type any
ticker in the box next to the detail title and press Enter (it doesn't need to be on the
watchlist). You get its price candles (1D/1W/1M/3M/1Y/5Y), and its full options chain for any
listed expiration (calls | strike | puts with bid, ask, last, volume, open interest, IV, delta;
in-the-money shaded, a line at the current price). Click a bid, ask or last to chart that one
contract (1D/1W/1M/All candles + volume) with its quote, IV, greeks and breakeven. These are
fetched live from Alpaca when you click (not stored): stock and option candles are ~15 minutes
delayed on the free plan, chain quotes are near live, and open interest comes from the database
(or live from OCC for symbols not collected). Option history only goes back to Feb 2024.

**Panels:** drag any panel by its header and drop it anywhere: it snaps to a 24-column grid (a
dashed outline shows where it will land) and panels in the way are pushed down. Gaps you leave stay
put, so you can, say, make a panel 3/4 wide (18 columns) and centre it. Drag a panel's bottom-right
corner to resize it. **−** in a panel's header hides it; **+** (top right) lists the tab's panels to
show or hide them, and says how many are hidden. The layout is saved per tab in this browser;
**Reset layout** (top right) restores the current tab and shows every panel. **A− / A+** (top right) make all text below the top bar smaller or bigger (80% to 200%), remembered per browser. Under 900px wide, panels
stack in one column. **Strike charts** (open interest, volume, IV): scroll to zoom,
drag to pan, double-click to reset; the three share one zoom window, the y-axis rescales to the
strikes in view, presets ±5/10/20%/All, and **Compressed** switches to a square-root scale.
Index ETFs (SPY, QQQ) look different from stocks because they have ~5× more strikes ($1 apart)
and much more concentrated open interest (hedges at a few round strikes: the tallest SPY bar was
28× a typical one vs 5–7× for NVDA/AAPL), so the default view is ±10% of price.

Design follows World Monitor (dense dark panels, monospace, small uppercase titles, status dot,
freshness badges): its palette and layout conventions, with fresh CSS (`dashboard/static/style.css`).
Charts: TradingView Lightweight Charts 4.2.0 (Apache 2.0), saved locally in `dashboard/static/vendor/`.

**Any pair:** type two tickers in the Spreads toolbar (Any pair: long / short) and press Show.
Tickers that aren't saved are fetched from Alpaca on demand (same adjusted daily bars, 2016 on, kept in
memory 10 minutes). **Save** adds the pair to `shared/pairs.json` as a chip, and the next `spreads` run
stores its history; × on a chip removes it. You can also edit `shared/pairs.json` by hand (`id`, `long`,
`short`, `name`, `reads`) to give a pair a custom name and description. The ticker boxes suggest every
stock with data (the universal watchlist) but accept any ticker.

**History back to 2000 (added 2026-11-10):** before Alpaca's first day (2016-01-04), each leg is filled
with Yahoo daily closes (dividend-adjusted), fetched on demand by `dashboard/long_history.py` and kept in
memory 6 hours; nothing is stored. The Yahoo part is rescaled to meet Alpaca exactly on the join day, so
the ratio has no jump there (checked: CPER/GLD's −4.2% on 2016-01-04 is the real move). The ratio chart
marks the join ("Yahoo before · Alpaca after"). A fund that started later begins at its first day and
the chart says so (e.g. XLRE 2015, IBIT 2024). A ticker Alpaca doesn't have at all is shown from Yahoo
alone. If Yahoo fails, the pair still shows from 2016 with the reason under the performance chart.
**Time window:** presets 1M–20Y, YTD and MAX, or custom from/to dates; the "Window" row in Returns and
the "In window" stat follow it. Returns for 5Y/10Y/20Y appear only when both legs go back that far.

## Layout

```
collectors/   background jobs that fetch data and write to the database (+ install.sh)
dashboard/    server.py (read-only JSON API + static files) and static/ (the page)
shared/       watchlist.json (options symbols collected), pairs.json (spreads), watchlists.json (your custom watchlists)
docs/         project notes
research/     one-off studies, run by hand; they print a report and store nothing (see below)
backups/      nightly compressed copy of the database
```

## Where the data lives

- **Database: `~/MarketData/`**, a normal local folder that iCloud doesn't touch. A database
  that's written every hour can be corrupted by iCloud syncing it mid-write, or offloaded by
  "Optimize Mac Storage".
- **Backup:** a nightly compressed copy of **everything that can't be re-downloaded for free** (live
  snapshots, open interest, Polymarket history, run log, plus the small free tables in case a free
  source disappears) goes into `~/Library/Mobile Documents/com~apple~CloudDocs/Vibe Coding/Market Dashboard/backups/` (iCloud, off this Mac; the code itself is in git). The 2024+ option-price backfill is left out
  (~70% of the database): re-run `collectors/backfill_alpaca.py` to rebuild it (~45 min). New tables are
  backed up automatically unless added to `BACKUP_EXCLUDE`.
- **API keys: `~/.config/market-dashboard/alpaca.env`**, outside the project and iCloud.
  Never put keys in this folder.

## Restoring from the backup
The political game machine's logs and snapshots are separate: unpack `backups/politics-data.tar.gz`
into `~/MarketData/politics` after running `collectors/install.sh`.


1. Uninstall the jobs so nothing writes meanwhile: `collectors/install.sh uninstall`
2. Move the damaged database aside (if any), then rebuild from all backup files:
   `cd collectors && ~/MarketData/.venv/bin/python restore_backup.py ~/MarketData/options.db`
3. `collectors/install.sh` (collectors recreate indexes and views on their first run)
4. Rebuild the option-price history: `cd ~/MarketData/app && ~/MarketData/.venv/bin/python backfill_alpaca.py`

Tested 2026-11-02 (core + Oct + Nov files): integrity check passed, every backed-up table matched the
live database row for row, views worked.

## Runs on

This Mac, which stays plugged in. The collectors run as background jobs, independent of the
dashboard being open, and restart after a reboot. Sleep must be disabled while plugged in
(System Settings → Battery/Energy → "Prevent automatic sleeping when the display is off").
Expect occasional gaps from restarts, power or Wi-Fi drops; collectors record their gaps.

## Tabs (build order)

1. **Options data collector:** open interest at every strike **once a day** (it only
   changes overnight), prices / implied volatility / volume **hourly** during market hours.
2. **Gamma** (built): call wall, put wall, gamma flip, live breakouts, prediction scorecard.
3. **Spreads** (built): relative-value pairs, starting with RSP/SPY.
4. **Events** (built): Polymarket.
5. **IPOs and geopolitics.**

## Data sources (free)

| Source | Gives | Limits |
|---|---|---|
| OCC Series Search | Today's open interest at every strike, official, no key | Latest only, no history |
| OCC Daily Open Interest | Market-wide open interest totals per day | Totals only, **not** by strike |
| Alpaca (free paper account) | Option prices back to Feb 2024 (tested: hourly bars available on the free plan); current chain with IV and greeks; expired contracts with `status=inactive` | Estimated "indicative" prices, not OPRA; open interest is latest only and lags OCC (see below) |
| Yahoo Finance | Current chains with open interest, stock prices; S&P 500 index daily history (`^GSPC`, 1990 on) | Unofficial, ~15 min delayed. Its S&P closes matched SqueezeMetrics' on 3,903 of 3,904 days (within 0.05%) |
| Cboe | Daily VIX (1990 on), VIX9D (2011 on), VIX3M (2009 on), no key | End of day only |
| Federal Reserve | FOMC meeting calendar, 2002 to next year | Scheduled meetings only are kept |
| BLS | CPI and jobs-report release dates | Blocks scripts (403), so the dates were read in a browser into `shared/release_dates.json`; refresh yearly |

There's no free source of **past** open interest by strike, so the collector builds that
history going forward. Alpaca prices can backfill price history to Feb 2024.

### Best source per data type (tested side by side on 2026-10-26, 1:50 pm)

| Data | Use | Why | Backup |
|---|---|---|---|
| Open interest | **OCC** | Official source. Yahoo's numbers were identical (it republishes OCC); Alpaca's were dated 4 days earlier | Yahoo (matched OCC on 97.8% of NVDA strikes) |
| Option bid/ask, IV, greeks | **Alpaca** | Near live; Yahoo's option quotes were ~15–20 min old, its IV ran low on puts (0.33 vs 0.39), and it has no greeks | none yet |
| Option volume | **Alpaca** | Same as Yahoo to within a few contracts | — |
| Stock volume | **Yahoo** | Live, all exchanges, regular hours only | Alpaca SIP (all exchanges, but ~15 min old and includes pre-market) |
| Stock price | **Alpaca IEX** | Live; matches the full market to within cents | Yahoo |

Yahoo isn't used for everything because its option quotes are delayed and its IV is
inconsistent, and because it's unofficial (no API agreement; it can rate-limit or change
without notice). Irreplaceable data gets a second source where one exists.

## Options collector (running since 2026-10-26)

`collectors/options_collector.py`, installed as three launchd background jobs by
`collectors/install.sh`. Schedule is Mac local time (US/Eastern), Mon–Fri:

| Job | When | What |
|---|---|---|
| `daily` | 07:30, retry 09:15 | OCC open interest at every strike, all expirations; Yahoo for any symbol OCC fails (`occ_oi.source`) |
| `bars` | 17:15, retry 20:15, Mon–Fri | `options_collector.py bars`: official full-market (SIP) daily bars, raw, for every watchlist symbol into `stock_bars_daily` (re-reads the last 5 days, so a partial or corrected bar gets replaced). Added 2026-11-10: before that, the table only had the one-time backfill |
| `snapshot` | 09:35, 10:00–15:00 hourly, 15:55 | Alpaca bid/ask, last trade, volume, IV, greeks for expirations ≤60 days and strikes ±25% of price, plus stock price (Alpaca) and volume (Yahoo live + Alpaca SIP). Skips when the market is closed. |
| `backup` | 20:30 daily | `backups/`: `options-core.db.gz` (small tables, all schemas and views; rewritten nightly) + `options-YYYY-MM.db.gz` (that month's snapshots, open interest, Polymarket history, run log). Only the current month (and the previous one for 3 days after it ends) is rewritten, so iCloud re-uploads a few hundred MB at most; closed months are never touched again. Everything except the re-downloadable backfill (`BACKUP_EXCLUDE`) |
| `positioning` | 07:45 Mon–Fri, plus 16:45 Fri | `collectors/positioning_collector.py`: S&P 500 dealer gamma (SqueezeMetrics) and CFTC futures positioning; see below |
| `spreads` | 09:40, 10:05–15:05 hourly, 16:30 Mon–Fri | `collectors/spreads_collector.py`: dividend- and split-adjusted full-market daily bars for every pair leg, 2016 onward; today's bar is partial and ~16 min old; full reload on Saturdays |
| `events` | every hour at :05, every day | `collectors/events_collector.py`: Polymarket events, see below |
| `strategy` | every 5 min, 09:25–16:30 Mon–Fri | `collectors/strategy_collector.py`: gamma breakout tracker, see below |
| `politics` | every hour at :25, every day | `collectors/politics_job.py`: political game machine, see below |
| `spxmove` | 16:50, 18:20, 20:50, plus 08:05, Mon–Fri | `collectors/spx_move.py`: S&P 500 move-size model. Refreshes S&P and VIX history and the Fed/CPI/jobs calendar, resolves the last prediction, predicts the next trading day; later runs only retry. See below |
| `watchdog` | every 30 min (:20, :50), every day | `collectors/watchdog.py`: sends a phone notification when something goes wrong; see Failure alerts below |
| `briefing` | 10:00 every day | `collectors/briefing.py`: daily update notification, see Daily update below |
| `dashboard` | always on | `dashboard/server.py` on http://127.0.0.1:8765 (restarts itself if it stops) |

Watchlist and snapshot filters: `shared/watchlist.json`. **After editing the collector or the
watchlist, re-run `collectors/install.sh`**: launchd runs a copy in `~/MarketData/app/`.

- Status: `~/MarketData/.venv/bin/python collectors/options_collector.py status`
- Logs: `~/MarketData/logs/{daily,snapshot,backup}.log`
- Every run (ok, partial, skipped, failed) is recorded in the `runs` table, so gaps are visible.
- Uninstall: `collectors/install.sh uninstall`

### Failure alerts (since 2026-11-02)

`collectors/watchdog.py` checks every 30 minutes (read-only) and sends one iPhone push notification
per check listing what's wrong:

- **failed run**: a job finished `failed`, `partial` or `stopped` (with the error and log path)
- **stuck run**: a job has been `running` for over 2 hours (crashed or hung)
- **thin data**: a `snapshot` or `events` run saved under half its usual rows
- **missed run**: a job didn't run within 20 min of its scheduled time (schedules read from the
  launchd plists, so they never drift from `install.sh`)
- **missing open interest**: weekdays after 09:30, watchlist symbols with no OCC rows for today
- **dashboard down**, **under 10 GB free disk**, **core backup file over 30 h old**

One-off problems are sent once; ongoing ones are sent when they start, re-sent once a day
while they last, and get a "resolved" note when they clear. State: `~/MarketData/watchdog_state.json`.
If the Mac is off or asleep nothing can alert; the next check after it wakes reports the missed runs.

**Phone setup** (ntfy, https://ntfy.sh: free, no account, nothing gets access to email or Apple ID):
the private channel name is in `~/.config/market-dashboard/alert.env` (`NTFY_TOPIC`, chmod 600,
outside iCloud). The iPhone ntfy app subscribes to that name. The name is the only secret (anyone
who knows it can read the alerts), so alerts carry no personal details: no file paths, just what
broke and when. To change it, put a new random name in the file and re-subscribe in the app. If
the file is missing, alerts show as Mac notifications; if sending fails, it's retried next check.
(Email via Gmail was considered and dropped: the owner didn't want an app password on their account.)

- Test notification: `~/MarketData/.venv/bin/python ~/MarketData/app/watchdog.py test`
- See what's wrong right now without sending: `... watchdog.py dry`

### Daily update (since 2026-11-02)

`collectors/briefing.py` sends a phone notification at 10:00 every day on the same ntfy channel as
the failure alerts. It answers "what matters this morning?" with plain rules (no LLM). The owner
chose the contents: no SPY options section, no spreads; WTI **and** Brent; S&P futures; VIX; Mag 7
as average plus best/worst; the overnight open-interest line; events.

- **Headline** (the notification title): the 2–3 moves biggest relative to *their own normal*,
  e.g. `Brent -7.5% (6x)`. "Normal" = average size of the last 20 daily moves. Nothing at 1.5x or
  more → "Quiet morning".
- **Markets**, each with its normal in brackets:
  - SPY, plus the Mag 7 average, best and worst, and any single name moving 2.5x its own normal.
    Live price from Alpaca IEX; previous close from Alpaca SIP daily bars.
  - S&P 500 futures overnight, from yesterday's 4 pm to today's 9:30 am (Yahoo 30-min bars).
  - WTI, Brent, the 10-year (in bp) and the VIX (in points), from Yahoo.
- **Futures contract rolls:** Yahoo's continuous futures series (`CL=F`, `BZ=F`, `ES=F`) jump when
  a contract expires. On 2026-11-02 that made Brent show −10.8% on a −7.5% day. So the script
  finds the specific contract the series points at (`front_contract`, e.g. `BZF27.NYM`) and
  compares that contract with itself.
- **New option bets**: the 3 biggest overnight open-interest increases across the watchlist (OCC).
- **Events**: the 3 biggest 24h odds moves. Same filters as the Events tab: liquid markets only,
  none resolving within 48 h, no sports or other.
- **System**: one line at the bottom, or at the top (and in the title) if something's wrong.
- **Weekends and market holidays**: system line and events only.
- **Commands:**
  - Preview without sending: `~/MarketData/.venv/bin/python ~/MarketData/app/briefing.py dry`
  - Test the trading-day version after hours: `FORCE=1 ... briefing.py dry`

### Gamma tab: the breakout tracker (since 2026-11-06)

Tests one idea: when a liquid large-cap stock breaks above its options call wall and holds, dealer
hedging pushes it further up. It makes predictions and grades them. It never trades. The design is in
`docs/gamma-strategy/`, and the rules are `collectors/scoring.py` (21 tests).

`collectors/strategy_collector.py` runs every 5 minutes in market hours:

1. **Levels, once a day:** call wall and put wall are the strikes with the most open interest across
   expirations in the next 30 days, from this morning's OCC file (yesterday's close). The gamma flip
   is where total dealer gamma changes sign, recomputed at prices within ±30% from that open interest
   and the last option snapshot before today. Some stocks have no flip in that range: that's a real
   result, and it costs them that point. It only sees expirations up to 60 days and strikes within
   25%, because that's what the snapshots hold.
2. **Bars:** SIP 5-minute bars, about 16 minutes behind. IEX is live but only ~3% of volume, which
   would break the volume rule. Raw prices, because walls are real strikes.
3. **Rules:** `scoring.py` over each stock's day. Every finished breakout is logged, including
   failures: they're the comparison group. Events are written once and never changed.
4. **Grades:** at that day's close, the next close and three closes later, using Alpaca's trading
   calendar (so half days work).

- **Stocks and sector ETFs:** `shared/strategy.json`. Re-run `install.sh` after editing.
- **Dealer view:** `dealer_view` in that file. It flips the sign of dealer gamma but never moves the
  flip: the same line crosses zero either way.
- **Tables:** `strategy_levels`, `strategy_events`, `strategy_grades`, `strategy_state`,
  `strategy_bars_5m` (bars aren't backed up: they can be downloaded again).
- **Live vs replay:** `mode` is `live` for days the job ran on. `replay` is the same rules run later on
  past days with point-in-time inputs (`strategy_collector.py replay`, done for 2026-10-27 to 11-06). The
  tab keeps them apart: only live days count as the forward test.
- **Short interest:** no free daily source, so that point is never earned. Scores run 0 to 2.
- **Missed days:** if the Mac was asleep, the next run fills them in from the same inputs.

### Politics tab: the political game machine (since 2026-11-06)

Treats the 2028 race as a turn-based game, with raw model, market and blended odds side by side.
Research only: it places no bets. `politics/HANDOFF.md` has the commands and what still needs the
owner, and `politics/PLAN.md` has the design.

- **Code and inputs:** `politics/`. **Running copy and data:** `~/MarketData/politics`. `install.sh`
  refreshes the copy and never touches `data/`, `kalshi/` or `outputs/`.
- **Hourly at :25** (`collectors/politics_job.py`): Kalshi, Polymarket and Senate prices, headlines,
  then `run_all.py` (about 3.5 minutes), which writes `outputs/data.json`. A failed price step is
  noted as `partial` and the rebuild uses the last good data. Past prices refresh at 2:25 am.
- **The tab:** `dashboard/static/politics.js` and `politics.css`, built the first time the tab opens.
  Each section is its own grid, so its panels drag, resize and hide like any other, saved as
  `layout:politics-<section>`. Play the game runs `game_engine.js` in the browser, served at
  `/politics-engine.js` so its names stay out of the page's global scope.
- **Logging forecasts stays manual:** `run_all.py --log`. The ratings are mostly drafts, and the logs
  are permanent.

### Scorecard tab: the prediction ledger (since 2026-11-09)

One place where every model's predictions are written down before the outcome is known and scored
the same way. New models write to the ledger (`collectors/ledger.py`, tests in `test_ledger.py`).
The gamma tracker and the political machine keep their own records, which the tab reads as they are.

- **The rules** (enforced in `ledger.py`): a live prediction is stamped when logged and refused if its
  window has already opened; live rows are only ever added, each chained by hash to the one before,
  and `verify()` catches a changed or removed row or a changed outcome; every prediction carries at
  least one baseline (a simple guess made at the same moment); live and backtest are kept apart
  (backtests may be cleared and rerun with `clear_backtest`, live rows never); a retuned model is a
  new version, scored on its own.
- **Two kinds:** `probability` (a chance, scored by the Brier score) and `quantiles` (a range for a
  number, scored by the quantile loss, plus coverage: how often the outcome landed inside each range).
- **Verdicts:** "too few" until 30 are resolved. After that, better or worse only when the average gap
  to the baseline is more than about two standard errors (a paired comparison, prediction by prediction).
  The standard error allows for streaks (Newey-West), since a stormy week is stormy for every model;
  it's never smaller than the plain one.
- **Tables:** `predictions`, `prediction_outcomes`. Created by the first model job that calls
  `ledger.ensure()`, so until then the tab says the ledger is empty. The server only reads them.
- **First model:** the S&P 500 move-size model, below.

### S&P 500 move-size model (since 2026-11-09)

Each weekday evening, a range for the next trading day's S&P 500 close-to-close move: five quantiles
(5/25/50/75/95%), so a 90% and a 50% range. Size, not direction. Full write-up, with the backtest and the
comparison of methods: `docs/spx-move/README.md`. Code `collectors/spx_move.py`, tests `test_spx_move.py`.

- **Inputs** (all fixed at the close): the S&P's realized moves over the last day, week and month (from
  the daily range plus the opening gap), today's VIX, the previous trading day's dealer gamma (whether
  negative, and its rank in the past year; that day's own figure may not be out yet), how far the index
  fell today, and whether tomorrow brings a scheduled Fed decision, CPI or jobs report.
- **Method (v1, agreed before testing):** a HAR regression of log realized variance on those inputs, refit
  every evening on every day since May 2012. The range comes from how big past surprises really were
  (empirical quantiles), not a bell curve. Baselines logged with it: `recent` (21-day standard deviation,
  bell curve) and `vix` (VIX ÷ √252, bell curve).
- **Timing:** made after the close. The ledger window opens at 9:30 the next trading day, when the index
  next prints; futures trade overnight but aren't used. If Cboe hasn't posted the VIX close by the 20:50
  run, Yahoo's is used and flagged (`index_daily.source = 'yahoo-backup'`; Cboe's replaces it later, and the
  value actually used stays in the prediction's `inputs`). The 08:05 run is a last chance before the open.
- **Commands:** `python spx_move.py` (the job), `backtest` (clears and reruns the v1 backtest in the ledger),
  `research [out.json]` (variants, GARCH and boosted trees on the same days; needs scipy and scikit-learn,
  which the job itself doesn't).
- **Tables:** `index_daily` (symbol, date, OHLC, source: SPX from Yahoo, VIX/VIX9D/VIX3M from Cboe) and
  `econ_calendar` (date, event `fomc`/`cpi`/`jobs`, time, detail, source). Unscheduled Fed moves, notation
  votes and the cancelled March 2020 meeting are left out: nobody knew of them the day before.
- **Upkeep:** `shared/release_dates.json` holds BLS's schedule through Dec 2027. The Monday 16:50 run
  flags it (status partial, so the watchdog alerts) once fewer than 60 days are left; refresh it from
  bls.gov in a browser and re-run `install.sh`. Fed dates refresh themselves daily.
- **Health checks:** each run compares the last 10 Yahoo S&P closes with SqueezeMetrics' and reports a
  gap over 0.05%.

### Stock direction model (since 2026-11-11)

Each Tuesday evening, for each S&P 100 stock (and, for one version, the other 400 S&P 500 stocks): the chance it beats SPY (total return) from Wednesday's
close to the next Wednesday's close. Plan fixed before any result: `docs/stock-direction/PLAN.md`;
results: `docs/stock-direction/README.md`. Code `collectors/stock_direction.py`, tests
`test_stock_direction.py`.

- **Inputs** (published research, weekly values from the 5 days Tuesday to Tuesday): call-vs-put implied
  volatility gap, crash protection (out-of-the-money put minus at-the-money call volatility), the
  4-week change in at-the-money call and put volatility, last week's return against its sector ETF.
- **Data:** options history for the S&P 500 stocks from Feb 2024 (added to `option_bars_daily` by
  `backfill_alpaca.py`: the 100 on 2026-11-11, the other 400 on 11-12; ~5.4 GB, excluded from the backup
  like the rest of that table), dividends (`dividends`, Alpaca), 3-month T-bill (`rates_daily`, FRED),
  earnings dates (`earnings_dates`, Yahoo; tests only). Implied volatility per stock and day in
  `direction_iv_daily`. Lists and sectors in `shared/sp100.json` and `shared/sp500_ex100.json`.
- **Result:** no version reliably beats the base rate (sealed 2026 test). On a fresh test of the other
  400 (2026-11-12) crash protection alone lean-passed; five more research signals did nothing reliable.
  Three versions log live from 2026-11-17 (`shared/stock_direction_live.json`): `1-learned` (lean pass
  under the plan's rule), `3-skew` (crash protection alone; chosen after the results, so judged live
  only) and `3-skew@sp400` (crash protection on the 400, passed the fresh test).
- **Job `direction`:** Mon–Fri 18:40. On the last trading day of a Wednesday–Tuesday week it downloads
  the S&P 500 stocks' recent options (about an hour under the free request limit), recomputes the last 50 days
  of implied volatility, and predicts; other days it refreshes prices and resolves closed weeks.
- **Commands** (from `collectors/`): `stock_direction.py live --dry-run 2026-11-10` (logs nothing),
  `explore`, `tune`, `signals`, `iv SYMBOL`, `earnings SYMBOL`, `data`; `--universe sp400` before the
  command for the other 400.

### Volatility-managed market test (2026-11-12, failed, not live)

`collectors/vol_managed.py`, plan and write-up in `docs/vol-managed/`. Tests Moreira & Muir's
"hold less after wild months" rule on Kenneth French's daily returns (US 1926-2026, four other
markets, 49 industries; table `ff_daily`, loaded by `vol_managed.py data`) and SPX. It lost to
buy-and-hold on every pass rule. No job; rerun by hand with `vol_managed.py backtest`.

### Nine classic strategies (2026-11-12, none passed, not live)

`collectors/classic_strategies.py`, plan and write-up in `docs/classic-strategies/`. Trend (10- and
12-month), Halloween, turn of the month, stock and industry momentum, low volatility, small value
and profitability, on French data (`ff_daily`, `ff_monthly`). None beats the market after
publication by the plan's rules; 10-month trend is "safer, not better".

### Risk budget model (2026-11-12, failed, not live)

`collectors/risk_budget.py`, plan and write-up in `docs/risk-budget/`. Stocks + 10-year Treasuries by
equal risk, trend filter, scaled to a chosen volatility; bond returns from FRED DGS10 yields in
`rates_daily`. Lost to SPY + T-bills at the same risk at every level, 1965-2026.

### Research scripts

Run by hand with `~/MarketData/.venv/bin/python research/<script>.py`. They fetch what they need and
print a report; nothing is written to the database.

- `fear_spikes.py` (2026-11-10): what SPY did after days when the VIX jumped >=30% and closed above
  the 3-month VIX (like 2026-11-05), split by credit (HYG/IEF) and by whether fear calmed within 5
  days. Yahoo daily history from 2007; ~20 spikes, so the results are clues, not proof. First
  result: SPY up a median +2.3% over the next 20 days (up 80% of the time) vs +1.5% / 67% for any
  day; the two spikes where credit kept falling for 5 days (Aug 2011, Feb 2020) went flat or crashed.

### Watchlist changes

- 2026-10-26: added ORCL (AI infrastructure / data-center spending), PLTR (heavy retail options
  flow), LLY (largest non-tech mega-cap, healthcare), TSM (chip supply chain, Taiwan risk) and
  HYG (high-yield credit stress). 30 symbols. Their open interest starts 2026-10-26; their
  option-price backfill was run the same day.
- 2026-11-05: added 42 symbols, all with full data, chosen to study how markets affect each other:
  market structure (QQQE MDY IWF IWD MTUM SPHB SPLV MAGS), bonds (SHY IEF TIP LQD), commodities
  (USO BNO UNG SLV CPER COPX GDX), the last 4 sectors (XLP XLU XLB XLRE), industries (KRE PEJ JETS
  XRT XHB IYT ITA IGV AIQ XBI XOP), global/dollar/fear/crypto (EFA EEM FXI UUP FXY VXX IBIT ETHA).
  72 symbols; a snapshot is ~60,000 rows (was ~41,000) and takes ~50 s. Open interest and snapshots
  start 2026-11-05; their option-price backfill ran the same day (30 min, 2,558,477 bars, no errors; DB 3.1 GB after). Options are very thin on PEJ, QQQE,
  XLRE and UUP: their prices are the useful part. Futures aren't collected: no free options data.

### Historical backfill (Feb 2024 → 2026-10-26)

`collectors/backfill_alpaca.py`, run once on 2026-10-26 (log: `~/MarketData/logs/backfill.log`): all 25
symbols, 6,565,075 daily bars across 378,250 contracts, 2024-02-01 to 2026-10-26, no errors.
On 2026-11-11 it was run for the 87 S&P 100 stocks not on the watchlist (log
`~/MarketData/logs/backfill_sp100.log`: 10.9 million bars, 979,000 contracts, no errors, ~1½ hours under the
free request limit; table now 21.6 million rows, 159 underlyings) and topped up for the 13 watchlist
stocks in the S&P 100. Class shares trade options under a joined root (BRK.B → `BRKB`), which the script
now accepts. The `direction` job keeps the S&P 100 stocks current each week.

- `option_bars_daily`: daily open/high/low/close/volume/VWAP/trade count of actual trades, from
  Alpaca's indicative feed. Scope: the last expiration of each week, the 45 days before each
  expiration, strikes within 10% of the stock's range in that window, standard contracts only.
  A contract that didn't trade on a day has no bar.
- `stock_bars_daily`: full-market (SIP) daily bars, **raw** (not split-adjusted), kept current by the
  `bars` job since 2026-11-10 (before that, backfill only), so they line
  up with the strikes of the time (NVDA closed at $878 on 2024-03-15 and $121.79 after the
  June 2024 10-for-1 split).
- `stock_splits` + view `stock_bars_split_adj`: every split for the watchlist and stored bars, from
  Alpaca's corporate actions feed (`/v1/corporate-actions`, free), refreshed by the `daily` job (ex-dates
  up to today only). The view puts `stock_bars_daily` in today's share terms (prices times
  `split_factor`, volume divided by it). Use it for any series across a split; 15 symbols split inside
  the stored history (NVDA, AVGO, XLK and the other Select Sector funds, ITA 3:1 and MTUM 4:1 on
  2026-11-05, ...). The raw table stays as it is, to match strikes.
- **No** bid/ask, implied volatility, greeks or open interest: Alpaca doesn't provide them
  historically. IV can be calculated from these prices; open interest can't be recovered.
- This is a different kind of data from the live snapshots (trade bars vs. point-in-time
  quotes). Don't mix the two in one series without noting it.
- The bar for 2026-10-26 is partial (the free plan stops 16 minutes before now). Re-running the
  script refreshes expirations that haven't passed yet; finished ones are skipped
  (`backfill_progress`).

### Market-wide positioning (loaded 2026-10-26 with full history)

Index-level context, **not** single-stock walls: a regime filter and dashboard backdrop.

- `market_gamma`: SqueezeMetrics' free daily S&P 500 dealer gamma exposure (`gex`, dollars)
  and dark-pool index (`dix`), 2011-05-02 onward (3,894 days on load). A day's row is
  computed after that day's close, so a backtest deciding on day D must use D−1.
- `cftc_tff` / view `cftc_net`: CFTC Traders in Financial Futures, weekly, 2010-06-15 onward,
  for S&P 500, Nasdaq-100 and Dow (consolidated), Russell 2000 E-mini (from 2017), VIX, and
  2/5/10-year notes and the Treasury bond. Groups: dealers, asset managers, leveraged money
  (hedge funds), other reportables, small traders. Positions are as of Tuesday
  (`report_date`) and published Friday (`available_date`); a backtest must not use a row
  before its `available_date`.
- Each run re-reads SqueezeMetrics' whole file and the last 8 weeks of CFTC, so late
  corrections are picked up.
- Not collected: Goldman Sachs prime-brokerage data (private client reports, leaks are
  sporadic and can't be collected automatically).

### News tab: headlines and shipping (since 2026-11-10)

**Headlines** (`collectors/news_collector.py`, every 15 minutes at :02/:17/:32/:47, all week).
Sources, topics and alert words are in `shared/news_feeds.json` (edit, then re-run `install.sh`).
Feed list partly taken from the open-source World Monitor project's catalog (`~/world monitor`,
`src/config/feeds.ts`), which uses the same trick for outlets without free feeds.
- About 80 sources: wires (Reuters, AP, Bloomberg through Google News searches; they have no free
  feeds), WSJ, FT, CNBC, MarketWatch, BBC, Guardian, Al Jazeera, NPR, Politico, The Hill, Axios,
  network news, France 24, DW, Euronews, Kyiv Independent, Ukrinform, ISW, Times of Israel, shipping
  press (gCaptain, Splash247, Lloyd's List), the Fed (statements and speeches), ECB, BEA, SEC,
  Treasury, White House, State, Pentagon, UN, IAEA, think tanks, plus topic searches (Hormuz,
  Red Sea, Ukraine, Russia sanctions, Iran, Israel/Gaza, China/Taiwan, tariffs, oil, Fed, global
  central banks, US data, bonds, earnings, deals, AI, metals, crypto). Google searches are split
  in two halves read on alternate runs, so each is read every 30 minutes.
- One row per distinct headline: headline, outlet, link, time, a summary of up to 300 characters.
  No article text (size and copyright). Items older than 72 hours when first seen are skipped;
  undated items on a feed's first read are skipped as old backlog.
- **Stories**: a headline joins a story when its words overlap at least 50% (Jaccard) with a
  headline from the last 36 hours. Importance = sum over distinct outlets of 1 + 2 x rating/100
  (government sources 3) + 3 if any headline has an alert word. A story's topics are the ones at
  least a third of its headlines carry. (The old `tier` columns are still filled but no longer used.)
- **Outlet ratings and story trust** (since 2026-11-10, owner's request): `shared/source_ratings.json`
  rates ~45 outlets 0-100 from Media Bias/Fact Check's factual score (100 - 10 x score) and Ad Fontes'
  reliability (100 x (R - 8) / 40), averaged where both rate an outlet; outlets neither rates are
  `unrated` (40); government and central-bank sources are `official` (no rating: a reliable record of
  what was said, still one side's claim). Only accuracy is used, never the bias scores. Each headline
  stores `outlet` and `rating`; each story stores `trust` = best outlet's rating + 5 per other outlet
  rated 60+ (or official) carrying it (max +15) - 15 if the lead headline hedges ("reportedly",
  "sources say", "could", "alleged", a question mark ...) - 10 if any headline denies or disputes,
  capped 0-100, with `trust_label` High (80+) / Medium (60-79) / Low / Official and `trust_why`.
  It measures sourcing, not truth. The News tab can filter by reliability (All, 50+, 70+, 80+, 90+: stories by trust, headlines by outlet rating; "+ Official" keeps government sources in). After editing the ratings file: `install.sh`, then
  `~/MarketData/.venv/bin/python ~/MarketData/app/news_collector.py rescore`. On 2026-11-10 about 41% of
  headlines came from unrated outlets (Yahoo Finance, The National, Iran International, Lloyd's List ...).
- **Search**: `news_fts` (SQLite full-text, word stems). Left out of the backup and rebuilt from
  `news_items` automatically when its count doesn't match.
- A run is `ok` while at least 60% of feeds answer (dead feeds show red in the Sources panel and
  in the run detail); below that it's `partial`, which the watchdog reports.
- Size: about 1–3 MB a day. `news_items` and `news_stories` are backed up by month.

**Shipping** (`collectors/shipping_collector.py`, 09:40 and 19:40 daily). IMF PortWatch's daily
transit counts for 28 chokepoints, by ship type, with carrying capacity, from 2019 (~80,000 rows,
12 MB). PortWatch runs 2–4 days behind and revises recent days, so each run re-reads the last
45 days. "Normal" on the tab is the Jan–Oct 2023 average, before the Red Sea attacks.

**Fed panel**: next decision from `econ_calendar`, Polymarket's "Fed Decision in <month>?" odds, the
scheduled CPI and jobs dates, and the latest Fed statements and speeches.

**Not built yet**: linking headlines to market moves (each story with the moves in stocks, oil,
VIX and related Polymarket odds in the hour after it, and each big move with the headlines before it).

### Events (Polymarket)

`collectors/events_collector.py` reuses the ingestion layer of `polymarket-bot-v2` (Gamma API
paging, outcome/price parsing, the negRisk end-date rule, deterministic volume/liquidity
filters). Its LLM agent chain and its signal, sizing and trading layers are not used.

- Hourly, all week. Keeps events with ≥ $5K 24h volume or ≥ $25K liquidity, and within them
  open markets with ≥ $5K liquidity or ≥ $2.5K 24h volume (about 870 events / 6,900 markets
  on 2026-10-26). Sports/culture keeps only the top 50 events.
- Groups come from Polymarket's tags through a fixed map (`GROUPS` in the collector).
- `poly_snapshots.price` is the first outcome's price ("Yes" for binary markets); `change_*`
  are Polymarket's own 1h/1d/1w/1m changes. History starts 2026-10-26.
- Dashboard movers exclude markets resolving within 48 hours (vote counts, "up or down
  today" markets converge to 0/100 by design). "All" excludes sports/other.
- Size: roughly 20 MB a day (~7 GB a year). Raise the market filters if that's too much.

### Official layer: read these, not the raw tables

Anything that makes decisions (dashboard, scoring, backtests) reads **only** these three
views. Each gives one value per field, picked by a fixed rule (defined in `VIEWS` in
`options_collector.py`). A backup fills in only when the primary is **missing**: never
averaged, never chosen because the numbers differ. When a backup is used, it's flagged.

| View | Primary | Backup (only if missing) | Flags |
|---|---|---|---|
| `stock_snapshots` | price: Alpaca IEX; volume: Yahoo | volume: Alpaca SIP | `volume_from_backup`; `volume_check` (sources differ by >10% after 11:00, health check only) |
| `open_interest` | OCC | Yahoo, for a symbol OCC failed that day (never mixed within a symbol/day) | `from_backup` |
| `option_quotes` | Alpaca | none (a failed snapshot is a recorded gap) | — |

The raw tables keep every source's number for checking and recovery. The 09:15 retry only
fills symbols still missing OCC data, so it can never replace OCC numbers with Yahoo's.

Database tables (`~/MarketData/options.db`): `occ_oi`, `option_snap`, `underlying_snap`,
`runs`, plus `alpaca_contracts` (collected on 2026-10-26 only, then dropped as stale). Size:
about 90 MB per trading day (roughly 22 GB a year).

Known data quirks:
- **Open interest freshness:** OCC prints no as-of date. Its numbers normally reflect the
  previous trading day's close; compare day-over-day changes to confirm.
- **Stock volume:** the free plan's live stock feed is IEX, one exchange with 1–11% of trading
  depending on the symbol (QQQ 1.2%, XLC 11.4% on 2026-10-26), so scaling it up isn't reliable.
  Use `underlying_snap.yahoo_day_volume` (live, all exchanges, regular hours, as of
  `yahoo_asof`). `sip_day_volume` is the backup: all exchanges but including pre-market, so
  don't compare it against a regular-hours baseline. `day_volume` is IEX only.
- About 21% of snapshot contracts have no IV or greeks (mostly illiquid or deep in-the-money).
- After splits, OCC lists adjusted products separately (e.g. `2NVDA`, `1NVDA`); they're kept
  under their own `product`, so filter `product = underlying` for standard contracts.
- Python from python.org ships without CA certificates; the collector uses `truststore` to
  read the Mac's keychain instead. Its environment is `~/MarketData/.venv`.
