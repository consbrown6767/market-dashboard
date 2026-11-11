/* Free-placement panels, saved per tab in this browser.
   - The grid is 24 columns wide with 10px rows. Each panel has a box {x, y, w, h} in those units, so it
     can sit anywhere: three-quarters wide and centred is w 18 at x 3.
   - Move: drag a panel by its header. It snaps to the grid where you drop it (a dashed outline shows
     where); panels in the way are pushed down. Nothing is pulled up, so gaps you leave stay.
   - Resize: drag the bottom-right corner (width in columns, height in rows); panels below get pushed.
   - Compact panels (stats rows) keep fitting their content until you resize them by hand.
   - Hide: the − in a panel's header; the + menu in the page header lists the tab's panels to show them again.
   - Saved in localStorage under "layout:<tab>" as {pos, hidden}. The first time a tab is shown without
     saved positions, the boxes are measured from the default layout (the col-* classes), and from an
     older saved order/size if there is one, so nothing jumps. "Reset layout" goes back to the default.
   - Under 900px wide the grid falls back to one full-width column in the same top-to-bottom order.
   Panels need a stable data-panel id inside a .grid[data-layout]. */
"use strict";

const Layout = (() => {
  const COLS = 24, ROW = 10, MIN_W = 4, MIN_H = 9;
  const narrow = matchMedia("(max-width: 900px)");
  const key = (grid) => `layout:${grid.dataset.layout}`;
  const load = (grid) => { try { return JSON.parse(localStorage.getItem(key(grid))) || {}; } catch { return {}; } };
  const store = (grid, v) => { try { localStorage.setItem(key(grid), JSON.stringify(v)); } catch { /* private mode etc. */ } };
  const panels = (grid) => [...grid.querySelectorAll(":scope > .panel[data-panel]")];
  const shown = (grid) => panels(grid).filter((p) => !p.hidden);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const defaults = new Map(); // grid -> original panel order, for reset
  const boxes = new Map();    // grid -> {panel id: {x, y, w, h, auto}}, once the grid is in free mode
  let busy = false;           // a drag or resize is in progress

  // Name for the + menu: data-title, else the panel's title as first rendered (some change once data loads).
  const names = new Map();
  const nameOf = (p) => names.get(p) || p.dataset.panel;

  function metrics(grid) {
    const cs = getComputedStyle(grid), r = grid.getBoundingClientRect();
    const padL = parseFloat(cs.paddingLeft) || 0, padT = parseFloat(cs.paddingTop) || 0, gap = parseFloat(cs.columnGap) || 0;
    return { left: r.left + padL, top: r.top + padT, gap, col: (r.width - 2 * padL - gap * (COLS - 1)) / COLS };
  }

  function place(grid, panel, b, gap = metrics(grid).gap) {
    panel.style.gridColumn = `${b.x + 1} / span ${b.w}`;
    panel.style.gridRow = `${b.y + 1} / span ${b.h}`;
    panel.style.setProperty("--free-h", `${b.h * ROW - gap}px`);
    panel.classList.toggle("auto-h", !!b.auto);
  }
  function placeAll(grid, bx = boxes.get(grid), skip = null) {
    const { gap } = metrics(grid);
    for (const p of panels(grid)) if (bx[p.dataset.panel] && p !== skip) place(grid, p, bx[p.dataset.panel], gap);
  }

  // Push every shown panel that overlaps `id` down below it, then whatever those overlap, and so on.
  function resolve(grid, bx, id) {
    const ids = shown(grid).map((p) => p.dataset.panel).filter((i) => bx[i]);
    const queue = [id];
    while (queue.length) {
      const curId = queue.shift(), cur = bx[curId];
      for (const o of ids.sort((a, b) => bx[a].y - bx[b].y || bx[a].x - bx[b].x)) {
        if (o === id || o === curId || !overlaps(cur, bx[o])) continue;
        bx[o].y = cur.y + cur.h;
        queue.push(o);
      }
    }
    return bx;
  }
  // Clear any overlaps, top to bottom (after measuring, or after a compact panel changes height).
  function normalize(grid, bx) {
    const ids = shown(grid).map((p) => p.dataset.panel).filter((i) => bx[i]);
    const placed = [];
    for (const id of ids.sort((a, b) => bx[a].y - bx[b].y || bx[a].x - bx[b].x)) {
      const b = bx[id];
      for (let hit; (hit = placed.find((p) => overlaps(b, p))); ) b.y = hit.y + hit.h; // only ever moves down
      placed.push(b);
    }
    return bx;
  }

  function save(grid) {
    const saved = load(grid), bx = boxes.get(grid);
    saved.pos = bx;
    delete saved.order; delete saved.size; // the older flow layout, now folded into pos
    store(grid, saved);
    // Keep the DOM in reading order (top to bottom, left to right) for the narrow layout and Tab key.
    const ps = panels(grid).sort((a, b) => {
      const A = bx[a.dataset.panel], B = bx[b.dataset.panel];
      return !A || !B ? 0 : A.y - B.y || A.x - B.x;
    });
    if (ps.some((p, i) => p !== panels(grid)[i])) for (const p of ps) grid.appendChild(p);
  }

  // Boxes from the flow layout as rendered: default col-* classes, or an older saved order/size.
  function measure(grid, saved) {
    grid.classList.remove("free");
    const ps = panels(grid), wasHidden = ps.map((p) => p.hidden);
    for (const p of ps) {
      p.hidden = false;
      p.style.gridColumn = p.style.gridRow = p.style.height = "";
      p.classList.remove("auto-h");
      if (p.dataset.compact === "1") p.classList.add("compact");
    }
    if (saved.order) {
      const byId = new Map(ps.map((p) => [p.dataset.panel, p]));
      for (const id of saved.order) if (byId.has(id)) grid.appendChild(byId.get(id));
    }
    for (const p of ps) {
      const s = saved.size?.[p.dataset.panel];
      if (s?.span) p.style.gridColumn = `span ${s.span}`;
      if (s?.h) { p.style.height = `${s.h}px`; p.classList.remove("compact"); }
    }
    const m = metrics(grid), bx = {};
    for (const p of ps) {
      const r = p.getBoundingClientRect(), auto = p.classList.contains("compact");
      const w = clamp(Math.round((r.width + m.gap) / (m.col + m.gap)), MIN_W, COLS);
      bx[p.dataset.panel] = {
        x: clamp(Math.round((r.left - m.left) / (m.col + m.gap)), 0, COLS - w), w,
        y: Math.max(0, Math.round((r.top - m.top) / ROW)),
        h: Math.max(auto ? 1 : MIN_H, Math.round((r.height + m.gap) / ROW)), auto,
      };
      p.style.gridColumn = p.style.height = "";
    }
    ps.forEach((p, i) => (p.hidden = wasHidden[i]));
    return bx;
  }

  // Switch a grid to free mode once it is visible and wide enough (hidden tabs have no size to measure).
  function activate(grid) {
    if (boxes.has(grid) || narrow.matches || !grid.clientWidth) return;
    const saved = load(grid);
    let bx = saved.pos ? clone(saved.pos) : measure(grid, saved);
    // Panels added to the page after the layout was saved go at the bottom, side by side at their
    // default width (col-* class) and height (tall/medium), wrapping to a new row when full.
    let bottom = Math.max(0, ...Object.values(bx).map((b) => b.y + b.h)), x = 0, rowH = 0;
    for (const p of panels(grid)) {
      if (bx[p.dataset.panel]) continue;
      const w = p.classList.contains("col-all") ? COLS : p.classList.contains("col-3") ? 18 : p.classList.contains("col-2") ? 12 : 6;
      const h = p.classList.contains("tall") ? 64 : p.classList.contains("medium") ? 42 : 30;
      if (x + w > COLS) { bottom += rowH; x = 0; rowH = 0; }
      bx[p.dataset.panel] = { x, y: bottom, w, h, auto: p.dataset.compact === "1" };
      x += w; rowH = Math.max(rowH, h);
    }
    for (const id of Object.keys(bx)) {
      if (panels(grid).some((p) => p.dataset.panel === id)) continue;
      const gone = bx[id];
      delete bx[id];
      if (gone.w === COLS) for (const b of Object.values(bx)) if (b.y >= gone.y + gone.h) b.y -= gone.h; // close the gap
    }
    boxes.set(grid, normalize(grid, bx));
    grid.classList.add("free");
    for (const p of panels(grid)) { p.classList.remove("compact"); p.style.height = ""; }
    placeAll(grid);
    save(grid);
    window.dispatchEvent(new Event("panel-resized"));
  }

  // Compact panels follow their content height: shift what's below by the change. Applied on the next
  // frame, since moving panels inside the observer callback would trigger it again in the same frame.
  const fit = new ResizeObserver((entries) => requestAnimationFrame(() => {
    for (const { target: p } of entries) {
      const grid = p.parentElement, bx = boxes.get(grid), b = bx?.[p.dataset.panel];
      if (busy || !b?.auto || p.hidden || narrow.matches || !p.offsetHeight) continue;
      const h = Math.max(1, Math.ceil((p.offsetHeight + metrics(grid).gap) / ROW));
      if (h === b.h) continue;
      const bottom = b.y + b.h;
      for (const o of shown(grid)) {
        const ob = bx[o.dataset.panel];
        if (ob && ob !== b && ob.y >= bottom) ob.y = Math.max(0, ob.y + h - b.h);
      }
      b.h = h;
      normalize(grid, bx);
      placeAll(grid);
      save(grid);
    }
  }));

  function applyHidden(grid) {
    const hidden = load(grid).hidden || [];
    for (const p of panels(grid)) p.hidden = hidden.includes(p.dataset.panel);
    window.dispatchEvent(new CustomEvent("panels-changed", { detail: { grid } }));
  }
  function setHidden(grid, id, hide) {
    const saved = load(grid);
    const hidden = new Set(saved.hidden || []);
    if (hide) hidden.add(id); else hidden.delete(id);
    saved.hidden = [...hidden];
    store(grid, saved);
    applyHidden(grid);
    const bx = boxes.get(grid);
    if (!hide && bx?.[id]) { resolve(grid, bx, id); placeAll(grid); save(grid); } // back in its old spot
    activate(grid);
    window.dispatchEvent(new Event("panel-resized"));
  }
  const list = (grid) => panels(grid).map((p) => ({ id: p.dataset.panel, name: nameOf(p), hidden: p.hidden }));
  const showAll = (grid) => { for (const p of panels(grid)) if (p.hidden) setHidden(grid, p.dataset.panel, false); };

  function addHideButton(grid, panel) {
    const header = panel.querySelector(":scope > .panel-header");
    if (!header) return;
    const b = document.createElement("button");
    b.className = "panel-hide";
    b.type = "button";
    b.title = "Hide this panel (bring it back with + at the top right)";
    b.setAttribute("aria-label", `Hide ${nameOf(panel)}`);
    b.textContent = "−";
    b.addEventListener("click", () => setHidden(grid, panel.dataset.panel, true));
    header.appendChild(b);
  }

  // Shared pointer handling for move and resize: `step(ev)` returns the trial layout for this pointer
  // position (or null for no change); the last one is kept on release.
  function track(grid, el, e, onStart, step, onEnd) {
    e.preventDefault(); e.stopPropagation();
    el.setPointerCapture(e.pointerId);
    let started = false, pending = null;
    const move = (ev) => {
      if (!started) {
        if (Math.hypot(ev.clientX - e.clientX, ev.clientY - e.clientY) < 4) return;
        started = busy = true;
        document.body.classList.add("no-select");
        onStart();
      }
      const bx = step(ev);
      if (bx) pending = bx;
    };
    const up = () => {
      el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up);
      if (!started) return;
      busy = false;
      document.body.classList.remove("no-select");
      onEnd();
      if (pending) { boxes.set(grid, pending); placeAll(grid); save(grid); }
      window.dispatchEvent(new Event("panel-resized"));
    };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  }

  function enableDrag(grid, panel) {
    const header = panel.querySelector(":scope > .panel-header");
    if (!header) return;
    header.title = "Drag to move";
    header.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button, a, input, select, .chip, .range")) return;
      if (!boxes.has(grid) || narrow.matches) return;
      const id = panel.dataset.panel, start = clone(boxes.get(grid)), b0 = start[id];
      const r0 = panel.getBoundingClientRect(), grabX = e.clientX - r0.left, grabY = e.clientY - r0.top;
      const bottom = Math.max(0, ...Object.entries(start).filter(([k]) => k !== id && shown(grid).some((p) => p.dataset.panel === k)).map(([, b]) => b.y + b.h));
      const main = grid.closest(".main");
      let ghost = null, last = null;
      track(grid, header, e,
        () => {
          ghost = document.createElement("div");
          ghost.className = "panel-ghost";
          grid.appendChild(ghost);
          place(grid, ghost, b0);
          panel.classList.add("lifted");
        },
        (ev) => {
          if (main) { // scroll the page when dragging near its top or bottom edge
            const mr = main.getBoundingClientRect();
            if (ev.clientY > mr.bottom - 40) main.scrollBy(0, 24);
            else if (ev.clientY < mr.top + 40) main.scrollBy(0, -24);
          }
          const m = metrics(grid), left = ev.clientX - grabX, top = ev.clientY - grabY;
          // Follow the pointer from where the panel's grid cell is now.
          panel.style.transform = `translate(${left - (m.left + b0.x * (m.col + m.gap))}px, ${top - (m.top + b0.y * ROW)}px)`;
          const x = clamp(Math.round((left - m.left) / (m.col + m.gap)), 0, COLS - b0.w);
          const y = clamp(Math.round((top - m.top) / ROW), 0, bottom);
          if (last && last.x === x && last.y === y) return null;
          last = { x, y };
          const bx = clone(start);
          Object.assign(bx[id], last);
          resolve(grid, bx, id);
          placeAll(grid, bx, panel);
          place(grid, ghost, bx[id], m.gap);
          return bx;
        },
        () => { panel.classList.remove("lifted"); panel.style.transform = ""; ghost?.remove(); });
    });
  }

  function enableResize(grid, panel) {
    const h = document.createElement("div");
    h.className = "resize-handle";
    h.title = "Drag to resize";
    panel.appendChild(h);
    h.addEventListener("pointerdown", (e) => {
      if (!boxes.has(grid) || narrow.matches) return;
      const id = panel.dataset.panel, start = clone(boxes.get(grid)), b0 = start[id];
      const r0 = panel.getBoundingClientRect();
      let last = null;
      track(grid, h, e,
        () => panel.classList.add("resizing"),
        (ev) => {
          const m = metrics(grid);
          const w = clamp(Math.round((r0.width + ev.clientX - e.clientX + m.gap) / (m.col + m.gap)), MIN_W, COLS - b0.x);
          const hh = Math.max(MIN_H, Math.round((r0.height + ev.clientY - e.clientY + m.gap) / ROW));
          if (last && last.w === w && last.h === hh) return null;
          last = { w, h: hh };
          const bx = clone(start);
          Object.assign(bx[id], last, { auto: false });
          resolve(grid, bx, id);
          placeAll(grid, bx);
          return bx;
        },
        () => panel.classList.remove("resizing"));
    });
  }

  // Kept at module level: a ResizeObserver held only by a local can be garbage-collected before it fires.
  const sized = new ResizeObserver((entries) => entries.forEach((en) => activate(en.target)));
  const activateAll = () => requestAnimationFrame(() => document.querySelectorAll(".grid[data-layout]").forEach(activate));

  function adopt(grid) {
    defaults.set(grid, panels(grid).map((p) => p.dataset.panel));
    for (const p of panels(grid)) {
      const t = p.querySelector(".panel-title")?.textContent.trim();
      names.set(p, p.dataset.title || (t && t !== "–" ? t : p.dataset.panel));
      enableResize(grid, p); enableDrag(grid, p); addHideButton(grid, p);
      fit.observe(p);
    }
    applyHidden(grid);
    sized.observe(grid);
  }

  function init() {
    document.querySelectorAll(".grid[data-layout]").forEach(adopt);
    narrow.addEventListener("change", activateAll);
    // Backups for the observer: when a tab is shown, and once everything has loaded.
    window.addEventListener("hashchange", activateAll);
    document.getElementById("tabs")?.addEventListener("click", activateAll);
    window.addEventListener("load", activateAll);
  }

  function reset(grid) {
    try { localStorage.removeItem(key(grid)); } catch { /* ignore */ }
    boxes.delete(grid);
    grid.classList.remove("free");
    const byId = new Map(panels(grid).map((p) => [p.dataset.panel, p]));
    for (const id of defaults.get(grid) || []) grid.appendChild(byId.get(id));
    applyHidden(grid);
    activate(grid);
    window.dispatchEvent(new Event("panel-resized"));
  }

  return { init, adopt, reset, list, setHidden, showAll };
})();

