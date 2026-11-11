# Plan: Political Game Machine (v1: 2028 presidential race)

Status: all six build steps have a first version, running on draft ratings. See `HANDOFF.md`.
Written 2026-11-04.

## Goal
A local research dashboard that treats the 2028 presidential race as a turn-based game.
Candidates enter and exit, news changes the odds, and every turn shows three numbers per
candidate: **raw model**, **market**, and **blended**.

The question it tests: **can my model and news judgment add anything to what prediction
markets already know?**

Like the gamma tracker, this is **not** a trading bot. It makes forecasts forward, logs
them, and checks them later. It places no bets.

## What the live data check found
I queried the public Polymarket and Kalshi APIs on 2026-11-04. No API key was needed.

| Finding | What it means for the build |
|---|---|
| Both venues list the winner, Democratic nominee, Republican nominee and party markets | All four views can be built from day one |
| The main markets show large volume and tight spreads (about 1 point or less at the top) | Good enough to blend with |
| Polymarket's state markets show only about $4k-7k of volume | Display them, but don't blend them |
| Polymarket's API has daily price history (234 points for the top candidate, back to Feb 2026) | Useful for long charts, but prices only, not bid/ask. Kalshi offers hourly bid/ask history too |
| Candidate prices don't sum to 100%: Polymarket about 77-98%, Kalshi 102-109% | Filtering isn't the cause: every active market is included, and no Kalshi candidate at 1% or more is missing from Polymarket's Republican list. Likely a mix of unlisted people and money tied up until 2028, but that's unproven. See the market layer for how it's handled |
| Names differ: "JD Vance" and "J.D. Vance" within Polymarket's own events | My test silently lost him. A candidate ID table is required |

### Implied chance of winning if nominated (win price / nominee price, uncleaned)

| Candidate | Polymarket | Kalshi |
|---|---|---|
| Ossoff | 68% | 81% |
| Ocasio-Cortez | 88% | 78% |
| Newsom | 56% | 74% |
| Vance | 49% | 49% |
| Rubio | 45% | 53% |
| DeSantis | 38% | 38% |

For reference, the party markets put Democrats at about 65-68%. The venues disagree by up
to 18 points on the same question. Some of that is noise from dividing small prices, but
this table is useful on its own, and it comes from step 1 alone.

## Data sources

### Polymarket: read from Market Dashboard
Market Dashboard already archives Polymarket hourly, so this project doesn't need its own
Polymarket collector. Checked 2026-11-04 from temporary copies of its backups:

- **Coverage:** the winner, both nominee and party events (154 markets), plus VP nominees,
  "who will announce," and House and Senate control.
- **History:** hourly from 2026-10-26, with bid and ask. The top market had 223 snapshots
  and no gap over 2 hours. Hourly is enough here, since turns are driven by news.
- **Missing bids:** only on long shots priced at 0.1% or less, so use their plain price.
- **State markets come and go:** the collector's liquidity filter drops thin ones. They're
  display-only anyway.

**Hands-off rule: this project never changes anything in Market Dashboard.** No edits, no
new tables, tabs or jobs, and none of its scripts are run. It only reads:

- **Live database (M1 Pro):** `~/MarketData/options.db` lives on the M1 Pro. Open it
  read-only (`mode=ro`), the same way the dashboard's own server does.
- **Backups (M4):** the `backups/` folder syncs through iCloud, up to a day behind. Unpack
  copies outside that folder and read those. Good enough for building and testing.

Only the 2028 rows are saved, and never anywhere inside Market Dashboard or `~/MarketData`.

### Kalshi: our own collector
Market Dashboard has no Kalshi data. A small collector in this project saves hourly
snapshots, so its timing lines up with Polymarket's.

### Development data (on the M4 for now)
`python3 read_polymarket.py` rebuilds `data/dev/` from the latest backups. The first pull
(2026-11-04) has 27 events, 353 markets and 59,665 hourly snapshots in 21 MB, covering
Oct 26 to Nov 4. It grows by roughly 2 MB a day. State races appear as only 2 markets each,
because the archive's liquidity filter drops the thin outcomes.

