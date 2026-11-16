# Polymarket long-shot bias: results

*Run once on 2026-11-16 by the plan in `PLAN.md` (committed first). Code: `collectors/poly_bias.py`.
Raw output: `~/MarketData/poly_bias/results-2026-11-16.json`. Research only: nothing was bet.*

## In one paragraph

Long shots on Polymarket did come in a little less often than their prices said, which is the
direction the research predicts. But the gap is small, well within luck, and after paying the
bid-ask cost both trading rules made about nothing. **Neither rule passes. Nothing goes to a live test.**

## What was tested

1,076 markets in 608 events, first seen between Oct 26 and Nov 14, 2026, each settled at least 48
hours after we first saw it. Each market is counted once, at the first price we stored.

| Step | Markets |
|---|---|
| Stored | 96,603 |
| No longer listed | 91,818 |
| Of those, settled clearly at Yes or No | 53,419 |
| Left out: last price wasn't near 0 or 1 | 38,399 |
| In the test (48+ hours of history, $1,000+ daily volume, price 1-99%) | 1,076 |

## Were prices right?

| Priced at | Markets | Average price | Happened | Gap (95% range) |
|---|---|---|---|---|
| 1-5% | 225 | 2.6% | 1.3% | −1.3 pts (−2.6 to +0.5) |
| 5-10% | 120 | 7.0% | 5.8% | −1.2 pts (−5.1 to +3.0) |
| 10-20% | 159 | 14.7% | 12.6% | −2.1 pts (−6.9 to +3.1) |
| 20-40% | 165 | 28.2% | 24.9% | −3.3 pts (−10.0 to +4.2) |
| 40-60% | 127 | 49.7% | 53.5% | +3.9 pts (−5.7 to +12.8) |
| 60-80% | 106 | 70.1% | 73.6% | +3.4 pts (−5.6 to +12.0) |
| 80-90% | 53 | 85.4% | 84.9% | −0.5 pts (−10.3 to +8.7) |
| 90-95% | 44 | 92.7% | 95.5% | +2.7 pts (−4.1 to +7.4) |
| 95-99% | 77 | 96.9% | 97.4% | +0.5 pts (−3.4 to +3.2) |

Every range includes zero. The pattern (cheap outcomes slightly overpriced, likely ones slightly
underpriced) matches the research, but this sample can't tell it from luck. Overall the prices were
close to right.

## The two trading rules, after the bid-ask cost

| | Sell long shots (price 10% or less) | Buy favourites (price 90% or more) |
|---|---|---|
| Bets, events | 343 in 257 | 120 in 108 |
| Won | 97.1% | 96.7% |
| Average return per bet (95% range) | +0.4% (−1.5% to +2.1%) | +0.3% (−3.3% to +3.1%) |
| Average by event | +0.4% (−1.9% to +2.3%) | +0.4% (−3.3% to +3.3%) |
| First half / second half | −0.5% / +1.4% | +2.1% / −1.7% |
| Without the biggest group (politics) | +0.7% | −4.4% |
| **Verdict** | **Fails** (rules 1, 2 and 3) | **Fails** (all four rules) |

Both rules win about 97% of the time and lose everything on the rest, which nets to about zero.

## What it means

- Polymarket's prices for short-lived, actively traded markets were close to fair over these three
  weeks. The small long-shot bias that showed up is about the size of the bid-ask cost.
- The test is weak: three weeks, 608 events, and only markets that settle fast. A real bias of a
  point or two could be hiding in the noise.

## Limits

- 38,399 markets were left out because their last stored price wasn't near 0 or 1 (mostly ones the
  collector stopped following before they settled). That could tilt the result either way.
- Markets that run for months, where the research finds the biggest long-shot bias, aren't covered.
- Returns assume a bet could be placed at the quoted price.

## If it's ever rerun

More data is collected every hour. The same plan could be run again in six months on markets first
seen **after 2026-11-16** only, which would be a clean second test.
