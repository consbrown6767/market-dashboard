// The same simulation as model.py, senate.py and house.py, so the dashboard's game can run live.
// test_engine.py checks that it agrees with the Python version. Change both together.

function makeRandom(seed) {
  let state = seed >>> 0, spare = null;
  const next = () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  next.gauss = (mean, sd) => {
    if (spare !== null) { const v = spare; spare = null; return mean + sd * v; }
    const u = 1 - next(), w = next(), radius = Math.sqrt(-2 * Math.log(u));
    spare = radius * Math.sin(2 * Math.PI * w);
    return mean + sd * radius * Math.cos(2 * Math.PI * w);
  };
  return next;
}

function applyChoices(game, choices) {
  // choices: {env: points, people: {id: {status: "in"|"out", multiplier: 1.2}}}
  const people = (choices && choices.people) || {};
  return {
    env: game.env_mean + ((choices && choices.env) || 0),
    candidates: game.candidates.map(c => {
      const pick = people[c.id] || {};
      return {
        ...c,
        p_run: pick.status === "in" ? 1 : pick.status === "out" ? 0 : c.p_run,
        strength: c.strength + Math.log(pick.multiplier || 1),
        defer_prob: pick.status === "in" ? 0 : c.defer_prob,  // someone certain to run isn't deferring
      };
    }),
  };
}

// Raw, Market and Weighted are one game. A world swaps only the numbers: who's strong, who runs,
// and the mood. Players, calendar and rules stay the same. worlds.py fits these numbers.
function worldGame(game, name) {
  const world = game.worlds && game.worlds[name];
  if (!world) return game;
  return {
    ...game, env_mean: world.env_mean, senate_shift: world.senate_shift, house_shift: world.house_shift,
    candidates: game.candidates.map(c => ({ ...c, ...world.people[c.id] })),
  };
}

function drawField(random, candidates) {
  const running = {};
  const ordered = [...candidates.filter(c => !c.defers_to), ...candidates.filter(c => c.defers_to)];
  for (const c of ordered) {
    const p = running[c.defers_to] ? c.p_run * (1 - c.defer_prob) : c.p_run;
    running[c.id] = random() < p;
  }
  return candidates.filter(c => running[c.id]);
}

function startPrimary(random, field, params) {
  const race = { scores: {}, people: {}, delegates: {}, active: field.map(c => c.id), stage: 0 };
  for (const c of field) {
    race.scores[c.id] = c.strength + random.gauss(0, params.strength_sd);
    race.people[c.id] = c;
    race.delegates[c.id] = 0;
  }
  return race;
}

function playStage(random, race, params) {
  const number = race.stage, stage = params.stages[number], { scores, people, delegates } = race;
  if (number) for (const id of race.active) scores[id] += random.gauss(0, params.stage_drift);
  const party = people[race.active[0]].party, regional = params.lane_region[party] || {}, power = party === "D" ? 1 : 2;
  const windowVotes = {}, contests = [];
  let totalWeight = 0;
  for (const id of race.active) windowVotes[id] = 0;
  for (const contest of stage.contests) {
    const votes = {};
    let total = 0, winner = null;
    for (const id of race.active) {
      const person = people[id], lane = regional[person.lane] || {};
      let score = scores[id] + (lane[contest.region] || 0) + random.gauss(0, params.contest_noise);
      if (person.home === contest.code) score += params.home_primary_edge;
      votes[id] = Math.exp(score);
      total += votes[id];
      if (winner === null || votes[id] > votes[winner]) winner = id;
    }
    let delegateTotal = 0;
    for (const id of race.active) delegateTotal += (votes[id] / total) ** power;
    for (const id of race.active) {
      windowVotes[id] += contest.weight * votes[id] / total;
      delegates[id] += contest.weight * (votes[id] / total) ** power / delegateTotal;
    }
    totalWeight += contest.weight;
    contests.push([contest.code, winner]);
  }
  const shares = {};
  for (const id of race.active) shares[id] = windowVotes[id] / totalWeight;
  const ranked = [...race.active].sort((a, b) => shares[b] - shares[a]);
  scores[ranked[0]] += stage.momentum;
  if (ranked.length > 1) scores[ranked[1]] += stage.momentum / 3;
  const kept = ranked.slice(0, stage.survivors), dropped = ranked.slice(stage.survivors);
  for (const out of dropped) {
    for (const id of kept) if (people[id].lane === people[out].lane) scores[id] += params.lane_transfer * shares[out];
  }
  race.active = kept;
  race.stage++;
  return { results: ranked.map(id => [id, shares[id]]), dropped, contests };
}

function nomineeOf(race) {
  return race.active.reduce((a, b) => (race.delegates[b] > race.delegates[a] ? b : a));
}

