# Candidate ratings: evidence and rules

*Set by Claude on 2026-11-10, at the owner's request, from research rather than judgment. Not yet reviewed by the owner.*
Betting-market prices were not used as evidence: the raw model is meant to be compared with them, not built from them.
To update a number, change the evidence and re-apply the rule; don't edit a number on its own.

## The rules

**poll.** Each candidate's share among voters with a preference (share divided by 100 minus undecided, or by the total of
listed shares when undecided isn't given), averaged over the national primary polls fielded Oct 1 to Nov 5 2026 that name them.
Source: Wikipedia's nationwide 2028 primary polling tables, read 2026-11-10. No post-midterm polls existed yet. Anyone never named
gets 0.5. The field entries get the average "someone else" share left after listed people.

**p_run** (chance of running, before deferring), by what they've said and done:

| Tier | Chance | Meaning |
|---|---|---|
| declared | 0.97 | Declared or filed an exploratory committee |
| leaning | 0.80 | Says leaning toward it or seriously considering, and has taken concrete steps (early-state trips, PAC, book) |
| open_steps | 0.65 | Hasn't ruled it out, and has taken concrete steps |
| considering | 0.50 | Says considering or won't rule it out, few concrete steps; or credible reports both ways |
| talked | 0.25 | Talked about, nothing from them |
| no | 0.10 | Has ruled it out, or no sign of interest |

Then 0.1 off for each constraint (a new term starting in Jan 2027, their own seat up in 2028, another race on offer) and 0.1 on
for a pull (their term ending, sitting vice president). `defers_to` is used only where the person has said they'd step aside.

**adj** (strength the polls miss): 0.25 per evidence item, capped at 1. Items: a fresh 2025-26 win where they ran at least 5 points
ahead of their state and year (+); money or a campaign team (a big war chest, self-funding, a named strategist) (+); the party
leader's backing (+); a recent statewide or national loss (-); support that's mostly name recognition: a celebrity or family name with
no organization (-). A "room to grow" item (low name recognition but well liked) was planned, but no poll measures it for these
people, so it isn't used.

**general** (points versus a generic nominee in November): 0.1 per point the candidate ran ahead of a generic candidate in their
latest statewide race since 2018, capped at 2. A generic candidate's margin = the state's 2024 lean (its 2024 presidential margin
minus the nation's, from `states.json`) + that year's national mood: House vote 2022 R+2.8, president 2024 R+1.5, House vote 2026
D+13 (Cook, 13.5 with counting still going on Nov 10). Off-year races (2021, 2023) use the next federal year. For four Democrats
a North Carolina favorability poll adds 0.05 per point of net favorability above the four's average (Elon University, Sep 29 to
Oct 8 2026: Harris -15, Buttigieg -1, Newsom -10, Ocasio-Cortez -7). No national favorability poll covering the field was found,
so everyone else without a statewide race gets 0. Total capped at 2.5. The 0.1 scale is a judgment: home-state strength carries
over to a national race only weakly, and some of it is the quality of the opponent.

Unchanged from Claude's earlier drafts: `lane`, `home`, the national mood, and every model setting.

## Each candidate

