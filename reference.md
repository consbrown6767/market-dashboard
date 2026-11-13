# Market Dashboard: the complete reference

*Last updated 2026-11-13 (live paper record started: leveraged trend, 10-month trend, pre-Fed drift; Fed calendar parser fixed and history reloaded; constant leverage tested: 2x more money but −98.7% in 1929-32, fails; monthly savers at 2x ahead in all 60 cohorts; Fed-day drift and Fed cycle tested: both faded after publication, Fed calendar gap found; earnings-week premium tested: failed; overnight-only investing and trend across many markets tested: both failed; round 4 and tournament of all 24 strategies: none beats SPY by the rules; 10-month trend safest, leveraged trend most money; pairs trading and macro timing models tested: both failed; risk budget model, stocks + Treasuries by equal risk, tested 1965-2026: failed; nine classic published strategies tested on 100 years: none beats the market, 10-month trend is safer; volatility-managed market model tested on 100 years of data: failed, not live; stock direction model: fresh test on the other 400 S&P 500 stocks, five more signals, crash protection live on the 400; 2026-11-11: the stock direction model, its S&P 100 options history, and its weekly live job; 2026-11-10: news outlet ratings and story trust; code moved to `~/Code/market-dashboard` and put in git; split table; nightly daily bars) by Claude. One place for everything about this project: what it is, the data,
the four prediction models, the political game machine, how it all runs, and the rules agreed along
the way. Numbers are as of the evening of Monday 2026-11-09 unless a date says otherwise.*

Kept up to date: any change to something described here is written into this file in the same piece
of work (the rule is in `CLAUDE.md`). Fast-moving numbers (row counts, odds, results) are snapshots
from the date above; the dashboard always has the live ones. The detailed documents remain the source
of truth for their parts: `README.md` (how it runs), `CLAUDE.md` (short notes and rules),
`docs/spx-move/README.md` (S&P model), `docs/stock-direction/` (stock direction model: `PLAN.md` fixed before results, `README.md` results), `docs/gamma-strategy/` (breakout tracker), `politics/HANDOFF.md`
and `politics/PLAN.md` (political machine).

---

## 1. What this is, in one paragraph