function finishPrimary(random, race, params) {
  while (race.stage < params.stages.length) playStage(random, race, params);
  return nomineeOf(race);
}

function electoralVotes(random, states, margin, dem, rep, params, wins) {
  const regions = {};
  let votes = 0;
  for (const s of states) {
    if (!(s.region in regions)) regions[s.region] = random.gauss(0, params.region_noise);
    let result = s.lean + margin + regions[s.region] + random.gauss(0, params.state_noise);
    if (s.code === dem.home) result += params.home_edge;
    if (s.code === rep.home) result -= params.home_edge;
    if (result > 0) { votes += s.ev; if (wins) wins[s.code] = (wins[s.code] || 0) + 1; }
  }
  return votes;
}

function playGeneral(random, game, environment, dem, rep, stateWins, seatWins) {
  const params = game.params, senate = game.senate, house = game.house;
  const margin = environment + dem.general - rep.general + random.gauss(0, params.general_noise);
  const votes = electoralVotes(random, game.states, margin, dem, rep, params, stateWins);
  const demWon = votes >= params.ev_to_win;
  const ticket = environment + senate.ticket_effect * (margin - environment);
  let seats = senate.not_up_d;
  for (const p of senate.uncalled) if (random() < p) seats++;
  for (const seat of senate.seats) {
    const advantage = random() < seat.p_open ? 0 : seat.edge;
    if (seat.lean + advantage + ticket + (game.senate_shift || 0) + random.gauss(0, senate.seat_noise) > 0) {
      seats++;
      if (seatWins) seatWins[seat.code] = (seatWins[seat.code] || 0) + 1;
    }
  }
  const houseVote = environment + house.ticket_effect * (margin - environment) + (game.house_shift || 0) + random.gauss(0, house.vote_noise);
  const houseSeats = Math.round(house.majority + house.seats_per_point * (houseVote - house.majority_margin) + random.gauss(0, house.seat_noise));
  return { margin, votes, demWon, seats, senateDem: seats >= 51 || (seats === 50 && demWon), houseSeats, houseDem: houseSeats >= house.majority };
}

function newTally() {
  return { nominee_d: {}, nominee_r: {}, winner: {}, ran: {}, party: 0, senate: 0, seats: 0, house: 0, ev: 0 };
}

function count(bucket, id) { bucket[id] = (bucket[id] || 0) + 1; }

function record(tally, dem, rep, result) {
  count(tally.nominee_d, dem.id);
  count(tally.nominee_r, rep.id);
  count(tally.winner, result.demWon ? dem.id : rep.id);
  tally.party += result.demWon;
  tally.senate += result.senateDem;
  tally.seats += result.seats;
  tally.house += result.houseDem;
  tally.ev += result.votes;
}

function summarize(tally, runs, stateWins, seatWins) {
  const share = bucket => Object.fromEntries(Object.entries(bucket || {}).map(([k, v]) => [k, v / runs]));
  return {
    party_d: tally.party / runs, ev_mean: tally.ev / runs, senate_d: tally.senate / runs, senate_seats: tally.seats / runs,
    house_d: tally.house / runs, nominee_d: share(tally.nominee_d), nominee_r: share(tally.nominee_r),
    winner: share(tally.winner), ran: share(tally.ran), states: share(stateWins), seats: share(seatWins),
  };
}

function simulateGame(game, choices, runs, seed) {
  const random = makeRandom(seed || 2028), params = game.params;
  const { env, candidates } = applyChoices(game, choices);
  const dems = candidates.filter(c => c.party === "D"), reps = candidates.filter(c => c.party === "R");
  const tally = newTally(), stateWins = {}, seatWins = {};
  for (let i = 0; i < runs; i++) {
    const environment = random.gauss(env, game.env_sd);
    const demField = drawField(random, dems), repField = drawField(random, reps);
    for (const c of [...demField, ...repField]) count(tally.ran, c.id);
    const demId = finishPrimary(random, startPrimary(random, demField, params), params);
    const repId = finishPrimary(random, startPrimary(random, repField, params), params);
    const dem = demField.find(c => c.id === demId), rep = repField.find(c => c.id === repId);
    record(tally, dem, rep, playGeneral(random, game, environment, dem, rep, stateWins, seatWins));
  }
  return summarize(tally, runs, stateWins, seatWins);
}

// SEASON MODE: play one cycle a turn at a time. The real outcome stays hidden, and after each
// turn the odds are recomputed from only what has been revealed so far.

// Share of national-mood uncertainty gone after each turn: a fifth at the start, all of it by election night.
function moodResolved(game, turn) { return 0.2 + 0.8 * (turn - 1) / (seasonTotalTurns(game) - 1); }