| Candidate | poll | p_run | adj | general | Why |
|---|---|---|---|---|---|
| kamala-harris | 26.5 | 0.65 (open_steps 0.65) | -0.25 | -0.34 | Running: Says undecided ('I will keep you posted', after the midterms). Fall 'freedom tour', extended book tour, DNC speech; Axios: 'stepping toward' a run. Adj: recent loss - (Lost the 2024 election). General: no statewide race since 2018; NC net favorability -15. |
| gavin-newsom | 15.8 | 0.9 (leaning 0.80 +0.10) | +0.00 | -0.14 | Running: Says he'll decide after the midterms ('I'd be lying if I said otherwise'); trips to NH, SC, NC. Term ends Jan 2027. Said he won't run if Harris does. Defers to kamala-harris (80%). Adj: none. General: CA governor 2022, 59.2-40.8: ran -0.5 vs a generic candidate; NC net favorability -10. |
| pete-buttigieg | 12.3 | 0.8 (leaning 0.80) | +0.00 | +0.36 | Running: Says he's leaning toward 2028 (Newsweek). Third early-state trip by Feb 2026 (NH, IA). An outside PAC is urging him to run. Adj: none. General: no statewide race since 2018; NC net favorability -1. |
| alexandria-ocasio-cortez | 12.1 | 0.4 (considering 0.50 -0.10) | +0.25 | +0.06 | Running: Deciding between president and a Senate run for Schumer's seat, after the midterms. 'Ready for AOC' group isn't hers. Adj: money/team + ($17.4M in her House account (Sept 30)). General: no statewide race since 2018; NC net favorability -7. |
| jon-ossoff | 9.0 | 0.1 (no 0.10) | +0.25 | +0.57 | Running: Repeatedly says he isn't running ('zero interest in running for president'); ruled it out on CNN, June 2026. Adj: fresh win +. General: GA Senate 2026, 59-41 (Reuters): ran +5.7 vs a generic candidate. |
| josh-shapiro | 5.6 | 0.55 (open_steps 0.65 -0.10) | +0.25 | +0.93 | Running: Brushes off questions; memoir 'Where We Keep the Light'; hasn't visited early states. Just re-elected (new term Jan 2027). Adj: fresh win +. General: PA governor 2026, 60.4-38.3 (NBC, 99%): ran +9.3 vs a generic candidate. |
| jb-pritzker | 3.9 | 0.4 (considering 0.50 -0.10) | +0.25 | -0.15 | Running: Didn't rule out a run (Meet the Press, Nov 1). Just won a third term. Adj: money/team + (Billionaire, can self-fund). General: IL governor 2026, 60.3-36.4 (NBC, 97%): ran -1.5 vs a generic candidate. |
| mark-kelly | 7.0 | 0.55 (open_steps 0.65 -0.10) | +0.25 | +1.17 | Running: Hasn't ruled out; trips to SC, NV, IA. His Senate seat is up in 2028. Adj: money/team + (Biggest war chest of the Democrats, over $22M (FEC)). General: AZ Senate 2022, 51.4-46.5: ran +11.7 vs a generic candidate. |
| cory-booker | 2.3 | 0.4 (considering 0.50 -0.10) | +0.25 | +0.64 | Running: Has left the door open; ran in 2020. Just re-elected (new term Jan 2027). Adj: fresh win +. General: NJ Senate 2026, 62.1-35.3: ran +6.4 vs a generic candidate. |
| andy-beshear | 2.9 | 0.9 (leaning 0.80 +0.10) | +0.00 | +2.00 | Running: Says he's considering it; decides after his DGA chair term ends in December. Book 'Go and Do Likewise' (Sept 22) with NH and SC tour stops. Term ends Dec 2027. Adj: none. General: KY governor 2023, 52.5-47.5: ran +35.5 vs a generic candidate. |
| wes-moore | 1.1 | 0.1 (no 0.10) | +0.00 | -1.02 | Running: Has said he isn't running. Adj: none. General: MD governor 2026, 64.4-31.6 (NBC, 88%): ran -10.2 vs a generic candidate. |
| gretchen-whitmer | 1.3 | 0.35 (talked 0.25 +0.10) | +0.00 | +1.33 | Running: Earlier seemed to rule it out, then 'never say never'; didn't rule it out in October. Term ends Jan 2027. Adj: none. General: MI governor 2022, 54.5-43.9: ran +13.3 vs a generic candidate. |
| chris-murphy | 0.9 | 0.25 (talked 0.25) | +0.25 | +0.45 | Running: On prospect lists; no statement found. Adj: money/team + (More than $11M in his campaign account). General: CT Senate 2024, about 58.6-39.6 (from memory): ran +4.5 vs a generic candidate. |
| ro-khanna | 0.8 | 0.8 (leaning 0.80) | +0.00 | +0.00 | Running: Says he's seriously considering; calls himself a 'long-shot presidential candidate'. Adj: none. General: no statewide race since 2018. |
| james-talarico | 3.1 | 0.15 (talked 0.25 -0.10) | +0.25 | +1.13 | Running: No 2028 statement found. Just elected to the Senate (term starts Jan 2027). Adj: fresh win +. General: TX Senate 2026, 55.1-43.0, beat Paxton: ran +11.3 vs a generic candidate. |
| ruben-gallego | 0.5 | 0.25 (talked 0.25) | +0.00 | +0.79 | Running: Named among prospects; no statement found. Adj: none. General: AZ Senate 2024, 50.1-47.7: ran +7.9 vs a generic candidate. |
| raphael-warnock | 1.1 | 0.15 (talked 0.25 -0.10) | +0.00 | +0.63 | Running: No statement found. His Senate seat is up in 2028. Adj: none. General: GA Senate 2022 runoff, 51.4-48.6: ran +6.3 vs a generic candidate. |
| stephen-a-smith | 0.5 | 0.1 (no 0.10) | -0.25 | +0.00 | Running: Ruled out 2028 (would lose his broadcast job); maybe 2032. Adj: name recognition only -. General: no statewide race since 2018. |
| jon-stewart | 0.5 | 0.1 (no 0.10) | -0.25 | +0.00 | Running: No sign of interest found; not named in recent polls. Adj: name recognition only -. General: no statewide race since 2018. |
| mark-cuban | 0.5 | 0.1 (no 0.10) | -0.25 | +0.00 | Running: Considered it, then ruled it out (2028 tracker). Adj: name recognition only -. General: no statewide race since 2018. |
| field-d | 4.4 | 1 | 0 | 0 | Everyone not listed. |
| jd-vance | 42.5 | 0.75 (open_steps 0.65 +0.10) | +0.50 | -0.64 | Running: No announcement; 'if I run, the president will endorse me'. Trump told donors 'we need to elect JD'. WSJ: some close to him doubt a Republican can win after the midterms. Sitting VP. Adj: party backing +, money/team + (Trump's backing with donors; Trump Jr. endorsed him; Rubio says he'd defer). General: OH Senate 2022, 53.0-46.9: ran -6.4 vs a generic candidate. |
| marco-rubio | 25.9 | 0.5 (considering 0.50) | +0.00 | +0.20 | Running: Says he has no plans to run (Sept 2026) and would back Vance if Vance runs. Chance here is for a race without Vance. Defers to jd-vance (90%). Adj: none. General: FL Senate 2022, 57.7-41.3: ran +2.0 vs a generic candidate. |
| donald-trump-jr | 10.4 | 0.25 (talked 0.25) | -0.25 | +0.00 | Running: No plan reported; has endorsed Vance. Defers to jd-vance (95%). Adj: name recognition only -. General: no statewide race since 2018. |
| ron-desantis | 9.1 | 0.6 (considering 0.50 +0.10) | +0.00 | +0.50 | Running: Washington Post: planning a run (media blitz); he publicly denies it. Term ends Jan 2027. Adj: none. General: FL governor 2022, 59.4-40.0: ran +5.0 vs a generic candidate. |
| ted-cruz | 3.2 | 0.8 (leaning 0.80) | +0.25 | -0.52 | Running: Openly says he may run again; would use consultant Jeff Roe (Axiom). Adj: money/team + (Campaign team lined up). General: TX Senate 2024, 53.1-44.6: ran -5.2 vs a generic candidate. |
| robert-f-kennedy-jr | 4.1 | 0.1 (no 0.10) | -0.25 | +0.00 | Running: He and his wife say he won't run and will keep backing Trump. Adj: name recognition only -. General: no statewide race since 2018. |
| nikki-haley | 3.9 | 0.1 (no 0.10) | +0.00 | +0.00 | Running: Said in April 2026 she won't run. Adj: none. General: no statewide race since 2018. |
| vivek-ramaswamy | 1.1 | 0.25 (talked 0.25) | -0.25 | -0.17 | Running: No statement after losing the Ohio governor race. Adj: recent loss - (Lost the 2026 Ohio governor race). General: OH governor 2026, lost to Acton by about 5 (87% counted): ran -1.7 vs a generic candidate. |
| tucker-carlson | 1.6 | 0.1 (no 0.10) | -0.25 | +0.00 | Running: 'Of course not' (The Economist); source: won't run against Vance. Adj: name recognition only -. General: no statewide race since 2018. |
| josh-hawley | 2.2 | 0.1 (no 0.10) | +0.00 | -0.44 | Running: Said in Sept 2026 he has no intention of seeking the nomination. Adj: none. General: MO Senate 2024, about 55.8-41.8 (from memory): ran -4.4 vs a generic candidate. |
| brian-kemp | 0.5 | 0.5 (considering 0.50) | +0.00 | +0.40 | Running: Reported weighing a run, or a 2028 Senate race against Warnock (unconfirmed). Term ends Jan 2027 (+0.1), Senate option (-0.1). Adj: none. General: GA governor 2022, 53.4-45.9: ran +4.0 vs a generic candidate. |
| glenn-youngkin | 1.1 | 0.25 (talked 0.25) | +0.00 | +0.65 | Running: Plays down his prospects; called Vance a 'great nominee'; runs a national school-choice group. Adj: none. General: VA governor 2021, 50.6-48.6: ran +6.5 vs a generic candidate. |
| tim-scott | 1.5 | 0.4 (considering 0.50 -0.10) | +0.00 | +0.67 | Running: Iowa and New Hampshire stops sparked speculation. His Senate seat is up in 2028. Adj: none. General: SC Senate 2022, 62.9-37.1: ran +6.7 vs a generic candidate. |
| thomas-massie | 0.5 | 0.05 (no 0.10 -0.05) | -0.25 | +0.00 | Running: Lost his 2026 House primary; talk is of a Libertarian third-party run, which the model doesn't cover. Adj: recent loss - (Lost his 2026 primary). General: no statewide race since 2018. |
| sarah-huckabee-sanders | 1.1 | 0.15 (talked 0.25 -0.10) | +0.00 | -0.08 | Running: No statement found. Just re-elected. Adj: none. General: AR governor 2026, 53.9-38.6 (NBC, 99%): ran -0.8 vs a generic candidate. |
| tom-cotton | 1.0 | 0.15 (talked 0.25 -0.10) | +0.00 | -0.42 | Running: Seen as possible; just re-elected. Adj: none. General: AR Senate 2026, 54.3-42.4: ran -4.2 vs a generic candidate. |
| kristi-noem | 0.8 | 0.25 (talked 0.25) | +0.00 | -0.37 | Running: No statement found. Adj: none. General: SD governor 2022, 62.0-35.2: ran -3.7 vs a generic candidate. |
| field-r | 2.4 | 1 | 0 | 0 | Everyone not listed. |

