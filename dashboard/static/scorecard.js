/* Scorecard tab: every model's record in one place. New models write to the prediction ledger
   (collectors/ledger.py); the gamma tracker and the political machine keep their own records. */
"use strict";

(() => {
  // Models the ledger knows by name. A planned model shows as a placeholder until its first prediction.
  const MODELS = {
    "spx-move": { name: "S&P 500 move size", what: "How big tomorrow's S&P 500 move will be (a range, not a direction)", planned: true },
    "stock-direction": { name: "Stock direction", what: "Each week, the chance each S&P 100 stock beats SPY over the next week (from options prices and last week's move)", planned: true,
      // Versions ending "@sp400" cover the 400 other S&P 500 stocks.
      whatFor: v => v.endsWith("@sp400") ? "Each week, the chance each of the other 400 S&P 500 stocks beats SPY over the next week (from options prices)" : null },
  };
  const BASELINE_NAMES = { recent: "Recent moves", vix: "VIX implied move", wide: "Wide range", base_rate: "Base rate (how often stocks beat SPY)", price_only: "Last week's move only" };
  const VERDICTS = { better: ["fresh", "Beats it"], worse: ["down", "Worse"], "no clear difference": ["stale", "No clear difference"], "too few": ["", "Too few to judge"] };
  const state = { recentMode: "all" };

  // A bare date ("2026-11-09") would be read as UTC midnight, the evening before in New York.
  const day = (ts) => (ts ? new Date(ts.length === 10 ? `${ts}T12:00:00-05:00` : ts).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric" }) : "–");
  const pctText = (x, d = 0) => (isNum(x) ? `${(x * 100).toFixed(d)}%` : "–");
  const verdict = (v, n, min) => {
    const [kind, label] = VERDICTS[v] || ["", esc(v)];
    return `<span class="badge ${kind}">${label}</span>${v === "too few" && isNum(n) ? ` <span class="dim">${n} / ${min}</span>` : ""}`;
  };

  function forecastText(kind, f) {
    if (kind === "probability") return pctText(f.p);
    const q = f.q, lo = q["0.05"], hi = q["0.95"], mid = q["0.5"];
    if (isNum(lo) && isNum(hi)) return `90%: ${signed(lo, 2)} to ${signed(hi, 2)}${isNum(mid) ? ` <span class="dim">mid ${signed(mid, 2)}</span>` : ""}`;
    return Object.entries(q).map(([k, v]) => `${(k * 100).toFixed(0)}%: ${fixed(v)}`).join(" · ");
  }

  // ---------- one table, a row per model (and per baseline for ledger models)
  function ledgerRows(d) {
    const rows = [], seen = new Set();
    for (const m of d.ledger?.models ?? []) {
      seen.add(m.model);
      const info = MODELS[m.model] || { name: m.model, what: "" };
      const bases = Object.entries(m.baselines);
      const first = `<td><b>${esc(info.name)}</b> <span class="dim">v${esc(m.version)}${m.mode === "backtest" ? " · backtest" : ""}</span></td>
        <td class="wrap">${esc((info.whatFor && info.whatFor(m.version)) || info.what)}</td><td>${m.mode === "backtest" ? `<span class="dim">tested from<br>${day(m.first)}</span>` : day(m.first)}</td>
        <td>${m.logged.toLocaleString("en-US")}</td><td>${m.resolved.toLocaleString("en-US")}</td>`;
      if (!bases.length) {
        rows.push(`<tr>${first}<td class="dim">–</td><td class="dim">–</td><td>${verdict("too few", m.resolved, d.min_resolved)}</td><td>${ledgerBadge(d, m.mode)}</td></tr>`);
        continue;
      }
      bases.forEach(([name, b], i) => {
        const lead = i === 0 ? first : `<td></td><td></td><td></td><td></td><td></td>`;
        const better = isNum(b.skill) ? `${Math.abs(b.skill * 100).toFixed(0)}% ${b.skill >= 0 ? "smaller" : "bigger"} error` : "–";
        rows.push(`<tr>${lead}<td>${isNum(b.model_loss) ? better : "–"}</td><td>${esc(BASELINE_NAMES[name] || name)}</td>
          <td>${verdict(b.verdict, b.resolved, d.min_resolved)}</td><td>${i === 0 ? ledgerBadge(d, m.mode) : ""}</td></tr>`);
      });
    }
    for (const [id, info] of Object.entries(MODELS)) {
      if (info.planned && !seen.has(id)) {
        rows.push(`<tr class="dim"><td><b>${esc(info.name)}</b></td><td class="wrap">${esc(info.what)}</td><td>Not started</td><td>–</td><td>–</td><td>–</td><td>–</td>
          <td><span class="badge">Planned</span></td><td>Prediction ledger</td></tr>`);
      }
    }
    return rows;
  }

  function ledgerBadge(d, mode) {
    if (mode === "backtest") return `<span class="dim">Backtest, rerunnable</span>`;
    const v = d.ledger?.verify;
    return v ? `<span class="badge ${v.ok ? "fresh" : "down"}" title="${esc(v.problems.join("\n"))}">Chained · ${v.ok ? "check ok" : "BROKEN"}</span>` : "";
  }

  function gammaRow(d) {
    const g = d.gamma;
    if (!g.ready) return `<tr><td><b>Gamma breakout tracker</b></td><td colspan="8" class="dim">No live data yet</td></tr>`;
    const t = g.table, preds = ["strong", "prediction"];
    const graded = preds.reduce((s, k) => s + t[k].eod.graded, 0), held = preds.reduce((s, k) => s + t[k].eod.held, 0);
    const other = t.no_prediction.eod;
    const share = (h, n) => (n ? `${h} / ${n} held <span class="dim">(${Math.round((h / n) * 100)}%)</span>` : "none graded yet");
    return `<tr><td><b>Gamma breakout tracker</b> <span class="dim">live</span></td>
      <td class="wrap">Whether a breakout above the call wall keeps holding (checked at the close, next close and 3 closes later)</td>
      <td>${day(g.first_live)}</td><td>${g.predictions} <span class="dim">of ${g.breakouts} breakouts</span></td><td>${graded}</td>
      <td>${share(held, graded)}</td><td class="wrap">Breakouts that held 30 min but missed the filters: ${share(other.held, other.graded)}</td>
      <td>${verdict("too few", graded, d.min_resolved)}</td><td><span class="dim">Own log, rules agreed with you</span></td></tr>`;
  }

  function politicsRow(d) {
    const p = d.politics;
    if (!p.ready) return `<tr><td><b>Political game machine</b></td><td colspan="8" class="dim">No data yet</td></tr>`;
    const b = p.brier || {}, mine = b.raw || b["raw-draft"], market = b.market;
    const score = (x) => (x ? `Brier ${x.brier.toFixed(3)} <span class="dim">(${x.questions} questions)</span>` : "none resolved yet");
    return `<tr><td><b>Political game machine</b></td>
      <td class="wrap">Chances of election outcomes: 2026 seats still open, 2028 nominations, President, Senate and House</td>
      <td>${day(p.first_forecast)}</td><td>${big(p.forecasts)} <span class="dim">on ${p.open_questions + p.resolved} questions</span></td><td>${p.resolved}</td>
      <td>${score(mine)}</td><td class="wrap">Market prices (Kalshi, Polymarket): ${score(market)}</td>
      <td>${verdict("too few", p.resolved, d.min_resolved)}</td>
      <td><span class="badge ${p.tamper_check === "ok" ? "fresh" : "down"}">Chained · ${p.tamper_check === "ok" ? "check ok" : "BROKEN"}</span></td></tr>`;
  }

  function drawSummary(d) {
    const rows = [...ledgerRows(d), gammaRow(d), politicsRow(d)];
    $("#sc-summary").innerHTML = `<table><thead><tr><th>Model</th><th>What it predicts</th><th>Live since</th><th>Predictions</th><th>Resolved</th>
      <th>Model's result</th><th>Simple guess it must beat</th><th>Verdict</th><th>Record</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
    const v = d.ledger?.verify;
    const b = $("#sc-badge");
    if (!d.ledger) { b.className = "badge"; b.textContent = "Ledger empty"; b.title = "No model has written to the ledger yet"; }
    else { b.className = `badge ${v.ok ? "fresh" : "down"}`; b.textContent = v.ok ? `Ledger check ok · ${v.live_predictions} live` : "Ledger check failed"; b.title = v.problems.join("\n"); }
  }

  // ---------- ranges vs reality (quantile models only)
  function drawCalibration(d) {
    const models = (d.ledger?.models ?? []).filter((m) => m.coverage && Object.keys(m.coverage).length);
    $("#sc-calibration").innerHTML = models.length
      ? `<table><thead><tr><th>Model</th><th>Range</th><th>Should catch</th><th>Caught</th><th>Out of</th></tr></thead><tbody>${models.flatMap((m) =>
          Object.entries(m.coverage).map(([range, c], i) => `<tr><td>${i ? "" : `<b>${esc(MODELS[m.model]?.name || m.model)}</b> <span class="dim">v${esc(m.version)} ${esc(m.mode)}</span>`}</td>
            <td>${esc(range)}</td><td>${pctText(c.expected)}</td><td class="${Math.abs(c.share - c.expected) > 0.05 && c.n >= d.min_resolved ? "neg" : ""}">${pctText(c.share, 1)}</td><td>${c.n}</td></tr>`)).join("")}</tbody></table>`
      : `<div class="empty" style="padding:16px">Nothing to check yet. Once a range model has resolved predictions, this shows whether its 90% ranges really catch about 90% of outcomes.</div>`;
  }

  // ---------- latest ledger predictions
  function drawRecent(d) {
    const modes = [["all", "All"], ["live", "Live"], ["backtest", "Backtest"]];
    $("#sc-recent-mode").innerHTML = modes.map(([v, l]) => `<button class="chip ${v === state.recentMode ? "active" : ""}" data-v="${v}">${l}</button>`).join("");
    $("#sc-recent-mode").onclick = (e) => { if (e.target.dataset.v) { state.recentMode = e.target.dataset.v; drawRecent(d); } };
    const items = (d.ledger?.recent ?? []).filter((r) => state.recentMode === "all" || r.mode === state.recentMode);
    $("#sc-recent-n").textContent = items.length;
    $("#sc-recent").innerHTML = items.length
      ? `<table><thead><tr><th>Made</th><th>Model</th><th>Target</th><th>Prediction</th><th>Simple guess</th><th>Outcome</th><th>Closer than the guess?</th></tr></thead><tbody>${items.map((r) => {
          const [bName, bF] = Object.entries(r.baselines)[0] || [];
          const resolved = isNum(r.outcome);
          const closer = resolved && bName ? r.loss < r.baseline_loss[bName] : null;
          return `<tr><td>${etTime(r.made_at)}${r.mode === "backtest" ? ' <span class="dim">backtest</span>' : ""}</td><td>${esc(MODELS[r.model]?.name || r.model)}</td>
            <td class="wrap">${esc(r.target)}</td><td>${forecastText(r.kind, r.forecast)}</td><td>${bF ? `<span class="dim">${esc(BASELINE_NAMES[bName] || bName)}:</span> ${forecastText(r.kind, bF)}` : "–"}</td>
            <td>${resolved ? (r.kind === "probability" ? (r.outcome ? "Happened" : "Didn't") : signed(r.outcome, 2)) : `<span class="dim">due ${etTime(r.resolves_at)}</span>`}</td>
            <td class="${closer == null ? "dim" : closer ? "pos" : "neg"}">${closer == null ? "–" : closer ? "Yes" : "No"}</td></tr>`;
        }).join("")}</tbody></table>`
      : `<div class="empty" style="padding:16px">No predictions in the ledger yet. The first model to write here will be the S&P 500 move-size model.</div>`;
  }

  // ---------- S&P 500 move size: next day's range, its inputs, and recent ranges vs what happened
  const EVENT_NAMES = { fomc: "Fed decision", cpi: "CPI (inflation)", jobs: "Jobs report" };
  const range = (q, lo, hi) => `${signed(q[lo], 2)} to ${signed(q[hi], 2)}`;
  const clock12 = (t) => { const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`; };

  function drawSpx(d) {
    const s = d.spx;
    if (!s?.ready) {
      $("#sc-spx-facts").innerHTML = `<div class="empty" style="padding:16px">No predictions yet. The model runs each weekday evening after the close.</div>`;
      $("#sc-spx-legend").innerHTML = ""; $("#sc-spx-chart").innerHTML = "";
      return;
    }
    const p = s.latest && s.latest.outcome == null ? s.latest : null;  // tomorrow's, still open
    const show = p || s.last;
    const x = show.inputs || {};
    const head = p ? `Prediction for ${day(p.day)}` : s.latest ? `Latest: ${day(show.day)}, resolved` : `No live prediction yet. Last backtest day: ${day(show.day)}`;
    const gamma = isNum(x.gex) ? `${x.gex >= 0 ? "+" : "−"}$${Math.abs(x.gex).toFixed(1)}B <span class="dim">(${esc(day(x.gex_date))}; ${x.gex < 0 ? "negative" : `higher than ${Math.round(x.gex_rank * 100)}% of the past year`})</span>` : "–";
    const events = (x.events || []).map((e) => EVENT_NAMES[e] || e).join(", ") || "None scheduled";
    const rowsHtml = [
      ["S&P 500 close", `${isNum(x.spx_close) ? x.spx_close.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "–"} <span class="dim">(${esc(day(x.day))}, ${signed(x.move_today, 2)})</span>`],
      ["VIX", `${fixed(x.vix, 2)}${x.vix_source && x.vix_source !== "cboe" ? ` <span class="badge stale" title="Cboe hadn't posted the close; Yahoo's was used">${esc(x.vix_source)}</span>` : ""}`],
      ["Dealer gamma", gamma],
      ["Realized moves", `day ${fixed(x.rv_day, 2)}% · week ${fixed(x.rv_week, 2)}% · month ${fixed(x.rv_month, 2)}%`],
      ["News that day", esc(events)],
      ["Made", show.mode === "live" ? `${etTime(show.made_at)} ET` : `backtest (would run ${etTime(show.made_at)})`],
    ];
    const upcoming = (s.upcoming || []).map((e) => `${esc(day(e.date))} · ${esc(EVENT_NAMES[e.event] || e.event)} ${clock12(e.time_et)}`).join("<br>");
    $("#sc-spx-facts").innerHTML = `<div class="item-sub" style="padding:8px 10px 0">${head}${show.outcome != null ? ` · actual ${signed(show.outcome, 2)}` : ""}</div>
      <div class="stats"><div class="stat"><small>90% range</small><strong>${range(show.q, "0.05", "0.95")}</strong></div>
        <div class="stat"><small>50% range</small><strong>${range(show.q, "0.25", "0.75")}</strong></div>
        <div class="stat"><small>VIX at face value</small><strong class="dim">${show.baselines?.vix ? range(show.baselines.vix, "0.05", "0.95") : "–"}</strong><em>90% range</em></div>
        <div class="stat"><small>Recent moves</small><strong class="dim">${show.baselines?.recent ? range(show.baselines.recent, "0.05", "0.95") : "–"}</strong><em>90% range</em></div></div>
      <table><tbody>${rowsHtml.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</tbody></table>
      ${upcoming ? `<div class="note" style="padding:8px 10px"><b>Next scheduled news</b><br>${upcoming}</div>` : ""}`;
    $("#sc-spx-asof").textContent = s.latest ? `live since ${day(s.history.find((h) => h.mode === "live").day)}` : "backtest only so far";

    const done = s.history.filter((h) => h.outcome != null);
    const caught = done.filter((h) => h.q["0.05"] <= h.outcome && h.outcome <= h.q["0.95"]).length;
    $("#sc-spx-legend").innerHTML = `<span><i style="background:var(--series-1)"></i>90% range</span><span><i style="background:var(--series-1);opacity:.5"></i>50% range</span>
      <span><i style="background:var(--series-2)"></i>VIX at face value (90%)</span><span><i style="background:var(--text-dim);height:8px"></i>Actual move</span>
      <span><i style="background:var(--elevated);height:8px"></i>Outside the 90% range</span>
      <span class="dim">${done.length ? `90% range caught ${caught} of the last ${done.length} (${Math.round((caught / done.length) * 100)}%)` : ""}</span>`;
    const c = makeChart($("#sc-spx-chart"), { rightPriceScale: { borderColor: css("--border"), scaleMargins: { top: 0.08, bottom: 0.08 } } });
    const pct = { type: "custom", formatter: (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%` };
    c.addHistogramSeries({ priceFormat: pct, priceLineVisible: false, lastValueVisible: false }).setData(done.map((h) => ({
      time: h.day, value: h.outcome, color: h.outcome < h.q["0.05"] || h.outcome > h.q["0.95"] ? css("--elevated") : css("--text-muted") })));
    const line = (key, color, opts = {}) => c.addLineSeries({ color, lineWidth: 1, priceFormat: pct, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...opts })
      .setData(s.history.map((h) => ({ time: h.day, value: key(h) })).filter((r) => isNum(r.value)));
    line((h) => h.baselines?.vix?.["0.95"], css("--series-2"), { lineStyle: 2 });
    line((h) => h.baselines?.vix?.["0.05"], css("--series-2"), { lineStyle: 2 });
    for (const k of ["0.25", "0.75"]) line((h) => h.q[k], `${css("--series-1")}88`);
    for (const k of ["0.05", "0.95"]) line((h) => h.q[k], css("--series-1"), { lineWidth: 2 });
    c.timeScale().fitContent();
  }

  // ---------- live paper record of three trading rules (collectors/paper_record.py)
  const money = (x) => (isNum(x) ? `$${Math.round(x).toLocaleString("en-US")}` : "–");
  const HOLD_NAMES = { SSO: "SSO (2x S&P 500)", SPY: "SPY", cash: "Cash (T-bills)" };

  function drawPaper(d) {
    const p = d.paper;
    const badge = $("#sc-paper-badge");
    if (!p?.ready || !p.strategies.length) {
      $("#sc-paper-facts").innerHTML = `<div class="empty" style="padding:16px">Not started yet. The job runs weekdays at 9:10 am, 4:40 pm and 8:40 pm.</div>`;
      $("#sc-paper-legend").innerHTML = ""; $("#sc-paper-chart").innerHTML = "";
      badge.className = "badge"; badge.textContent = "Not started";
      return;
    }
    const v = p.verify;
    badge.className = `badge ${v.ok ? "fresh" : "down"}`;
    badge.title = v.problems.join("\n");
    badge.textContent = v.ok ? `Chained · check ok · ${v.positions} positions` : "Chain check FAILED";
    const verdictBadge = (e) => e.verdict === "too early" ? `<span class="badge">Too early to judge</span>`
      : `<span class="badge ${e.verdict.startsWith("beats") ? "fresh" : "down"}">${esc(e.verdict)}</span>`;
    const holding = (e) => {
      const lp = e.latest_position;
      if (!lp) return `<span class="dim">–</span>`;
      if (e.kind === "fed") return `Window: ${esc(day(lp.buy_at))} 2 pm to ${esc(day(lp.decision_day))} 2 pm`;
      return `${esc(HOLD_NAMES[lp.hold] || lp.hold)} <span class="dim">from the ${esc(day(lp.trade_date))} close (decided ${etTime(lp.decided_at)})</span>`;
    };
    const rowsHtml = p.strategies.map((e) => {
      const skips = e.skips.length
        ? ` <span class="badge stale" title="${esc(e.skips.map((s) => `${s.signal_date}: ${s.reason}`).join("\n"))}">${e.skips.length} skipped</span>` : "";
      let res;
      if (e.kind === "fed") {
        res = e.meetings
          ? `${e.meetings} meeting${e.meetings > 1 ? "s" : ""}: avg ${signed(e.avg_window * 100, 2)} per window <span class="dim">vs SPY's avg day ${signed(isNum(e.avg_spy_day) ? e.avg_spy_day * 100 : null, 3)}</span>`
          : `<span class="dim">No meeting finished yet</span>`;
      } else {
        res = e.marks ? `${money(e.rule_10k)} <span class="dim">vs SPY ${money(e.spy_10k)} · since ${esc(day(e.first_day))}</span>`
          : `<span class="dim">Starts at its first close</span>`;
      }
      return `<tr><td><b>${esc(e.name)}</b> <span class="dim">v${esc(e.version)}</span>${skips}<br><span class="dim">${esc(e.what)}</span></td>
        <td>${res}</td><td>${holding(e)}</td><td>${verdictBadge(e)}</td></tr>`;
    });
    $("#sc-paper-facts").innerHTML = `<table><thead><tr><th>Rule</th><th>$10k so far</th><th>Holding now</th><th>Verdict</th></tr></thead><tbody>${rowsHtml.join("")}</tbody></table>`;
    const lt = p.strategies.find((e) => e.strategy === "lev-trend"), t10 = p.strategies.find((e) => e.strategy === "trend10");
    $("#sc-paper-asof").textContent = lt?.last_day ? `marked to ${day(lt.last_day)}` : "";
    $("#sc-paper-legend").innerHTML = `<span><i style="background:var(--series-1)"></i>Leveraged trend</span><span><i style="background:var(--series-2)"></i>10-month trend</span>
      <span><i style="background:var(--text-dim)"></i>SPY</span><span class="dim">$10,000 from the record's first close</span>`;
    const host = $("#sc-paper-chart");
    if (!lt?.curve?.length) { host.innerHTML = `<div class="empty" style="padding:16px">The chart starts after the first marked day.</div>`; return; }
    const c = makeChart(host, { rightPriceScale: { borderColor: css("--border") } });
    const usd = { type: "custom", formatter: (x) => `$${Math.round(x).toLocaleString("en-US")}` };
    const series = (pts, key, color) => c.addLineSeries({ color, lineWidth: 2, priceFormat: usd, priceLineVisible: false, lastValueVisible: true })
      .setData(pts.map((x) => ({ time: x.date, value: x[key] })));
    series(lt.curve, "spy", css("--text-dim"));
    if (t10?.curve?.length) series(t10.curve, "rule", css("--series-2"));
    series(lt.curve, "rule", css("--series-1"));
    c.timeScale().fitContent();
  }

  loaders.scorecard = async () => {
    const d = await api("/api/scorecard");
    drawSummary(d); drawSpx(d); drawPaper(d); drawCalibration(d); drawRecent(d);
    $("#sc-asof").textContent = `updated ${etTime(new Date().toISOString())}`;
  };
})();
