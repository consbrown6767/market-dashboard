/* Market Dashboard front end. Plain JS, no build step. Reads /api/* from dashboard/server.py. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path) => {
  const r = await fetch(path);
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
};

// ---------- formatting
const isNum = (x) => typeof x === "number" && isFinite(x);
const fixed = (x, d = 2) => (isNum(x) ? x.toFixed(d) : "–");
const signed = (x, d = 2, suffix = "%") => (isNum(x) ? `${x > 0 ? "+" : ""}${x.toFixed(d)}${suffix}` : "–");
const cls = (x) => (!isNum(x) || x === 0 ? "dim" : x > 0 ? "pos" : "neg");
const big = (x) => {
  if (!isNum(x)) return "–";
  const a = Math.abs(x);
  if (a >= 1e9) return `${(x / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(x / 1e3).toFixed(0)}K`;
  return x.toFixed(0);
};
const usd = (x) => (isNum(x) ? `$${big(x)}` : "–");
const minutesAgo = (ts) => (ts ? (Date.now() - new Date(ts).getTime()) / 60000 : Infinity);
const ago = (ts) => {
  const m = minutesAgo(ts);
  if (!isFinite(m)) return "never";
  if (m < 1) return "just now";
  if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 48 * 60) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
};
const etTime = (ts) => (ts ? new Date(ts).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "–");
const shortDate = (ts) => (ts ? new Date(ts).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", year: "2-digit" }) : "–");
function badge(el, ts, freshMinutes, label) {
  const m = minutesAgo(ts);
  el.className = `badge ${m <= freshMinutes ? "fresh" : m <= freshMinutes * 3 ? "stale" : "down"}`;
  el.textContent = label ?? ago(ts);
  el.title = ts ? `Data from ${etTime(ts)} ET` : "No data yet";
}

// ---------- charts (TradingView Lightweight Charts, styled like the panels)
function makeChart(el, opts = {}) {
  el.innerHTML = "";
  return LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { type: "solid", color: css("--surface") }, textColor: css("--text-dim"), fontFamily: css("--font-mono"), fontSize: 10 },
    grid: { vertLines: { color: css("--border-subtle") }, horzLines: { color: css("--border-subtle") } },
    rightPriceScale: { borderColor: css("--border") },
    timeScale: { borderColor: css("--border") },
    crosshair: { mode: 0 },
    ...opts,
  });
}

// ---------- tabs, clock, status
const loaders = {};
let current = "options";
function show(view) {
  current = loaders[view] ? view : "options";
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === current));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${current}`));
  history.replaceState(null, "", `#${current}`);
  loaders[current]().catch(showError);
}
function showError(e) {
  console.error(e);
  const s = $("#status");
  s.className = "status-indicator down";
  $("#status-text").textContent = "Error";
  s.title = String(e);
}
$("#tabs").addEventListener("click", (e) => e.target.dataset.view && show(e.target.dataset.view));
setInterval(() => {
  $("#clock").textContent = new Date().toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) + " ET";
}, 1000);

async function refreshStatus() {
  const h = await api("/api/health");
  const jobs = Object.fromEntries(h.jobs.map((j) => [j.job, j]));
  const failed = h.jobs.filter((j) => ["daily", "snapshot", "events", "positioning", "spreads"].includes(j.job) && j.status === "failed");
  const s = $("#status");
  if (failed.length) {
    s.className = "status-indicator down";
    $("#status-text").textContent = `${failed.map((j) => j.job).join(", ")} failed`;
  } else if (minutesAgo(jobs.events?.started_at) > 150) {
    s.className = "status-indicator stale";
    $("#status-text").textContent = "Stale";
  } else {
    s.className = "status-indicator";
    $("#status-text").textContent = "Collecting";
  }
  s.title = `Database ${h.db_mb} MB`;
  return h;
}

// ---------- OPTIONS
loaders.options = async () => {
  const d = await api("/api/options");
  const latest = d.stocks[0]?.ts;
  badge($("#opt-badge"), latest, 75, latest ? `Snapshot ${ago(latest)}` : "No snapshot");
  $("#opt-count").textContent = `${d.stocks.length} symbols`;
  $("#opt-table").innerHTML = `<table><thead><tr><th>Symbol</th><th>Price</th><th>Chg</th><th>Volume</th><th>OI fetched</th><th title="Every strike × expiration OCC lists, out to ~3 years">OCC series</th><th title="Contracts priced each hour: expirations ≤60 days, strikes ±25% of price, call + put">In snapshot</th></tr></thead><tbody>${d.stocks
    .map((s) => {
      const chg = s.prev_close ? (s.price / s.prev_close - 1) * 100 : null;
      return `<tr class="clickable ${s.symbol === od.symbol ? "selected" : ""}" data-symbol="${esc(s.symbol)}"><td>${esc(s.symbol)}</td><td>${fixed(s.price)}</td><td class="${cls(chg)}">${signed(chg)}</td>
        <td title="source: ${esc(s.volume_source)}">${big(s.volume)}${s.volume_source === "alpaca_sip" ? " *" : ""}</td>
        <td>${s.date ? esc(s.date) : "–"}${s.backup ? " (Yahoo)" : ""}</td><td>${s.strikes ?? "–"}</td><td>${s.contracts ?? "–"}</td></tr>`;
    })
    .join("")}</tbody></table>`;
  loadWatchlists().catch(showError);
  await loadOptionDetail();
  loadSymbolViews().catch(showError); // price chart + chain: only re-fetched when the symbol changes

  const g = d.gamma;
  if (g.length) {
    const last = g[g.length - 1];
    const vals = g.map((x) => x.gex).sort((a, b) => a - b);
    const pctile = (100 * vals.filter((v) => v <= last.gex).length) / vals.length;
    badge($("#gex-badge"), `${last.date}T16:00:00-04:00`, 60 * 36, last.date);
    $("#gex-stats").innerHTML = `<div class="stat"><small>Dealer gamma</small><strong>$${fixed(last.gex / 1e9)}B</strong><em>${shortDate(last.date + "T12:00:00")}</em></div>
      <div class="stat"><small>12-mo percentile</small><strong>${fixed(pctile, 0)}%</strong><em>${pctile < 25 ? "low: moves can run" : pctile > 75 ? "high: moves damped" : "middle of range"}</em></div>
      <div class="stat"><small>S&amp;P 500</small><strong>${fixed(last.spx, 0)}</strong><em>DIX ${fixed(last.dix * 100, 1)}%</em></div>`;
    const ch = makeChart($("#gex-chart"));
    ch.addHistogramSeries({ priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false })
      .setData(g.map((x) => ({ time: x.date, value: x.gex, color: x.gex >= 0 ? "rgba(68,170,68,.6)" : "rgba(255,68,68,.7)" })));
    ch.timeScale().fitContent();
  }

  if (d.cftc.length) {
    badge($("#cftc-badge"), `${d.cftc[0].available_date}T16:00:00-04:00`, 60 * 24 * 8, `As of ${shortDate(d.cftc[0].report_date + "T12:00:00")}`);
    $("#cftc-table").innerHTML = `<table><thead><tr><th>Contract</th><th>Hedge funds</th><th>Asset mgrs</th><th>Dealers</th></tr></thead><tbody>${d.cftc
      .map((c) => {
        const dealer = c.open_interest ? (100 * c.dealer_net) / c.open_interest : null;
        return `<tr><td>${esc(c.contract)}</td><td class="${cls(c.lev_money_net_pct_oi)}">${signed(c.lev_money_net_pct_oi, 1)}</td>
          <td class="${cls(c.asset_mgr_net_pct_oi)}">${signed(c.asset_mgr_net_pct_oi, 1)}</td><td class="${cls(dealer)}">${signed(dealer, 1)}</td></tr>`;
      })
      .join("")}</tbody></table>`;
  }
};

// ---------- WATCHLISTS: universal (every symbol with data) and custom lists (shared/watchlists.json)
const wl = { universe: [], lists: [], cur: null };
try { wl.cur = localStorage.getItem("watchlists:cur"); } catch { /* private mode etc. */ }
const curList = () => wl.lists.find((l) => l.id === wl.cur);

