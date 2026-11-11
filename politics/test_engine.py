"""Checks that the dashboard's JavaScript simulation agrees with the Python model."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import house
import run_all
import senate
import turns
from model import simulate, with_changes

HERE = Path(__file__).resolve().parent
RUNS = 20000
TOLERANCE = 0.02  # two independent random streams of 20,000 runs differ by about 1 point at most


def run_engine(payload: dict, choices: dict) -> dict:
    script = ("const {simulateGame}=require(process.argv[1]);const fs=require('fs');"
              "const p=JSON.parse(fs.readFileSync(process.argv[2]));"
              f"console.log(JSON.stringify(simulateGame(p.game,p.choices,{RUNS},7)));")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.json"
        path.write_text(json.dumps({"game": payload, "choices": choices}), encoding="utf-8")
        output = subprocess.run(["node", "-e", script, str(HERE / "game_engine.js"), str(path)],
                                capture_output=True, text=True, check=True).stdout
    return json.loads(output)


def run_python(game) -> dict:
    result = simulate(game, runs=RUNS, keep_draws=True)
    seats = senate.simulate_senate(senate.load_map(), result["draws"])
    result["senate"] = seats
    result["house"] = house.simulate_house(result["draws"], seats["control_by_race"])
    return result


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class EngineTests(unittest.TestCase):
    def compare(self, game, choices):
        js, py = run_engine(run_all.game_payload(turns.current_game()), choices), run_python(game)
        self.assertAlmostEqual(js["party_d"], py["party"]["D"], delta=TOLERANCE)
        self.assertAlmostEqual(js["senate_d"], py["senate"]["control_d"], delta=TOLERANCE)
        self.assertAlmostEqual(js["senate_seats"], py["senate"]["dem_seats_mean"], delta=0.3)
        self.assertAlmostEqual(js["house_d"], py["house"]["control_d"], delta=TOLERANCE)
        for market in ("nominee_d", "nominee_r"):
            for name, odds in py[market].items():
                self.assertAlmostEqual(js[market].get(name, 0), odds, delta=TOLERANCE, msg=name)
        for code, odds in py["electoral"]["states"].items():
            self.assertAlmostEqual(js["states"].get(code, 0), odds, delta=TOLERANCE, msg=code)

    def test_engine_matches_python_at_baseline(self):
        self.compare(turns.current_game(), {})

    def test_engine_matches_python_with_senate_and_house_shifts(self):
        game = turns.current_game()
        payload = {**run_all.game_payload(game), "senate_shift": -2, "house_shift": 1}
        js, draws = run_engine(payload, {}), simulate(game, runs=RUNS, keep_draws=True)["draws"]
        seats = senate.simulate_senate(senate.load_map(), draws, shift=-2)
        self.assertAlmostEqual(js["senate_d"], seats["control_d"], delta=TOLERANCE)
        self.assertAlmostEqual(js["house_d"], house.simulate_house(draws, seats["control_by_race"], shift=1)["control_d"], delta=TOLERANCE)

    def test_engine_matches_python_after_changes(self):
        game = with_changes(turns.current_game(), p_run={"jd-vance": 0.0, "jon-ossoff": 1.0},
                            strength_shift={"gavin-newsom": 0.5}, env_shift=-2.0)
        import math
        game = with_changes(game, strength_shift={"gavin-newsom": math.log(1.5) - 0.5})
        choices = {"env": -2, "people": {"jd-vance": {"status": "out"}, "jon-ossoff": {"status": "in"},
                                         "gavin-newsom": {"multiplier": 1.5}}}
        self.compare(game, choices)


SEASON_SCRIPT = """
const e=require(process.argv[1]),fs=require('fs'),game=JSON.parse(fs.readFileSync(process.argv[2]));
const seasons=1500,turns=e.seasonTotalTurns(game),sums=Array(turns+1).fill(0);let won=0,ended=0;
for(let i=0;i<seasons;i++){const s=e.newSeason(game,{},1000+i);sums[0]+=e.seasonForecast(s,40).party_d;
  for(let t=1;t<turns;t++){e.seasonNext(s);sums[t]+=e.seasonForecast(s,40).party_d}
  const last=e.seasonNext(s);won+=last.demWon?1:0;ended+=s.outcome?1:0}
