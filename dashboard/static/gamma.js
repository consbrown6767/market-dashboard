/* Gamma tab: the breakout tracker. Reads what collectors/strategy_collector.py logged. */
"use strict";

(() => {
  const GROUP_NAMES = { strong: "Strong prediction", prediction: "Prediction", no_prediction: "Held, no prediction", failed_hold: "Failed hold" };
  const POINTS = [["eod", "Same day"], ["next_day", "Next day"], ["three_days", "3 days"]];
  const LOG_FILTERS = [["all", "All"], ["predictions", "Predictions"], ["other", "Other breakouts"]];
  const RANGES = [["1", "1D"], ["5", "5D"]];
  const state = { symbol: null, days: "1", scoreMode: null, logFilter: "all", data: null, chart: null, drawn: null };

  const pctTo = (price, level) => (isNum(price) && isNum(level) ? (level / price - 1) * 100 : null);
  const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }) : "–");
  const dayName = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

  function rangeChips(el, items, active, onPick) {
    el.innerHTML = items.map(([v, l]) => `<button class="chip ${v === active ? "active" : ""}" data-v="${v}">${l}</button>`).join("");
    el.onclick = (e) => e.target.dataset.v && onPick(e.target.dataset.v);
  }

  function statusOf(lv) {
    if (lv.holding_since) return `<span class="badge stale">Holding since ${clock(lv.holding_since)}</span>`;
    const ev = lv.events[0]; // newest first
    if (ev?.group === "strong" || ev?.group === "prediction") return `<span class="badge fresh">${GROUP_NAMES[ev.group]}</span>`;
    if (ev) return `<span class="dim">${GROUP_NAMES[ev.group]}</span>`;
    if (isNum(lv.price) && lv.price > lv.call_wall) return `<span class="dim">Above wall</span>`;
    return `<span class="dim">Watching</span>`;
  }

  function drawSummary(d) {
    const events = d.events, predictions = events.filter((e) => e.kind === "prediction");
    const today = events.filter((e) => e.date === d.date);
    const live = events.filter((e) => e.mode === "live" && e.kind === "prediction");
    const liveGraded = live.filter((e) => e.grades.eod);
    const held = liveGraded.filter((e) => e.grades.eod.status === "held").length;
    const near = [...d.levels].filter((l) => isNum(l.price)).sort((a, b) => Math.abs(pctTo(a.price, a.call_wall)) - Math.abs(pctTo(b.price, b.call_wall)))[0];
    const stat = (label, value, sub = "") => `<div class="stat"><small>${label}</small><strong>${value}</strong><em>${sub}</em></div>`;
    $("#gm-stats").innerHTML =
      stat("Stocks watched", d.levels.length, `levels for ${dayName(d.date)}`) +
      stat("Breakouts that day", today.length, `${today.filter((e) => e.kind === "prediction").length} predictions`) +
      stat("Holding now", d.levels.filter((l) => l.holding_since).length, "in the 30-minute hold") +
      stat("Closest to its wall", near ? esc(near.symbol) : "–", near ? `${signed(pctTo(near.price, near.call_wall), 1)} to ${fixed(near.call_wall, 0)}` : "") +
      stat("Live predictions", live.length, `${d.live_days} live days logged`) +
      stat("Live held at close", liveGraded.length ? `${held} / ${liveGraded.length}` : "–", liveGraded.length ? "same-day check" : "none graded yet") +
      stat("Replay predictions", predictions.filter((e) => e.mode === "replay").length, `${d.replay_days} past days rerun`);
    $("#gm-date").textContent = `${dayName(d.date)} · bars through ${clock(d.last_bar)}`;
    const run = d.run;
    if (run) badge($("#gm-badge"), run.started_at, 15, run.status === "skipped" ? "Market closed" : `Checked ${ago(run.started_at)}`);
    else { $("#gm-badge").className = "badge stale"; $("#gm-badge").textContent = "Live job not run yet"; }
  }

  function drawLevels(d) {
    $("#gm-levels-n").textContent = d.levels.length;
    const rows = [...d.levels].sort((a, b) => Math.abs(pctTo(a.price, a.call_wall) ?? 1e9) - Math.abs(pctTo(b.price, b.call_wall) ?? 1e9));
    $("#gm-levels").innerHTML = `<table><thead><tr><th>Stock</th><th>Price</th><th>Call wall</th><th>To wall</th><th>Put wall</th><th>Gamma flip</th><th>Volume</th><th>Status</th></tr></thead><tbody>${rows.map((l) => {
      const above = isNum(l.gamma_flip) && isNum(l.price) ? l.price > l.gamma_flip : null;
      return `<tr class="clickable ${l.symbol === state.symbol ? "selected" : ""}" data-symbol="${esc(l.symbol)}"><td><b>${esc(l.symbol)}</b></td><td>${fixed(l.price)}</td><td>${fixed(l.call_wall, 0)}</td>
        <td class="${pctTo(l.price, l.call_wall) <= 0 ? "pos" : ""}">${signed(pctTo(l.price, l.call_wall), 1)}</td><td>${fixed(l.put_wall, 0)}</td>
        <td class="${above == null ? "dim" : above ? "pos" : "neg"}" title="${above == null ? "No flip found: dealer gamma doesn't change sign within 30% of the price" : `Price is ${above ? "above" : "below"} the flip`}">${isNum(l.gamma_flip) ? fixed(l.gamma_flip, 1) : "none"}</td>
        <td>${isNum(l.volume_ratio) ? `${l.volume_ratio.toFixed(2)}×` : "–"}</td><td>${statusOf(l)}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function drawLive(d) {
    const live = d.levels.filter((l) => l.holding_since);
    $("#gm-live-n").textContent = live.length;
    $("#gm-live").innerHTML = live.length
      ? `<table><thead><tr><th>Stock</th><th>Broke out</th><th>At</th><th>Wall</th><th>Now</th><th>Volume</th></tr></thead><tbody>${live.map((l) => `<tr class="clickable" data-symbol="${esc(l.symbol)}"><td><b>${esc(l.symbol)}</b></td><td>${clock(l.holding_since)}</td><td>${fixed(l.holding_price)}</td><td>${fixed(l.call_wall, 0)}</td><td>${fixed(l.price)}</td><td>${isNum(l.volume_ratio) ? `${l.volume_ratio.toFixed(2)}×` : "–"}</td></tr>`).join("")}</tbody></table>`
      : `<p class="note" style="margin:0">No stock is in a hold right now.</p>`;
  }

  function drawScore(d) {
    const hasLive = d.events.some((e) => e.mode === "live");
    state.scoreMode ??= hasLive ? "live" : "replay";
    const live = d.scorecard.live, replay = d.scorecard.replay;
    rangeChips($("#gm-score-mode"), [["live", "Live forward test"], ["replay", "Replay"]], state.scoreMode, (v) => { state.scoreMode = v; drawScore(d); });
    const table = state.scoreMode === "live" ? live : replay;
    const cell = (c) => `<td>${c.graded ? `${c.held} / ${c.graded}` : "–"}</td><td class="${cls(c.avg_move)}">${signed(c.avg_move, 2)}</td>`;
    $("#gm-score").innerHTML = `<table><thead><tr><th>Breakout type</th><th>Count</th>${POINTS.map(([, l]) => `<th>${l}: held</th><th>Avg move</th>`).join("")}</tr></thead><tbody>${Object.entries(GROUP_NAMES)
      .map(([k, name]) => `<tr><td>${name}</td><td>${table[k].count}</td>${POINTS.map(([p]) => cell(table[k][p])).join("")}</tr>`).join("")}</tbody></table>`;
    $("#gm-score-note").textContent = state.scoreMode === "live"
      ? "Held means no 5-minute bar closed below the wall before the check. Average move is from the price when the hold finished. Compare the rows: predictions need to beat the other breakouts."
      : `Replay: the same rules run after the fact on ${d.replay_days} past days. A sample this small proves nothing either way, and it's not part of the forward test.`;
  }

  function gradeCell(e, point) {
    const g = e.grades[point];
    if (!g) return `<td class="dim">–</td>`;
    return `<td class="${g.status === "held" ? "pos" : "neg"}">${g.status === "held" ? "Held" : "Wrong"} ${signed(g.pct_move, 1)}</td>`;
  }

  function drawLog(d) {
    rangeChips($("#gm-log-filter"), LOG_FILTERS, state.logFilter, (v) => { state.logFilter = v; drawLog(d); });
    const events = d.events.filter((e) => state.logFilter === "all" || (state.logFilter === "predictions") === (e.kind === "prediction"));
    $("#gm-log-n").textContent = events.length;
    $("#gm-log").innerHTML = events.length
      ? `<table><thead><tr><th>Day</th><th>Stock</th><th>Type</th><th>Score</th><th>Wall</th><th>Broke out</th><th>Decided</th><th>Price</th><th>Volume</th><th>Same day</th><th>Next day</th><th>3 days</th><th>Why not / notes</th></tr></thead><tbody>${events.map((e) => `<tr class="clickable" data-symbol="${esc(e.symbol)}">
        <td>${dayName(e.date)}${e.mode === "replay" ? ' <span class="dim">replay</span>' : ""}</td><td><b>${esc(e.symbol)}</b></td><td>${GROUP_NAMES[e.group]}</td><td>${e.kind === "failed_hold" ? "–" : e.score}</td><td>${fixed(e.call_wall, 0)}</td>
        <td>${clock(e.breakout_time)}</td><td>${clock(e.decision_time)}</td><td>${fixed(e.decision_price)}</td><td>${isNum(e.volume_ratio) ? `${e.volume_ratio.toFixed(2)}×` : "–"}</td>
        ${POINTS.map(([p]) => gradeCell(e, p)).join("")}<td class="dim" style="text-align:left">${esc([...e.reasons, ...e.notes].join("; "))}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty" style="padding:16px">Nothing logged here yet.</div>`;
  }

  async function drawChart() {
    // The page refreshes every minute: only redraw for new bars, so zooming in on the chart lasts.
    const key = `${state.symbol}|${state.days}|${state.data?.last_bar}`;
    if (!state.symbol || key === state.drawn) return;
    state.drawn = key;
    const d = await api(`/api/gamma_bars?symbol=${encodeURIComponent(state.symbol)}&days=${state.days}`);
    $("#gm-chart-title").textContent = `${d.symbol} · 5-minute`;
    rangeChips($("#gm-range"), RANGES, state.days, (v) => { state.days = v; drawChart().catch(showError); });
    if (state.chart) { state.chart.remove(); state.chart = null; }
    const el = $("#gm-chart");
    if (!d.bars.length) { el.innerHTML = `<div class="empty" style="padding:16px">No bars for ${esc(d.symbol)} yet.</div>`; return; }
    const ch = state.chart = makeChart(el, { timeScale: { borderColor: css("--border"), timeVisible: true, secondsVisible: false } });
    const series = ch.addCandlestickSeries({ upColor: css("--normal"), downColor: css("--critical"), borderVisible: false, wickUpColor: css("--normal"), wickDownColor: css("--critical") });
    series.setData(d.bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    const lv = d.levels, lines = [];
    if (lv) {
      for (const [price, color, title] of [[lv.call_wall, css("--normal"), "Call wall"], [lv.put_wall, css("--critical"), "Put wall"], [lv.gamma_flip, css("--elevated"), "Gamma flip"]]) {
        if (!isNum(price)) continue;
        series.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title });
        lines.push(`<span><i style="background:${color}"></i>${title} ${fixed(price, price < 1000 ? 1 : 0)}</span>`);
      }
    }
    const marks = d.events.flatMap((e) => {
      const made = e.kind === "prediction", color = made ? css("--normal") : css("--text-muted");
      return [{ time: e.breakout, position: "belowBar", color, shape: "arrowUp", text: made ? (e.strong ? "Strong" : "Prediction") : "" }];
    }).sort((a, b) => a.time - b.time);
    series.setMarkers(marks);
    $("#gm-legend").innerHTML = lines.join("");
    $("#gm-chart-sub").textContent = lv ? `sector ${lv.sector} · levels for ${dayName(lv.date)}` : "";
    ch.timeScale().fitContent();
  }
  // The chart can be built before its panel settles at full size, so fit the bars again on resize.
  new ResizeObserver(() => state.chart?.timeScale().fitContent()).observe($("#gm-chart"));

  function pick(symbol) {
    state.symbol = symbol;
    if (state.data) drawLevels(state.data);
    drawChart().catch(showError);
  }
  for (const id of ["#gm-levels", "#gm-log", "#gm-live"]) {
    $(id).addEventListener("click", (e) => { const s = e.target.closest("[data-symbol]")?.dataset.symbol; if (s) pick(s); });
  }

  loaders.gamma = async () => {
    const d = await api("/api/gamma");
    if (!d.ready) {
      $("#gm-levels").innerHTML = `<div class="empty" style="padding:16px">No levels yet. They appear after the first run on a trading day.</div>`;
      return;
    }
    const first = !state.data;
    state.data = d;
    if (first || !d.levels.some((l) => l.symbol === state.symbol)) state.symbol = d.levels[0]?.symbol ?? null;
    drawSummary(d); drawLevels(d); drawLive(d); drawScore(d); drawLog(d);
    await drawChart();
  };
})();