async function loadWatchlists() {
  const d = await api("/api/watchlists");
  wl.universe = d.universe; wl.lists = d.lists;
  renderWatchlists();
}
async function editWatchlists(body) {
  const r = await fetch("/api/watchlists", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.error) { $("#ml-msg").textContent = j.error || r.statusText; return false; }
  wl.lists = j.lists;
  if (j.id !== undefined) wl.cur = j.id;
  try { localStorage.setItem("watchlists:cur", wl.cur ?? ""); } catch { /* ignore */ }
  $("#ml-msg").textContent = "";
  renderWatchlists();
  return true;
}

function renderWatchlists() {
  if (!curList()) wl.cur = wl.lists[0]?.id ?? null;
  const list = curList(), bySym = new Map(wl.universe.map((u) => [u.symbol, u]));
  const row = (u, action) => {
    const tags = `${u.options ? `<span class="grp-tag">OPT</span>` : ""}${u.spreads ? `<span class="grp-tag">SPR</span>` : ""}`;
    return `<tr class="clickable ${u.symbol === od.symbol ? "selected" : ""}" data-symbol="${esc(u.symbol)}"><td><b>${esc(u.symbol)}</b></td>
      <td>${fixed(u.price)}</td><td class="${cls(u.change)}">${signed(u.change)}</td><td>${tags}</td><td>${action}</td></tr>`;
  };
  const head = `<thead><tr><th>Symbol</th><th>Price</th><th>Chg</th><th>Data</th><th></th></tr></thead>`;

  $("#uni-count").textContent = `${wl.universe.length} symbols`;
  $("#uni-target").textContent = list ? `+ adds to ${list.name}` : "make a list in My watchlists to use +";
  $("#uni-table").innerHTML = `<table>${head}<tbody>${wl.universe.map((u) => row(u, !list ? ""
    : list.symbols.includes(u.symbol) ? `<span class="dim" title="Already in ${esc(list.name)}">✓</span>`
    : `<button class="chip" data-add="${esc(u.symbol)}" title="Add to ${esc(list.name)}">+</button>`)).join("")}</tbody></table>`;

  $("#ml-select").innerHTML = wl.lists.map((l) => `<option value="${esc(l.id)}" ${l.id === wl.cur ? "selected" : ""}>${esc(l.name)} (${l.symbols.length})</option>`).join("");
  $("#ml-select").hidden = !wl.lists.length;
  $("#ml-rename").hidden = $("#ml-delete").hidden = !list;
  $("#ml-count").textContent = `${wl.lists.length} list${wl.lists.length === 1 ? "" : "s"}`;
  $("#ml-table").innerHTML = !list ? `<div class="empty" style="padding:16px">No watchlists yet: click New.</div>`
    : !list.symbols.length ? `<div class="empty" style="padding:16px">${esc(list.name)} is empty. Use + in the universal watchlist to add stocks.</div>`
    : `<table>${head}<tbody>${list.symbols.map((sym) => row(bySym.get(sym) || { symbol: sym },
        `<button class="chip" data-remove="${esc(sym)}" title="Remove from ${esc(list.name)}">×</button>`)).join("")}</tbody></table>`;
}

for (const id of ["#uni-table", "#ml-table"]) {
  $(id).addEventListener("click", (e) => {
    const add = e.target.closest("[data-add]")?.dataset.add, rm = e.target.closest("[data-remove]")?.dataset.remove;
    if (add) return editWatchlists({ action: "add", id: wl.cur, symbol: add }).catch(showError);
    if (rm) return editWatchlists({ action: "remove", id: wl.cur, symbol: rm }).catch(showError);
    const sym = e.target.closest("tr[data-symbol]")?.dataset.symbol;
    if (!sym) return;
    pickSymbol(sym);
    renderWatchlists();
    $('[data-panel="od-summary"]').scrollIntoView({ behavior: "smooth", block: "start" });
  });
}
$("#ml-select").addEventListener("change", (e) => {
  wl.cur = e.target.value;
  try { localStorage.setItem("watchlists:cur", wl.cur); } catch { /* ignore */ }
  renderWatchlists();
});
$("#ml-new").addEventListener("click", () => {
  const name = prompt("Name for the new watchlist:");
  if (name?.trim()) editWatchlists({ action: "create", name }).catch(showError);
});
$("#ml-rename").addEventListener("click", () => {
  const list = curList(), name = list && prompt(`Rename "${list.name}" to:`, list.name);
  if (name?.trim() && name.trim() !== list.name) editWatchlists({ action: "rename", id: list.id, name }).catch(showError);
});
$("#ml-delete").addEventListener("click", () => {
  const list = curList();
  if (list && confirm(`Delete the watchlist "${list.name}"? The stocks stay in the universal watchlist.`))
    editWatchlists({ action: "delete", id: list.id }).catch(showError);
});

// ---------- OPTIONS DETAIL (one symbol: open interest, volume and IV by strike; per-expiration summary)
// The three strike charts share one zoom window: mouse wheel zooms around the pointer, drag pans,
// double-click resets. The y-axis always rescales to the bars in view, so a few huge strikes (index
// hedges at round numbers) don't flatten everything else; "Compressed" uses a square-root scale.
const od = { symbol: "SPY", exp: "30d", data: null, rows: [], ivQuotes: [], lo: null, hi: null, preset: 10, scale: "linear" };
const ZOOM_PRESETS = [5, 10, 20, null]; // ± % of price; null = everything loaded (±30%)

$("#opt-table").addEventListener("click", (e) => {
  const sym = e.target.closest("tr[data-symbol]")?.dataset.symbol;
  if (!sym) return;
  pickSymbol(sym);
  $('[data-panel="od-summary"]').scrollIntoView({ behavior: "smooth", block: "start" });
});
$("#od-exps").addEventListener("click", (e) => {
  const x = e.target.closest("[data-exp]")?.dataset.exp;
  if (x) { od.exp = x; renderOptionDetail(); }
});
$("#od-exp-table").addEventListener("click", (e) => {
  const x = e.target.closest("tr[data-exp]")?.dataset.exp;
  if (x) { od.exp = x; renderOptionDetail(); }
});
document.querySelectorAll("[data-strike-controls]").forEach((box) => {
  box.innerHTML = ZOOM_PRESETS.map((p) => `<button class="chip" data-zoom="${p ?? "all"}">${p ? `±${p}%` : "All"}</button>`).join("") +
    `<button class="chip" data-scale="1" title="Square-root scale: keeps small strikes visible next to huge ones">Compressed</button>`;
  box.addEventListener("click", (e) => {
    const z = e.target.closest("[data-zoom]")?.dataset.zoom;
    if (z) { od.preset = z === "all" ? null : +z; setPresetView(); drawStrikeCharts(); }
    if (e.target.closest("[data-scale]")) { od.scale = od.scale === "linear" ? "sqrt" : "linear"; drawStrikeCharts(); }
  });
});

async function loadOptionDetail() {
  try { od.data = await api(`/api/option_detail?symbol=${encodeURIComponent(od.symbol)}`); }
  catch (e) { od.data = { error: String(e) }; }
  renderOptionDetail();
}

const expLabel = (e) => `${new Date(e.expiration + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })} · ${e.days}d`;

function strikeDomain() {
  const ks = od.data.oi.map((r) => r.strike).concat(od.data.quotes.map((q) => q.strike));
  return ks.length ? [Math.min(...ks), Math.max(...ks)] : [od.data.price * 0.7, od.data.price * 1.3];
}
function setPresetView() {
  const [dlo, dhi] = strikeDomain(), p = od.data.price;
  od.lo = od.preset ? Math.max(dlo, p * (1 - od.preset / 100)) : dlo;
  od.hi = od.preset ? Math.min(dhi, p * (1 + od.preset / 100)) : dhi;
}

