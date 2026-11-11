"""Deterministic prediction rules for the gamma breakout tracker.

Pure functions only: no data fetching, no I/O, standard library only.
See SCORING.md for what to pass in and what comes back.

Rules (agreed 2026-10-21):
  Requirements (all must pass, or no prediction):
    1. A 5-minute bar closes above the call wall (crossing up from at/below it).
    2. None of the next 6 bars closes below the wall (30-minute hold).
    3. Cumulative volume at decision time > 1.5x the 20-day average by that time.
  Score (ranks breakouts that pass every requirement):
    +1 sector ETF above both its open and its previous close
    +1 price above the gamma flip
    +1 crowded shorts / expensive borrow (only when data exists)
  Decision: all requirements and score >= 1 -> prediction; score >= 2 -> strong.
  Breakout bar must close by 15:30 ET. At most one prediction per stock per day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Sequence

HOLD_BARS = 6
VOLUME_MULTIPLE = 1.5
STRONG_SCORE = 2
LAST_BREAKOUT_BAR_END = time(15, 30)
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


@dataclass(frozen=True)
class Bar:
    end: datetime  # time the 5-minute bar closed, US/Eastern
    open: float
    close: float
    volume: float


@dataclass(frozen=True)
class SectorData:
    prev_close: float
    bars: Sequence[Bar]  # the sector ETF's 5-minute bars for the same day


@dataclass(frozen=True)
class StockDay:
    symbol: str
    prev_close: float  # stock's previous regular-session close
    bars: Sequence[Bar]  # today's 5-minute bars so far (extra-hours bars are ignored)
    call_wall: float  # from the previous day's open interest
    gamma_flip: Optional[float]  # None when it couldn't be computed
    avg_cum_volume: Dict[time, float]  # 20-day avg cumulative volume, keyed by bar end time
    sector: Optional[SectorData] = None
    shorts_crowded: Optional[bool] = None  # None = no short-interest/borrow data


class EventKind(str, Enum):
    FAILED_HOLD = "failed_hold"  # closed back below the wall during the 30-minute hold
    NO_PREDICTION = "no_prediction"  # held, but failed volume or scored 0
    PREDICTION = "prediction"


@dataclass
class Event:
    symbol: str
    kind: EventKind
    call_wall: float
    breakout_time: datetime
    breakout_price: float
    decision_time: datetime  # when the attempt failed or the hold finished
    decision_price: float
    volume_ratio: Optional[float] = None
    points: Dict[str, int] = field(default_factory=dict)
    score: int = 0
    strong: bool = False
    reasons: List[str] = field(default_factory=list)  # why there was no prediction
    notes: List[str] = field(default_factory=list)  # missing data that cost a point


@dataclass
class DayResult:
    events: List[Event]
    holding_since: Optional[Bar]  # breakout bar of a hold still in progress, if any


def _regular_session(bars: Sequence[Bar]) -> List[Bar]:
    return [b for b in sorted(bars, key=lambda b: b.end) if SESSION_OPEN < b.end.time() <= SESSION_CLOSE]


def evaluate_day(day: StockDay) -> DayResult:
    """Run the rules over one stock's day. Safe to call again each time a new bar arrives."""
    bars = _regular_session(day.bars)
    wall = day.call_wall
    events: List[Event] = []
    last_close = day.prev_close
    cum_volume = 0.0
    hold_start: Optional[int] = None

    for i, bar in enumerate(bars):
        cum_volume += bar.volume
        if hold_start is not None:
            breakout = bars[hold_start]
            if bar.close < wall:
                events.append(Event(
                    symbol=day.symbol, kind=EventKind.FAILED_HOLD, call_wall=wall,
                    breakout_time=breakout.end, breakout_price=breakout.close,
                    decision_time=bar.end, decision_price=bar.close,
                    reasons=[f"closed below the wall at {bar.end:%H:%M} during the hold"],
                ))
                hold_start = None
            elif i - hold_start == HOLD_BARS:
                event = _decide(day, breakout, bar, cum_volume)
                events.append(event)
                hold_start = None
                if event.kind is EventKind.PREDICTION:
                    break
        elif last_close <= wall < bar.close and bar.end.time() <= LAST_BREAKOUT_BAR_END:
            hold_start = i
        last_close = bar.close

    holding = bars[hold_start] if hold_start is not None else None
    return DayResult(events=events, holding_since=holding)


def _decide(day: StockDay, breakout: Bar, bar: Bar, cum_volume: float) -> Event:
    event = Event(
        symbol=day.symbol, kind=EventKind.NO_PREDICTION, call_wall=day.call_wall,
        breakout_time=breakout.end, breakout_price=breakout.close,
        decision_time=bar.end, decision_price=bar.close,
    )

    avg = day.avg_cum_volume.get(bar.end.time())
    if avg:
        event.volume_ratio = cum_volume / avg

    event.points["sector"] = _sector_point(day.sector, bar.end, event.notes)
    if day.gamma_flip is None:
        event.notes.append("no gamma flip")
        event.points["gamma_flip"] = 0
    else:
        event.points["gamma_flip"] = int(bar.close > day.gamma_flip)
    if day.shorts_crowded is None:
        event.notes.append("no short-interest data")
    event.points["shorts"] = int(bool(day.shorts_crowded))
    event.score = sum(event.points.values())

    if event.volume_ratio is None:
        event.reasons.append(f"no volume baseline for {bar.end:%H:%M}")
    elif event.volume_ratio <= VOLUME_MULTIPLE:
        event.reasons.append(f"volume {event.volume_ratio:.2f}x normal, needs more than {VOLUME_MULTIPLE}x")
    if event.score == 0:
        event.reasons.append("score 0")

    if not event.reasons:
        event.kind = EventKind.PREDICTION
        event.strong = event.score >= STRONG_SCORE
    return event


def _sector_point(sector: Optional[SectorData], at: datetime, notes: List[str]) -> int:
    bars = [b for b in _regular_session(sector.bars) if b.end <= at] if sector else []
    if not bars:
        notes.append("no sector data")
        return 0
    price = bars[-1].close
    return int(price > bars[0].open and price > sector.prev_close)


class GradeStatus(str, Enum):
    WRONG = "wrong"  # a bar closed below the wall before the checkpoint
    HELD = "held"  # reached the checkpoint without closing below the wall
    PENDING = "pending"  # checkpoint not reached yet


@dataclass
class Grade:
    checkpoint: datetime
    status: GradeStatus
    price: Optional[float]  # last close seen up to the checkpoint
    pct_move: Optional[float]  # % from the decision price
    broke_below_at: Optional[datetime]


def grade_prediction(prediction: Event, bars_after: Sequence[Bar], checkpoint: datetime) -> Grade:
    """Check a prediction at one checkpoint (end of day, next day close, 3 days later).

    bars_after: the stock's 5-minute bars from the prediction onward, any number of days.
    checkpoint: end time of the last bar to include, e.g. 16:00 ET on the check day.
    """
    seen = [b for b in _regular_session(bars_after) if prediction.decision_time < b.end <= checkpoint]
    broke = next((b.end for b in seen if b.close < prediction.call_wall), None)
    price = seen[-1].close if seen else None
    pct = (price / prediction.decision_price - 1) * 100 if price is not None else None

    if broke is not None:
        status = GradeStatus.WRONG
    elif seen and seen[-1].end == checkpoint:
        status = GradeStatus.HELD
    else:
        status = GradeStatus.PENDING
    return Grade(checkpoint=checkpoint, status=status, price=price, pct_move=pct, broke_below_at=broke)