function newSeason(game, choices, seed) {
  const { env, candidates } = applyChoices(game, choices);
  return { game, seed, random: makeRandom(seed), turn: 0, knownEnv: env, resolved: 0, candidates, fields: null, races: null, outcome: null };
}

function moveMood(season, target) {
  season.knownEnv += season.random.gauss(0, season.game.env_sd * Math.sqrt(target - season.resolved));
  season.resolved = target;
}

function seasonTotalTurns(game) { return game.params.stages.length + 3; }

function seasonNext(season) {
  const { game, random } = season, params = game.params, stages = params.stages.length;
  season.turn++;
  moveMood(season, moodResolved(game, season.turn));
  if (season.turn === 1) {
    const dems = season.candidates.filter(c => c.party === "D"), reps = season.candidates.filter(c => c.party === "R");
    season.fields = { D: drawField(random, dems), R: drawField(random, reps) };
    season.races = { D: startPrimary(random, season.fields.D, params), R: startPrimary(random, season.fields.R, params) };
    return { kind: "field", fields: season.fields };
  }
  if (season.turn <= stages + 1) {
    return { kind: "stage", number: season.turn - 2, D: playStage(random, season.races.D, params), R: playStage(random, season.races.R, params) };
  }
  const dem = season.fields.D.find(c => c.id === nomineeOf(season.races.D));
  const rep = season.fields.R.find(c => c.id === nomineeOf(season.races.R));
  if (season.turn === stages + 2) return { kind: "conventions", dem, rep };
  season.outcome = { ...playGeneral(random, game, season.knownEnv, dem, rep), dem, rep };
  return { kind: "general", ...season.outcome };
}

function seasonExit(season, id) {
  // A forced exit. Lane-mates pick up a little, as they do when someone drops out.
  for (const party of ["D", "R"]) {
    const race = season.races && season.races[party];
    if (!race || !race.active.includes(id) || race.active.length < 2) continue;
    race.active = race.active.filter(x => x !== id);
    season.fields[party] = season.fields[party].filter(c => c.id !== id || race.stage > 0);
    if (race.stage > 0) for (const other of race.active) if (race.people[other].lane === race.people[id].lane) race.scores[other] += 0.2;
    return true;
  }
  return false;
}

function seasonForecast(season, runs, lens) {
  // lens is another world's game. It re-prices this same season and never changes what happened.
  // Worlds disagree about what's still unknown, so a gap in strength fades as votes come in and a
  // gap in mood fades as the mood is revealed. By the end they're all looking at the same facts.
  const game = lens || season.game, params = game.params, own = season.game;
  const random = makeRandom(season.seed * 31 + 9973 * (season.turn + 1)), tally = newTally();
  const leftover = game.env_sd * Math.sqrt(1 - season.resolved);
  const mood = season.knownEnv + (game.env_mean - own.env_mean) * (1 - season.resolved);
  const theirs = Object.fromEntries(game.candidates.map(c => [c.id, c]));
  const ours = Object.fromEntries(own.candidates.map(c => [c.id, c]));
  const gap = id => theirs[id].strength - ours[id].strength;
  const see = c => (lens ? { ...c, strength: c.strength + gap(c.id), p_run: theirs[c.id].p_run, general: theirs[c.id].general } : c);
  const dems = season.candidates.filter(c => c.party === "D").map(see), reps = season.candidates.filter(c => c.party === "R").map(see);
  const pick = (party, pool) => {
    if (!season.races) {
      const field = drawField(random, pool);
      const winner = finishPrimary(random, startPrimary(random, field, params), params);
      return field.find(c => c.id === winner);
    }
    const known = season.races[party], seen = season.fields[party].map(see);
    const field = seen.filter(c => known.active.includes(c.id) || known.stage === 0);
    const fade = lens ? 1 - known.stage / params.stages.length : 0;
    const scores = Object.fromEntries(Object.entries(known.scores).map(([id, score]) => [id, score + (fade && gap(id) * fade)]));
    // Before any votes, a candidate's true strength is still hidden, so redraw it.
    const race = known.stage === 0 ? startPrimary(random, field, params)
      : { ...known, scores, delegates: { ...known.delegates }, active: [...known.active] };
    const winner = finishPrimary(random, race, params);
    return seen.find(c => c.id === winner);
  };
  for (let i = 0; i < runs; i++) {
    const environment = mood + random.gauss(0, leftover);
    const dem = pick("D", dems), rep = pick("R", reps);
    record(tally, dem, rep, playGeneral(random, game, environment, dem, rep));
  }
  return summarize(tally, runs);
}

if (typeof module !== "undefined") module.exports = { worldGame, simulateGame, newSeason, seasonNext, seasonForecast, seasonExit, seasonTotalTurns };