Kalshi snapshots go to `~/PoliticalGameData/kalshi/`, 137 markets per snapshot, about 1 MB
a day. The hourly job has been running on the M4 since 2026-11-04 (installed with
`install_kalshi.sh`). Hours are skipped while the laptop is asleep, and it takes one
catch-up snapshot on waking. The first three snapshots are test runs minutes apart.

### Two-Mac setup (later, once the code works)
- **M4:** write and test the code here, using the backups and exported data.
- **M1 Pro:** runs the hourly jobs, writing to its own `~/PoliticalGameData/` folder. That
  folder is outside iCloud, for the same reason Market Dashboard keeps its database
  outside iCloud: background jobs and sync don't mix well.
- **Getting data to the M4:** an hourly export copies the small 2028 files into this
  project's `data/markets/`, so the M4 can see them through iCloud.
- **One writer per file:** two Macs writing to the same synced file can create conflict
  copies. Market files are written only on the M1 Pro.

## Core design

### Turns and phases
A **turn** is one logged update: a news event, a candidate entering or leaving, or a
scheduled result. Each turn saves a full snapshot of all three sets of odds.

**Phases** are the stages of the game. The turn moves the race forward within them:

1. Shadow primary (now until candidates declare)
2. Declared field
3. Early states
4. Super Tuesday and the rest of the primaries
5. Conventions and VP picks
6. General election

The 2028 primary calendar isn't final, so dates live in a config file.

### Raw model
A Monte Carlo simulation: run the race 20,000 times with a saved random seed and count
outcomes. The same inputs always give the same answer, which keeps it testable.

- **Candidates:** each has a status (`potential`, `running`, `out`, `nominee`), a strength
  rating, and an uncertainty on that rating.
- **Primaries:** candidates win states based on strength plus noise. Winners gain momentum,
  losers drop out, and their support moves to similar candidates.
- **General election:** nominee strength plus one national environment number with
  uncertainty. No 50-state map in v1.
- **Independence rule:** the raw model never reads market prices. Otherwise the comparison
  is meaningless.

### News updates
Each update is logged with its date, source link, candidates affected, reason, and a
**multiplier** on their odds. For example, 1.3x means "this news is 1.3 times more likely
if this candidate is the eventual winner."

- Write the multiplier **before** looking at how the market moved. That keeps the judgment
  independent.
- Ordinary news is capped between 0.5x and 2x, so one headline can't swing everything.
- Hard facts such as a formal entry or withdrawal change the candidate's status instead.

### Market layer
Built in `clean_markets.py`, with `candidates.json` as the ID table (115 people). Run
`python3 clean_markets.py` for a report.

Use the midpoint of bid and ask, not the last trade, and one snapshot per hour.

- **Over 100%:** scale down, since real probabilities can't exceed 100%.
- **Under 100%:** don't scale up. Keep the gap as "unlisted." Scaling up would have added
  up to 30% to every named candidate's odds, for a gap nobody can explain yet.

Two consistency checks run on the latest data:

- The implied win-if-nominated table above.
- Candidate win odds summed by party, compared with the party market. On 2026-11-04, both
  venues had Republican candidates adding up to about 4 points more than the party market.

Averaging the two venues comes with blending in step 5.

**Watch out:** Polymarket's Republican market moved sharply around the midterms. DeSantis
went from about 4% to 11-14% in a day, and the market's total rose with it. Comparisons from
that period are noisy, and venue timing matters.

### Blending
Combine raw and market odds in log-odds, which behaves better than plain averaging near 0%
and 100%, then rescale to 100%:

`logit(blend) = w * logit(raw) + (1 - w) * logit(market)`

Start with `w = 0.25`, because the market should be assumed better until shown otherwise.
Change `w` only when the scorecard supports it.

### Game theory layer
Added last, and only where actors really are making strategic choices:

- **Entry:** run if the expected payoff beats the cost, given who else is running.
- **Dropout and endorsement:** in a crowded lane, each candidate weighs staying in against
  consolidating behind someone else.