function renderOptionDetail() {
  const d = od.data;
  if (!d || d.error) {
    $("#od-title").textContent = `${od.symbol} options`;
    $("#od-badge").textContent = "Not collected";
    $("#od-exps").innerHTML = "";
    $("#od-stats").innerHTML = `<div class="stat" style="grid-column:1/-1"><em>${esc(od.symbol)} isn't on the watchlist, so there's no collected open-interest/volume/IV history below. Its price chart and live options chain still work. Add it to shared/watchlist.json to start collecting.</em></div>`;
    for (const id of ["#od-oi", "#od-vol", "#od-iv", "#od-exp-table"]) $(id).innerHTML = `<div class="empty" style="padding:16px">Not collected for ${esc(od.symbol)}.</div>`;
    return;
  }
  if (od.lo === null) setPresetView();
  const inSel = (exp) => (od.exp === "30d" ? d.expirations.find((e) => e.expiration === exp)?.days <= 30 : exp === od.exp);
  const exps = d.expirations;
  // For IV and implied move with the 30-day view, use the nearest expiration at least a week out.
  const ref = od.exp === "30d" ? exps.find((e) => e.days >= 7 && e.atm_iv) : exps.find((e) => e.expiration === od.exp);

  $("#od-title").textContent = `${d.symbol} options · ${od.exp === "30d" ? "all expirations within 30 days" : expLabel(exps.find((e) => e.expiration === od.exp))}`;
  $("#od-badge").textContent = `OI ${d.oi_date} · snapshot ${ago(d.snapshot_ts)}`;
  $("#od-exps").innerHTML = `<button class="chip ${od.exp === "30d" ? "active" : ""}" data-exp="30d">≤30 days</button> ` +
    exps.map((e) => `<button class="chip ${od.exp === e.expiration ? "active" : ""}" data-exp="${e.expiration}">${expLabel(e)}</button>`).join(" ");

  const strikes = new Map();
  const at = (k) => strikes.get(k) || strikes.set(k, { strike: k, call_oi: 0, put_oi: 0, call_vol: 0, put_vol: 0 }).get(k);
  for (const r of d.oi) if (inSel(r.expiration)) { const s = at(r.strike); s.call_oi += r.call_oi || 0; s.put_oi += r.put_oi || 0; }
  for (const q of d.quotes) if (inSel(q.expiration)) { const s = at(q.strike); s[q.type === "call" ? "call_vol" : "put_vol"] += q.volume || 0; }
  od.rows = [...strikes.values()].sort((a, b) => a.strike - b.strike);
  od.ivQuotes = ref ? d.quotes.filter((q) => q.expiration === ref.expiration && q.iv) : [];

  const sum = (k) => od.rows.reduce((t, r) => t + r[k], 0);
  const topCall = od.rows.reduce((a, b) => (b.call_oi > (a?.call_oi ?? -1) ? b : a), null);
  const topPut = od.rows.reduce((a, b) => (b.put_oi > (a?.put_oi ?? -1) ? b : a), null);
  const chg = d.prev_close ? (d.price / d.prev_close - 1) * 100 : null;
  const pcOi = sum("call_oi") ? sum("put_oi") / sum("call_oi") : null, pcVol = sum("call_vol") ? sum("put_vol") / sum("call_vol") : null;
  const dist = (k) => (k ? signed((k / d.price - 1) * 100, 1) + " from price" : "");
  $("#od-stats").innerHTML = [
    ["Price", fixed(d.price), signed(chg) + " today", cls(chg)],
    ["Most call OI", topCall ? `$${topCall.strike}` : "–", topCall ? `${big(topCall.call_oi)} contracts · ${dist(topCall.strike)}` : ""],
    ["Most put OI", topPut ? `$${topPut.strike}` : "–", topPut ? `${big(topPut.put_oi)} contracts · ${dist(topPut.strike)}` : ""],
    ["Put/call OI", fixed(pcOi), `${big(sum("put_oi"))} puts · ${big(sum("call_oi"))} calls`],
    ["Put/call volume", fixed(pcVol), `${big(sum("put_vol"))} puts · ${big(sum("call_vol"))} calls today`],
    ["ATM implied vol", ref?.atm_iv ? `${fixed(ref.atm_iv * 100, 1)}%` : "–", ref ? `${expLabel(ref)} · $${ref.atm_strike} strike` : ""],
    ["Implied move", ref?.implied_move ? `±${fixed(ref.implied_move, 1)}%` : "–", ref?.implied_move ? `±$${fixed((ref.implied_move * d.price) / 100)} by ${expLabel(ref).split(" ·")[0]}` : ""],
  ].map(([k, v, sub, c]) => `<div class="stat"><small>${k}</small><strong class="${c || ""}">${v}</strong><em>${sub}</em></div>`).join("");
  $("#od-vol-note").textContent = `snapshot ${etTime(d.snapshot_ts)} ET`;
  $("#od-iv-note").textContent = ref ? `(${expLabel(ref)})` : "";

  $("#od-exp-table").innerHTML = `<table><thead><tr><th>Expiration</th><th>Call OI</th><th>Put OI</th><th>P/C</th><th>Call vol</th><th>Put vol</th><th>ATM IV</th><th>Implied move</th></tr></thead><tbody>${exps
    .map((e) => `<tr class="clickable ${od.exp === e.expiration ? "selected" : ""}" data-exp="${e.expiration}"><td>${expLabel(e)}</td><td>${big(e.call_oi)}</td><td>${big(e.put_oi)}</td>
      <td>${e.call_oi ? fixed(e.put_oi / e.call_oi) : "–"}</td><td>${big(e.call_vol)}</td><td>${big(e.put_vol)}</td>
      <td>${e.atm_iv ? fixed(e.atm_iv * 100, 1) + "%" : "–"}</td><td>${e.implied_move ? "±" + fixed(e.implied_move, 1) + "%" : "–"}</td></tr>`).join("")}</tbody></table>`;
  drawStrikeCharts();
}

const CHART_PAD = { L: 46, R: 10, T: 18, B: 20 };
function drawStrikeCharts() {
  if (!od.data || od.data.error) return;
  document.querySelectorAll("[data-strike-controls]").forEach((box) => {
    box.querySelectorAll("[data-zoom]").forEach((b) => b.classList.toggle("active", (od.preset === null ? "all" : String(od.preset)) === b.dataset.zoom));
    box.querySelector("[data-scale]").classList.toggle("active", od.scale === "sqrt");
  });
  const inView = (k) => k >= od.lo && k <= od.hi;
  $("#od-oi").innerHTML = mirrorBars($("#od-oi"), od.rows.filter((r) => inView(r.strike)), "call_oi", "put_oi", "open interest");
  $("#od-vol").innerHTML = mirrorBars($("#od-vol"), od.rows.filter((r) => inView(r.strike) && (r.call_vol || r.put_vol)), "call_vol", "put_vol", "volume");
  $("#od-iv").innerHTML = ivCurve($("#od-iv"), od.ivQuotes.filter((q) => inView(q.strike)));
}

const xScale = (W) => (k) => CHART_PAD.L + ((k - od.lo) / (od.hi - od.lo || 1)) * (W - CHART_PAD.L - CHART_PAD.R);
const strikeTicks = () => Array.from({ length: 7 }, (_, i) => od.lo + ((od.hi - od.lo) * i) / 6)
  .map((k) => (k >= 100 ? k.toFixed(0) : k.toFixed(1)));
const hint = `<div class="strike-hint">scroll to zoom · drag to pan · double-click to reset</div>`;

