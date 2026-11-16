/* Today tab: the home page. One screen of what matters now, read from records the other tabs
   already hold (/api/today). It decides nothing and trades nothing. Headlines and market names
   are outside text: every one goes through esc(). */
"use strict";

// One table of everything on a live test; the Research tab shows the same one.
function liveTestsTable(tests) {
  const verdict = (v) => v === "too early" ? `<span class="badge">Too early to judge</span>`
    : `<span class="badge ${/^beats/.test(v) ? "fresh" : /worse|doesn't/.test(v) ? "down" : "stale"}">${esc(v)}</span>`;
  return `<table class="tests"><thead><tr><th>Test</th><th>Right now</th><th>Record so far</th><th>Verdict</th><th>A verdict needs</th></tr></thead><tbody>${tests.map((t) =>
    `<tr data-goto="${esc(t.tab)}" title="Open the ${esc(t.tab)} tab"><td class="wrap"><b>${esc(t.name)}</b><br><span class="dim">${esc(t.what)}</span></td>
      <td class="wrap">${esc(t.now)}</td><td class="wrap">${esc(t.record)}</td><td>${verdict(t.verdict)}</td><td class="dim">${esc(t.needs)}</td></tr>`).join("")}</tbody></table>`;
}
document.addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-goto]");
  if (row && !e.target.closest("a")) show(row.dataset.goto);
});

