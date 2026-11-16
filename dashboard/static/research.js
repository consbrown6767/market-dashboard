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

  loaders.research = async () => { state.data = await api("/api/research"); draw(); };
})();