// Calls drawn up, puts down, by strike, with the current price marked.
function mirrorBars(host, data, upKey, downKey, unit) {
  if (!data.length) return `<div class="empty" style="padding:16px">No ${unit} in this range.</div>`;
  const W = host.clientWidth || 600, H = host.clientHeight || 280, { L, R, T, B } = CHART_PAD, mid = T + (H - T - B) / 2;
  const x = xScale(W), price = od.data.price;
  const max = Math.max(1, ...data.map((r) => Math.max(r[upKey], r[downKey])));
  const f = od.scale === "sqrt" ? (v) => Math.sqrt(v / max) : (v) => v / max;
  const h = (v) => f(v) * (mid - T);
  const gaps = data.slice(1).map((r, i) => x(r.strike) - x(data[i].strike)).filter((g) => g > 0);
  const bw = Math.max(1, Math.min(24, (gaps.length ? Math.min(...gaps) : 12) * 0.8));
  const bars = data.map((r) => {
    const tip = `<title>$${r.strike}: ${r[upKey].toLocaleString()} calls · ${r[downKey].toLocaleString()} puts</title>`;
    return `<rect x="${x(r.strike) - bw / 2}" y="${mid - h(r[upKey])}" width="${bw}" height="${h(r[upKey])}" fill="${css("--normal")}">${tip}</rect>` +
      `<rect x="${x(r.strike) - bw / 2}" y="${mid}" width="${bw}" height="${h(r[downKey])}" fill="${css("--critical")}" opacity=".85">${tip}</rect>`;
  }).join("");
  const px = price >= od.lo && price <= od.hi ? `<line class="price" x1="${x(price)}" x2="${x(price)}" y1="${T}" y2="${H - B}"/><text class="price-label" x="${x(price) + 4}" y="${T + 10}">${fixed(price)}</text>` : "";
  const half = od.scale === "sqrt" ? max / 4 : max / 2; // value drawn at half height
  return `<svg class="bars strike-chart" width="${W}" height="${H}">
    <line class="grid" x1="${L}" x2="${W - R}" y1="${T}" y2="${T}"/><line class="grid" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>
    <line class="grid" x1="${L}" x2="${W - R}" y1="${(T + mid) / 2}" y2="${(T + mid) / 2}"/><line class="grid" x1="${L}" x2="${W - R}" y1="${(mid + H - B) / 2}" y2="${(mid + H - B) / 2}"/>
    <text x="${L - 4}" y="${T + 3}" text-anchor="end">${big(max)}</text><text x="${L - 4}" y="${(T + mid) / 2 + 3}" text-anchor="end">${big(half)}</text>
    <text x="${L - 4}" y="${mid + 3}" text-anchor="end">0</text>
    <text x="${L - 4}" y="${(mid + H - B) / 2 + 3}" text-anchor="end">${big(half)}</text><text x="${L - 4}" y="${H - B + 3}" text-anchor="end">${big(max)}</text>
    ${bars}<line class="axis" x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}"/>${px}
    ${strikeTicks().map((k, i) => `<text x="${x(od.lo + ((od.hi - od.lo) * i) / 6)}" y="${H - 6}" text-anchor="middle">${k}</text>`).join("")}</svg>${hint}`;
}

function ivCurve(host, quotes) {
  if (quotes.length < 3) return `<div class="empty" style="padding:16px">Not enough implied-volatility points in this range.</div>`;
  const W = host.clientWidth || 600, H = host.clientHeight || 280, { L, R, T, B } = CHART_PAD, price = od.data.price;
  const ivs = quotes.map((q) => q.iv), vlo = Math.min(...ivs) * 0.95, vhi = Math.max(...ivs) * 1.05;
  const x = xScale(W), y = (v) => H - B - ((v - vlo) / (vhi - vlo || 1)) * (H - T - B);
  const line = (type, color) => {
    const pts = quotes.filter((q) => q.type === type).sort((a, b) => a.strike - b.strike);
    return `<polyline fill="none" stroke="${color}" stroke-width="1.5" points="${pts.map((q) => `${x(q.strike)},${y(q.iv)}`).join(" ")}"/>` +
      pts.map((q) => `<circle cx="${x(q.strike)}" cy="${y(q.iv)}" r="2" fill="${color}"><title>$${q.strike} ${type}: ${(q.iv * 100).toFixed(1)}%</title></circle>`).join("");
  };
  const yt = Array.from({ length: 5 }, (_, i) => vlo + ((vhi - vlo) * i) / 4);
  const px = price >= od.lo && price <= od.hi ? `<line class="price" x1="${x(price)}" x2="${x(price)}" y1="${T}" y2="${H - B}"/>` : "";
  return `<svg class="bars strike-chart" width="${W}" height="${H}">
    ${yt.map((v) => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 4}" y="${y(v) + 3}" text-anchor="end">${(v * 100).toFixed(0)}%</text>`).join("")}
    ${px}${line("call", css("--series-1"))}${line("put", css("--series-2"))}
    ${strikeTicks().map((k, i) => `<text x="${x(od.lo + ((od.hi - od.lo) * i) / 6)}" y="${H - 6}" text-anchor="middle">${k}</text>`).join("")}</svg>${hint}`;
}

// Zoom / pan on any of the strike charts (shared window).
for (const id of ["od-oi", "od-vol", "od-iv"]) {
  const host = $(`#${id}`);
  const frac = (clientX) => {
    const r = host.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - r.left - CHART_PAD.L) / (r.width - CHART_PAD.L - CHART_PAD.R)));
  };
  const clampView = (lo, hi) => {
    const [dlo, dhi] = strikeDomain(), minSpan = (dhi - dlo) * 0.02 || 1;
    if (hi - lo < minSpan) { const c = (lo + hi) / 2; lo = c - minSpan / 2; hi = c + minSpan / 2; }
    const span = Math.min(hi - lo, dhi - dlo);
    lo = Math.max(dlo, Math.min(lo, dhi - span));
    od.lo = lo; od.hi = lo + span; od.preset = undefined;
  };
  host.addEventListener("wheel", (e) => {
    if (!od.data || od.data.error) return;
    e.preventDefault();
    const k = od.lo + frac(e.clientX) * (od.hi - od.lo), f = Math.exp(e.deltaY * 0.0015);
    clampView(k - (k - od.lo) * f, k + (od.hi - k) * f);
    drawStrikeCharts();
  }, { passive: false });
  host.addEventListener("pointerdown", (e) => {
    if (!od.data || od.data.error || e.button !== 0) return;
    host.setPointerCapture(e.pointerId);
    const lo0 = od.lo, hi0 = od.hi, x0 = e.clientX, w = host.getBoundingClientRect().width - CHART_PAD.L - CHART_PAD.R;
    const move = (ev) => {
      const dk = ((ev.clientX - x0) / w) * (hi0 - lo0);
      clampView(lo0 - dk, hi0 - dk);
      host.firstElementChild?.classList.add("panning");
      drawStrikeCharts();
    };
    const up = () => { host.removeEventListener("pointermove", move); host.removeEventListener("pointerup", up); };
    host.addEventListener("pointermove", move); host.addEventListener("pointerup", up);
  });
  host.addEventListener("dblclick", () => { od.preset = 10; setPresetView(); drawStrikeCharts(); });
  new ResizeObserver(() => drawStrikeCharts()).observe(host);
}

// ---------- PRICE CHART, OPTIONS CHAIN, CONTRACT CHART (fetched live from Alpaca/OCC on demand)
// Pick a symbol (click a row, or type any ticker), see its price history and full chain; click a
// bid/ask/last in the chain to chart that one contract (Robinhood-Legend style candles + volume).
const sel = { loaded: null, pxRange: "3M", chExp: null, chain: null, contract: null, ctRange: "1W" };
const PX_RANGES = ["1D", "1W", "1M", "3M", "1Y", "5Y"], CT_RANGES = ["1D", "1W", "1M", "ALL"];

$("#px-range").innerHTML = PX_RANGES.map((r) => `<button class="chip" data-r="${r}">${r}</button>`).join("");
$("#ct-range").innerHTML = CT_RANGES.map((r) => `<button class="chip" data-r="${r}">${r === "ALL" ? "All" : r}</button>`).join("");
$("#px-range").addEventListener("click", (e) => { const r = e.target.dataset.r; if (r) { sel.pxRange = r; loadPriceChart().catch(showError); } });
$("#ct-range").addEventListener("click", (e) => { const r = e.target.dataset.r; if (r && sel.contract) { sel.ctRange = r; loadContractChart().catch(showError); } });
$("#ch-exps").addEventListener("click", (e) => { const x = e.target.closest("[data-exp]")?.dataset.exp; if (x) { sel.chExp = x; loadChain().catch(showError); } });
$("#od-symbol").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !e.target.value.trim()) return;
  pickSymbol(e.target.value.trim().toUpperCase().replace(/[^A-Z.]/g, ""));
  e.target.value = "";
  e.target.blur();
});