(() => {
  const EVENT_NAMES = { fomc: "Fed decision", cpi: "CPI inflation", jobs: "Jobs report" };
  const dayText = (d) => new Date(`${d}T12:00:00-05:00`).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" });
  const daysUntil = (d, today) => Math.round((new Date(`${d}T12:00:00-05:00`) - new Date(`${today}T12:00:00-05:00`)) / 86400000);
  const clock12 = (t) => { if (!t) return ""; const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h >= 12 ? "pm" : "am"}`; };
  const stat = (label, value, sub = "", kind = "") => `<div class="stat"><small>${label}</small><strong class="${kind}">${value}</strong><em>${sub}</em></div>`;
  const marketName = (m) => { const l = m.label || (m.outcomes?.[0] !== "Yes" ? m.outcomes?.[0] : ""); return l && l !== m.question ? `${m.event_title}: ${l}` : (m.question || m.event_title); };

  function drawMarket(d) {
    const m = d.market, spy = m.spy, cells = [];
    const move = spy && spy.prev_close ? (spy.price / spy.prev_close - 1) * 100 : null;
    cells.push(stat("S&P 500 (SPY)", spy ? fixed(spy.price, 2) : "–", spy ? `${signed(move)} today` : "no snapshot yet", cls(move)));
    if (spy && isNum(m.avg200)) {
      const gap = (spy.price / m.avg200 - 1) * 100;
      cells.push(stat("Trend", gap >= 0 ? "Up" : "Down", `${signed(gap, 1)} ${gap >= 0 ? "above" : "below"} its 200-day average`, gap >= 0 ? "pos" : "neg"));
    }
    cells.push(stat("VIX", m.vix ? fixed(m.vix.close, 1) : "–", m.vix ? `${dayText(m.vix.date)} close` : ""));
    const r = m.range;
    if (r) {
      const lo = r.q["0.05"], hi = r.q["0.95"];
      const outside = r.is_today && isNum(move) && (move < lo || move > hi);
      cells.push(stat(r.is_today ? "Expected range today" : `Expected range ${esc(dayText(r.day))}`, `${signed(lo)} to ${signed(hi)}`,
        r.is_today && isNum(move) ? `9 days in 10 · so far ${outside ? "outside it" : "inside it"}` : "9 days in 10", outside ? "neg" : ""));
      cells.push(stat("Usual day", `${signed(r.q["0.25"])} to ${signed(r.q["0.75"])}`, "half of days land here"));
    }
    const next = d.calendar.upcoming?.[0];
    if (next) {
      const n = daysUntil(next.date, d.today);
      cells.push(stat("Next scheduled news", esc(EVENT_NAMES[next.event] || next.event), `${esc(dayText(next.date))} ${clock12(next.time_et)} · ${n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`}`));
    }
    const top = d.calendar.odds?.[0];
    if (top && d.calendar.next_fomc) cells.push(stat("Fed, as priced", esc(top.label), `${fixed(top.price * 100, 0)}% on Polymarket · ${esc(dayText(d.calendar.next_fomc.date))}`));
    $("#td-market").innerHTML = cells.join("");
    badge($("#td-market-badge"), spy?.ts, 90, spy ? `Prices ${ago(spy.ts)}` : "No prices");
  }

  function drawNews(d) {
    $("#td-news").innerHTML = d.stories.length ? d.stories.map((s) => `<div class="nw-item">
        <div class="nw-head"><span class="nw-trust ${esc(String(s.trust_label || "").toLowerCase())}" title="${esc(`How well sourced this story is, not whether it's true${s.trust_why ? ` (${s.trust_why})` : ""}`)}">${esc(s.trust_label || "")}</span>
          <a class="nw-link" href="${esc(s.link)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a></div>
        <div class="item-sub">${s.alert ? `<span class="nw-flag">ALERT</span> ` : ""}${s.n_sources} outlet${s.n_sources === 1 ? "" : "s"} · ${ago(s.first_published)}</div></div>`).join("")
      : `<div class="empty">No well-sourced stories in the last 24 hours yet.</div>`;
    badge($("#td-news-badge"), d.newest_news, 30, `Updated ${ago(d.newest_news)}`);
  }

  function drawMovers(d) {
    $("#td-movers").innerHTML = d.movers.length ? d.movers.map((m) => `<div class="item"><div><div class="item-name">${esc(marketName(m))}</div>
        <div class="item-sub">${usd(m.volume_24h)} traded in 24h</div></div>
        <div><div class="item-value">${fixed(m.price * 100, 0)}%</div><div class="item-change ${cls(m.change_1d)}">${signed(m.change_1d * 100, 1, " pts")}</div></div></div>`).join("")
      : `<div class="empty">No liquid movers yet.</div>`;
    badge($("#td-movers-badge"), d.movers_asof, 75, `Updated ${ago(d.movers_asof)}`);
  }

  function drawCalendar(d) {
    const c = d.calendar, rowsHtml = (c.upcoming || []).slice(0, 6).map((u) => {
      const n = daysUntil(u.date, d.today);
      return `<tr><td>${esc(dayText(u.date))} <span class="dim">${clock12(u.time_et)}</span></td><td>${esc(EVENT_NAMES[u.event] || u.event)}</td>
        <td class="dim">${n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`}</td></tr>`;
    });
    const odds = c.next_fomc && c.odds?.length
      ? `<div class="note" style="padding:8px 10px"><b>${esc(dayText(c.next_fomc.date))} Fed decision, as Polymarket prices it:</b> ${c.odds.slice(0, 4).map((o) => `${esc(o.label)} ${fixed(o.price * 100, 0)}%`).join(" · ")}</div>` : "";
    $("#td-calendar").innerHTML = rowsHtml.length
      ? `<table><thead><tr><th>When (ET)</th><th>What</th><th>How soon</th></tr></thead><tbody>${rowsHtml.join("")}</tbody></table>${odds}`
      : `<div class="empty" style="padding:16px">No scheduled Fed, CPI or jobs news stored.</div>`;
  }

  function drawSystem(d) {
    const bad = d.jobs.bad, b = $("#td-system-badge");
    b.className = `badge ${bad.length ? "down" : "fresh"}`;
    b.textContent = bad.length ? `${bad.length} need${bad.length === 1 ? "s" : ""} a look` : "All ok";
    $("#td-system").innerHTML = `<div class="note">${d.jobs.total - bad.length} of ${d.jobs.total} jobs that ran in the last 4 days finished cleanly on their latest run. Database ${fixed(d.db_mb / 1000, 1)} GB.</div>`
      + bad.map((j) => `<div class="item"><div><div class="item-name">${esc(j.job)} <span class="neg">${esc(j.status)}</span></div><div class="item-sub">${esc(j.detail || "")}</div></div>
          <div class="item-change dim">${ago(j.started_at)}</div></div>`).join("")
      + `<div class="item-sub" style="margin-top:6px">Failures also go to your phone. The Status tab has every job.</div>`;
  }

  loaders.today = async () => {
    const d = await api("/api/today");
    drawMarket(d);
    $("#td-tests-n").textContent = d.tests.length;
    $("#td-tests").innerHTML = liveTestsTable(d.tests);
    drawNews(d); drawMovers(d); drawCalendar(d); drawSystem(d);
  };
})();
