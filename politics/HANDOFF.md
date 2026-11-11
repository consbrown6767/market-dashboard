# Handoff: Political Game Machine

Last updated 2026-11-05. `PLAN.md` has the original design. This file covers how to use what's
built and what needs you. Research only: nothing here places bets.

## Where it lives now (since 2026-11-06)
This is the Politics tab of Market Dashboard, at http://127.0.0.1:8765/#politics.

- **Code and inputs** (`ratings.json`, `senate_seats.json` and so on): this `politics/` folder.
- **Where it runs:** `~/MarketData/politics`, a copy next to its data, because background jobs and
  iCloud don't mix well. `collectors/install.sh` refreshes the copy and never touches the data.
- **Data:** `~/MarketData/politics/data` (logs, snapshots) and `~/MarketData/politics/kalshi`.
- **Page:** `dashboard/static/politics.js` and `politics.css`. The simulation is `game_engine.js` here.
- **Rebuilds:** `collectors/politics_job.py` runs hourly at :25, and also pulls past prices at 2:25 am.
  Its results show on the Status tab, and the watchdog alerts if it fails.
- **Backups:** nightly into `backups/politics-data.tar.gz`.

The original copy in `box of scraps/political-game-machine` was left untouched. It no longer updates.

| Section | What's there |
|---|---|
| Overview | Headline odds, odds by turn, the turn log, where we are in the cycle, market moves, headlines |
| Play the game | Pick Raw, Market or Weighted odds. Set anyone in or out, move the national mood, see odds change live, and copy the matching log command. Season mode plays one made-up cycle turn by turn |
| President | Odds by candidate, win if nominated, odds at each stage, matchups, Electoral College map, announcements |
| Senate and House | Senate map, seat counts, competitive seats, all eight outcomes vs Kalshi |
| Strategy | What-if exits, entry reactions, lane pressure, VP picks |
| Ratings | Every candidate's inputs in one place |
| Scorecard | Forecast log, gap checks, Brier scores, how it works |

## Everyday commands
Run these from `~/MarketData/politics`, with `~/MarketData/.venv/bin/python` in place of `python3`.
After editing anything in `politics/`, run `collectors/install.sh`: the next hourly rebuild picks it up.

| Job | Command |
|---|---|
| Rebuild now | `python3 run_all.py` |
| Rebuild and log today's forecasts (deliberately not automatic) | `python3 run_all.py --log` |
| Log news (set the multiplier before checking markets) | `python3 turns.py add --headline "..." --source URL --multiplier jon-ossoff=1.2` |
| Log someone entering or leaving | `python3 turns.py add --headline "..." --status kamala-harris=out` |
| Shift the national mood | `python3 turns.py add --headline "..." --env 0.5` |
| List the turns so far | `python3 turns.py list` |
| List open questions | `python3 forecasts.py questions` |
| Resolve a question | `python3 forecasts.py resolve "senate-2026/AK-dem" no "Sullivan held the seat"` |
| Check that logs weren't edited | `python3 forecasts.py verify` |
| Compare settings with real elections | `python3 calibrate.py` |
| Run all tests | `python3 -m unittest` |

Valid candidate IDs are in `ratings.json`. `read_polymarket.py` reads the dashboard's database
read-only. `snapshot_polymarket.py` gets fresh prices straight from Polymarket.

## What's built

| File | Job |
|---|---|
| `model.py`, `states.json`, `primaries.json` | Presidential simulation: 37 named candidates plus "Other," a state-by-state primary calendar, every state in November |
| `senate.py`, `senate_seats.json` | All 35 Senate races, in the same simulated worlds |
| `house.py` | A simple seats-per-point House model |
| `game_engine.js` | The same simulation in the browser, plus Season mode. Tests check it against Python |
| `game_theory.py` | Entry reactions, lane pressure, VP picks |
| `turns.py` | The game log: news, entries, exits |
| `blend.py` | The one place raw and market odds meet |
| `worlds.py` | Fits the game to prices, so Market and Weighted are the same game as Raw with different numbers |
| `forecasts.py` | Tamper-evident forecast log and scorecard |
| `calibrate.py`, `history_*.csv` | Checks settings against real elections |
| `backfill_history.py`, `venue_check.py` | Past prices on both venues, and which venue moves when they disagree |
| `run_all.py` | Pipeline. Writes `outputs/data.json` for the Politics tab |
| `collect_kalshi.py`, `snapshot_polymarket.py`, `snapshot_senate.py`, `news_scan.py`, `clean_markets.py` | Market data and headlines |

`ENVIRONMENT.md` is the proposal for running all your projects from one home, written before this moved here.

## What needs you

