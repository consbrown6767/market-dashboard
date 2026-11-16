/* Research tab: every idea tested and what came of it. The list lives in shared/research.json
   (one entry per study, numbers from each study's write-up); the live tests come from the same
   records as the Scorecard tab. */
"use strict";

(() => {
  const VERDICTS = { live: ["fresh", "On live test"], failed: ["down", "Failed"], finding: ["stale", "Finding kept"] };
  const state = { filter: "all", data: null };
  const day = (d) => new Date(`${d}T12:00:00-05:00`).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });

  function draw() {
    const d = state.data, all = d.studies;
    const count = (v) => all.filter((s) => s.verdict === v).length;
    const versions = all.reduce((n, s) => n + (s.versions || 0), 0);
    const stat = (label, value, sub, kind = "") => `<div class="stat"><small>${label}</small><strong class="${kind}">${value}</strong><em>${sub}</em></div>`;
    $("#rs-stats").innerHTML = stat("Studies", all.length, "each planned before its results")
      + stat("Versions tried", versions, "every variant, failures included")
      + stat("Led to a live test", count("live"), "still being scored", "pos")
      + stat("Failed", count("failed"), "on years they hadn't seen", "neg")
      + stat("Findings kept", count("finding"), "useful, not a trading rule");
    $("#rs-lessons").innerHTML = `<div class="note"><b>What it adds up to</b></div>${d.lessons.map((l) => `<div class="rs-lesson">${esc(l)}</div>`).join("")}`;

    $("#rs-live-n").textContent = d.tests.length;
    $("#rs-live").innerHTML = liveTestsTable(d.tests);

    const filters = [["all", "All"], ["live", "On live test"], ["failed", "Failed"], ["finding", "Findings"]];
    $("#rs-filter").innerHTML = filters.map(([v, l]) => `<button class="chip ${v === state.filter ? "active" : ""}" data-rs="${v}">${l}</button>`).join("");
    const shown = all.filter((s) => state.filter === "all" || s.verdict === state.filter).sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
    $("#rs-list-n").textContent = shown.length;
    $("#rs-list").innerHTML = `<table class="tests"><thead><tr><th>Idea</th><th>Tested</th><th>Versions</th><th>Verdict</th><th>What happened</th><th>Takeaway</th></tr></thead><tbody>${shown.map((s) => {
      const [kind, label] = VERDICTS[s.verdict] || ["", s.verdict];
      return `<tr><td class="wrap"><b>${esc(s.name)}</b> <span class="grp-tag">${esc(s.area)}</span><br><span class="dim">${esc(s.idea)}</span><br><span class="dim rs-doc">${esc(s.doc)}</span></td>
        <td>${esc(day(s.date))}</td><td>${s.versions}</td><td><span class="badge ${kind}">${esc(label)}</span></td>
        <td class="wrap">${esc(s.result)}</td><td class="wrap">${esc(s.lesson)}</td></tr>`;
    }).join("")}</tbody></table>`;
  }
  $("#rs-filter").addEventListener("click", (e) => { if (e.target.dataset.rs) { state.filter = e.target.dataset.rs; draw(); } });

  // ---------- savings paths: the same monthly saving replayed from every start month in the data
  const sav = { years: 30, data: null };
  const money = (x) => `$${Math.round(x).toLocaleString("en-US")}`;
  function paths(returns, amount, n) {
    // One ending value per start month: save `amount` at the start of each month for n months.
    // Also the biggest fall in the account from an earlier high (new savings included).
    const ends = [], falls = [];
    for (let s = 0; s + n <= returns.length; s++) {
      let w = 0, peak = 0, fall = 0;
      for (let i = s; i < s + n; i++) {
        w = (w + amount) * (1 + returns[i]);
        if (w > peak) peak = w; else if (peak > 0) fall = Math.min(fall, w / peak - 1);
      }
      ends.push(w); falls.push(fall);
    }
    return { ends, falls };
  }
  const pick = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  function drawSavings() {
    const d = sav.data;
    if (!d?.ready) { $("#rs-savings").innerHTML = `<div class="empty" style="padding:16px">Not built yet. Run collectors/savings_paths.py.</div>`; return; }
    const amount = Math.max(1, Number($("#rs-sav-amount").value) || 500), n = sav.years * 12, paid = amount * n;
    $("#rs-sav-years").innerHTML = [10, 20, 30, 40].map((y) => `<button class="chip ${y === sav.years ? "active" : ""}" data-sav="${y}">${y} years</button>`).join(" ");
    const base = paths(d.returns.market, amount, n);
    const rowsHtml = ["tbills", "market", "lev2", "lev_trend"].map((k) => {
      const p = paths(d.returns[k], amount, n), sorted = [...p.ends].sort((a, b) => a - b);
      const worstAt = d.months[p.ends.indexOf(sorted[0])];
      const ahead = k === "market" || k === "tbills" ? null : p.ends.filter((e, i) => e > base.ends[i]).length / p.ends.length;
      const below = p.ends.filter((e) => e < paid).length / p.ends.length;
      return `<tr><td><b>${esc(d.names[k])}</b></td><td>${money(sorted[0])} <span class="dim">(started ${esc(worstAt.slice(0, 4))})</span></td>
        <td>${money(pick(sorted, 0.1))}</td><td><b>${money(pick(sorted, 0.5))}</b></td><td>${money(pick(sorted, 0.9))}</td>
        <td class="${below > 0 ? "neg" : "dim"}">${(below * 100).toFixed(0)}%</td>
        <td>${ahead == null ? `<span class="dim">–</span>` : `${(ahead * 100).toFixed(0)}%`}</td>
        <td class="neg">${(Math.min(...p.falls) * 100).toFixed(0)}%</td></tr>`;
    });
    $("#rs-savings").innerHTML = `<table><thead><tr><th>Held in</th><th>Worst start</th><th>1 in 10 did worse than</th><th>Typical (middle)</th><th>1 in 10 did better than</th>
      <th>Ended with less than paid in</th><th>Beat the 1x market</th><th>Biggest fall along the way</th></tr></thead><tbody>${rowsHtml.join("")}</tbody></table>`;
    $("#rs-sav-asof").textContent = `${base.ends.length} start months, ${d.first.slice(0, 4)} to ${d.months[base.ends.length - 1].slice(0, 4)}`;
    $("#rs-sav-foot").textContent = `You'd pay in ${money(paid)} over ${sav.years} years. Each row replays that saving from every start month in US history (data ${d.first} to ${d.last}) and shows where it ended. Dollars aren't adjusted for inflation, so compare each row with T-bills, not with what was paid in. Leverage costs are included (1% a year to borrow, 0.05% per trade); taxes and fund fees aren't. Start months overlap, so these aren't independent tries. History replayed, not a forecast, and not advice.`;
  }
  $("#rs-sav-years").addEventListener("click", (e) => { if (e.target.dataset.sav) { sav.years = Number(e.target.dataset.sav); drawSavings(); } });
  $("#rs-sav-amount").addEventListener("input", drawSavings);

  loaders.research = async () => {
    state.data = await api("/api/research"); draw();
    if (!sav.data) sav.data = await api("/api/savings");
    drawSavings();
  };
})();
