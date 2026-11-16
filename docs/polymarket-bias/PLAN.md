# Polymarket long-shot bias: the plan, fixed before any result

*Written 2026-11-16, before any outcome was compared with any price. Only row counts were looked at
(about 84,000 ended markets stored, about 5,500 with two or more days of history). Changes go at the
bottom and don't count.*

## The question

Betting research finds a "favourite-long-shot bias": long shots win less often than their prices say
(Snowberg & Wolfers 2010; on prediction markets, Page & Clemen 2013). Is that true on Polymarket, and
is it big enough to survive the cost of trading?

## Data

- Hourly Polymarket snapshots collected by this dashboard since 2026-10-26 (`poly_snapshots`,
  `poly_markets`, `poly_events`). So only markets that **ended within about three weeks** can be tested.
- **Outcome:** a market counts as resolved Yes if its last stored price is 0.98 or more, No if 0.02 or
  less. Markets that end anywhere else are left out and counted.
- **One observation per market:** its **first** stored snapshot, provided that snapshot is at least 48
  hours before its last one, the price is between 0.01 and 0.99, and 24-hour volume was at least $1,000.
- **Price:** the middle of bid and ask when both exist, else the stored price.

## Tests (all counted)

1. **Calibration.** Markets grouped by price: 1-5%, 5-10%, 10-20%, 20-40%, 40-60%, 60-80%, 80-90%,
   90-95%, 95-99%. For each: average price against the share that resolved Yes.
2. **Trading rule A, sell long shots:** for every market priced 10% or less, buy "No" at the price a
   real order would pay (1 minus the Yes bid; markets with no bid are skipped) and hold to the end.
3. **Trading rule B, buy favourites:** for every market priced 90% or more, buy "Yes" at the ask.

Markets in one event move together (a ladder of "Bitcoin above X" prices is really one bet). So all
error bars resample **whole events**, not markets (2,000 bootstrap draws), and each rule's return is
also shown averaged by event.

## Pass rule ("worth a live test")

A rule passes only if **all** hold:
1. its average return per market after the bid-ask cost is positive, with the bootstrap 95% range
   entirely above zero;
2. the same is true of its return averaged by event;
3. it's positive in both halves of the sample (events split at the median end date);
4. it's positive without the largest group of markets (crypto, sports or whichever is biggest), so one
   kind of market isn't carrying it.

## Known limits, written now

- Three weeks of data, and only short-lived markets. It says nothing about markets that run for months.
- Markets the collector lost track of before they settled are left out; that could flatter or hurt.
- Returns ignore how much could really be traded at the quoted price, and any fees.
- Nothing here trades or bets. A pass would lead to a paper record, not money.

## Changes

(none yet)
