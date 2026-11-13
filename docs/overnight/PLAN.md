# Overnight-only investing: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the tests below was run. Committed so the date and contents are on record.
Changes after results go at the bottom and don't count.*

## The idea

Buy SPY at each day's closing price, sell it at the next morning's opening price, and hold cash during
the trading day. Research finds that most of the US market's gains since the 1990s came overnight, and
roughly none during trading hours.

- Cooper, Cliff & Gulen (2008), "Return Differences between Trading and Non-trading Hours: Like Night
  and Day" (data 1993-2006).
- Kelly & Clark (2011), "Returns in Trading Hours versus Non-trading Hours: The Difference is Day and
  Night" (Journal of Asset Management).
- Lou, Polk & Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns" (Journal of
  Financial Economics, data to 2013).

**After publication:** 2009-01 on (the first paper).

## Data

Yahoo daily SPY, QQQ and IWM open and close prices, not adjusted, plus each fund's dividends (paid to
whoever holds it overnight into the ex-date). SPY from 1993-02, QQQ from 1999-03, IWM from 2000-05,
to 2026-10.

- Overnight return = (today's open + any dividend going ex today) ÷ yesterday's close − 1.
- Daytime return = today's close ÷ today's open − 1.

## The strategy (fixed)

Hold the fund every night (close to next open); cash during the day, earning nothing (conservative).

**Costs:**
- **Main:** 0.01% of each dollar traded, each trade (buy at the close, sell at the open: two trades a
  trading day). That's about 1 basis point for spread and auction impact in the most-traded fund in the
  world.
- **Also reported:** 0.005% and 0.02%, and the break-even cost (the cost per trade that would erase the
  gap with buy and hold).

**Compared with:** buying and holding the same fund, and the daytime-only reverse (information).

## Pass rules

**Overnight beats buy and hold** if, for SPY, at the main cost:
1. more money and a better Sharpe ratio over 1993-2026; **and**
2. the same from 2009 (after publication); **and**
3. in QQQ and IWM (fresh funds), more money than buy and hold from 2009.

## Changes after results

(none yet)