### 1. Review the researched ratings (most important)
On 2026-11-10 you asked for your Ossoff view to be dropped and for every candidate to be set from
research, not judgment. Claude re-set `poll`, `p_run`, `adj`, `general` and `defers_to` for all 37
people by fixed rules; the rules, each input and its source are in `ratings_evidence.md` (the old
drafts and your Ossoff and Newsom numbers are gone). Betting prices weren't used as evidence. Still
Claude's drafts: `lane`, `home`, the national mood, the model settings, and `edge` and `p_open` in
`senate_seats.json`. Once you're happy with the ratings, change the `status` line in `ratings.json`
so it no longer starts with PROVISIONAL. After that, forecasts log as `raw`, not `raw-draft`. To
update a rating, change its evidence and re-apply the rule, not the number on its own.

### 2. Facts to confirm
- **Uncalled races:** Alaska and Mississippi are still uncalled. On 2026-11-10 both Democrats led the
  count and Polymarket had them at about 98.6%, so `uncalled_2026` in `senate_seats.json` went from
  0.45/0.5 to 0.98 each (the forecast log keeps the Nov 5 numbers). When they're called, set `p_dem`
  to 1 or 0 and resolve the two `senate-2026/...` questions.
- **Senate and House totals:** these are CBS election-night projections, not certified. The House
  model isn't tied to the actual 2026 seat count.
- **Bennet:** did he win the Colorado governorship? If so, his seat changes hands.
- **Tennessee:** Wikipedia lists a special election for Blackburn's seat. Confirm it.
- **Kalshi coverage:** Kalshi has no 2028 market for Kentucky or Tennessee, so those two races show no Kalshi price. The snapshot's 404s for them are expected.
- **Vance running:** now 75% by the tier rule (hasn't ruled it out and has taken steps, plus 10 points as sitting VP), down from Claude's earlier 93% draft.
- **Governor results:** Ramaswamy lost Ohio to Amy Acton by about 5 points (87% counted). Now in `ratings_evidence.md`.
- **Partly counted 2026 margins:** Moore's, Pritzker's and Ramaswamy's came from partial counts. The first post-midterm primary polls should replace the `poll` column.
- **2024 margins** in `states.json` and `senate_seats.json` are from memory and approximate.
- **`history_primaries.csv`** is from memory, and some "early leader" calls are debatable.

### 3. The old Kalshi job on the M4
The hourly job now runs on this Mac (the M1 Pro), inside the politics job. The M4's copy
(`com.politicalgamemachine.kalshi`) still runs there and nothing reads it any more. To remove it,
run this on the M4: `launchctl bootout gui/$UID/com.politicalgamemachine.kalshi`

### 4. Decisions
- **Git:** the project still isn't a git repository. The hash chain covers tamper checks without it.
- **Blend weight:** it stays at 25% raw until the scorecard supports changing it.

## Limits to keep in mind
- **Raw is a demo until the ratings are yours.** Don't read its gaps from the market as signals yet.
- **Checked against real data:** Senate noise and incumbent edge (`calibrate.py`). `STRENGTH_SD` and
  `STAGE_DRIFT` were chosen by sweeping values against a rough base rate from memory. The browser
  simulation is tested against Python. Season mode's odds are also tested for fairness over 1,500 seasons.
- **Set by judgment, not fitted:** `CONTEST_NOISE`, the national environment, all
  game-theory settings, and every House setting. They have a big effect on how confident the model is.
- **The primary calendar is a stand-in.** The 2028 order isn't set, electoral votes stand in for
  delegates, and the regional lane effects in `primaries.json` are Claude's drafts.
- **Game theory uses a quick formula** and is meant for comparing choices.
- **News multipliers are approximate.** They shift strength, so odds move roughly, not exactly, that much.
- **Long-dated market prices are distorted.** Kalshi rarely prices a party below about 8%, even in
  safe states. Most Polymarket state markets are nearly empty, so they're hidden unless spreads are tight.
- **Market and Weighted odds in the game are fitted, not quoted.** They reproduce prices to about a
  point. Scenarios no market prices are filled by the game's own rules and labeled "Game," so they
  inherit its stand-in calendar and lanes. Seven people have no announce price and keep their raw
  chance of running. Senate and House each get one fitted shift, so single seats aren't matched to prices.
- **Prices don't fully agree with each other.** Candidate win prices add up to about 60% Democratic,
  Kalshi's eight-way market to 76%, and the party market says about 67%. The game follows the party
  market and scales candidate win prices to it, so those differ a little from the President tab.
- **Rebuilds are slower.** `run_all.py` takes about 3.5 minutes on the M1 Pro, mostly fitting.
- **Gap checks are presidential only.** Senate gaps aren't logged yet.
- **Headlines are hints only.** The kind labels come from simple keyword matching and can be wrong.