function pickSymbol(sym) {
  od.symbol = sym; od.exp = "30d"; od.lo = null;
  document.querySelectorAll("#opt-table tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.symbol === sym));
  loadOptionDetail().catch(() => {}).finally(() => loadSymbolViews().catch(showError));
}

async function loadSymbolViews() {
  if (sel.loaded === od.symbol) return;
  sel.loaded = od.symbol; sel.chExp = null; sel.chain = null; sel.contract = null;
  $("#ct-title").textContent = "Option contract"; $("#ct-stats").innerHTML = ""; $("#ct-empty").style.display = "";
  $("#ct-chart").innerHTML = "";
  await Promise.all([loadPriceChart(), loadChain()]);
}

function candles(el, bars, intraday) {
  const ch = makeChart(el, { timeScale: { borderColor: css("--border"), timeVisible: intraday, secondsVisible: false } });
  const price = ch.addCandlestickSeries({ upColor: css("--normal"), downColor: css("--critical"), borderVisible: false,
    wickUpColor: css("--normal"), wickDownColor: css("--critical") });
  price.setData(bars.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
  const vol = ch.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
  ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  vol.setData(bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(68,170,68,.35)" : "rgba(255,68,68,.35)" })));
  ch.timeScale().fitContent();
  return ch;
}

async function loadPriceChart() {
  const sym = od.symbol, d = await api(`/api/stock_bars?symbol=${encodeURIComponent(sym)}&range=${sel.pxRange}`);
  if (sym !== od.symbol) return;
  document.querySelectorAll("#px-range .chip").forEach((c) => c.classList.toggle("active", c.dataset.r === sel.pxRange));
  $("#px-title").textContent = `${sym} price · ${sel.pxRange}`;
  if (!d.bars.length) { $("#px-chart").innerHTML = `<div class="empty" style="padding:16px">No price data for ${esc(sym)}.</div>`; $("#px-last").textContent = ""; return; }
  const first = d.bars[0].open, last = d.bars[d.bars.length - 1].close, chg = (last / first - 1) * 100;
  $("#px-last").innerHTML = `${fixed(last)} <span class="${cls(chg)}">${signed(chg)}</span>`;
  candles($("#px-chart"), d.bars, d.intraday);
}

async function loadChain() {
  const sym = od.symbol;
  if (!sel.chExp) {
    const ex = await api(`/api/chain_expirations?symbol=${encodeURIComponent(sym)}`);
    sel.exps = ex.expirations;
    sel.chExp = (ex.expirations.find((e) => e.days >= 1) || ex.expirations[0])?.expiration;
    if (!sel.chExp) { $("#ch-table").innerHTML = `<div class="empty" style="padding:16px">No listed options found for ${esc(sym)}.</div>`; return; }
  }
  $("#ch-exps").innerHTML = sel.exps.map((e) => `<button class="chip ${e.expiration === sel.chExp ? "active" : ""}" data-exp="${e.expiration}">${expLabel(e)}</button>`).join(" ");
  $("#ch-title").textContent = `${sym} options chain`;
  $("#ch-table").innerHTML = `<div class="empty" style="padding:16px">Loading chain…</div>`;
  const d = (sel.chain = await api(`/api/chain?symbol=${encodeURIComponent(sym)}&exp=${sel.chExp}`));
  if (sym !== od.symbol) return;
  badge($("#ch-badge"), d.fetched_at, 5, `Quotes ${etTime(d.fetched_at)} ET`);
  $("#ch-note").textContent = `price ${fixed(d.price)} · OI ${d.oi_date === "live" ? "live from OCC" : `as of ${d.oi_date}`} · click a bid, ask or last to chart it`;
  renderChain();
}

function renderChain() {
  const d = sel.chain, p = d.price;
  const cols = ["bid", "ask", "last", "volume", "oi", "iv", "delta"], head = ["Bid", "Ask", "Last", "Vol", "OI", "IV", "Δ"];
  const cell = (o, k) => {
    if (!o) return "–";
    const v = o[k];
    if (k === "iv") return isNum(v) ? `${(v * 100).toFixed(1)}%` : "–";
    if (k === "delta") return isNum(v) ? v.toFixed(2) : "–";
    if (k === "volume" || k === "oi") return isNum(v) ? v.toLocaleString() : "–";
    return isNum(v) ? v.toFixed(2) : "–";
  };
  const side = (r, type) => cols.map((k) => {
    const o = r[type], itm = type === "call" ? r.strike < p : r.strike > p;
    const pick = ["bid", "ask", "last"].includes(k) && o;
    const chosen = pick && sel.contract?.symbol === o.symbol;
    return `<td class="${itm ? "itm" : ""} ${pick ? "pick" : ""} ${chosen ? "chosen" : ""}" ${pick ? `data-contract="${esc(o.symbol)}"` : ""}>${cell(o, k)}</td>`;
  }).join("");
  let priceDone = false;
  const body = d.rows.map((r) => {
    let pre = "";
    if (!priceDone && isNum(p) && r.strike >= p) { pre = `<tr class="price-row" id="ch-price"><td colspan="${cols.length * 2 + 1}">${esc(d.symbol)} ${fixed(p)}</td></tr>`; priceDone = true; }
    return `${pre}<tr>${side(r, "call")}<td class="strike">${r.strike}</td>${side(r, "put")}</tr>`;
  }).join("");
  $("#ch-table").innerHTML = `<table class="chain"><thead>
    <tr><th class="side" colspan="${cols.length}">Calls</th><th class="strike">${new Date(d.expiration + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}</th><th class="side" colspan="${cols.length}">Puts</th></tr>
    <tr>${head.map((h) => `<th>${h}</th>`).join("")}<th class="strike">Strike</th>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>`;
  const pr = $("#ch-price"), box = $("#ch-table");
  if (pr) box.scrollTop = pr.offsetTop - box.clientHeight / 2;
}

$("#ch-table").addEventListener("click", (e) => {
  const c = e.target.closest("[data-contract]")?.dataset.contract;
  if (!c) return;
  const row = sel.chain.rows.find((r) => r.call?.symbol === c || r.put?.symbol === c);
  sel.contract = row.call?.symbol === c ? { ...row.call, type: "call", strike: row.strike } : { ...row.put, type: "put", strike: row.strike };
  document.querySelectorAll("#ch-table td.chosen").forEach((td) => td.classList.remove("chosen"));
  document.querySelectorAll(`#ch-table td[data-contract="${CSS.escape(c)}"]`).forEach((td) => td.classList.add("chosen"));
  loadContractChart().then(() => $('[data-panel="contract"]').scrollIntoView({ behavior: "smooth", block: "nearest" })).catch(showError);
});

async function loadContractChart() {
  const k = sel.contract, d = sel.chain;
  document.querySelectorAll("#ct-range .chip").forEach((c) => c.classList.toggle("active", c.dataset.r === sel.ctRange));
  const expTxt = new Date(d.expiration + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  $("#ct-title").textContent = `${d.symbol} $${k.strike} ${k.type === "call" ? "Call" : "Put"} · ${expTxt} (${d.days}d) · ${sel.ctRange}`;
  const be = isNum(k.mid) ? (k.type === "call" ? k.strike + k.mid : k.strike - k.mid) : null;
  const toBe = be && d.price ? (be / d.price - 1) * 100 : null;
  $("#ct-stats").innerHTML = [
    ["Bid / Ask", `${fixed(k.bid)} / ${fixed(k.ask)}`, `mid ${fixed(k.mid)} · ×100 = $${fixed(k.mid * 100, 0)}`],
    ["Last", fixed(k.last), `volume ${isNum(k.volume) ? k.volume.toLocaleString() : "–"} today`],
    ["Implied vol", isNum(k.iv) ? `${(k.iv * 100).toFixed(1)}%` : "–", `open interest ${isNum(k.oi) ? k.oi.toLocaleString() : "–"}`],
    ["Delta / Theta", `${fixed(k.delta)} / ${fixed(k.theta)}`, `gamma ${fixed(k.gamma, 3)} · vega ${fixed(k.vega)}`],
    ["Breakeven", be ? fixed(be) : "–", toBe !== null ? `${signed(toBe)} from ${fixed(d.price)}` : ""],
  ].map(([a, b, c]) => `<div class="stat"><small>${a}</small><strong>${b}</strong><em>${c}</em></div>`).join("");
  const bars = await api(`/api/option_bars?contract=${encodeURIComponent(k.symbol)}&range=${sel.ctRange}`);
  if (sel.contract?.symbol !== k.symbol) return;
  $("#ct-empty").style.display = bars.bars.length ? "none" : "";
  $("#ct-empty").textContent = bars.bars.length ? "" : "No trades in this range for this contract. Try a longer range.";
  if (bars.bars.length) candles($("#ct-chart"), bars.bars, bars.intraday); else $("#ct-chart").innerHTML = "";
}

// ---------- SPREADS
// Any two tickers: saved pairs (shared/pairs.json) show as chips; anything else is fetched on demand.
// The last pair viewed is remembered in this browser.
// History reaches back to 2000 where it exists (Yahoo before 2016, see dashboard/long_history.py).
// The window is a preset or custom from/to dates; the window row, stat and charts follow it.
const spreads = { pairs: [], sel: null, range: "1Y", from: "", to: "", data: null };
try { spreads.sel = JSON.parse(localStorage.getItem("spreads:sel")); } catch { /* private mode etc. */ }
const RANGES = { "1M": 30, "3M": 91, "6M": 182, YTD: "ytd", "1Y": 365, "3Y": 3 * 365, "5Y": 5 * 365, "10Y": 10 * 365, "20Y": 20 * 365, MAX: 1e6 };
$("#range").innerHTML = Object.keys(RANGES).map((r) => `<button class="chip" data-range="${r}">${r}</button>`).join("") +
  // Styled inline: style.css is being edited elsewhere, and these two inputs are the only ones that need it.
  `<span class="range-dates" style="display:flex;gap:3px;align-items:center;margin-left:6px">` +
  ["from", "to"].map((k) => `<input class="search" type="date" id="range-${k}" min="2000-01-01" aria-label="${k === "from" ? "From" : "To"} date" title="${k === "from" ? "From" : "To"}" style="width:auto;padding:1px 4px;color-scheme:dark">`).join(`<span class="dim">→</span>`) + `</span>`;
$("#range").addEventListener("click", (e) => {
  if (!e.target.dataset.range) return;
  spreads.range = e.target.dataset.range;
  spreads.from = spreads.to = "";
  drawSpreadCharts();
});
$("#range").addEventListener("change", (e) => {
  if (!e.target.matches("input[type=date]")) return;
  spreads.from = $("#range-from").value;
  spreads.to = $("#range-to").value;
  spreads.range = spreads.from || spreads.to ? "custom" : "1Y";
  drawSpreadCharts();
});
// Ticker suggestions for the two leg boxes: every stock with data (the universal watchlist); any other ticker still works.
const legList = document.createElement("datalist");
legList.id = "leg-options";
document.body.append(legList);
$("#leg-long").setAttribute("list", "leg-options");
$("#leg-short").setAttribute("list", "leg-options");
api("/api/watchlists").then((w) => { legList.innerHTML = w.universe.map((u) => `<option value="${esc(u.symbol)}">`).join(""); }).catch(() => {});
function showPair(long, short) {
  spreads.sel = { long: long.trim().toUpperCase(), short: short.trim().toUpperCase() };
  try { localStorage.setItem("spreads:sel", JSON.stringify(spreads.sel)); } catch { /* ignore */ }
  loaders.spreads().catch((err) => ($("#pair-msg").textContent = err.message));
}
const savePairs = async (body) => {
  const r = await fetch("/api/pairs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  spreads.pairs = j.pairs;
};
$("#pair-chips").addEventListener("click", async (e) => {
  const chip = e.target.closest("[data-pair]");
  if (!chip) return;
  const p = spreads.pairs.find((x) => x.id === chip.dataset.pair);
  if (e.target.closest(".x")) {
    if (!confirm(`Remove ${p.long} / ${p.short} from saved pairs?`)) return;
    await savePairs({ remove: p.id });
    return loaders.spreads();
  }
  showPair(p.long, p.short);
});
$("#pair-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const long = $("#leg-long").value, short = $("#leg-short").value;
  if (!long.trim() || !short.trim()) return ($("#pair-msg").textContent = "Enter two tickers");
  showPair(long, short);
});
$("#pair-swap").addEventListener("click", () => {
  const long = $("#leg-long").value;
  $("#leg-long").value = $("#leg-short").value;
  $("#leg-short").value = long;
  if ($("#leg-long").value.trim() && $("#leg-short").value.trim()) showPair($("#leg-long").value, $("#leg-short").value);
});
$("#pair-save").addEventListener("click", async () => {
  const p = spreads.data?.pair;
  if (!p) return;
  try {
    await savePairs({ long: p.long, short: p.short });
    $("#pair-msg").textContent = "Saved: the collector will keep it updated";
    loaders.spreads();
  } catch (err) { $("#pair-msg").textContent = err.message; }
});

loaders.spreads = async () => {
  if (!spreads.pairs.length) spreads.pairs = (await api("/api/pairs")).pairs;
  spreads.sel ??= spreads.pairs[0] && { long: spreads.pairs[0].long, short: spreads.pairs[0].short };
  const { long, short } = spreads.sel;
  const isSel = (p) => p.long === long && p.short === short;
  $("#pair-chips").innerHTML = spreads.pairs.map((p) => `<button class="chip ${isSel(p) ? "active" : ""}" data-pair="${esc(p.id)}" title="${esc(p.name)}">${esc(p.long)} / ${esc(p.short)}<span class="x" title="Remove from saved pairs">×</span></button>`).join(" ");
  if (document.activeElement?.closest("#pair-form") == null) { $("#leg-long").value = long; $("#leg-short").value = short; }
  $("#pair-msg").textContent = "Loading…";
  let d;
  try {
    d = spreads.data = await api(`/api/pair?long=${encodeURIComponent(long)}&short=${encodeURIComponent(short)}`);
  } catch (err) {
    $("#pair-msg").textContent = err.message;
    throw err;
  }
  $("#pair-msg").textContent = d.pair.saved ? "" : "Not saved: fetched on demand";
  $("#pair-save").hidden = d.pair.saved;
  const p = d.pair, s = d.stats;
  $("#pair-title").textContent = p.name === `${p.long} vs ${p.short}` ? `${p.long} / ${p.short}` : `${p.long} / ${p.short} · ${p.name}`;
  $("#ratio-title").textContent = `${p.long} / ${p.short} ratio`;
  badge($("#pair-badge"), s.fetched_at, 75, `Updated ${ago(s.fetched_at)}`);
  const z = s.zscore_1y;
  $("#pair-stats").innerHTML = [
    ["Ratio", fixed(s.ratio, 4), `as of ${shortDate(s.date + "T12:00:00")}`],
    ["vs 50-day", signed(s.vs_ma50), s.vs_ma50 > 0 ? "above" : "below", cls(s.vs_ma50)],
    ["vs 200-day", signed(s.vs_ma200), s.vs_ma200 > 0 ? "above: uptrend" : "below: downtrend", cls(s.vs_ma200)],
    ["Z-score (1Y)", fixed(z, 2), Math.abs(z) >= 2 ? "stretched" : Math.abs(z) >= 1 ? "elevated" : "normal range", cls(z)],
    ["1Y percentile", `${fixed(s.percentile_1y, 0)}%`, `0% = 1Y low, 100% = high`],
    ["From 1Y high", signed(s.from_high_1y), `high ${fixed(s.high_1y, 4)} · low ${fixed(s.low_1y, 4)}`, cls(s.from_high_1y)],
  ].map(([k, v, sub, c]) => `<div class="stat"><small>${k}</small><strong class="${c || ""}">${v}</strong><em>${sub}</em></div>`).join("");
  $("#pair-returns").innerHTML = `<table><thead><tr><th>Period</th><th>${esc(p.long)}</th><th>${esc(p.short)}</th><th>Spread</th></tr></thead><tbody>${d.returns
    .map((r) => `<tr><td>${r.label}</td><td class="${cls(r.long)}">${signed(r.long)}</td><td class="${cls(r.short)}">${signed(r.short)}</td><td class="${cls(r.spread)}"><b>${signed(r.spread)}</b></td></tr>`)
    .join("")}</tbody></table>`;
  const trend = s.vs_ma200 > 0 ? `<b>${esc(p.long)}</b> has been gaining on <b>${esc(p.short)}</b> (ratio above its 200-day average)` : `<b>${esc(p.long)}</b> has been losing ground to <b>${esc(p.short)}</b> (ratio below its 200-day average)`;
  $("#pair-read").innerHTML = `<p class="note">${esc(p.reads)}</p><p class="note">Now: ${trend}. The ratio sits at the <b>${fixed(s.percentile_1y, 0)}th percentile</b> of the past year${Math.abs(z) >= 2 ? `, <b>unusually ${z > 0 ? "high" : "low"}</b> (z ${fixed(z, 1)})` : ""}.</p>`;
  drawSpreadCharts();
};

function drawSpreadCharts() {
  const d = spreads.data;
  if (!d?.series?.length) return;
  document.querySelectorAll("#range .chip").forEach((c) => c.classList.toggle("active", c.dataset.range === spreads.range));
  const lastDate = d.series[d.series.length - 1].date, firstDate = d.series[0].date;
  const span = RANGES[spreads.range];
  const from = spreads.range === "custom" ? spreads.from || firstDate
    : span === "ytd" ? `${lastDate.slice(0, 4)}-01-01` : new Date(new Date(lastDate) - (span ?? 365) * 864e5).toISOString().slice(0, 10);
  const to = spreads.range === "custom" ? spreads.to || lastDate : lastDate;
  const rows = d.series.filter((r) => r.date >= from && r.date <= to);
  $("#range-from").value = spreads.range === "custom" ? spreads.from : "";
  $("#range-to").value = spreads.range === "custom" ? spreads.to : "";
  const p = d.pair, h = d.history || { joins: {}, starts: {}, notes: [] };
  const late = Object.entries(h.starts).filter(([, s]) => s === firstDate && s > "2000-01-31");
  const startNote = from < firstDate && late.length ? `History starts ${firstDate}: ${late.map(([sym]) => esc(sym)).join(" and ")} began trading then. ` : "";
  if (!rows.length) {
    $("#ratio-chart").innerHTML = $("#perf-chart").innerHTML = `<div class="empty" style="padding:16px">${startNote}No trading days between ${esc(from)} and ${esc(to)}.</div>`;
    return;
  }

  // 25 years is ~6,500 days: allow thin bars, or the chart can't fit them and silently shows only the last few years.
  const timeScale = { borderColor: css("--border"), minBarSpacing: 0.01 };
  const rc = makeChart($("#ratio-chart"), { rightPriceScale: { borderColor: css("--border"), scaleMargins: { top: 0.1, bottom: 0.1 } }, timeScale });
  const ratioLine = rc.addLineSeries({ color: css("--text"), lineWidth: 2, priceFormat: { type: "price", precision: 4, minMove: 0.0001 } });
  ratioLine.setData(rows.map((r) => ({ time: r.date, value: r.ratio })));
  // Mark where the older Yahoo history meets Alpaca's (one date for both legs when both were extended).
  const join = Object.values(h.joins).filter(Boolean).sort().pop();
  if (join && join > rows[0].date && join <= rows[rows.length - 1].date)
    ratioLine.setMarkers([{ time: join, position: "aboveBar", color: css("--text-dim"), shape: "arrowDown", text: "Yahoo before · Alpaca after" }]);
  for (const [key, color] of [["ma50", "--series-1"], ["ma200", "--series-2"]])
    rc.addLineSeries({ color: css(color), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(rows.filter((r) => r[key]).map((r) => ({ time: r.date, value: r[key] })));
  rc.timeScale().fitContent();

  // The window you picked: its own row in Returns and its own stat, next to the fixed periods.
  const a = rows[0], b = rows[rows.length - 1], ch = (x, y) => (x / y - 1) * 100;
  const ratios = rows.map((r) => r.ratio), hi = Math.max(...ratios), lo = Math.min(...ratios);
  const wpct = (100 * ratios.filter((x) => x <= b.ratio).length) / ratios.length;
  $("#pair-returns tbody")?.querySelector("tr.window")?.remove();
  $("#pair-returns tbody")?.insertAdjacentHTML("afterbegin", `<tr class="window"><td title="${esc(a.date)} to ${esc(b.date)}"><b>Window</b> <span class="dim">${esc(a.date.slice(0, 7))}→${esc(b.date.slice(0, 7))}</span></td>` +
    [ch(b.long, a.long), ch(b.short, a.short)].map((v) => `<td class="${cls(v)}">${signed(v)}</td>`).join("") + `<td class="${cls(ch(b.ratio, a.ratio))}"><b>${signed(ch(b.ratio, a.ratio))}</b></td></tr>`);
  $("#pair-stats .stat.window")?.remove();
  $("#pair-stats")?.insertAdjacentHTML("beforeend", `<div class="stat window"><small>In window</small><strong class="${cls(ch(b.ratio, a.ratio))}">${signed(ch(b.ratio, a.ratio))}</strong><em>ratio at ${fixed(wpct, 0)}% of its window range</em></div>`);

  const base = rows[0];
  const srcNote = join && join > base.date ? ` · before ${esc(join)}: Yahoo history` : "";
  $("#perf-legend").innerHTML = `<span><i style="background:var(--series-1)"></i>${esc(p.long)}</span><span><i style="background:var(--series-2)"></i>${esc(p.short)}</span><span class="dim">${startNote}indexed to 100 at ${esc(base.date)}${srcNote}${h.notes.length ? ` · ${esc(h.notes.join("; "))}` : ""}</span>`;
  const pc = makeChart($("#perf-chart"), { timeScale });
  for (const [key, color] of [["long", "--series-1"], ["short", "--series-2"]])
    pc.addLineSeries({ color: css(color), lineWidth: 2, priceFormat: { type: "price", precision: 1, minMove: 0.1 } }).setData(rows.map((r) => ({ time: r.date, value: (100 * r[key]) / base[key] })));
  pc.timeScale().fitContent();
}

// ---------- EVENTS
const GROUPS = [["all", "All (ex sports)"],["macro", "Macro & Fed"], ["geopolitics", "Geopolitics"], ["business", "Business & tech"], ["politics", "Politics"], ["crypto", "Crypto"], ["other", "Sports & other"]];
const events = { group: "all", q: "", data: null };
$("#grp-chips").addEventListener("click", (e) => {
  const g = e.target.closest("[data-grp]")?.dataset.grp;
  if (g) { events.group = g; loaders.events(); }
});
let searchTimer;
$("#ev-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { events.q = e.target.value; loaders.events(); }, 250);
});

const marketLabel = (m) => m.label || (m.outcomes[0] && m.outcomes[0] !== "Yes" ? m.outcomes[0] : m.question);
const outcomeRow = (m) => {
  const p = isNum(m.price) ? m.price * 100 : null, c = isNum(m.change_1d) ? m.change_1d * 100 : null;
  return `<div class="outcome"><div class="outcome-label"><div class="outcome-bar" style="width:${Math.max(0, Math.min(100, p ?? 0))}%"></div><span>${esc(marketLabel(m))}</span></div>
    <div class="outcome-pct">${p === null ? "–" : p < 1 ? "<1%" : `${p.toFixed(0)}%`}</div><div class="outcome-chg ${cls(c)}">${c === null ? "" : signed(c, 1, "")}</div></div>`;
};
const grpName = (g) => (GROUPS.find(([k]) => k === g) || [g, g])[1];

function eventBlock(e, max = 3) {
  const single = e.markets.length === 1 && !e.neg_risk;
  const shown = single ? e.markets : e.markets.slice(0, max);
  return `<div class="event" data-event="${esc(e.id)}">
    <div class="event-head"><div class="event-title">${events.group === "all" ? `<span class="grp-tag">${esc(grpName(e.grp))}</span>` : ""}${esc(e.title)}</div>
      <a class="ext" href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">Polymarket ↗</a></div>
    <div class="event-meta">${usd(e.volume_24h)} 24h vol · ${usd(e.liquidity)} liquidity · resolves ${shortDate(e.end_date)}${e.markets.length > max && !single ? ` · ${e.markets.length} outcomes` : ""}</div>
    ${shown.map(outcomeRow).join("")}
    <div class="event-detail"></div></div>`;
}

loaders.events = async () => {
  const d = (events.data = await api(`/api/events?group=${events.group}&q=${encodeURIComponent(events.q)}`));
  $("#grp-chips").innerHTML = GROUPS.map(([k, label]) => `<button class="chip ${k === events.group ? "active" : ""}" data-grp="${k}">${label}${k !== "all" ? `<span class="n">${d.counts[k] ?? 0}</span>` : ""}</button>`).join(" ");
  badge($("#ev-badge"), d.fetched_at, 75, `Updated ${ago(d.fetched_at)}`);
  $("#ev-movers").innerHTML = d.movers.length
    ? d.movers.map((m) => `<div class="item"><div><div class="item-name">${esc(marketLabel(m) === m.question ? m.question : `${m.event_title}: ${marketLabel(m)}`)}</div><div class="item-sub">${esc(grpName(m.grp))} · ${usd(m.volume_24h)} 24h vol</div></div>
        <div><div class="item-value">${fixed(m.price * 100, 0)}%</div><div class="item-change ${cls(m.change_1d)}">${signed(m.change_1d * 100, 1, " pts")}</div></div></div>`).join("")
    : `<div class="empty">No liquid movers yet.</div>`;
  $("#ev-ending-n").textContent = d.ending.length;
  $("#ev-ending").innerHTML = d.ending.length ? d.ending.map((e) => eventBlock(e, 2)).join("") : `<div class="empty">Nothing resolving in the next 7 days${events.group !== "all" ? " in this group" : ""}.</div>`;
  $("#ev-list-title").textContent = events.group === "all" ? "All market-relevant events by 24h volume" : grpName(events.group);
  $("#ev-list-n").textContent = d.events.length;
  $("#ev-list").innerHTML = d.events.length ? d.events.slice(0, 120).map((e) => eventBlock(e)).join("") : `<div class="empty">No events match.</div>`;
};

document.addEventListener("click", async (e) => {
  if (e.target.closest("a")) return;
  const el = e.target.closest(".event");
  if (!el) return;
  el.classList.toggle("open");
  const box = $(".event-detail", el);
  if (!el.classList.contains("open") || box.dataset.loaded) return;
  const ev = [...(events.data?.events || []), ...(events.data?.ending || [])].find((x) => x.id === el.dataset.event);
  if (!ev) return;
  box.dataset.loaded = "1";
  const top = ev.markets.slice(0, 6);
  const hist = await Promise.all(top.map((m) => api(`/api/market_history?id=${encodeURIComponent(m.id)}`)));
  box.innerHTML = `${ev.markets.map(outcomeRow).join("")}
    <div class="item-sub" style="margin-top:10px">Price history (from this dashboard's hourly snapshots, since collection began):</div>
    ${top.map((m, i) => `<div class="item-sub" style="margin-top:6px">${esc(marketLabel(m))}</div>${sparkline(hist[i].points.map((p) => p.price))}`).join("")}
    <div class="item-sub" style="margin-top:8px">Tags: ${esc(ev.tags.join(", "))}</div>`;
});

function sparkline(vals) {
  const v = vals.filter(isNum);
  if (v.length < 2) return `<div class="item-sub dim">One snapshot so far. History builds every hour.</div>`;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 0.01;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * 100},${34 - ((x - lo) / span) * 30}`).join(" ");
  return `<svg class="spark" viewBox="0 0 100 36" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${css("--info")}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
}

// ---------- STATUS
const JOB_NOTES = {
  daily: "OCC open interest, weekdays 7:30 (retry 9:15)", snapshot: "Alpaca option chains, 8× per trading day",
  positioning: "SqueezeMetrics gamma + CFTC, weekdays 7:45, Fri 4:45", backup: "Database copy to iCloud, daily 8:30 pm",
  spreads: "Pair prices, hourly in market hours + 4:30 pm", events: "Polymarket, every hour", backfill: "One-off history load",
  strategy: "Gamma breakout tracker, every 5 min in market hours", "strategy-replay": "One-off rerun of past days through the rules",
  politics: "Political game machine: prices, headlines and rebuild, hourly at :25", briefing: "Daily phone update, 10:00", 
  news: "Headlines from ~80 feeds grouped into stories, every 15 min", shipping: "Ships through 28 chokepoints (IMF PortWatch), 9:40 am and 7:40 pm", 
};
loaders.status = async () => {
  const h = await refreshStatus();
  $("#db-size").textContent = `Database ${h.db_mb} MB`;
  $("#jobs").innerHTML = `<table><thead><tr><th>Job</th><th>What</th><th>Last run</th><th>Status</th><th>Rows</th><th>Detail</th></tr></thead><tbody>${h.jobs
    .map((j) => `<tr><td>${esc(j.job)}</td><td style="text-align:left" class="dim">${esc(JOB_NOTES[j.job] || "")}</td><td>${etTime(j.started_at)} <span class="dim">(${ago(j.started_at)})</span></td>
      <td><span class="badge ${j.status === "ok" || j.status === "skipped" ? "fresh" : j.status === "running" || j.status === "partial" ? "stale" : "down"}">${esc(j.status)}</span></td>
      <td>${big(j.rows)}</td><td style="text-align:left;white-space:normal" class="dim">${esc(j.detail)}</td></tr>`).join("")}</tbody></table>`;
  $("#runs").innerHTML = `<table><thead><tr><th>#</th><th>Job</th><th>Started</th><th>Status</th><th>Rows</th><th>Detail</th></tr></thead><tbody>${h.recent
    .map((r) => `<tr><td>${r.id}</td><td>${esc(r.job)}</td><td>${etTime(r.started_at)}</td><td>${esc(r.status)}</td><td>${big(r.rows)}</td><td style="text-align:left;white-space:normal" class="dim">${esc(r.detail)}</td></tr>`).join("")}</tbody></table>`;
};

// ---------- text size: A− / A+ zoom everything below the top bar, remembered in this browser
const TEXT_SIZES = [0.8, 0.9, 1, 1.1, 1.2, 1.35, 1.5, 1.75, 2];
let textSize = 1;
try { textSize = Number(localStorage.getItem("ui-zoom")) || 1; } catch (e) { /* no storage */ }
function applyTextSize() {
  document.documentElement.style.setProperty("--ui-zoom", textSize);
  $("#text-size-pct").textContent = `${Math.round(textSize * 100)}%`;
  $("#text-smaller").disabled = textSize <= TEXT_SIZES[0];
  $("#text-bigger").disabled = textSize >= TEXT_SIZES[TEXT_SIZES.length - 1];
  try { localStorage.setItem("ui-zoom", textSize); } catch (e) { /* ignore */ }
  window.dispatchEvent(new Event("resize"));  // charts redraw at the new size
}
function stepTextSize(dir) {
  const i = TEXT_SIZES.findIndex((z) => z >= textSize - 1e-9);
  textSize = TEXT_SIZES[Math.min(TEXT_SIZES.length - 1, Math.max(0, (i < 0 ? 2 : i) + dir))];
  applyTextSize();
}
$("#text-smaller").addEventListener("click", () => stepTextSize(-1));
$("#text-bigger").addEventListener("click", () => stepTextSize(1));
applyTextSize();

$("#reset-layout").addEventListener("click", () => {
  Layout.reset($(`#view-${current} .grid[data-layout]:not([hidden])`));
  drawStrikeCharts();
});
// ---------- boot + auto-refresh every minute
// (after the other tabs' scripts have added their loaders)
document.addEventListener("DOMContentLoaded", () => {
  show((location.hash || "#options").slice(1));
  refreshStatus().catch(showError);
  setInterval(() => { refreshStatus().catch(showError); loaders[current]().catch(showError); }, 60_000);
});
