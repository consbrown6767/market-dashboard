# Plugging in scoring.py

`collectors/scoring.py` is the prediction rules from HANDOFF.md as code. It's one file, uses only
the standard library, and has no data fetching or UI. Import it from the tracker and call it.

Check it still works: from `collectors/`, run `python3 -m unittest test_scoring` (21 tests).

## 1. Decide on a day: `evaluate_day(StockDay) -> DayResult`

Call it once per stock, each time a new 5-minute bar arrives (re-running on the same day's
bars always gives the same answer), or once at day end.

What the data pipeline must supply in `StockDay`:

| Field | What it is |
|---|---|
| `symbol` | Ticker |
| `prev_close` | Stock's previous regular-session close |
| `bars` | Today's 5-minute bars: `Bar(end, open, close, volume)`. `end` = time the bar closed, **US/Eastern**. Bars outside 9:30–16:00 are ignored. |
| `call_wall` | From the **previous day's** open interest (most call OI across expirations within 30 days) |
| `gamma_flip` | Float, or `None` if it couldn't be computed (costs that point) |
| `avg_cum_volume` | `{datetime.time: float}`: 20-day average **cumulative** volume by each bar end time (e.g. `time(10,20)` → avg shares traded from the open to 10:20) |
| `sector` | `SectorData(prev_close, bars)` for the stock's sector ETF, or `None` |
| `shorts_crowded` | `True`/`False`, or `None` when there's no data |

What comes back in `DayResult`:

- `holding_since`: the breakout bar if a 30-minute hold is in progress right now (good for a "live breakouts" panel), else `None`.
- `events`: every finished breakout attempt today, in order. Each `Event` has:
  - `kind`: `prediction`, `no_prediction` (held but failed volume or scored 0), or `failed_hold` (closed back below the wall during the hold)
  - `breakout_time/price`, `decision_time/price` (when the hold finished or failed)
  - `volume_ratio`, `points` (`{"sector", "gamma_flip", "shorts"}`), `score`, `strong`
  - `reasons`: why there was no prediction; `notes`: missing data that cost a point

**Log every event, not just predictions.** The non-qualifying ones are the comparison group.

## 2. Check a prediction later: `grade_prediction(event, bars_after, checkpoint) -> Grade`

Call it for each prediction at three checkpoints: 16:00 on the prediction day, 16:00 the
next trading day, and 16:00 three trading days later. The pipeline picks the trading days
(holidays, half days).

- `bars_after`: the stock's 5-minute bars from the prediction onward (any number of days).
- `checkpoint`: the end time of the last bar to include.

Returns `status` (`wrong` if any bar closed below the wall before the checkpoint, `held`,
or `pending` if bars don't reach the checkpoint yet), `pct_move` from the decision price,
`price`, and `broke_below_at`.

## Rules locked in by the code
- Breakout = a bar closes **above** the wall after the previous close was **at or below**
  it. A gap up through the wall counts if yesterday's close was at or below it. A stock
  already above the wall at the open doesn't count until it drops back and re-crosses.
- Hold fails only on a close **below** the wall. A close exactly at the wall is fine.
- Volume must be **more than** 1.5× (exactly 1.5× fails). No baseline → no prediction.
- Sector point: the ETF's latest close is above both its first bar's open and its previous close.
- A hold that finishes but doesn't qualify is logged. The stock needs to drop to the wall
  or below and break again to get another try.
- Breakout bar must end by 15:30. At most one prediction per stock per day.

Thresholds are constants at the top of `scoring.py` (`HOLD_BARS`, `VOLUME_MULTIPLE`,
`STRONG_SCORE`, `LAST_BREAKOUT_BAR_END`).
