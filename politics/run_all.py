#!/usr/bin/env python3
"""Run everything and rebuild outputs/data.json, which the dashboard's Politics tab shows.

Order: current game (ratings + turns) -> simulation -> markets -> blend -> Senate -> what-ifs
-> scorecard -> page. Raw model numbers are computed before any market data is loaded.

Usage: python3 run_all.py          rebuild the page
       python3 run_all.py --log    also record today's forecasts and raw-vs-market gaps

The background job runs this copy in ~/MarketData/politics (see collectors/politics_job.py).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import blend
import clean_markets as cm
import forecasts
import game_theory as gt
import house
import senate
import turns
import venue_check
import worlds
import model
from model import RATINGS, simulate, what_if_out, with_changes

HERE = Path(__file__).resolve().parent
PAGE_DATA = HERE / "outputs" / "data.json"
SUMMARY = HERE / "outputs" / "summary.json"

ANNOUNCE_EVENT = "798125"  # Polymarket: "Who will announce Presidential run before 2028?"
ANNOUNCE_RATE = 0.95  # nearly everyone who runs in 2028 declares before that year starts
LOG_FLOOR = 0.02  # candidates below this on both sides aren't worth a logged forecast
SHOCK_PLAYERS = ("kamala-harris", "gavin-newsom", "alexandria-ocasio-cortez", "jon-ossoff", "jd-vance", "marco-rubio")
RESOLVE_BY = {"party": "2028-11-07", "winner": "2028-11-07", "nominee_d": "2028-08-31", "nominee_r": "2028-08-31"}
FIELD_NAMES = {"field-d": "Other Democrats", "field-r": "Other Republicans", "D": "Democrats", "R": "Republicans"}
STALE_HOURS = 6
MAX_STATE_SPREAD = 0.15  # many state markets are nearly empty, and their midpoints mean nothing


def name_table() -> dict:
    return {**{c["id"]: c["name"] for c in cm.load_candidates()}, **FIELD_NAMES}


def table_rows(table: dict, names: dict, extras: dict) -> list:
    rows = [{"id": k, "name": names.get(k, k), **v, **{e: values.get(k) for e, values in extras.items()}}
            for k, v in table.items()]
    return sorted(rows, key=lambda r: -max(r["raw"], r["market"]))


def implied_rows(raw: dict, views: dict, names: dict) -> list:
    poly, kalshi = cm.win_if_nominated(views["polymarket"]), cm.win_if_nominated(views["kalshi"])
    ids = sorted(set(poly) & set(kalshi), key=lambda c: -max(views["polymarket"]["winner"]["odds"].get(c, 0),
                                                             views["kalshi"]["winner"]["odds"].get(c, 0)))
    return [{"name": names[c], "polymarket": poly[c], "kalshi": kalshi[c], "raw": raw["win_if_nominated"].get(c)} for c in ids[:12]]


def price_history(views: dict, tables: dict, names: dict, count: int = 4) -> dict:
    """Polymarket's hourly win odds for today's market leaders."""
    leaders = sorted((k for k in tables["winner"] if not k.startswith("field")),
                     key=lambda k: -tables["winner"][k]["market"])[:count]
    hours = sorted(views["books"]["polymarket"]["winner"])
    series = {names[c]: [] for c in leaders}
    for hour in hours:
        odds = cm.clean_market(views["books"]["polymarket"]["winner"][hour])["odds"]
        for c in leaders:
            series[names[c]].append(round(odds.get(c, 0), 4))
    return {"hours": hours, "series": series}


def long_view(names: dict, count: int = 4) -> dict:
    """Daily market odds since 2025 for today's leaders, averaging the venues that have data."""
    data = read_optional(HERE / "data" / "history" / "daily.json").get("markets", {})
    result = {}
    for market, people in data.items():
        dates = sorted({d for person in people.values() for venue in person.values() for d in venue})
        series = {}
        for person, venues in people.items():
            values, last = [], None
            for date in dates:
                today = [v[date] for v in venues.values() if date in v]
                last = sum(today) / len(today) if today else last
                values.append(round(last or 0, 4))
            series[person] = values
        leaders = sorted(series, key=lambda p: -series[p][-1])[:count]
        result[market] = {"dates": dates, "series": {names.get(p, p): series[p] for p in leaders}}
    return result