## Sources

- Polls: [Democratic](https://en.wikipedia.org/wiki/Nationwide_opinion_polling_for_the_2028_Democratic_Party_presidential_primaries) and [Republican](https://en.wikipedia.org/wiki/Nationwide_opinion_polling_for_the_2028_Republican_Party_presidential_primaries) nationwide polling tables (McLaughlin, AtlasIntel, Harvard Harris, Leger, NYT/Siena, Echelon, Noble, Clarity, Focaldata)
- [2028tracker: are they running](https://2028tracker.com/are-they-running-2028)
- Harris: [Fox News, undecided](https://www.foxnews.com/media/kamala-harris-says-she-hasnt-decided-2028-presidential-campaign-amid-report-shes-stepping-toward-run), [Washington Post, Nov 8](https://washingtonpost.com/ripple/2026/11/08/kamala-harris-urges-democrats-stop-writing-off-deep-red-states)
- Newsom: [Yahoo, decision after midterms](https://www.yahoo.com/news/articles/gavin-newsom-admits-ll-decide-191022804.html), [Yahoo, after election night](https://www.yahoo.com/news/politics/articles/gavin-newsom-2028-run-clearer-122200553.html)
- Buttigieg: [Newsweek, leaning toward 2028](https://www.newsweek.com/buttigieg-says-hes-leaning-toward-2028-heres-what-the-numbers-say-12279632), [LGBTQ Nation, NH visit](https://www.lgbtqnation.com/2026/02/president-pete-pete-buttigieg-sparks-2028-speculation-with-visit-to-new-hampshire/)
- Ocasio-Cortez: [Yahoo, 'all or nothing'](https://www.yahoo.com/news/politics/articles/aoc-2028-presidential-run-nothing-135057565.html), [Washington Sun, cash](https://www.washingtonsun.com/influence/aoc-schumer-senate-2028-money)
- Ossoff: [MS NOW, again says he won't run](https://www.ms.now/news/senator-john-ossoff-georgia-again-says-he-wont-run-for-president-in-2028), [Fox 5 Atlanta](https://www.fox5atlanta.com/news/senator-ossoffs-victory-fuels-2028-presidential-speculation)
- Governors: [Newsnation](https://www.newsnationnow.com/politics/2028-election-democrats-running-for-president/), [The Hill, Beshear](https://thehill.com/homenews/campaign/5745769-beshear-considering-2028-presidential-run/), [PBS](https://www.pbs.org/newshour/politics/the-midterms-stakes-are-high-for-these-2028-presidential-prospects)
- Senators: [Detroit News, who's doing what](https://www.detroitnews.com/story/news/politics/2026/09/23/democrats-already-making-moves-to-run-for-president-2028-heres-whos-doing-what/91904795007/), [CBS, summit](https://www.cbsnews.com/news/booker-van-hollen-khanna-democrats-2028-hopefuls-summit-midterms/)
- Stephen A. Smith: [Yahoo](https://www.yahoo.com/entertainment/celebrity/articles/stephen-smith-announces-decision-running-211637321.html); celebrities: [2028tracker](https://2028tracker.com/celebrity-candidates-2028)
- Vance and Rubio: [Fox News, 'we need to elect JD'](https://www.foxnews.com/politics/trump-told-donors-we-need-elect-jd-source-confirms-weighs-vance-rubio-2028), [KATV, 'if I run'](https://katv.com/news/nation-world/vance-on-2028-presidential-race-i-think-if-i-run-the-president-will-endorse-me-trump-air-force-two-marco-rubio-midterm-elections-republicans), [Yahoo, WSJ report](https://www.yahoo.com/news/politics/articles/jd-vance-hits-roadblock-over-163449430.html)
- Republicans: [Yahoo, DeSantis, Kemp, Cruz](https://yahoo.com/news/politics/articles/desantis-kemp-cruz-eye-2028-145917547.html), [The Hill, after the midterms](https://thehill.com/homenews/campaign/6204859-vances-2028-stock-drops-ranking-top-5-presidential-gop-contenders-post-midterms/), [The Hill, Carlson](https://thehill.com/homenews/campaign/5939120-tucker-carlson-rules-out-2028-bid/), [Axios, Massie](https://axios.com/2026/11/08/massie-president-2028-libertarian)
- 2026 results: [NBC governors](https://www.nbcnews.com/politics/2026-elections/governor-results), [NBC Texas Senate](https://www.nbcnews.com/politics/2026-elections/texas-senate-results), [political.org Senate table](https://political.org/2026/11/04/2026-senate-results-how-every-race-compares-with-the-last-10-elections/), [Ballotpedia, Ohio](https://news.ballotpedia.org/?p=52384), [The Blaze, Ohio margin](https://www.theblaze.com/news/amy-acton-wins-ohio-governor-s-seat-beating-republican-vivek-ramaswamy)
- National House vote: [Political Wire / Cook, D+13.5](https://politicalwire.com/2026/11/10/democrats-beat-republicans-by-13-5-in-house-vote/)
- NC favorability: [Elon University Poll](https://www.elon.edu/u/news/2026/11/10/elon-university-poll-measures-n-c-attitudes-toward-impeachment-potential-2028-presidential-candidates/)
- Races from 2021-2024 (Newsom, Kelly, Beshear, Whitmer, Murphy, Gallego, Warnock, Vance, Rubio, DeSantis, Cruz, Hawley, Kemp, Youngkin, Tim Scott, Noem) are from memory. Murphy's and Hawley's are approximate.

## Not certain yet

- Moore's, Pritzker's and Ramaswamy's 2026 margins were from partly counted results (88%, 97%, 87%).
- No post-midterm national primary poll existed on Nov 10. The first ones should replace the poll column.
- Kemp's interest is from unconfirmed reports. DeSantis publicly denies the reported planning.