console.log(JSON.stringify({means:sums.slice(0,turns).map(v=>v/seasons),won:won/seasons,ended:ended/seasons}));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SeasonTests(unittest.TestCase):
    def test_odds_stay_honest_turn_by_turn(self):
        # If the odds at each turn are fair, then averaged over many seasons they should stay near
        # the starting odds and match how often Democrats actually win.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.json"
            path.write_text(json.dumps(run_all.game_payload(turns.current_game())), encoding="utf-8")
            output = subprocess.run(["node", "-e", SEASON_SCRIPT, str(HERE / "game_engine.js"), str(path)],
                                    capture_output=True, text=True, check=True).stdout
        result = json.loads(output)
        self.assertEqual(result["ended"], 1)
        for mean in result["means"]:
            self.assertAlmostEqual(mean, result["means"][0], delta=0.035)
        self.assertAlmostEqual(result["won"], result["means"][0], delta=0.04)


WORLD_SCRIPT = """
const e=require(process.argv[1]),fs=require('fs'),game=JSON.parse(fs.readFileSync(process.argv[2]));
const other=e.worldGame(game,'test'),turns=e.seasonTotalTurns(game);
const play=(seed,peek)=>{const s=e.newSeason(game,{},seed),events=[];
  for(let t=0;t<turns;t++){if(peek)e.seasonForecast(s,30,other);events.push(JSON.stringify(e.seasonNext(s)))}return events};
const seasons=300,gaps=Array(turns).fill(0);
for(let i=0;i<seasons;i++){const s=e.newSeason(game,{},500+i);
  for(let t=0;t<turns;t++){gaps[t]+=Math.abs(e.seasonForecast(s,60).party_d-e.seasonForecast(s,60,other).party_d)/seasons;e.seasonNext(s)}}
const s=e.newSeason(game,{},7),plain=e.seasonForecast(s,200),own=e.seasonForecast(s,200,game);
console.log(JSON.stringify({same:JSON.stringify(play(11,false))===JSON.stringify(play(11,true)),gaps,ownMatches:plain.party_d===own.party_d,
  ids:other.candidates.map(c=>c.id).join()===game.candidates.map(c=>c.id).join(),lanes:other.candidates.map(c=>c.lane).join()===game.candidates.map(c=>c.lane).join()}));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game = turns.current_game()
        payload = run_all.game_payload(game)
        people = {c.id: {"strength": c.strength + (1.0 if c.party == "D" else -0.5), "p_run": c.p_run, "general": c.general - 1}
                  for c in game.candidates}
        payload["worlds"] = {"test": {"env_mean": game.env_mean - 3, "senate_shift": -2, "house_shift": 1, "people": people}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = subprocess.run(["node", "-e", WORLD_SCRIPT, str(HERE / "game_engine.js"), str(path)],
                                    capture_output=True, text=True, check=True).stdout
        cls.result = json.loads(output)

    def test_a_world_changes_numbers_and_nothing_else(self):
        self.assertTrue(self.result["ids"])
        self.assertTrue(self.result["lanes"])

    def test_looking_through_another_world_never_changes_what_happens(self):
        self.assertTrue(self.result["same"])

    def test_a_seasons_own_world_gives_its_normal_odds(self):
        self.assertTrue(self.result["ownMatches"])

    def test_worlds_draw_together_as_the_season_plays_out(self):
        gaps = self.result["gaps"]
        self.assertLess(gaps[-2], gaps[0] * 0.7)


if __name__ == "__main__":
    unittest.main()