def announce_rows(raw: dict, names: dict) -> list:
    lookup = cm.name_lookup(cm.load_candidates(), "polymarket")
    labels = {m["id"]: lookup.get(m["label"]) for m in cm.polymarket_rows(cm.POLYMARKET_DIR, "poly_markets.jsonl", cm.LIVE_DIR)
              if m["event_id"] == ANNOUNCE_EVENT}
    latest = {}
    for row in cm.polymarket_rows(cm.POLYMARKET_DIR, "poly_snapshots.jsonl", cm.LIVE_DIR):
        if labels.get(row["market_id"]):
            latest[labels[row["market_id"]]] = cm.midpoint(row["best_bid"], row["best_ask"], fallback=row["price"])
    rows = [{"id": c, "name": names[c], "raw": raw["ran"][c] * ANNOUNCE_RATE, "market": p}
            for c, p in latest.items() if c in raw["ran"]]
    return sorted(rows, key=lambda r: -abs(r["raw"] - r["market"]))


def if_runs_rows(raw: dict, tables: dict, announce: list, names: dict) -> list:
    """Each side's implied nomination chance if the person runs: nominee odds / chance of running."""
    rows = []
    for row in announce:
        market = "nominee_d" if row["id"] in raw["nominee_d"] else "nominee_r"
        nominee = tables[market].get(row["id"])
        if nominee and row["market"] > 0.05 and max(nominee["raw"], nominee["market"]) >= 0.03:
            rows.append({"name": row["name"], "raw_run": raw["ran"][row["id"]], "market_run": row["market"],
                         "raw_if_runs": nominee["raw"] / max(raw["ran"][row["id"]], 0.001), "market_if_runs": nominee["market"] / row["market"]})
    return sorted(rows, key=lambda r: -r["market_if_runs"])


def disagreements(tables: dict, seats: dict, markets: dict, names: dict, count: int = 10) -> list:
    """The biggest gaps between raw and market. This is what the whole tool exists to find."""
    labels = {"winner": "President", "nominee_d": "Dem nominee", "nominee_r": "GOP nominee"}
    rows = [{"name": names.get(k, k), "market": label, "raw": v["raw"], "price": v["market"]}
            for m, label in labels.items() for k, v in tables[m].items() if not k.startswith("field")]
    for seat in seats["seats"]:
        price = markets.get("states", {}).get(seat["code"])
        # Skip prices near the floor, where the gap is mostly long-dated distortion.
        if price and not price["thin"] and 0.15 < price["p_dem"] < 0.85:
            rows.append({"name": f"Democrats in {seat['state']}", "market": "Senate seat", "raw": seat["p_dem"], "price": price["p_dem"]})
    return sorted(rows, key=lambda r: -abs(r["raw"] - r["price"]))[:count]


def implied_environment(game, target: float, runs: int = 3000) -> float:
    """The national mood that would make the raw model match the market on the White House."""
    low, high = -10.0, 10.0
    for _ in range(7):
        middle = (low + high) / 2
        if simulate(with_changes(game, env_shift=middle), runs=runs)["party"]["D"] < target:
            low = middle
        else:
            high = middle
    return game.env_mean + (low + high) / 2


def sensitivity(game, base: dict, runs: int = 5000) -> list:
    """How far single inputs move the Democrats' White House odds."""
    tests = [("National mood 1 point better for Democrats", {"env_shift": 1.0}),
             ("National mood 1 point worse for Democrats", {"env_shift": -1.0}),
             ("Ossoff certain to run", {"p_run": {"jon-ossoff": 1.0}}),
             ("Ossoff stays out", {"p_run": {"jon-ossoff": 0.0}}),
             ("Newsom's strength doubled", {"strength_shift": {"gavin-newsom": 0.693}}),
             ("Vance's strength halved", {"strength_shift": {"jd-vance": -0.693}})]
    reference = simulate(game, runs=runs)["party"]["D"]
    return [{"label": label, "change": simulate(with_changes(game, **change), runs=runs)["party"]["D"] - reference}
            for label, change in tests]


def senate_gaps(seats: dict, markets: dict) -> None:
    for seat in seats["seats"]:
        market = markets.get("states", {}).get(seat["code"])
        if market and not market["thin"]:
            forecasts.record_gap("senate", seat["code"], seat["p_dem"], market["p_dem"])