document.querySelectorAll(".panel.compact").forEach((p) => (p.dataset.compact = "1"));
Layout.init();

// + menu (page header): every panel on the current tab, checked = shown.
(() => {
  const btn = document.getElementById("panels-btn"), menu = document.getElementById("panels-menu");
  if (!btn || !menu) return;
  const grid = () => document.querySelector(".view.active .grid[data-layout]:not([hidden])");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function render() {
    const g = grid();
    const items = g ? Layout.list(g) : [];
    const hidden = items.filter((i) => i.hidden).length;
    btn.textContent = hidden ? `+ ${hidden} hidden` : "+";
    btn.classList.toggle("active", hidden > 0);
    menu.innerHTML = `<div class="panels-menu-title">Panels on this tab</div>${items
      .map((i) => `<label><input type="checkbox" data-id="${esc(i.id)}" ${i.hidden ? "" : "checked"}> ${esc(i.name)}</label>`).join("")}
      <button type="button" class="chip" data-show-all ${hidden ? "" : "disabled"}>Show all</button>`;
  }
  btn.addEventListener("click", (e) => { e.stopPropagation(); render(); menu.hidden = !menu.hidden; });
  menu.addEventListener("change", (e) => {
    const id = e.target.dataset.id;
    if (id) Layout.setHidden(grid(), id, !e.target.checked);
  });
  menu.addEventListener("click", (e) => { if (e.target.closest("[data-show-all]")) Layout.showAll(grid()); });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) menu.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.hidden = true; });
  window.addEventListener("panels-changed", render);
  window.addEventListener("hashchange", () => { menu.hidden = true; render(); });
  document.getElementById("tabs")?.addEventListener("click", () => setTimeout(render));
  render();
})();
