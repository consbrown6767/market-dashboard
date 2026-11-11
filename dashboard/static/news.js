/* News tab: top stories and latest headlines (news_collector.py), shipping chokepoints
   (shipping_collector.py), the Fed and data calendar with Polymarket's odds. Headlines are outside
   text: every one goes through esc(), and links open in a new tab without referrer. */
"use strict";

(() => {
  const TOPICS = [["all", "All"], ["fed", "Fed & rates"], ["economy", "Economy"], ["markets", "Markets"], ["business", "Business"],
    ["tech", "Tech & AI"], ["energy", "Energy & commodities"], ["shipping", "Shipping"], ["ukraine", "Russia & Ukraine"],
    ["middle_east", "Middle East"], ["china", "China"], ["politics", "US politics"], ["world", "World"], ["crypto", "Crypto"]];
  const HOURS = [[6, "6h"], [24, "24h"], [72, "3d"], [168, "7d"]];
  const RANGES = [[90, "3M"], [365, "1Y"], [1095, "3Y"], [0, "All"]];
  const EVENT_NAMES = { fomc: "Fed decision", cpi: "CPI inflation", jobs: "Jobs report" };
  const TIER_NAMES = { 1: "Wire / official", 2: "Major outlet", 3: "Specialist", 4: "Search result" };
  const state = { topic: "all", hours: 24, q: "", ship: "chokepoint6", range: 365, shipData: null };

  const topicName = (t) => (TOPICS.find(([k]) => k === t) || [t, t])[1];
  const link = (url, text) => `<a class="nw-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  const tierDot = (t) => `<span class="nw-tier t${esc(t)}" title="${esc(TIER_NAMES[t] || "")}"></span>`;
  const tags = (topics) => (topics || "").split(",").filter((t) => t && t !== state.topic)
    .slice(0, 3).map((t) => `<span class="grp-tag">${esc(topicName(t))}</span>`).join("");
  const pctOf = (a, b) => (isNum(a) && isNum(b) && b > 0 ? (a / b) * 100 : null);
  const clock12 = (t) => {
    if (!t) return "";
    const [h, m] = t.split(":").map(Number);
    return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h >= 12 ? "pm" : "am"}`;
  };
  const dayText = (d) => new Date(`${d}T12:00:00-05:00`).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" });
  const daysUntil = (d) => Math.round((new Date(`${d}T12:00:00-05:00`) - new Date(new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }) + "T12:00:00-05:00")) / 86400000);

  // ---------- toolbar
  function drawToolbar(counts) {
    $("#nw-topics").innerHTML = TOPICS.map(([k, label]) => `<button class="chip ${k === state.topic ? "active" : ""}" data-nw-topic="${k}">${label}${k !== "all" && counts ? `<span class="n">${counts[k] ?? 0}</span>` : ""}</button>`).join(" ");
    $("#nw-hours").innerHTML = HOURS.map(([h, label]) => `<button class="chip ${h === state.hours ? "active" : ""}" data-nw-hours="${h}" title="Stories first published in the last ${label}">${label}</button>`).join("");
  }
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-nw-topic]"), h = e.target.closest("[data-nw-hours]"), r = e.target.closest("[data-nw-range]");
    if (t) { state.topic = t.dataset.nwTopic; loaders.news(); }
    if (h) { state.hours = Number(h.dataset.nwHours); loaders.news(); }
    if (r) { state.range = Number(r.dataset.nwRange); drawShipChart(); }
    const ship = e.target.closest("[data-ship]");
    if (ship) { state.ship = ship.dataset.ship; drawShips(); loadShipChart(); }
    const story = e.target.closest(".nw-story");
    if (story && !e.target.closest("a")) story.classList.toggle("open");
  });
  let timer;
  $("#nw-search").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = e.target.value.trim(); loaders.news(); }, 300);
  });

  // ---------- stories and headlines
  function drawStories(d) {
    $("#nw-top-n").textContent = d.stories.length;
    $("#nw-top").innerHTML = d.stories.length ? d.stories.map((s) => `<div class="nw-story ${s.alert ? "alert" : ""}">
        <div class="nw-head">${tierDot(s.best_tier)}<span class="nw-title">${esc(s.title)}</span></div>
        <div class="item-sub">${s.alert ? `<span class="nw-flag">ALERT</span> ` : ""}${s.n_sources} outlet${s.n_sources === 1 ? "" : "s"} · ${ago(s.first_published)} ${tags(s.topics)}</div>
        <div class="nw-more">${s.items.map((i) => `<div class="nw-row">${tierDot(i.tier)}<span class="dim">${esc(i.source)}</span> ${link(i.link, esc(i.title))} <span class="dim">${ago(i.published_at)}</span></div>`).join("")}</div>
      </div>`).join("")
      : `<div class="empty">No stories in this window${state.topic !== "all" ? ` for ${esc(topicName(state.topic))}` : ""} yet.</div>`;
  }

  function drawLatest(d) {
    $("#nw-latest-title").textContent = state.q ? `Headlines matching “${state.q}”` : "Latest headlines";
    $("#nw-latest-n").textContent = d.latest.length;
    $("#nw-latest").innerHTML = d.latest.length ? d.latest.map((i) => `<div class="nw-item">
        <div class="nw-head">${tierDot(i.tier)}${link(i.link, esc(i.title))}</div>
        <div class="item-sub">${i.alert ? `<span class="nw-flag">ALERT</span> ` : ""}${esc(i.source)} · ${etTime(i.published_at)} ${tags(i.topics)}</div>
        ${i.summary ? `<div class="nw-summary">${esc(i.summary)}</div>` : ""}</div>`).join("")
      : `<div class="empty">${state.q ? "No stored headline matches. Search looks at every headline collected, by whole words (the last word can be a start, like “tarif”)." : "No headlines yet."}</div>`;
  }

  function drawFeeds(d) {
    const bad = d.feeds.filter((f) => f.error);
    $("#nw-feeds-n").textContent = d.feeds.length;
    $("#nw-feeds-note").textContent = `${(d.total_headlines || 0).toLocaleString("en-US")} headlines stored · ${bad.length ? `${bad.length} not answering` : "all answering"}`;
    $("#nw-feeds").innerHTML = `<div class="nw-feeds">${d.feeds.map((f) => `<span class="nw-feed ${f.error ? "bad" : ""}" title="${esc(f.error ? `Last error: ${f.error}` : `Last read ${etTime(f.last_ok)} ET, ${f.items} items in the feed`)}">${esc(f.feed)}</span>`).join("")}</div>`;
  }

  // ---------- Fed and calendar
  function drawFed(f) {
    const n = f.next_fomc;
    const head = n ? `<div class="stats"><div class="stat"><small>Next Fed decision</small><strong>${dayText(n.date)}</strong><em>${clock12(n.time_et)} ET${n.detail ? ` · ${esc(n.detail)}` : ""}</em></div>
        <div class="stat"><small>Days away</small><strong>${daysUntil(n.date)}</strong><em>statement, then press conference</em></div></div>` : "";
    const odds = f.odds.length ? `<div class="item-sub" style="margin:8px 0 2px">Polymarket: what traders expect ${n.market_url ? link(n.market_url, "↗") : ""}</div>
      ${f.odds.map((o) => { const p = (o.price ?? 0) * 100, c = isNum(o.change_1d) ? o.change_1d * 100 : null;
        return `<div class="outcome"><div class="outcome-label"><div class="outcome-bar" style="width:${Math.min(100, p)}%"></div><span>${esc(o.label || o.question)}</span></div>
          <div class="outcome-pct">${p < 1 ? "<1%" : `${p.toFixed(0)}%`}</div><div class="outcome-chg ${cls(c)}">${c === null ? "" : signed(c, 1, "")}</div></div>`; }).join("")}` : "";
    const cal = f.upcoming.length ? `<div class="item-sub" style="margin:10px 0 2px">Scheduled</div>${f.upcoming.map((u) => `<div class="item"><div class="item-name">${esc(EVENT_NAMES[u.event] || u.event)}</div>
      <div class="item-value" style="font-weight:400">${dayText(u.date)} <span class="dim">${clock12(u.time_et)}</span></div></div>`).join("")}` : "";
    const st = f.statements.length ? `<div class="item-sub" style="margin:10px 0 2px">Latest from the Fed</div>${f.statements.slice(0, 5).map((s) => `<div class="nw-row">${link(s.link, esc(s.title))} <span class="dim">${ago(s.published_at)}</span></div>`).join("")}` : "";
    $("#nw-fed").innerHTML = head + odds + cal + st || `<div class="empty">No calendar yet.</div>`;
    const b = $("#nw-fed-badge");
    if (n) { b.textContent = `${daysUntil(n.date)} days`; b.className = `badge ${daysUntil(n.date) <= 7 ? "stale" : ""}`; } else b.textContent = "–";
  }

  // ---------- shipping
  function drawShips() {
    const d = state.shipData;
    if (!d?.ready) { $("#nw-ships").innerHTML = `<div class="empty" style="padding:16px">No shipping data yet.</div>`; return; }
    $("#nw-ships-asof").textContent = `through ${dayText(d.latest_day)}`;
    const shown = d.ports.slice(0, 11);
    $("#nw-ships").innerHTML = `<table><thead><tr><th>Chokepoint</th><th title="Average ships per day, last 7 days of data">Last 7d</th><th title="Average ships per day, Jan–Oct 2023">Normal</th><th>vs normal</th><th title="Same week a year earlier">Year ago</th><th title="Tankers per day, last 7 days vs normal">Tankers</th><th>6 months</th></tr></thead><tbody>${shown.map((p) => {
      const v = pctOf(p.avg7, p.normal), dropped = isNum(v) && v < 60;
      return `<tr class="clickable ${p.portid === state.ship ? "selected" : ""}" data-ship="${esc(p.portid)}"><td>${esc(p.portname.replace(/ Strait$/, ""))}</td>
        <td><b>${fixed(p.avg7, 0)}</b></td><td class="dim">${fixed(p.normal, 0)}</td>
        <td class="${dropped ? "neg" : isNum(v) && v > 115 ? "pos" : ""}">${isNum(v) ? `${v.toFixed(0)}%` : "–"}</td><td class="dim">${fixed(p.year_ago, 0)}</td>
        <td>${fixed(p.tankers7, 0)} <span class="dim">/ ${fixed(p.tankers_normal, 0)}</span></td>
        <td style="width:90px">${sparkline(p.spark)}</td></tr>`; }).join("")}</tbody></table>`;
  }

  async function loadShipChart() {
    const d = await api(`/api/shipping?id=${encodeURIComponent(state.ship)}`);
    state.shipDetail = d.detail || [];
    drawShipChart();
  }

  function drawShipChart() {
    const rows = state.shipDetail || [];
    const port = state.shipData?.ports.find((p) => p.portid === state.ship);
    $("#nw-ship-chart-title").textContent = port ? `${port.portname}: ships per day` : "Chokepoint history";
    $("#nw-ship-range").innerHTML = RANGES.map(([n, label]) => `<button class="chip ${n === state.range ? "active" : ""}" data-nw-range="${n}">${label}</button>`).join("");
    if (!rows.length) { $("#nw-ship-chart").innerHTML = `<div class="empty" style="padding:16px">No history.</div>`; return; }
    const from = state.range ? new Date(Date.parse(rows[rows.length - 1].date) - state.range * 86400000).toISOString().slice(0, 10) : "";
    const r = rows.filter((x) => x.date >= from);
    const avg7 = r.map((x, i) => { const w = r.slice(Math.max(0, i - 6), i + 1); return { time: x.date, value: w.reduce((a, b) => a + b.n_total, 0) / w.length }; });
    $("#nw-ship-legend").innerHTML = `<span><i style="background:var(--text-muted)"></i>Each day</span><span><i style="background:var(--series-1)"></i>7-day average</span>
      <span><i style="background:var(--series-2)"></i>Tankers (7-day average)</span>${port && isNum(port.normal) ? `<span class="dim">Normal (2023): ${port.normal.toFixed(0)} a day</span>` : ""}`;
    const c = (state.chart = makeChart($("#nw-ship-chart")));
    c.addHistogramSeries({ color: css("--text-muted"), priceLineVisible: false, lastValueVisible: false }).setData(r.map((x) => ({ time: x.date, value: x.n_total })));
    c.addLineSeries({ color: css("--series-1"), lineWidth: 2, priceLineVisible: false }).setData(avg7);
    const tank = r.map((x, i) => { const w = r.slice(Math.max(0, i - 6), i + 1); return { time: x.date, value: w.reduce((a, b) => a + b.n_tanker, 0) / w.length }; });
    c.addLineSeries({ color: css("--series-2"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(tank);
    c.timeScale().fitContent();
  }

  // The chart is drawn before its panel has its final width; refit whenever the panel resizes (as gamma.js does).
  new ResizeObserver(() => state.chart?.timeScale().fitContent()).observe($("#nw-ship-chart"));

  loaders.news = async () => {
    const [d, s] = await Promise.all([
      api(`/api/news?topic=${state.topic}&hours=${state.hours}&q=${encodeURIComponent(state.q)}`),
      state.shipData ? Promise.resolve(state.shipData) : api("/api/shipping"),
    ]);
    state.shipData = s;
    if (!d.ready) { $("#nw-top").innerHTML = `<div class="empty">The news collector hasn't run yet.</div>`; return; }
    drawToolbar(d.counts);
    badge($("#nw-badge"), d.newest, 30, `Updated ${ago(d.newest)}`);
    drawStories(d); drawLatest(d); drawFed(d.fed); drawFeeds(d); drawShips();
    if (!state.shipDetail) await loadShipChart();
  };
})();