def make_price_lookup(views: dict):
    """Market price at a past moment, for checking gaps. Averages the venues that have data."""
    senate_snapshots = cm.read_jsonl(senate.SNAPSHOTS) if senate.SNAPSHOTS.exists() else []

    def senate_price(code: str, when: datetime):
        usable = [s for s in senate_snapshots if datetime.fromisoformat(s["fetched_at"]) <= when
                  and when - datetime.fromisoformat(s["fetched_at"]) <= timedelta(days=3)]
        for row in (usable[-1]["kalshi_states"].get(code, []) if usable else []):
            if str(row["label"]).startswith("Democratic"):
                return senate.midpoint(row)
        return None

    def price_at(market: str, candidate: str, when: datetime):
        if market == "senate":
            return senate_price(candidate, when)
        hour = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
        oldest = (when - timedelta(hours=STALE_HOURS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
        prices = []
        for book in views["books"].values():
            usable = [h for h in book.get(market, {}) if oldest <= h <= hour]
            if usable:
                odds = cm.clean_market(book[market][max(usable)])["odds"].get(candidate)
                if odds is not None:
                    prices.append(odds)
        return sum(prices) / len(prices) if prices else None
    return price_at


def market_movers(views: dict, names: dict, hours_back: int = 24, count: int = 10) -> list:
    """The biggest Polymarket moves over the last day, to point you at news worth a look."""
    rows = []
    labels = {"winner": "President", "nominee_d": "Dem nominee", "nominee_r": "GOP nominee"}
    for market, label in labels.items():
        book = views["books"]["polymarket"][market]
        latest = max(book)
        then_time = (datetime.fromisoformat(latest + ":00:00+00:00") - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H")
        earlier = [h for h in book if h <= then_time]
        if not earlier:
            continue
        before, now = cm.clean_market(book[max(earlier)])["odds"], cm.clean_market(book[latest])["odds"]
        rows += [{"name": names.get(c, c), "market": label, "then": before.get(c, 0), "now": p, "change": p - before.get(c, 0)}
                 for c, p in now.items()]
    return sorted(rows, key=lambda r: -abs(r["change"]))[:count]


def log_forecasts(tables: dict, seats: dict, announce: list) -> int:
    # Forecasts from Claude's draft ratings are labeled, so they never count as yours.
    draft = json.loads(RATINGS.read_text(encoding="utf-8"))["status"].startswith("PROVISIONAL")
    labels = {"raw": "raw-draft" if draft else "raw", "market": "market", "blend": "blend-draft" if draft else "blend"}
    count = 0
    for market, table in tables.items():
        for candidate, row in table.items():
            if max(row["raw"], row["market"]) < LOG_FLOOR:
                continue
            for source in ("raw", "market", "blend"):
                forecasts.add_forecast(f"2028/{market}/{candidate}", row[source], labels[source], RESOLVE_BY[market])
                count += 1
            forecasts.record_gap(market, candidate, row["raw"], row["market"])
    forecasts.add_forecast("2028/senate-control/D", seats["control_d"], labels["raw"], "2028-11-07")
    count += 1
    senate_gaps(seats, senate.latest_markets())
    logged = {f["question"] for f in forecasts.read_log(forecasts.FORECASTS)}
    for race in senate.load_map()["uncalled_2026"]["seats"]:  # the first questions to resolve
        question = f"senate-2026/{race['code']}-dem"
        if question not in logged:
            forecasts.add_forecast(question, race["p_dem"], labels["raw"], "2026-12-15", race["race"])
            count += 1
    for row in announce:
        for source in ("raw", "market"):
            forecasts.add_forecast(f"announce-before-2028/{row['id']}", row[source], labels[source], "2027-12-31")
            count += 1
    return count


def build(log: bool = False) -> dict:
    game = turns.current_game()
    raw = simulate(game, keep_draws=True)
    draws = raw.pop("draws")
    seats = senate.simulate_senate(senate.load_map(), draws)
    lower_house = house.simulate_house(draws, seats.pop("control_by_race"))
    base_what_if = what_if_out(game, raw)
    shocks = gt.entry_shocks(game, list(SHOCK_PLAYERS))
    for shock in shocks:
        shock["effect"] = gt.strategic_what_if(game, shock, raw)
        del shock["new_p_run"]

    views = blend.market_views()  # market data enters here, after the raw numbers are fixed
    tables = blend.build_tables(raw, views)
    names = name_table()
    announce = announce_rows(raw, names)
    if log:
        print(f"Logged {log_forecasts(tables, seats, announce)} forecasts")
    senate_prices = senate.latest_markets()
    control = [p for p in (senate_prices.get("control_kalshi"), senate_prices.get("control_polymarket")) if p is not None]
    game_worlds = worlds.build_worlds(game, raw, seats["control_d"], lower_house["control_d"], tables, views,
                                      {row["id"]: row["market"] / ANNOUNCE_RATE for row in announce},
                                      sum(control) / len(control) if control else None, senate_prices.get("power"))

    extras = {"ran": raw["ran"], "win_if_nominated": raw["win_if_nominated"]}
    gap_hours = cm.hours_apart(views["polymarket"]["winner"]["hour"], views["kalshi"]["winner"]["hour"])
    logged_turns = forecasts.read_log(turns.TURNS)
    return {
        "generated_at": forecasts.now_utc(),
        "venue_hours": {"polymarket": views["polymarket"]["winner"]["hour"], "kalshi": views["kalshi"]["winner"]["hour"], "gap": gap_hours},
        "party": tables["party"],
        "movers": market_movers(views, names),
        "venue_check": venue_check.check(),
        "disagreements": disagreements(tables, seats, senate.latest_markets(), names),
        "implied_environment": implied_environment(game, tables["party"]["D"]["market"]),
        "sensitivity": sensitivity(game, raw),
        "markets": {m: table_rows(tables[m], names, extras) for m in blend.RAW_MARKETS},
        "totals": {v: {m: {"raw_sum": views[v][m]["raw_sum"], "unlisted": views[v][m]["unlisted"]}
                       for m in ("winner", "nominee_d", "nominee_r", "party")} for v in ("polymarket", "kalshi")},
        "implied": implied_rows(raw, views, names),
        "party_check": {v: cm.party_check(views[v], views["parties"]) for v in ("polymarket", "kalshi")},
        "history": price_history(views, tables, names),
        "announce": announce,
        "if_runs": if_runs_rows(raw, tables, announce, names),
        "long_view": long_view(names),
        "what_if": [{**row, "out": names[row["out"]], "biggest_gainer": names[row["biggest_gainer"]]} for row in base_what_if],
        "shocks": [{**s, "player": names[s["player"]], "responses": [{**r, "id": names[r["id"]]} for r in s["responses"]]} for s in shocks],
        "lanes": [{**r, "leader": names[r["leader"]], "chaser": names[r["chaser"]]}
                  for r in gt.lane_pressure(game, {**raw["nominee_d"], **raw["nominee_r"]})],
        "vp": [{**r, "nominee": names[r["nominee"]], "picks": [names[p["id"]] for p in r["picks"]]} for r in gt.vp_scores(game, raw)],
        "senate": seats,
        "state_markets": {code: price for code, price in read_optional(cm.LIVE_DIR / "poly_states.json").get("states", {}).items()
                          if price["spread"] <= MAX_STATE_SPREAD},
        "news": read_optional(HERE / "data" / "news" / "latest.json"),
        "house": lower_house,
        "electoral": raw["electoral"],
        "primary_states": {party: {code: [{"name": names.get(c, c), "p": p} for c, p in rows] for code, rows in states.items()}
                           for party, states in raw["primary_states"].items()},
        "funnel": {"D": funnel_rows(raw, names, "nominee_d"), "R": funnel_rows(raw, names, "nominee_r")},
        "power": [{"label": k, "model": v, "kalshi": (senate.latest_markets().get("power") or {}).get(k)}
                  for k, v in sorted(lower_house["outcomes"].items(), key=lambda kv: -kv[1])],
        "game": game_payload(game, game_worlds),
        "senate_markets": senate.latest_markets(),
        "senate_seat_check": senate.market_seat_check(seats, senate.latest_markets(), senate.load_map()),
        "matchups": [{**m, "dem": names.get(m["dem"], m["dem"]), "rep": names.get(m["rep"], m["rep"])} for m in raw["matchups"]],
        "ratings": [{**c, "name": names.get(c["id"], c["id"])} for c in json.loads(RATINGS.read_text(encoding="utf-8"))["candidates"]],
        "turns": [{"seq": t["seq"], "at": t["at"], "phase": t["phase"], "headline": t["headline"], "source": t["source"],
                   "party": t["odds"]["party"]["D"]} for t in logged_turns],
        "scorecard": forecasts.scorecard(make_price_lookup(views)),
        "environment": {"mean": game.env_mean, "sd": game.env_sd, "ec_bias": game.ec_bias},
    }


def read_optional(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def funnel_rows(raw: dict, names: dict, market: str, count: int = 8) -> list:
    """How each leading candidate survives each stage of the cycle."""
    leaders = sorted(raw[market], key=raw[market].get, reverse=True)[:count]
    return [{"name": names.get(c, c), "ran": raw["ran"][c], "past_early": raw["stages"][c]["past_early"],
             "past_super": raw["stages"][c]["past_super"], "nominee": raw[market][c], "winner": raw["winner"][c],
             "states_won": raw["states_won"][c],
             "if_won_early": raw["stages"][c]["nominee_if_won_early"]} for c in leaders]


def game_payload(game, game_worlds: dict | None = None) -> dict:
    """Everything the page's simulation needs, so its settings can't drift from Python's."""
    names = name_table()
    seat_map = senate.load_map()
    national = seat_map["national_2024_margin"]
    return {
        "env_mean": game.env_mean, "env_sd": game.env_sd, "worlds": game_worlds or {},
        "candidates": [{"id": c.id, "name": names.get(c.id, c.id), "party": c.party, "lane": c.lane, "strength": c.strength,
                        "p_run": c.p_run, "general": c.general, "defers_to": c.defers_to, "defer_prob": c.defer_prob,
                        "home": c.home} for c in game.candidates],
        "states": [{"code": s.code, "ev": s.ev, "lean": s.lean, "region": s.region} for s in game.states],
        "params": {"strength_sd": model.STRENGTH_SD, "contest_noise": model.CONTEST_NOISE, "stage_drift": model.STAGE_DRIFT,
                   "home_primary_edge": model.HOME_PRIMARY_EDGE, "lane_region": model.LANE_REGION, "lane_transfer": model.LANE_TRANSFER,
                   "general_noise": model.GENERAL_NOISE, "state_noise": model.STATE_NOISE, "region_noise": model.REGION_NOISE,
                   "home_edge": model.HOME_STATE_EDGE, "ev_to_win": model.EV_TO_WIN,
                   "stages": [{"name": s.name, "survivors": s.survivors, "momentum": s.momentum,
                               "contests": [{"code": c.code, "weight": c.weight, "region": c.region} for c in s.contests]}
                              for s in model.STAGES]},
        "senate": {"not_up_d": seat_map["not_up_in_2028"]["D"], "uncalled": [s["p_dem"] for s in seat_map["uncalled_2026"]["seats"]],
                   "ticket_effect": senate.TICKET_EFFECT, "seat_noise": senate.SEAT_NOISE,
                   "seats": [{"code": s["code"], "lean": s["pres_2024"] - national, "p_open": s.get("p_open", 0),
                              "edge": s["edge"] if s["party"] == "D" else -s["edge"]} for s in seat_map["seats"]]},
        "house": {"majority": house.MAJORITY, "seats_per_point": house.SEATS_PER_POINT, "majority_margin": house.MAJORITY_MARGIN,
                  "ticket_effect": house.TICKET_EFFECT, "vote_noise": house.HOUSE_VOTE_NOISE, "seat_noise": house.SEAT_NOISE},
    }


def write_page(data: dict) -> None:
    PAGE_DATA.parent.mkdir(parents=True, exist_ok=True)
    part = PAGE_DATA.with_suffix(".part")  # the Politics tab never sees a half-written file
    part.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    part.replace(PAGE_DATA)
    SUMMARY.write_text(json.dumps({
        "strategy": "political-game-machine", "generated_at": data["generated_at"],
        "headline": {"dem_president": data["party"]["D"], "dem_senate_control": data["senate"]["control_d"]},
        "scorecard": data["scorecard"]}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = build(log="--log" in sys.argv)
    write_page(result)
    print(f"Wrote {PAGE_DATA.relative_to(HERE)}")