A private research dashboard on this Mac (http://127.0.0.1:8765) that gives a broad view of the
market. Background jobs collect free data around the clock into one database. The page shows it in
tabs. On top of the data sit three models that make predictions **before** the outcome is known and
keep score honestly: an S&P 500 move-size model, a gamma breakout tracker for single stocks, and a
political game machine for the 2028 election. Nothing here trades or bets. The point is to find out,
with real records, whether any of these ideas know something the market doesn't.

## 2. Where things stand (2026-11-09)

| Piece | State |
|---|---|
| Data collection | Running since 2026-10-26. 747 recorded job runs: 744 ok, 1 failed, 1 partial, 1 stopped |
| Database | 9.1 GB at `~/MarketData/options.db` on 2026-11-12 (was 3.7 GB before 11-11; +5.4 GB of S&P 500 options history). 186 GB free on the Mac |
| Watchlist | 72 symbols (stocks, sector and industry ETFs, bonds, commodities, global, crypto) |
| S&P 500 move-size model | Built and backtested today. First live prediction logged at 8:50 pm for Tue 2026-11-10 (a CPI day): 90% range −2.19% to +1.97%, 50% range −0.64% to +0.94%. Tamper check ok |
| Gamma breakout tracker | Live forward test started today. Day 1: three breakout attempts, no predictions (volume too low or failed hold) |
| Political game machine | Rebuilds hourly. 509 forecasts logged (all on 2026-11-05), none resolved yet. Candidate ratings re-set from research on 11-10 (unreviewed) |
| Scorecard / prediction ledger | Built today. Holds 3,151 backtest rows for the S&P model; live rows start tonight |
| Stock direction model (added 2026-11-11) | Weekly chance each S&P 100 stock beats SPY, from options prices. Backtested on 2024-25, tuned (16 variants), sealed test on 2026: **no version reliably beats the base rate**; crash protection was the only input pointing the right way in both periods. Fresh test on the other 400 S&P 500 stocks (2026-11-12): crash protection pointed the right way again and lean-passed; five more research signals did nothing reliable. Three versions log live every Tuesday from 2026-11-17 (`1-learned`, `3-skew`, `3-skew@sp400`). ~90,000 backtest rows in the ledger |
| Alerts and daily update | Phone push via ntfy: problems every 30 min, a morning update at 10:00 |
| News and shipping (added 2026-11-10) | Headlines from 83 sources every 15 min, grouped into stories, searchable; ships through 28 chokepoints daily, history from 2019. First run: 83 of 83 feeds answered, about 3,000 headlines from the last 3 days. News tab built |

---

## 3. How the pieces fit

```
free sources (OCC, Alpaca, Yahoo, Cboe, SqueezeMetrics, CFTC, Fed, BLS, Polymarket, Kalshi,
              ~80 news feeds, IMF PortWatch)
        │
        ▼
collectors/  (launchd jobs on a schedule; the ONLY writers)
        │
        ▼
~/MarketData/options.db  (one SQLite database)      ~/MarketData/politics/  (political machine's own files)
        │                                                    │
        ▼                                                    ▼
dashboard/server.py  (read-only JSON API)  ◄──── reads outputs/data.json
        │
        ▼
dashboard/static/  (the page: tabs and panels)

Models: spx_move.py, stock_direction.py, strategy_collector.py + scoring.py, politics/ ─► their own records
        └─ new models log to the prediction ledger (ledger.py) ─► Scorecard tab
```

Three principles hold everything together:

1. **Collectors write, the dashboard only reads.** The server opens the database read-only. On-demand
   charts and chains are fetched live and never stored.
2. **One value per field.** Anything that makes a decision reads the *official views*, never the raw
   tables. A backup source only fills a gap, never averages in, and is always flagged.
3. **Predictions are written down first and never edited.** Every model is compared with a simple
   guess made at the same moment. Live results and backtests are kept apart.

---

## 4. Where everything lives

| What | Where | Notes |
|---|---|---|
| Code and docs | `~/Code/market-dashboard` | A git repo since 2026-11-10, on GitHub as the private repo `consbrown6767/market-dashboard` (moved out of iCloud: git and iCloud syncing clash). The old iCloud folder `Vibe Coding/Market Dashboard/` now only matters for its `backups/` |
| Database | `~/MarketData/options.db` | Outside iCloud on purpose: syncing a file mid-write can corrupt it |
| Logs | `~/MarketData/logs/` | One per job |
| Python | `~/MarketData/.venv` | Uses `truststore` because python.org Python has no CA certificates |
| Running copies of collectors | `~/MarketData/app/` | launchd runs these copies, so re-run `collectors/install.sh` after editing a collector or `shared/*.json` |
| Political machine (running copy and data) | `~/MarketData/politics/` (44 MB) | `install.sh` refreshes the code, never touches `data/`, `kalshi/`, `outputs/` |
| Alpaca keys | `~/.config/market-dashboard/alpaca.env` | Free paper account. Never printed, never in this folder |
| Phone alert channel | `~/.config/market-dashboard/alert.env` | The channel name is the only secret |
| Backups | `backups/` in this folder | Nightly at 20:30, see section 6.4 |
| Originals of the gamma strategy and political machine | `Vibe Coding/box of scraps/` | Copied (not moved) on 2026-11-06. The copies here are the live ones; the originals no longer update |

Configuration files in `shared/`:

| File | Holds |
|---|---|
| `watchlist.json` | The 72 symbols collected, and the snapshot filter (expirations ≤ 60 days, strikes within ±25% of price) |
| `strategy.json` | The breakout tracker's 14 stocks and their sector ETFs, the dealer assumption, the 30-day wall window, the 20-day volume baseline |
| `pairs.json` | Spreads tab pairs: RSP/SPY, KO/PEP, CVX/XOM |
| `release_dates.json` | CPI and jobs-report dates from BLS, past and scheduled through Dec 2027 |
| `watchlists.json` | Your own named watchlists (created when you first save one; none saved yet) |

*Note:* `CLAUDE.md` says you added an NVDA-AMD pair, but `pairs.json` holds only the three pairs above
and no NVDA/AMD bars are stored for the Spreads tab. It may have been removed with the × on its chip.

### The jobs (all times Eastern, Mac local time)

Seventeen launchd agents, all named `com.marketdashboard.options.*`, created by `collectors/install.sh`.

| Job | When | Does |
|---|---|---|
| `daily` | 07:30, retry 09:15, Mon–Fri | OCC open interest at every strike and expiration. Yahoo only for a symbol OCC fails |
| `bars` | 17:15, retry 20:15, Mon–Fri | Official daily bars (raw) for all 72 watchlist symbols into `stock_bars_daily`. Use these for daily closes, not the 15:55 snapshot |
| `positioning` | 07:45 Mon–Fri, plus 16:45 Fri | SqueezeMetrics S&P dealer gamma and dark-pool index; CFTC futures positioning |
| `snapshot` | 09:35, hourly 10:00–15:00, 15:55, Mon–Fri | Alpaca option quotes, IV and greeks; stock prices and volume. About 60,000 rows and 50 s per run |
| `spreads` | 09:40, hourly 10:05–15:05, 16:30, Mon–Fri | Adjusted daily bars for every pair leg; full reload Saturdays |
| `strategy` | Every 5 min, 09:25–16:30, Mon–Fri | Gamma breakout tracker |
| `spxmove` | 16:50, 18:20, 20:50 and 08:05, Mon–Fri | S&P move-size model: refresh data, resolve yesterday, predict tomorrow (only once) |
| `direction` | 18:40 Mon–Fri | Stock direction model: resolve predictions whose week has closed; on a week's last trading day (normally Tuesday), download the S&P 500 stocks' options (about an hour), recompute implied volatility, predict next week (`stock_direction.py live`) |
| `paper` | 09:10, 16:40, 20:40, Mon–Fri | Live paper record (`paper_record.py`): log the trend rules' positions before the next day's close and the pre-Fed window days ahead; mark finished days against SPY. 09:10 catches up a missed evening |
| `events` | Hourly at :05, every day | Polymarket events |
| `politics` | Hourly at :25, every day (past prices at 02:25) | Political machine: prices, headlines, rebuild |
| `news` | Every 15 min (:02, :17, :32, :47), every day | Headlines from ~80 sources, grouped into stories (`news_collector.py`) |
| `shipping` | 09:40 and 19:40 every day | Ships through 28 chokepoints, IMF PortWatch (`shipping_collector.py`) |
| `briefing` | 10:00 every day | Morning phone update |
| `watchdog` | Every 30 min (:20, :50), every day | Phone alert when something breaks |
| `backup` | 20:30 every day | Compressed backup into `backups/` |
| `dashboard` | Always on | The web server; restarts itself if it stops |

Every job records each run in the `runs` table (ok, partial, skipped, failed, stopped), so gaps are
visible. The Status tab shows them.

---

## 5. The dashboard tabs

The look follows World Monitor: dense dark panels, monospace text, small uppercase panel titles,
status dots and freshness badges. Every panel has a stable `data-panel` id because saved layouts
depend on it. Panels drag and drop onto a 24-column grid, resize from the corner, hide with −, come
back with +; layouts save per tab in the browser; **Reset layout** restores a tab. **A− / A+** (top right) make all text below the top bar smaller or bigger (80% to 200%), remembered per browser. Under 900 px wide,
panels stack. Charts are TradingView Lightweight Charts 4.2.0, stored locally.

| Tab | What it shows |
|---|---|
| **Options** | Click any symbol (or type any ticker): open interest by strike, today's volume by strike, IV by strike, per-expiration call/put OI and volume, put/call ratios, at-the-money IV and implied move. Price candles (1D to 5Y), the full live options chain, and a chart of any single contract with its greeks and breakeven. S&P dealer gamma (12 months) and CFTC positioning. Universal watchlist (every stock with data) and your own named watchlists |
| **Spreads** | Relative-value pairs: ratio with 50/200-day averages, z-score, 1-year percentile, returns per leg. "Any pair" lets you type two tickers; **Save** adds it to `pairs.json` |
| **Gamma** | The breakout tracker: each stock's call wall, put wall and gamma flip, a 5-minute chart with those levels, breakouts in their 30-minute hold, every breakout logged with its grades, and a scorecard. Live and replay kept apart |
| **Politics** | The political game machine in seven sections: Overview, Play the game, President, Senate and House, Strategy, Ratings, Scorecard |
| **Scorecard** | Every model's record against its simple guess, with a verdict and a tamper check. The S&P model's range for the next trading day, its inputs, the next scheduled Fed/CPI/jobs news, and its last 120 ranges against what happened. Whether 90% ranges really catch 90%. The live paper record of three trading rules ($10k vs SPY, holdings, chain check) |
| **News** | Top stories (headlines grouped by event, ranked by how many outlets carry them, weighted by each outlet's rating) with a trust badge (High/Medium/Low/Official: how well sourced, not whether true), each headline showing its outlet's 0-100 rating (from Media Bias/Fact Check and Ad Fontes; `shared/source_ratings.json`), latest headlines with topic filters (Fed and rates, economy, markets, business, tech and AI, energy, shipping, Russia and Ukraine, Middle East, China, US politics, world, crypto) and a search over every stored headline. Shipping chokepoints (last 7 days vs normal and a year ago, tankers, 6-month sparkline, full history chart). Hormuz, Bab el-Mandeb and the Kerch Strait are shown as "≥" (at least): many ships there turn trackers off, so the true number is higher. No estimate is added, because no free data can measure the dark ships. Fed and data calendar with Polymarket's odds for the next decision and the latest Fed statements. Feed health |
| **Events** | Polymarket by group (macro and Fed, geopolitics, business and tech, politics, crypto, sports and other), 24-hour movers, what resolves this week, every event with its price history |
| **Status** | Every job's last run, status and detail |

Pages refresh every minute. The server only listens on this Mac.

---

## 6. The data

### 6.1 Sources (all free)

| Source | Gives | Limits |
|---|---|---|
| **OCC** (Options Clearing Corp.) | Official open interest at every strike, every morning | Today only, no history. Prints no as-of date: numbers normally reflect the previous close |
| **Alpaca** (free paper account) | Live option quotes with IV and greeks; option prices back to Feb 2024; stock bars; trading calendar | "Indicative" prices, not official OPRA. Full-market (SIP) bars must end ≥ 16 min ago, or it refuses ("OPRA agreement is not signed"). About 200 requests a minute. Live stock feed is IEX, one exchange with 1–11% of volume |
| **Yahoo Finance** | Live stock volume (all exchanges); open interest as a backup; S&P 500 index history from 1990; oil, Brent, 10-year, VIX, S&P futures for the morning update; past earnings dates and surprises (stock direction tests) | Unofficial: can change or rate-limit without notice. Option quotes 15–20 min old, IV low on puts. Its S&P closes matched SqueezeMetrics' on 3,903 of 3,904 days |
| **Cboe** | Daily VIX (1990 on), VIX9D (2011 on), VIX3M (2009 on) | End of day only. On 2026-11-09, VIX9D and VIX3M were posted by 8:50 pm but the VIX file only at 9:29 pm, so that evening's prediction used Yahoo's VIX (flagged). Yahoo's figure matched Cboe's exactly (19.92) |
| **SqueezeMetrics** | S&P 500 dealer gamma (GEX) and dark-pool index (DIX), daily from May 2011 | A day's figure is computed after that day's close (2026-11-09's appeared at 6:04 pm) |
| **CFTC** | Weekly futures positioning by trader group (dealers, asset managers, hedge funds, others, small traders) | Positions as of Tuesday, published Friday |
| **Federal Reserve** | FOMC meeting dates, 2002 to next year | Scheduled meetings only |
| **FRED** (St. Louis Fed) | 3-month T-bill rate (`DTB3`), for option pricing | Drops requests carrying our own user-agent name; answers Python's standard one (not a browser's) |
| **Alpaca corporate actions** | Cash dividends and splits | Dividend amounts as paid at the time (not split-adjusted) |
| **BLS** | CPI and jobs-report dates | Blocks scripts, so dates were read in a browser into `shared/release_dates.json`. Refresh yearly by hand |
| **Polymarket** | Prices for every active event with real trading, all topics (about 560 in this evening's pull, 870 on 2026-10-26) | Thin markets filtered out (events need $5K of 24-hour volume or $25K of liquidity) |
| **Kalshi** | 2028 political markets (own collector in the political machine) | Long-dated prices rarely go below about 8% |
| **News feeds** (`shared/news_feeds.json`) | Headlines, outlet, link, time and a short summary from 83 sources: wires, major outlets, the Fed, ECB, BEA, SEC, White House, State, Pentagon, UN, IAEA, shipping press, think tanks, topic searches (Hormuz, Red Sea, Ukraine, Iran, China, tariffs, oil, Fed, data, earnings, AI and more) | Reuters, AP and Bloomberg have no free feeds: their headlines arrive through Google News searches. No article text is stored. Sources partly taken from the open-source World Monitor catalog |
| **IMF PortWatch** | Ships per day through 28 chokepoints by type, with carrying capacity, from 2019 | 2–4 days behind; recent days get revised. Built from ship tracking (AIS); live tracking would need a free AIS account the owner would have to create |

Best source per data type, from a side-by-side test on 2026-10-26:

| Data | Use | Backup |
|---|---|---|
| Open interest | OCC (Yahoo's matched; Alpaca's were 4 days stale) | Yahoo |
| Option bid/ask, IV, greeks | Alpaca (near live) | none |
| Option volume | Alpaca | — |
| Stock volume | Yahoo (live, all exchanges, regular hours) | Alpaca SIP (includes pre-market) |
| Stock price | Alpaca IEX (live, within cents of the full market) | Yahoo |

There is **no free source of past open interest by strike**, so that history is being built forward
from 2026-10-26. It can never be recovered for earlier dates.

### 6.2 Every table (row counts on 2026-11-09)

**Live collection (built forward; can't be re-downloaded):**

| Table | Rows | Covers | What it is |
|---|---|---|---|
| `occ_oi` | 752,269 | 11 trading days, 2026-10-26 → 11-09 | Open interest per strike and expiration, per morning |
| `option_snap` | 3,934,216 | 2026-10-26 → 11-09 | Hourly option quotes, IV and greeks (≤ 60 days, ±25%) |
| `underlying_snap` | 3,433 | 89 snapshot runs | Stock price, bid/ask, volume from three sources |
| `poly_events` / `poly_markets` | 6,125 / 71,092 | since 2026-10-26 | Polymarket events and their markets |
| `poly_snapshots` | 1,810,572 | hourly since 2026-10-26 | One price per market per hour, with bid/ask and Polymarket's own changes |
| `runs` | 747 | since 2026-10-26 | Every job run |
| `news_items` / `news_stories` | ~3,300 / ~2,900 (2026-11-10) | from 2026-11-07 | One row per distinct headline (with its outlet's rating); headlines grouped into stories with importance, topics and a trust score (since 2026-11-10: about 35% High, 16% Medium, 46% Low, 3% Official). `news_fts` is their full-text search index (not backed up; rebuilt automatically) |
| `news_feed_status` | 83 | — | Each source's last read and last error |

**History (free to re-download):**

| Table | Rows | Covers | What it is |
|---|---|---|---|
| `option_bars_daily` | 37,383,659 (2026-11-12) | 2024-02-01 → today, 558 underlyings (watchlist + S&P 500) | Daily trade bars per option contract (no bid/ask, IV, greeks or OI). The Alpaca backfill; the S&P 100 stocks added 2026-11-11, the other 400 on 11-12, kept current weekly by the `direction` job |
| `stock_bars_daily` | 403,481 (2026-11-12) | 2023-12-18 → today, 559 symbols | Raw (not split-adjusted) daily stock bars, so they line up with strikes of the time. Watchlist kept current by the `bars` job, the S&P 500 stocks by the `direction` job |
| `stock_splits` | 47 | 2016 → today | Every split for the watchlist and anything in `stock_bars_daily`, from Alpaca's corporate actions feed; refreshed by the daily job |
| `dividends` | 5,075 | 2023-11 → announced | Cash dividends (ex-date, amount as paid at the time) for the S&P 500, sector ETFs and SPY, from Alpaca. Used for total returns and option pricing |
| `rates_daily` | 734 | 2023-12 → today | 3-month T-bill (FRED `DTB3`) |
| `direction_iv_daily` | 885,570 | 2024-02-01 → today, 499 stocks | Implied-volatility measures per stock and day (call-vs-put gap, crash protection, at-the-money call and put volatility), for three minimum-trade rules. Computed by `stock_direction.py iv` from the two tables above |
| `earnings_dates` | 23,791 | 2007 → announced, 500 stocks | Earnings report times, EPS estimate, reported EPS and surprise, from Yahoo Finance (`yfinance`, unofficial). Used only by the stage 4 tests (earnings week, post-earnings drift); not refreshed by any job |
| `ff_daily` | 1,351,652 | 1926-07 → 2026-09 (US, 49 industries); 1990-07 → (4 other markets) | Kenneth French's daily returns (Dartmouth; CRSP-based, dividends in): US market minus T-bill and the T-bill, Developed ex US, Europe, Japan, Asia Pacific ex Japan, 49 value-weighted industries. Loaded by `vol_managed.py data` for the volatility-managed test; not refreshed by any job |
| `ff_monthly` | 75,459 | 1926-07 → 2026-09 (US); 1990-07 → (4 other markets) | French's monthly value-weighted sorted portfolios: 10 momentum deciles, size × value, variance and profitability quintiles; abroad, size × momentum/value/profitability. Loaded by `classic_strategies.py data`; not refreshed by any job |
| `gw_monthly` | 23,644 | 1871-01 → 2025-12 | Amit Goyal's monthly predictor data (Goyal & Welch): S&P level, dividends, earnings, rates, credit yields, issuance, variance, inflation, CRSP S&P returns. Loaded by `macro_timing.py data`; not refreshed by any job |
| `stock_bars_split_adj` (view) | | | `stock_bars_daily` in today's share terms. Use it for any price series across a split (returns, drawdowns, volatility); use the raw table to match strikes |
| `daily_bars_adj` | 1,763,500 | 2016 → today, 749 symbols | Split- and dividend-adjusted bars: the Spreads tab's 6 symbols (refreshed by `spreads`), plus every S&P 500 member since 2015 for the pairs test (`pairs_model.py prices`, one-time) |
| `market_gamma` | 3,904 | 2011-05-02 → 2026-11-06 | SqueezeMetrics GEX and DIX |
| `cftc_tff` (view `cftc_net`) | 7,330 | 2010-06-15 → 2026-11-03, 9 contracts | S&P, Nasdaq-100, Dow, Russell, VIX, 2/5/10-year notes, T-bond |
| `index_daily` | SPX 9,282; VIX 9,311; VIX3M 4,311; VIX9D 3,985 | SPX and VIX from 1990 | S&P 500 index (Yahoo) and the VIX family (Cboe), with a `source` column |
| `chokepoint_daily` | 80,332 | 2019-01-01 → 2026-11-08, 28 chokepoints | IMF PortWatch ships per day by type and capacity (12 MB) |
| `econ_calendar` | Fed 203, CPI 306, jobs 307 | 1995/2002 → Dec 2027 | Scheduled Fed decisions, CPI days, jobs-report days |

**Model records:**

| Table | Rows | What it is |
|---|---|---|
| `strategy_levels` | 14 live (today), 126 replay | Each stock's call wall, put wall, gamma flip per day |
| `strategy_events` | 3 live, 23 replay | Every finished breakout attempt, predictions or not |
| `strategy_grades` | 69 | Each event checked at the close, next close, and three closes later |
| `strategy_state` | 14 | Each stock's live state (holding, volume ratio) |
| `strategy_bars_5m` | 63,960 | 5-minute bars since 2026-09-14 (for the volume baseline). Not backed up |
| `paper_positions` / `paper_marks` / `paper_skips` | from 2026-11-13 | Live paper record: positions written before they take effect (hash-chained), daily or per-meeting results next to SPY (hash-chained), signals missed because the job didn't run |
| `predictions` / `prediction_outcomes` | 93,541 / 93,540 (2026-11-12) | The prediction ledger: S&P model backtest and live; stock direction backtests (S&P 100: 1, 1-learned, 2, 3-skew, 4-os, 4-earn, 4-pead, 4-rvi, 4-max, 5-research; the 400: the same names with `@sp400`, minus 2) |

Small housekeeping tables: `alpaca_contracts` (one day only, then dropped as stale), `backfill_progress`.

### 6.3 The official views (read these, not the raw tables)

| View | Primary | Backup (only if missing) | Flags |
|---|---|---|---|
| `stock_snapshots` | price: Alpaca IEX; volume: Yahoo | volume: Alpaca SIP | `volume_from_backup`; `volume_check` (sources differ by > 10% after 11:00, a health check only) |
| `open_interest` | OCC | Yahoo, for a whole symbol OCC failed that day (never mixed within a symbol and day) | `from_backup` |
| `option_quotes` | Alpaca | none (a failed snapshot is a recorded gap) | — |

### 6.4 Storage and backups

- **Size:** 3.7 GB today. It was 2.2 GB on 11-02 and grew faster after 42 symbols were added on 11-05
  (snapshots are about 50% bigger since). Polymarket adds about 20 MB a day; news about 1–3 MB a day
  (to be measured after a week).
- **Backup** (nightly, into `~/Library/Mobile Documents/com~apple~CloudDocs/Vibe Coding/Market Dashboard/backups/`, so iCloud keeps a copy): `options-core.db.gz` (6.6 MB: all small
  tables, schemas and views) plus one file per month (`options-2026-10.db.gz` 161 MB, `-11` 197 MB) and
  `politics-data.tar.gz`. Only the open month is rewritten, so closed months never re-upload. The
  option-price backfill (about 70% of the database) is left out because it can be rebuilt in about 45 min.
- **Projected:** about 10 GB of backups after a year (an estimate). Next levers if space gets tight:
  keep Polymarket hourly for 90 days then daily; store option snapshots without repeated columns
  (about half the size).
- **Restore:** `collectors/install.sh uninstall`, then `restore_backup.py ~/MarketData/options.db`,
  then `install.sh`, then rerun `backfill_alpaca.py`. Unpack `politics-data.tar.gz` into
  `~/MarketData/politics`. Tested 2026-11-02: every table matched row for row.

### 6.5 Known data quirks

- About 21% of snapshot contracts have no IV or greeks (mostly illiquid or deep in the money).
- After splits, OCC lists adjusted products separately (`2NVDA`, `1NVDA`). Filter `product = underlying`.
- Index ETFs (SPY, QQQ) have about 5× more strikes, $1 apart, and very concentrated open interest
  (hedges at round strikes), so their charts default to ±10% of price.
- Options are very thin on PEJ, QQQE, XLRE and UUP: their prices are the useful part.
- The backfill is trade bars; the live snapshots are point-in-time quotes. Don't mix them in one series
  without saying so.
- Yahoo's continuous futures (oil, Brent, S&P futures) jump at contract rolls. The morning update
  compares each specific contract with itself to avoid fake moves.

### 6.6 Watchlist history

- **2026-10-26:** 25 symbols at launch (Mag 7 and other mega-caps, index ETFs, sector ETFs, TLT, GLD),
  then ORCL, PLTR, LLY, TSM and HYG the same day: 30.
- **2026-11-05:** 42 added to study how markets affect each other: market structure (QQQE MDY IWF IWD
  MTUM SPHB SPLV MAGS), bonds (SHY IEF TIP LQD), commodities (USO BNO UNG SLV CPER COPX GDX), the last
  four sectors (XLP XLU XLB XLRE), industries (KRE PEJ JETS XRT XHB IYT ITA IGV AIQ XBI XOP), and
  global/dollar/fear/crypto (EFA EEM FXI UUP FXY VXX IBIT ETHA). 72 symbols.
- Futures aren't collected: there's no free futures options data.

### 6.7 Timing rules for honest backtests

- SqueezeMetrics GEX for day D is known only after D's close: a decision on D uses D−1.
- CFTC rows may only be used from their `available_date` (Friday), not their `report_date` (Tuesday).
- The gamma tracker's levels use only this morning's OCC file and the last snapshot before today.

---

## 7. The prediction ledger (how every model is kept honest)

`collectors/ledger.py`, shown on the Scorecard tab. Rules, the same for every model:

1. **Written down first.** A live prediction is stamped when it's logged and refused if its window has
   already opened.
2. **Never edited.** Live rows are only added. Each carries a hash of itself and of the row before
   (a hash chain), so `verify()` catches any changed or deleted row or outcome.
3. **Always next to a simple guess.** Every prediction carries at least one baseline made at the same
   moment by a simple rule. A model is only worth keeping if it beats them.
4. **Live and backtest kept apart.** Backtests can be cleared and rerun; live rows never.
5. **A retuned model is a new version**, scored on its own. The old version keeps running.

**Two kinds of prediction:**
- `probability` (a chance), scored by the **Brier score**: the squared gap between the chance and what
  happened (0 or 1). Lower is better; always saying 50% scores 0.25.
- `quantiles` (a range for a number), scored by the **quantile (pinball) loss**, which rewards ranges
  that are both tight and right, plus **coverage**: how often outcomes land inside each range.

**Verdicts:** "too few" until 30 are resolved. Then "beats it" or "worse" only when the average gap to
the baseline is more than about two standard errors, compared prediction by prediction. The error bar
allows for streaks (Newey-West), because a stormy week is stormy for every model, and it's never
smaller than the plain one.

The gamma tracker and the political machine keep their own records (they predate the ledger); the
Scorecard tab reads those as they are.

---

## 8. Model 1: S&P 500 move-size model

*Code `collectors/spx_move.py`, tests `collectors/test_spx_move.py`, full write-up `docs/spx-move/README.md`.
Built 2026-11-09. Version 1's inputs and method were agreed with you before any test was run; any change
is a v2, and only with your OK.*

### What it does

Every weekday evening, a range for how big the **next trading day's S&P 500 move** will be: five
points (5%, 25%, 50%, 75%, 95%), so a 90% range and a 50% range. It predicts size, not direction.

- **Target:** the S&P 500 index's close-to-close % change (the overnight gap plus the day).
- **Made:** after the close, from values fixed at the close. Runs at 16:50, retries 18:20, 20:50 and
  08:05; predicts only once.
- **Window opens** 09:30 the next trading day, when the index next prints. Futures trade overnight but
  are never used.
- **Resolved** the next evening from the closing level (Yahoo, cross-checked against SqueezeMetrics).
- **If Cboe hasn't posted the VIX** by the last run, Yahoo's VIX is used and flagged
  (`source = 'yahoo-backup'`); the value used stays in the prediction's inputs.

### Inputs (all known at the close)

| Input | What it is |
|---|---|
| Recent moves | Realized variance for today, the last 5 days and the last 22 days, from each day's high-low range (Parkinson) plus the opening gap |
| VIX | The options market's own expected move for the next 30 days |
| Dealer gamma | SqueezeMetrics GEX from the trading day before: whether it's negative, and its rank in the past year |
| Down day | How far the index fell today (0 if it rose) |
| Scheduled news ("#5") | Whether tomorrow has a Fed decision (2:00 pm), CPI (8:30 am) or jobs report (8:30 am) |

### Method (econometrics, financial engineering and statistics)

- **HAR regression** (Corsi 2009): the log of the next day's realized variance explained by today's,
  last week's and last month's, plus the VIX, gamma, down-day and news terms. Refit every evening on
  every day since May 2012 (the first date with a year of gamma for its rank).
- **The VIX is discounted.** It usually overstates real moves (the variance risk premium: buyers pay
  for insurance). The model learns a weight of about 0.79 instead of 1.
- **Ranges come from real past surprises**, not a bell curve: each past move divided by its forecast,
  and the 5%/95% points of those ratios set the range. Fat tails come through as they really happened.
- **Baselines logged with it:** `recent` (21-day standard deviation, bell curve) and `vix`
  (VIX ÷ √252, bell curve).

### Backtest (3,151 days, Apr 30 2014 → Nov 6 2026, each predicted only from earlier days)

| | Average loss (lower better) | 90% ranges caught | 50% caught | Avg 90% width |
|---|---|---|---|---|
| **Model v1** | **0.2249** | **90.3%** | **50.5%** | 3.05 pts |
| Recent moves | 0.2340 (model 3.9% better) | 87.7% | 54.0% | 3.01 |
| VIX at face value | 0.2344 (model 4.0% better) | 96.1% | 64.8% | 3.75 |

- Both gaps are 8 to 11 times their error bars: the ledger says "Beats it" for both.
- About 20% narrower than VIX's ranges, yet catches exactly 90%. Misses are balanced (156 below, 150 above).
- Better in every period: 2014–19, 2020–22 and 2023–26.
- **Dealer gamma is real and VIX misses it:** after negative-gamma days, moves averaged 1.09× what VIX
  implied; after positive-gamma days 0.73×. Negative gamma widens the range about 9%.
- **News days:** the range widens about 24% for a Fed day, 17% for jobs, 8% for CPI.
- **Down days:** about 8% wider per 1% the index fell.
- **Misses:** shocks out of calm (Nov 5 2026: −4.36% against a −1.5% to +1.4% range; Apr 3 2025).
  Extreme panics make it overreact (March 2020 ranges reached ±25–32%).

### Methods compared afterwards (didn't change v1)

| Variant | Result vs v1 |
|---|---|
| Plain HAR (recent moves only) | Worse |
| v1 without gamma | Worse (so gamma adds something VIX doesn't have, about 0.3%) |
| VIX alone, rescaled | Worse, but gets most of the way: the edge is mostly from correcting VIX |
| **v1 + VIX9D** | **Better** (the only clear improvement) |
| v1 + VIX term structure | No clear difference |
| GJR-GARCH(1,1) (returns only) | Worse: the options market knows things past returns don't |
| Boosted trees (machine learning) | Worse even than the simple guesses: ranges too narrow (caught 83%). Dropped |

### v2 ideas (not built; need your OK)

1. Add VIX9D. 2. Cap extreme ranges in panics. 3. Separate tails for news days (Fed ranges a bit too
wide, CPI a bit too narrow). 4. A second target: open to close only, which the gamma tracker cares about.

### Upkeep

The Monday 16:50 run warns (status partial, so the watchdog alerts) once fewer than 60 days of BLS
schedule are left. Refresh `shared/release_dates.json` from bls.gov **in a browser** (never by faking a
browser user agent), then `install.sh`. Fed dates refresh themselves. Each run compares the last 10
Yahoo closes with SqueezeMetrics' and reports any gap over 0.05%.

---

## 9. Model 2: the gamma breakout tracker

*Rules `collectors/scoring.py` (21 tests; agreed with you on 2026-10-21; not to be changed unasked),
data `collectors/strategy_collector.py`, page `dashboard/static/gamma.js`, design `docs/gamma-strategy/`.*

### The idea under test

When a liquid large-cap stock breaks above its options **call wall** and holds, dealers' hedging pushes
it further up. The tracker makes predictions and grades them. It never trades.

### The levels (once a day, from what was known before the open)

- **Call wall:** the strike with the most call open interest across expirations in the next 30 days,
  from this morning's OCC file (yesterday's close).
- **Put wall:** the same for puts. Shown on the chart, not used in the rules.
- **Gamma flip:** the price where total dealer gamma changes sign, computed at prices within ±30% from
  open interest and the last option snapshot before today. Assumes dealers are short the calls and long
  the puts customers hold (`dealer_view`, switchable; flipping it changes the sign, not the flip).
  Some stocks have no flip in range (today: AVGO, ORCL); that's a real result and costs them that point.

### The rules

**Requirements (all must pass, or no prediction):**
1. A 5-minute bar closes above the call wall, having been at or below it.
2. None of the next six bars (30 minutes) closes below the wall.
3. Volume so far today is more than 1.5× the 20-day average by the same time of day.

**Score (ranks breakouts that pass):** +1 sector ETF above both its open and previous close; +1 price
above the gamma flip; +1 crowded short sellers (no free data, so never earned). Score ≥ 1 is a
prediction, ≥ 2 is "strong." Scores run 0–2 in practice.

**Edge cases:** the breakout must happen by 15:30; at most one prediction per stock per day; a fall
below the wall during the hold voids that attempt; a fall below the wall after a prediction makes it
**wrong** (never thrown out). Every attempt is logged, including failures: they're the comparison group.

**Grades:** at the day's close, the next close, and three closes later (Alpaca's trading calendar
handles holidays and half days). Wrong if any 5-minute bar closed below the wall before the check.

**Caution written into the design:** common theory says dealers *dampen* moves above the flip, so the
+1 for being above it may point the wrong way. Kept as you designed it; the data will settle it.

### Stocks and sector ETFs (`shared/strategy.json`)

NVDA, AMD, AVGO, TSM → SMH · AAPL, MSFT, ORCL, PLTR → XLK · GOOGL, META → XLC · AMZN, TSLA → XLY ·
JPM → XLF · LLY → XLV. *ORCL, PLTR, LLY and TSM's matches are Claude's picks and were never confirmed by you.*

### Data used

SIP 5-minute bars (full market, about 16 min behind). IEX is live but only about 3% of volume, which
would break the volume rule. Raw prices, because walls are real strikes. The levels only see
expirations up to 60 days and strikes within 25%, because that's what the snapshots hold.

### Results so far

- **Replay** (same rules run later on 2026-10-27 → 11-06 with point-in-time inputs, kept apart from live):
  23 attempts, 4 predictions. One held at every check (LLY 10-29: −0.9% at the close, +2.2% next day,
  +1.8% after three days). LLY 10-30 held to the close, then fell below the wall. AAPL and JPM on 11-04
  fell below the wall the same day. Far too few to judge.
- **Live day 1 (2026-11-09):** AMZN broke its 270 wall at 9:35 and held, but volume was 1.48× (needs
  more than 1.5×); a second AMZN try at 10:35 fell back during the hold; PLTR broke 165 at 9:45 on 0.83×
  volume. No predictions.

---

## 10. Model 3: the political game machine (2028)

*Code and inputs `politics/`, running copy and data `~/MarketData/politics/`, job `collectors/politics_job.py`,
page `dashboard/static/politics.js`/`.css`, browser simulation `politics/game_engine.js`. Design
`politics/PLAN.md`, how-to `politics/HANDOFF.md`. Python standard library only, no extra packages.*

### The question it tests

**Can your model and news judgment add anything to what prediction markets already know?** It treats
the 2028 race as a turn-based game: candidates enter and exit, news changes the odds, and every turn
shows three numbers per candidate side by side: **raw model**, **market**, and **blend**.

### Turns and phases

A **turn** is one logged update: news, someone entering or leaving, or a result. Each saves a full
snapshot of all three sets of odds. The game moves through six **phases**: shadow primary (now),
declared field, early states, Super Tuesday and later, conventions, general election.

**News multipliers:** each news turn has a multiplier on the candidates it affects. 1.3 means "this news
is 1.3× more likely if this person ends up winning." Write it **before** looking at how markets moved,
so the judgment stays independent. Ordinary news is capped at 0.5× to 2×. Hard facts (a formal entry
or exit) change status instead. `--env` shifts the national mood. Six turns so far: five on 2026-11-05
(the baseline, your two Ossoff/Newsom rating turns, and two model upgrades) and one on 2026-11-10 (every
candidate's ratings re-set from research).

### The raw model (a Monte Carlo simulation)

Runs the race 20,000 times with a fixed seed (2028), so the same inputs always give the same answer.
**It never reads market prices.** One simulated race:

1. **Draw the national environment** (generic popular-vote margin): mean D+3, spread ±5 points.
   Reason: Democrats just won a wave midterm and Republicans would be seeking a third straight term,
   but waves fade.
2. **Each candidate decides whether to run** (their `p_run`). Some defer to a named rival.
3. **Primaries run state by state in five windows** (`primaries.json`). Regions favor some lanes,
   candidates get a home-state boost, winners gain momentum, weak candidates drop out between windows,
   and their support goes mostly (80%) to candidates in the same lane.
4. **The general election:** environment + each nominee's strength + noise sets the national margin.
   Every state then votes: its 2024 lean + that margin + regional noise + state noise + a home-state
   edge. 270 electoral votes wins (a 269–269 tie goes to Republicans: the House vote is too uncertain
   to model).

**Candidate ratings** (`ratings.json`, 37 named people plus a "field" for each party), per person:
`poll` (primary support), `adj` (what polls miss), `p_run`, `defers_to`, `general` (points added versus
a generic nominee), `lane` (shared voter base), `home` (home state). Since 2026-11-10 the first five are
set from research by fixed rules, not judgment (your call: "I don't want to be setting odds willy
nilly"). The rules, every input and its source are in `politics/ratings_evidence.md`:
- `poll`: average share among voters with a preference, national polls Oct 1 to Nov 5 2026.
- `p_run`: tiers from what they've said and done (ruled out 10%, talked about 25%, considering 50%,
  not ruled out plus concrete steps 65%, leaning toward it 80%, declared 97%), ±10 points for
  constraints or pulls.
- `adj`: 0.25 per evidence item (fresh win, money, party backing; minus a recent loss or name-only
  support), capped at 1.
- `general`: 0.1 per point they ran ahead of their state and year in their latest statewide race,
  capped at 2.
Betting prices aren't used as evidence.

**Main settings:** `STRENGTH_SD 1.0`, `STAGE_DRIFT 1.25` (lasting shocks between windows),
`CONTEST_NOISE 0.35`, `HOME_PRIMARY_EDGE 1.0`, `LANE_TRANSFER 0.8`, `GENERAL_NOISE 2.0`,
`STATE_NOISE 2.5`, `REGION_NOISE 1.5`, `HOME_STATE_EDGE 2.0`.

**Senate** (`senate.py`, all 35 seats up in 2028): each seat's margin = state lean + national
environment + incumbent edge + noise (6.5 points), with a quarter of the presidential matchup carrying
down the ballot. Every seat shares the same environment, so seats swing together, and joint odds like a
sweep come out naturally. Noise and incumbent edge were checked against real 2022 and 2024 races
(`calibrate.py`: real incumbents ran 3–5 points ahead).

**House** (`house.py`): not 435 districts, a straight line: about 6.5 seats per point of national vote,
Democrats need about D+1.5 for 218, and the House vote follows the top of the ticket halfway.

### The market layer

- **Venues:** Polymarket (read from this dashboard's database, plus fresh snapshots) and Kalshi (own
  hourly collector). Both list winner, both nominees and party markets. PredictIt is the first to add later.
- **One ID per person** (`candidates.json`, 115 people), because names differ even within one venue
  ("JD Vance" vs "J.D. Vance").
- **Cleaning:** midpoint of bid and ask, one snapshot an hour. If a market's prices add up to over 100%,
  scale down. Under 100%, **don't** scale up: keep the gap as "unlisted."
- **Thin markets:** most Polymarket state markets are nearly empty, so they're hidden unless spreads are
  tight (under 15 points). Kalshi rarely prices a party below about 8%, even in safe states.

### The blend

The only place raw and market meet (`blend.py`). Combined in log-odds, which behaves better than a plain
average near 0% and 100%:

`logit(blend) = 0.25 × logit(raw) + 0.75 × logit(market)`, then rescaled to 100%.

The weight stays at 25% raw until the scorecard shows the model deserves more.

### Fitted "worlds" (Play the game)

Markets price only a few things. The game needs far more (who wins Iowa, what if Vance stays out).
`worlds.py` builds Market and Weighted versions of the same game in three labelled layers: **Price**
(a live price as it stands), **Worked out** (follows from prices by probability rules alone), and
**Game** (candidates' numbers fitted until the game reproduces the prices to about a point, then the
game's rules fill in the rest). Nothing is invented where no market speaks. The fitted copies never
touch `ratings.json` or raw forecasts.

### The game theory layer (`game_theory.py`)

Only where players really react to each other. A quick formula, not the full simulation, so it's for
comparing choices, and its results only enter the model in explicit what-ifs.

1. **Entry.** Each candidate's payoff is their rough nomination chance minus a personal cost. The costs
   are solved so today's `p_run` values are already a resting point (an equilibrium), which adds no new
   opinions. The game then answers: when one player's decision changes, how do the others respond?
   (Responsiveness 8; a rival in your own lane counts 1.5×.)
2. **Consolidation (lane pressure).** Two candidates in one lane split its voters. Staying is better
   for each, unless their own chance falls below what an exit is worth (a VP slot or cabinet post,
   valued like a 5% chance of the nomination). That's a prisoner's-dilemma shape, and it shows which
   lanes are under pressure and who "should" drop out.
3. **VP pick.** Each likely nominee picks the running mate who helps the ticket most; swing-state
   politicians score higher.

### Scoring (three scores, because one election can't validate a model)

1. **Did the market move toward me?** Every gap of 3+ points between raw and market is logged and
   checked 7, 30 and 90 days later. Results within weeks. A proxy, not proof.
2. **Short-term questions** (e.g. "will X declare by June 30, 2027?") give real Brier scores within months.
3. **Final Brier scores** on nominees and the winner (November 2028).

Logs are append-only JSONL files with a hash chain; `forecasts.py verify` proves nothing was edited.
**Never edit them.** Logging stays manual on purpose (`run_all.py --log`), because the ratings are
mostly drafts and the logs are permanent.

### Current numbers (rebuild of 2026-11-10, 9:36 pm, after the researched ratings)

| Democrat wins the presidency | Raw | Polymarket | Kalshi | Market | Blend |
|---|---|---|---|---|---|
| | 71.0% | 67.5% | 65.5% | 66.5% | 67.7% |

| Win the presidency | Raw | Market | Blend |
|---|---|---|---|
| J.D. Vance | 15.5% | 14.7% | 16.5% |
| Kamala Harris | 15.5% | 3.3% | 5.4% |
| Pete Buttigieg | 13.3% | 2.6% | 4.5% |
| Gavin Newsom | 8.9% | 8.0% | 9.1% |
| Alexandria Ocasio-Cortez | 6.4% | 9.9% | 9.9% |
| Jon Ossoff | 1.3% | 17.5% | 10.6% |

| Nomination | Raw | Market | Blend |
|---|---|---|---|
| Harris (D) | 23.2% | 5.1% | 8.7% |
| Buttigieg (D) | 18.2% | 5.3% | 8.3% |
| Newsom (D) | 13.0% | 11.1% | 13.1% |
| Ocasio-Cortez (D) | 9.4% | 14.0% | 14.4% |
| Ossoff (D) | 1.8% | 25.8% | 16.2% |
| Vance (R) | 57.1% | 32.1% | 40.0% |
| DeSantis (R) | 11.3% | 16.2% | 15.7% |
| Rubio (R) | 8.6% | 17.8% | 15.8% |

Before the re-set (11-09), raw had Ossoff at 43% for the nomination and 33% for the presidency.

- **Senate (raw):** Democrats 98% to control, about 55.6 seats on average (state prices imply about 57;
  Kalshi and Polymarket have control at about 88%). It was 94% and 54.6 seats before Alaska and
  Mississippi were raised to 98% Democratic on 2026-11-10.
- **House (raw):** Democrats about 229.5 seats on average.
- **Whole ballot:** raw Democratic sweep 59% against Kalshi's 64.5%.
- **Tipping-point states:** Pennsylvania 26%, Michigan 16%, Georgia 15%, North Carolina 14%, Wisconsin 13%.
- **Markets' implied national mood:** about D+2.1, against the raw model's D+3.
- **Sensitivity:** one point of national mood moves the Democrats' presidency odds about 5.4–6.4 points.
  Ossoff's choice barely matters to raw now (under 1 point), because it gives him a 10% chance of running.
- **VP picks:** Harris → Whitmer, Kelly, Shapiro. Buttigieg → Warnock, Whitmer, Kelly. Vance → Youngkin,
  DeSantis, Kemp.
- **Biggest raw-vs-market gaps:** Ossoff for the Democratic nomination (2% vs 26%): raw goes by his
  repeated "I'm not running", markets don't. Vance for the Republican nomination (57% vs 32%).
  Harris (23% vs 5%) and Buttigieg (18% vs 5%): raw follows their poll leads and statements.
- **Venue check** (past year of daily prices): Polymarket and Kalshi differed by a point or more on
  5,618 candidate-days (2.0 points on average). Within a week Polymarket closed about 15% of the gap and
  Kalshi about 4%; about 81% was still there. So Kalshi leads slightly, but most gaps just persist.
- **Scorecard:** 509 forecasts and 111 gaps logged (all on 2026-11-05), 70 open questions, none resolved,
  tamper check ok. The first 7-day gap checks come due around 2026-11-12.

### What still needs you

1. **Review the researched ratings** (most important). On 2026-11-10 every candidate's numbers were
   re-set from research by fixed rules (`politics/ratings_evidence.md`); your Ossoff and Newsom numbers
   were dropped at your request. Still Claude's drafts: lanes, home states, the national mood, the
   model settings, and `edge` and `p_open` in `senate_seats.json`. Once you're happy, change the `status`
   line so it no longer starts with PROVISIONAL, and forecasts log as `raw`, not `raw-draft`.
2. **Facts to confirm:** Alaska and Mississippi Senate races (still uncalled; both Democrats lead the count,
   so set to 98% from Polymarket on 11-10; set to 1 or 0 when called); Senate and House totals
   are CBS projections, not certified; whether Bennet won Colorado's governorship; Tennessee's special
   election; 2024 state margins and `history_primaries.csv` are from memory. (Ramaswamy lost Ohio by
   about 5; Vance's chance of running is now set by the tier rule.)
3. **The old Kalshi job on the M4** still runs and nothing reads it. On the M4:
   `launchctl bootout gui/$UID/com.politicalgamemachine.kalshi`.

### Limits

- Raw is still a demo: the ratings are researched but unreviewed, and the national mood and model
  settings are judgment. Don't read its gaps as signals yet.
- Set by judgment, not fitted: contest noise, the national environment, all game-theory settings, all
  House settings. They strongly affect how confident the model is.
- The 2028 primary calendar isn't set; electoral votes stand in for delegates; regional lane effects are drafts.
- Prices don't fully agree: candidate win prices add to about 60% Democratic, Kalshi's eight-way market
  to 76%, the party market about 67%. The game follows the party market.
- Rebuilds take about 3.5 minutes. Gap checks are presidential only. Headlines are hints only (keyword labels).

---

## 11. Model 4: the stock direction model (S&P 500, weekly)

*Code `collectors/stock_direction.py`, tests `collectors/test_stock_direction.py`, plan (fixed before
any result) `docs/stock-direction/PLAN.md`, results `docs/stock-direction/README.md`.*

### What it does
Every Tuesday evening, for each S&P 100 stock (about 90 a week with enough options trading): the chance
it beats SPY, total return, from Wednesday's close to the next Wednesday's close. One probability each,
Brier-scored in the ledger against the base rate (49.5%, how often stocks beat SPY in 2024-25) and
against "last week's move only".

### Inputs (each from a published paper; weekly values from the 5 days Tuesday to Tuesday)
| Input | Points to "beats SPY" when | Source |
|---|---|---|
| Call-vs-put implied volatility gap | calls pricier | Cremers & Weinbaum (2010) |
| Crash protection (out-of-the-money put minus at-the-money call volatility) | protection cheap | Xing, Zhang & Zhao (2010) |
| Change in at-the-money call and put volatility over 4 weeks | calls up, puts down | An, Ang, Bali & Cakici (2014) |
| Last week's return minus its sector ETF's | it beat its sector | Medhat & Schmeling (2022) |

Implied volatility is computed here from Alpaca's daily option trade prices (no quotes): average traded
prices, dividends taken out, T-bill rate, binomial early-exercise premium for puts.

### Results (2026-11-11)
- 2024-25 building period (95 weeks): nothing beats the base rate, even fitted on the answer key.
- Tuning (16 variants incl. the owner's weekly mean/median mixes, learned on one year and scored on
  the other): only "last week reverses" beat the base rate in both years, by a hair. Every average
  beat the median, within noise.
- Sealed 2026 test (45 weeks, 4,092 predictions, run once): v1 equal weights fail (= base rate); v1
  learned weights a lean pass (gap −2.6 ± 2.8 Brier points × 10,000); v2 (reversal) fail.
- Inputs alone, 2024-25 / 2026: crash protection +0.021 / +0.032 (right way both times, not proven);
  gap and change wrong way both times; last week bounced back slightly both times.

### Fresh test on the other 400 S&P 500 stocks, and five more signals (2026-11-12)
- The 400 (`shared/sp500_ex100.json`; about 130 a week with enough options), fitted on their 2024-25,
  tested once on 2026 (5,951 predictions): crash protection alone **lean pass** (−2.7 ± 2.8 vs the base
  rate, −2.2 ± 3.1 vs last-week-only); its input score +0.028 / +0.035, right way again. v1 learned
  weights lean pass; v1 equal weights fail. Crash protection has now pointed the right way in all four
  looks: the best evidence in the project, still not proof.
- Survivorship check (2026-11-12): counting the 400 only after they joined the S&P 500 halves crash
  protection's 2024-25 score (+0.014) but leaves 2026 close (+0.028; still a lean pass). It slashes
  paper returns: equal amounts in all stocks then match the real equal-weight fund (RSP). The money is
  mostly in avoiding the priciest-protection fifth. S&P 100 return figures are too high (no past lists).
- Five more published signals, S&P 100 then the 400: option-to-stock volume, earnings week, realized
  minus implied volatility: nothing. Post-earnings drift: worked in 2024-25 (t 2.3 and 2.6), faded in
  2026. Lottery stocks: the reverse of the paper all four times (recent big jumpers kept winning).

### Live (from Tuesday 2026-11-17; `shared/stock_direction_live.json`)
- `1-learned`: v1 learned weights, live under the plan's lean-pass rule. Its edge mostly bets against
  the change signal, with no research reason, so probably luck.
- `3-skew`: crash protection alone, chosen after the 2026 results; only its live record counts.
- `3-skew@sp400`: crash protection alone on the 400 other S&P 500 stocks (~150 a week), live because
  it passed the pre-registered fresh test. Not live by judgment: drift (failed on the S&P 100) and
  the reversed lottery signal (runs against its research).


### Also tested: volatility-managed market (2026-11-12, failed; `docs/vol-managed/`)
Moreira & Muir (2017): hold more of the market after calm months, less after wild ones (amount =
c ÷ last month's variance, c from past data only, up to 1.5x or never borrowing). Plan fixed first
(`PLAN.md`), tested on 100 years of US data (French), 4 other markets, 49 industries and the S&P 500.
Failed all five pass rules: 1937-2026 9.3% a year vs 10.7% for buy-and-hold (Sharpe 0.47 vs 0.52);
2016-2026 9.3% vs 14.9%; worse Sharpe in all 4 other markets and 42 of 49 industries. It cuts crash
losses a lot (2008: −11% vs −50%) but misses the rebounds (Apr-Dec 2020: +5% vs +55%). The paper's
own result rests on 1926-1936; from 1937 even its look-ahead setup only ties the market. Not live.


### Also tested: nine classic strategies (2026-11-12; `docs/classic-strategies/`)
Plan fixed first. Long-only, after costs, judged mainly on the years after each paper, against
holding the market (French data, no survivorship bias). None beats the market. Near misses: industry
momentum (more money and better Sharpe since 1996, but 100-year t 2.99 against the 3 needed), small
value (more money since 1991 and in all 4 other markets, but rougher), stock momentum (strong before
1990, lost abroad since 2000). Edges shrank by a third to two-thirds after publication. The best
post-publication result has an 11% chance of being real (deflated Sharpe). **10-month trend** (hold the
market only above its 10-month average) passed "safer, not better": since 2006, 9.7% a year vs 11.3%,
worst drop −18% vs −50%. Not live.


### Also tested: risk budget model (2026-11-12, failed; `docs/risk-budget/`)
Pick a risk level (5-20% a year); stocks and 10-year Treasuries weighted by equal risk (Asness,
Frazzini & Pedersen), each dropped in a downtrend (10-month rule), scaled to the level, up to 2x. Bond
returns computed from FRED DGS10 yields (`rates_daily`). 1965-2026 after costs, it lost to plain SPY +
T-bills at the same risk at every level (15%: Sharpe 0.35 vs 0.46, $1.40M vs $2.73M from $10k), and
in both rising-rate stretches. It made money in 2000-02 and 2008. Cause: since 2011, Treasuries earned
about nothing above T-bills (Sharpe 0.03). Not live.


### Also tested: pairs trading (2026-11-12, failed; `docs/pairs/`)
Gatev, Goetzmann & Rouwenhorst's distance method: each month the 20 closest same-sector pairs over 12
months, traded 6 months, open at 2 standard deviations, close when prices cross. S&P 500 members at
the time (Wikipedia edit history, `shared/sp500_history.json`), Alpaca adjusted prices. 2017-2026:
−0.5% a year beyond T-bills after costs, +0.2% before; only 42% of trades converged. Not live.

### Also tested: macro timing (2026-11-12, failed; `docs/macro-timing/`)
14 economic indicators (Goyal & Welch data), predictions averaged (Rapach, Strauss & Zhou), floored at
zero, stocks held 0-1.5x by the prediction. Worked 1947-2005 (14.1% a year vs 11.9%, accuracy
p = 0.001); failed 2006-2025 (8.7% vs 11.1%, worse than the plain average; −67% in 2008). Not live.


### The tournament (2026-11-12; `docs/tournament/`)
Nine more strategies (leveraged trend, dual momentum, four-factor mix, two trend-filtered near misses,
CBOE put-selling, covered calls, protective puts, collar), then all 24 strategies on 2006-01 to 2025-09
against SPY (10.9% a year, Sharpe 0.65, worst drop −51%). By the pre-set rules **none beats SPY**.
Best risk-adjusted: **10-month trend** (10.0% a year, Sharpe 0.79, worst drop −18%; its Sharpe edge
within noise, its crash cuts consistent). Most money: **leveraged trend** (2x above the 200-day average:
12.9% a year, $109k vs $77k; 98-year Sharpe edge beyond noise; failed since 2016 on Sharpe). CBOE
index history and `SP500TR` are in `index_daily`. Not live.
Confirmation test (`CONFIRM_PLAN.md`): leveraged trend **confirmed** by its pre-set rules. 3 of 4 fresh markets
(Japan −86%), the real SSO fund 2007-2026 $90.7k vs SPY $72.8k (Sharpe 0.55 vs 0.64), ahead in 79 of 89
10-year stretches since 1928.


### Also tested: trend across many markets (2026-11-13, failed; `docs/multi-trend/`)
Faber's 10-month rule on five real funds (SPY, EFA, IEF, VNQ, DBC; `<SYM>_ADJ` in `index_daily`), long-only
and long/short (Moskowitz, Ooi & Pedersen), 2007-2026. Long-only: 4.8% a year, worst drop −12%. Long/short:
+52% in 2008, +3% in 2022, −30% in 2018 and 2020 (t 1.6). Half SPY, half long/short: Sharpe 0.656 vs SPY's
0.653 over the whole stretch, 0.68 vs 0.92 since 2013. Plain 60/40 had the best Sharpe (0.72). Not live.


### Also tested: overnight-only investing (2026-11-13, failed; `docs/overnight/`)
Hold SPY close to next open, cash by day. Before costs 94% of SPY's 1993-2026 gain came overnight, but at
0.01% per trade (two a day) it made 4.6% a year vs 10.8%. Since 2009 even free trading loses (8.7% vs
14.7%): daytime hours earn again. QQQ and IWM fail too. Data: `<SYM>_RAW` in `index_daily`, Yahoo dividends. Not live.

---

### Also tested: earnings-week premium (2026-11-13, failed; `docs/earnings-premium/`)
Hold each S&P 500 stock only on the 3 days around its earnings announcement (Savor & Wilson; Barber et al.),
2016-2026. No premium: −0.02% a day vs the same stocks on other days (t −0.4), negative since 2021. Holding
only the ~19 stocks with news each day: 34% volatility, $10k → $5.2k after costs vs SPY $44.7k. Only hint:
the 5-day run-up before announcements (+0.035% a day, t 2.5), below the t ≥ 3 bar and under trading costs. Not live.

### Also tested: Fed-day drift and Fed cycle (2026-11-13, failed; `docs/fed-drift/`)
Lucca & Moench's pre-Fed drift: +0.46% on decision days 2002-2011, +0.10% since 2012 (t 0.5, no better than other
days). Cieslak et al.'s even-weeks cycle beat SPY 2002-2016, then made 5.5% a year vs 15.0% since 2017. Still alive
on 2 pm-to-2 pm intraday windows: +0.20% per meeting 2016-2026 (t 2.9; information only, a live paper record would
need the owner's OK). **Found and fixed** (owner's OK, 2026-11-13): the Fed parser in `spx_move.py` skipped 5 meetings written
"April/May 30-1" (2013-2019) and kept a no-decision 2003-09-15 meeting; it now reads both forms and keeps only
meetings with a statement. `econ_calendar` reloaded; the S&P move model learns from the corrected days. Not live.

### Also tested: constant leverage (2026-11-13, 2x fails the safety rules; `docs/constant-leverage/`)
Always 2x the US market, 1927-2026: 12.4% a year vs 10.2% (best fixed level in hindsight; above it, less money), but
−98.7% in 1929-32 and ahead in only 72% of 20-year stretches (rule: 80%). Model matches real SSO (16.0% vs 15.5% a
year). Monthly savers (Ayres & Nalebuff) at 2x beat 1x in all 60 forty-year cohorts. The 200-day rule (leveraged
trend) cut 2x's worst drop to −56%. Real UPRO 3x 2009-2026: 32% a year, −63% drop. Not live.

### Live paper record (from 2026-11-13; `docs/paper-record/`)
Nothing traded. Three rules, version 1, fixed in `docs/paper-record/PLAN.md`: **leveraged trend** (SSO while SPY > its
200-day average, else T-bills, traded at the next close), **10-month trend** (SPY while above its 10-month-end average,
checked each month-end), **pre-Fed drift** (SPY from 2 pm the day before each Fed decision to 2 pm on it). Positions
are logged before they take effect and hash-chained; marks next to SPY. No verdict before 3 years (trend rules) or 30
meetings (Fed). First positions: SSO and SPY from the 2026-11-13 close; first Fed window 2026-12-08/09.

## 12. Alerts and the morning update

Both go to your iPhone through **ntfy** (free, no account, no access to email or Apple ID). The channel
name is the only secret, so alerts carry no personal details. Email was considered and dropped: you
didn't want an app password on your account.

**Watchdog** (`collectors/watchdog.py`, every 30 min, read-only) alerts on: a failed, partial or stopped
run; a run stuck over 2 hours; a snapshot or events run with under half its usual rows; a run missing
20 min past its schedule (schedules are read from the launchd plists, so new jobs need no watchdog
change, but a job must record itself in `runs`); missing open interest after 09:30; the dashboard down;
under 10 GB free; the core backup over 30 hours old. One-off problems are sent once; ongoing ones when
they start, once a day while they last, and "resolved" when they clear. If the Mac is asleep nothing can
alert; the next check reports the missed runs.

**Morning update** (`collectors/briefing.py`, 10:00 daily, plain rules, no AI). Contents chosen by you:
- **Headline:** the 2–3 moves biggest relative to their own normal (average of the last 20 daily
  moves), e.g. "Brent −7.5% (6x)". Nothing at 1.5× or more → "Quiet morning".
- **Markets:** SPY; the Mag 7 average, best and worst, plus any name moving 2.5× its normal; S&P futures
  overnight (4 pm to 9:30 am); WTI and Brent; the 10-year (in basis points); the VIX (in points).
- **New option bets:** the 3 biggest overnight open-interest increases across the watchlist.
- **Events:** the 3 biggest 24-hour Polymarket moves (liquid markets only, none resolving within
  48 hours, no sports).
- **System line:** at the bottom, or at the top if something's wrong. Weekends and holidays: system and
  events only. No SPY options section and no spreads (your choice).

---

## 13. Rules and decisions that stand

**Safety and privacy**
- Never print the Alpaca keys or the ntfy channel name, or put them in this folder.
- No trades, no bets, no personalized financial advice. This is research.
- No email alerts (you declined).
- BLS blocks scripts: refresh its dates in a browser, never by faking a browser user agent.

**Data integrity**
- Collectors are the only writers; the server is read-only.
- Decisions read the official views; backups only fill gaps and are flagged.
- Backtests respect when data was really available (GEX after the close, CFTC from `available_date`).
- Never edit live ledger rows or the political machine's hash-chained logs.
- Every prediction model logs through the ledger, next to a simple baseline, live and backtest apart.

**Models**
- The gamma rules in `scoring.py` were agreed with you; don't change them unasked.
- S&P model v1 is fixed; changes are a v2, only with your OK.
- The political raw model never reads market prices. The blend weight stays 25% until the scorecard
  supports a change. Logging forecasts stays manual.

**Working style (your preferences)**
- Plain English, strategy level, no assumed jargon. Short answers to questions.
- Ask before big or structural changes (including multi-file UI changes); do things in a deliberate order.
- Don't move or reorganize files unasked. Deleted files go to the Trash.
- Test for real (browser, background jobs) and report honestly.
- Keep the World Monitor look and stable `data-panel` ids.

**Ruled out**
ThetaData; Goldman prime-brokerage data (private, can't be collected); building inside World Monitor;
FRED (website blocks scripts, API needs a key); machine learning for the S&P model until there's far
more data; short-interest data (no free daily source).

---

## 14. Open items and what's next

- **Cboe's VIX timing:** on 2026-11-09 Cboe posted the day's VIX at 9:29 pm, after the last evening
  run (8:50 pm), so the first live prediction used Yahoo's VIX (flagged in its inputs; it matched Cboe's
  exactly). If that's normal, most predictions will. Cboe's figure replaces Yahoo's in `index_daily` on
  the next run (confirmed: the 8:05 am run on 11-10 swapped it in); the prediction keeps the value it
  used. A run at about 9:45 pm would let Cboe's be used.
- **Politics-to-sectors tracker: set aside** (your call, 2026-11-10). 2028 is far off and prices aren't
  reacting to it much yet. Elections do move sectors, so it's worth coming back to closer to 2028.
- **Implied volatility history:** done for the 100 S&P 100 stocks (`direction_iv_daily`, 2026-11-11); not yet for the watchlist ETFs. Use raw prices against strikes, but `stock_bars_split_adj` for the stock's own volatility.
- **Stock direction model:** watch the three live versions on the Scorecard (verdicts after a few weeks; a small real edge would take a year). Unbuilt ideas: crash protection held a month instead of a week, option-implied borrowing cost. BNY's options before its 2025 ticker change are missing.
- **News ↔ markets (next step of the News build, agreed 2026-11-10):** each story with the moves in
  stocks, oil, VIX and related Polymarket odds in the hour after it, and each big move with the
  headlines from the hour before. Shows what moved together, not cause and effect.
- **News tuning after a week of data:** measure size per day; some big stories still split in two
  (word-overlap threshold 50%); review dead feeds in the Sources panel.
- **More tabs:** broader breadth, IPOs.
- **S&P model v2** ideas (section 8), each needing your OK.
- **Political machine:** your ratings, the facts to confirm, the M4 job (section 10).
- **Gamma tracker:** confirm the four sector matches; let the live test run for weeks before judging.
- **Storage levers** if needed (section 6.4).
- **Git:** since 2026-11-10 the code is a git repo in `~/Code/market-dashboard` (data, logs, keys and backups excluded).
- **One-home proposal** (`politics/ENVIRONMENT.md`, not acted on): keep the M1 Pro always on, add an
  external SSD for data, Tailscale so the M4 and phone can reach it, code in GitHub, iCloud for documents only.

---

## 15. Commands

Use `~/MarketData/.venv/bin/python` as Python.

| Do this | Command |
|---|---|
| Open the dashboard | http://127.0.0.1:8765 |
| Status of every job | `~/MarketData/.venv/bin/python ~/MarketData/app/options_collector.py status` (or the Status tab) |
| Apply edits to collectors, `shared/*.json` or `politics/` | `collectors/install.sh` |
| Restart the server after editing `server.py` or `ledger.py` | `launchctl kickstart -k gui/$UID/com.marketdashboard.options.dashboard` |
| Stop all jobs | `collectors/install.sh uninstall` |
| Test phone alert / see problems without sending | `.../app/watchdog.py test` / `.../app/watchdog.py dry` |
| Preview the morning update | `.../app/briefing.py dry` (`FORCE=1` for the trading-day version after hours) |
| S&P model: run / backtest / compare methods | `spx_move.py` / `spx_move.py backtest` / `spx_move.py research` (from `collectors/`) |
| Gamma tracker replay of past days | `strategy_collector.py replay` |
| Stock direction model (from `collectors/`) | `stock_direction.py live --dry-run 2026-11-10` (what it would predict, logs nothing) / `explore` / `tune` / `signals` / `iv SYMBOL` / `earnings SYMBOL`; add `--universe sp400` (before the command) for the other 400 |
| Volatility-managed test (from `collectors/`) | `vol_managed.py data` (download French's files) / `vol_managed.py backtest` |
| Nine classic strategies (from `collectors/`) | `classic_strategies.py data` / `classic_strategies.py backtest` (needs `vol_managed.py data` first) |
| Risk budget test (from `collectors/`) | `risk_budget.py data` / `bondcheck` / `backtest` (needs `vol_managed.py data` first) |
| Pairs / macro tests (from `collectors/`) | `pairs_model.py members` / `prices` / `backtest`; `macro_timing.py data` / `backtest` |
| Tournament (from `collectors/`) | `tournament.py data` / `tournament.py backtest` |
| Multi-market trend (from `collectors/`) | `multi_trend.py data` / `multi_trend.py backtest` |
| Overnight test (from `collectors/`) | `overnight.py data` / `overnight.py backtest` |
| Earnings-week test (from `collectors/`) | `earnings_premium.py backtest` |
| Fed-drift test (from `collectors/`) | `fed_drift.py backtest` |
| Leverage test (from `collectors/`) | `constant_leverage.py data` / `constant_leverage.py backtest` |
| Paper record (from `~/MarketData/app/`) | `paper_record.py status` / `paper_record.py verify` |
| Collector tests | `cd collectors && ~/MarketData/.venv/bin/python -m unittest test_spx_move test_ledger test_scoring test_strategy_collector test_stock_direction test_paper_record` |
| Political machine (from `~/MarketData/politics`) | `run_all.py` (rebuild), `run_all.py --log` (log forecasts), `turns.py add --headline "..." --multiplier id=1.2`, `turns.py list`, `forecasts.py questions`, `forecasts.py verify`, `calibrate.py`, `python -m unittest` |
| Restore from backup | `restore_backup.py ~/MarketData/options.db`, then `install.sh`, then `backfill_alpaca.py` |
| News: read every source now / reload shipping history | `.../app/news_collector.py all` / `.../app/shipping_collector.py backfill` |
| Search stored headlines | `sqlite3 ~/MarketData/options.db "SELECT i.published_at, i.source, i.title FROM news_fts f JOIN news_items i ON i.id=f.rowid WHERE news_fts MATCH 'hormuz' ORDER BY i.published_at DESC LIMIT 20"` |

---

## 16. Glossary (plain English)

| Term | Meaning |
|---|---|
| **Open interest (OI)** | How many option contracts are open at a strike. Changes once a day, overnight |
| **Call wall / put wall** | The strike with the most call (or put) open interest in the next 30 days. Thought to act like a ceiling or floor because of dealer hedging |
| **Dealer gamma / gamma flip** | How much dealers must buy or sell as the price moves. When dealers are "short gamma," their hedging adds to moves; when "long gamma," it dampens them. The flip is the price where one turns into the other |
| **GEX / DIX** | SqueezeMetrics' daily S&P 500 dealer gamma (in dollars) and dark-pool buying index |
| **IV (implied volatility)** | The move size an option's price implies |
| **Greeks** | An option's sensitivities: delta (to price), gamma (delta's change), theta (to time), vega (to IV) |
| **VIX / VIX9D / VIX3M** | The S&P 500's implied volatility over the next 30 days / 9 days / 3 months |
| **Variance risk premium** | Options usually price bigger moves than happen: buyers pay for insurance |
| **Realized variance** | How much the market actually moved, measured from the day's range and opening gap |
| **HAR model** | A regression that predicts volatility from yesterday's, last week's and last month's |
| **GARCH** | A classic model of volatility built from past returns only |
| **Quantiles / 90% range** | Points that the outcome should fall below 5%, 25%, 50%, 75%, 95% of the time. 5%–95% is the 90% range |
| **Pinball (quantile) loss** | Scores a range: punishes both misses and needless width. Lower is better |
| **Coverage / calibration** | Whether 90% ranges really catch 90% (or 70% chances happen 70% of the time) |
| **Brier score** | Scores a probability: squared gap between the chance and what happened. Lower is better; 0.25 = always saying 50% |
| **Baseline** | A simple guess made at the same moment, so a model has something to beat |
| **Walk-forward backtest** | Each past day predicted using only the days before it, refit as it goes |
| **Newey-West error bar** | An error bar that allows for streaks of related days, so a stormy week isn't counted as many independent wins |
| **Hash chain** | Each record stores a fingerprint of the one before; editing any past record breaks the chain |
| **Log-odds blend** | Averaging chances on a scale that stretches near 0% and 100%, so a 1% vs 5% difference counts properly |
| **Monte Carlo** | Running a random simulation many times (here 20,000) and counting outcomes |
| **Lane** | A group of candidates who share a voter base; when one drops out, lane-mates gain most |
| **Equilibrium (entry game)** | A situation where no one wants to change their decision given what the others are doing |
| **Prisoner's dilemma** | Each player does better staying in, but together they'd do better if one stepped aside |
| **Tipping-point state** | The state that delivers the 270th electoral vote |
| **SIP / IEX** | Full-market stock data (all exchanges) vs one exchange's data |
| **OPRA** | The official US options price feed (not available on Alpaca's free plan) |
| **launchd** | The Mac's built-in scheduler that runs the background jobs |