- **VP pick:** balance the ticket against the expected opponent.

Until then, entry and exit are plain probabilities.

### Scoring
**A correction to what I said earlier:** Brier scores alone won't work. Forecasts of the
same election are all really one test, and it doesn't resolve until November 2028. So
there are three scores:

1. **Did the market move toward me?** Log every gap of 3+ points between raw and market,
   then check 7, 30 and 90 days later, like the gamma tracker's three checkpoints. This
   gives results within weeks. It's a proxy: the market moving my way doesn't prove I was
   right.
2. **Short-term questions:** forecasts like "will X declare by June 30, 2027?" resolve
   within months, so they give real Brier scores.
3. **Final Brier scores:** raw vs market vs blended, on nominees and the winner.

Log everything, including forecasts that look bad. The log is append-only: entries are
never edited.

## Tech
Same approach as the gamma tracker, with **no new dependencies**:

- Python standard library only, with `unittest` tests.
- JSONL files for logs (one JSON record per line, easy to read and append).
- A static `index.html` that reads generated JSON, reusing the gamma dashboard's colors.

```
political-game-machine/
  PLAN.md
  candidates.json     one ID per person, with each venue's spelling of the name
  phases.json         phase dates
  read_polymarket.py  read-only pull of 2028 rows from Market Dashboard
  collect_kalshi.py   hourly Kalshi snapshots
  install_kalshi.sh   sets up the hourly job on a Mac
  model.py            presidential simulation
  senate.py           Senate simulation
  game_theory.py      entry, lanes, VP picks
  turns.py            the game log
  forecasts.py        forecast log and scorecard
  run_all.py          pipeline
  clean_markets.py    cleaning, consistency checks, report
  blend.py            blending
  test_*.py
  data/               snapshots, turns, forecasts (append-only)
  outputs/index.html
```

## Build order
Each step can be run and checked before the next one starts.

1. **Market data (done on the M4).** Kalshi collector, read-only Polymarket pull, candidate
   IDs, cleaning, and the two consistency checks. Moving the hourly jobs to the M1 Pro is
   still to do.
2. **Forecast log and scorer (done).** Uses a hash chain, so edits to history are detectable.
3. **Raw model (done, on draft ratings).** Nomination and general election, with tests on
   simple cases.
4. **News turns (done).** `turns.py` logs an update and saves a snapshot.
5. **Blend and dashboard (done).** Raw vs market gaps, implied table, Senate map, scorecard.
6. **Game theory layer (first version).** Entry reactions, lane pressure and VP picks, using
   a quick formula.

## Not in v1
District-level House races, automatic news judgment,
polling feeds, trading of any kind. The Senate, a 50-state map, a primary calendar, a simple House model and a
headline scanner were added on request or as the build went on: see `HANDOFF.md`.

Market venues stay at Polymarket and Kalshi (decided 2026-11-04). PredictIt is the first
one to add later: it has a free public feed covering the main 2028 markets. Polymarket US
needs checking, Manifold would be display-only, and Robinhood and Opinion were skipped.

## Risks
- **The model may never beat the market.** That's a valid result, and the implied-odds
  and consistency tools stay useful either way.
- **Strength ratings are subjective.** They're written down and dated so they can be judged
  later, but the raw model is only as good as those inputs.
- **Long-dated prices are distorted** (long shots run high), so market odds aren't clean
  probabilities either.
- **API fields can change.** The collector should fail loudly rather than save bad data.

## Decisions needed
1. **Starting ratings:** Claude wrote draft ratings so the system could run. Replace them
   with your own. Don't seed them from market prices, as that breaks the independence rule.
2. **Git:** this folder isn't a git repository yet. I recommend adding one, because commit
   history proves forecasts weren't edited after the fact.
3. **Where this runs:** decided. Build on the M4, run the hourly jobs on the M1 Pro.
4. **Dashboard:** I recommend a separate page for now, using a scorecard format that a
   shared Box of Scraps hub could read later.
