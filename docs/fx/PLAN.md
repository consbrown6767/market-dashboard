# Currency (FX) strategies from international monetary theory: the plan, fixed before any result was seen

*Written 2026-11-13, before any of the strategies below was run. Committed so the date and contents are on record.
Changes go at the bottom and don't count.*

## The idea

Exchange rates are where international monetary theory makes testable predictions:
- **Uncovered interest parity (UIP):** a high-interest currency should fall by exactly its interest advantage, so
  holding it earns nothing extra. In the data it doesn't fall enough: the "forward premium puzzle" (Fama 1984).
  That gap is the **carry trade**.
- **Purchasing power parity (PPP):** in the long run, exchange rates drift back toward what prices say they should
  be. Currencies far from that level should revert: **value**.
- **Taylor rules:** central banks raise rates when inflation and employment run hot, so countries that should
  be tightening see their currencies rise (Molodtsova & Papell 2009).
- **Momentum:** currencies that rose keep rising for a while (Menkhoff, Sarno, Schmeling & Schrimpf 2012).
- **Crash risk:** carry earns a premium because it crashes in global panics (Brunnermeier, Nagel & Pedersen
  2008). Avoiding panics might keep most of the premium.

Every strategy trades once a month, with no high-frequency trading. A real version would use currency forwards or
futures, which need only margin, so each strategy is an **overlay**: it can sit on top of holding SPY.

## Research behind each version

| # | Version | Research | Signal at each month-end (for next month) |
|---|---|---|---|
| 1 | **Carry** | Lustig & Verdelhan (2007); Lustig, Roussanov & Verdelhan (2011) | Interest rate minus the US rate. Long the top third, short the bottom third |
| 2 | **Dollar carry** | Lustig, Roussanov & Verdelhan (2014) | If foreign rates average above the US rate: long all foreign currencies against the dollar; else short them all |
| 3 | **Momentum, 1 month** | Menkhoff, Sarno, Schmeling & Schrimpf (2012) | Last month's excess return. Long the top third, short the bottom third |
| 4 | **Momentum, 12 months** | Asness, Moskowitz & Pedersen (2013) | Last 12 months' excess return. Top vs bottom third |
| 5 | **Value (PPP)** | Asness, Moskowitz & Pedersen (2013); Menkhoff, Sarno, Schmeling & Schrimpf (2017) | Fall in the real exchange rate over 5 years (spot × foreign CPI ÷ US CPI, CPI two months old). Long the cheapest third, short the dearest third |
| 6 | **Taylor rule** | Molodtsova & Papell (2009) | 1.5 × inflation gap + 0.5 × unemployment gap against the US (12-month CPI inflation; unemployment below its 10-year average; data two months old). Long the most "should tighten" third, short the least |
| 7 | **Real carry** | Real interest parity; Ang & Chen (2010) | Rate minus 12-month inflation, minus the same for the US. Top vs bottom third |
| 8 | **Carry with a crash filter** | Brunnermeier, Nagel & Pedersen (2008) | Carry (1), but in cash whenever the VIX's month-end is above its average of the last 12 month-ends. *Sandbox from 1991 (VIX starts 1990)* |
| 9 | **Carry with a trend filter** | Timing factor strategies by their own trend | Carry (1), but only while carry's own last 12 months were positive; otherwise cash |
| 10 | **Trend per currency** | Moskowitz, Ooi & Pedersen (2012) | Each currency long against the dollar if its 12-month excess return is positive, short if negative, equal weights |
| 11 | **Combination** | Kroencke, Schindler & Schrimpf (2014) | Carry, 12-month momentum and value, each scaled to the same risk (36-month volatility), averaged |

**"A third":** with n currencies available that month, the top and bottom max(2, n÷3) each get equal weight
(longs add to 1, shorts add to −1).

## Data (FRED, all free)

- **Spot rates:** daily H.10 noon rates, last of each month. Pound, yen, Swiss franc, Canadian, Australian and New
  Zealand dollars, Norwegian and Swedish krone from 1971, the euro from 1999. The Deutsche mark's daily history isn't
  on FRED, so before 1999 there's no euro or mark.
- **Interest rates:** OECD 3-month interbank (monthly average) for each country. Where that is missing, the
  country's short-term (call money) rate: Japan before 2002, Switzerland before 1999-07, the UK after 2026-01.
  The euro uses Germany's 3-month series.
- **Inflation and unemployment:** OECD monthly CPI (quarterly for Australia and New Zealand, carried forward
  within the quarter) and harmonized unemployment. Where a series ends early (e.g. Japan's CPI in 2021), the
  last value is carried forward.
- **Each currency enters** once it has a spot rate and an interest rate: Norway 1979, Sweden 1982, Japan 1985,
  the euro 1999.

**Return of a long currency position for a US investor**, month t to t+1: (S(t+1) ÷ S(t)) × (1 + foreign rate ÷ 1200)
− (1 + US rate ÷ 1200). S is dollars per unit of the currency; the rates are known at the end of month t.

**Costs:** 0.05% per dollar traded when positions change, plus 0.01% a month per dollar held (rolling forwards).

## The sandbox and the vault (as in `docs/exploration/`)

- **Sandbox: 1980-01 to 2005-12** (version 8 from 1991). All 11 versions are run here, and every one is counted.
- **Vault: 2006-01 to 2026-10.** The code refuses to load it until `FINALISTS.md` is committed. Up to three
  finalists: the three versions with the best Sharpe ratio in the sandbox, as long as it's above 0.3. If none
  reaches 0.3, nothing goes in, and the answer is "nothing found".

## Pass rules in the vault ("worth live testing")

A finalist is **worth live testing** only if all three hold:
1. **SPY + the overlay beats SPY** over 2006-01 to 2026-10: more money **and** a better Sharpe ratio. The
   overlay is added at 1x, as constructed.
2. The overlay alone **made money in both halves** (2006-2015 and 2016-2026).
3. **Fresh currencies:** the same rule on emerging-market currencies it has never seen ends with a positive
   return after costs, with a Sharpe ratio of at least 0.2. Fixed before the vault: Mexico, South Korea, South
   Africa, Brazil, India, Singapore, Thailand, Malaysia, Taiwan, as far as FRED has spot rates and OECD
   short-term rates for them, from 2000 (or as soon as at least 5 are available) to 2026-10. Costs are doubled:
   0.10% per dollar traded and 0.02% a month to roll. If FRED lacks rates for most of them, a currency without
   a rate can't be used for carry signals, and that is reported as it is.

**Also reported (information):** each finalist's crashes (2008, 2020), its correlation with SPY, its Sharpe ratio
on its own, and for carry, the real Invesco DB G10 Currency Harvest fund (DBV, 2006-2023), if Yahoo still has it.

## Changes

(none yet)
