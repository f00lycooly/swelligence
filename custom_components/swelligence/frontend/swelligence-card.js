/*
 * Swelligence Lovelace card — one element, four modes.
 *
 *   type: custom:swelligence-card
 *   mode: podium | timeline | heatgrid | medallions   (default: podium)
 *   title: "Conditions"            # optional
 *   spots: ["Hurst Spit / Keyhaven", ...]   # optional filter (by spot name)
 *   sports: ["kitesurf", ...]               # optional filter (by sport key)
 *
 * NOW modes (heatgrid, medallions) read sensor states (live).
 * Forecast modes (timeline, podium) call the swelligence.get_overview service.
 * Theme-aware: uses HA card/text vars; verdict colours are fixed & semantic.
 */

const VERDICT = {
  epic: { c: "#1f9d57", t: "#fff" },
  great: { c: "#5cb85c", t: "#08230f" },
  good: { c: "#9bcf5f", t: "#0c2208" },
  marg: { c: "#f0a83d", t: "#241600" },
  poor: { c: "#e8593a", t: "#fff" },
};
const ORDER = ["kitesurf", "windsurf", "wingfoil", "surf", "sup",
  "sailing", "seaswim", "wakeboard_inland", "wakeboard_sea"];
const SYM = {
  kitesurf: "i-kite", windsurf: "i-windsurf", wingfoil: "i-wing", surf: "i-surf",
  sup: "i-sup", sailing: "i-sail", seaswim: "i-swim",
  wakeboard_inland: "i-wake", wakeboard_sea: "i-wake",
};
const LABELS = {
  kitesurf: "Kite", windsurf: "Windsurf", wingfoil: "Wing", surf: "Surf", sup: "SUP",
  sailing: "Sail", seaswim: "Swim", wakeboard_inland: "Wake", wakeboard_sea: "Wake",
};
const band = (s) => s >= 85 ? "epic" : s >= 70 ? "great" : s >= 55 ? "good" : s >= 35 ? "marg" : "poor";
const vc = (v) => (VERDICT[v] || VERDICT.poor).c;
const vt = (v) => (VERDICT[v] || VERDICT.poor).t;
const wday = (d) => { try { return new Date(d).toLocaleDateString(undefined, { weekday: "short" }); } catch { return d; } };

/* spot-detail helpers */
const COMPASS16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
const cardOf = (deg) => (deg == null ? null : COMPASS16[Math.round(((deg % 360) / 22.5)) % 16]);
const f1 = (n, d = 1) => (n == null ? "—" : Math.round(n * 10 ** d) / 10 ** d);
const vkey = (v) => (v === "marginal" ? "marg" : v);          // data verdict → palette key
const vcw = (v) => vc(vkey(v) in VERDICT ? vkey(v) : "poor"); // verdict word → colour
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "—");

/* WMO weather code -> [glyph, short label]. Compact; unknown -> blank. */
function WMO(code) {
  if (code == null) return ["", ""];
  const c = Number(code);
  if (c === 0) return ["☀️", "clear"];
  if (c <= 2) return ["🌤️", "fair"];
  if (c === 3) return ["☁️", "cloudy"];
  if (c <= 48) return ["🌫️", "fog"];
  if (c <= 67) return ["🌧️", "rain"];
  if (c <= 77) return ["🌨️", "snow"];
  if (c <= 82) return ["🌧️", "showers"];
  if (c <= 86) return ["🌨️", "snow"];
  return ["⛈️", "storm"]; // 95/96/99
}

// kit power verdict -> palette colour
const powerCol = (p) => p === "ideal" ? vc("good") : p === "underpowered" ? vc("marg") : p === "overpowered" ? vc("poor") : "var(--mut)";
const facCol = (n) => (n == null ? "var(--mut)" : n >= 67 ? vc("good") : n >= 34 ? vc("marg") : vc("poor"));

const ICON_DEFS = `
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
<symbol id="i-windsurf" viewBox="0 0 24 24"><path d="M3 19.5 Q12 22.5 21 19.5"/><path d="M12 19 L12 3.5"/><path d="M12 4 Q20 9.5 12 15"/><path d="M12 9.5 L17.5 9"/></symbol>
<symbol id="i-wing" viewBox="0 0 24 24"><path d="M3.5 8 Q12 2.5 20.5 8 Q12 10.5 3.5 8 Z"/><path d="M12 10.5 L12 16"/><path d="M7.5 17.5 Q12 15.5 16.5 17.5"/></symbol>
<symbol id="i-surf" viewBox="0 0 24 24"><path d="M2 17 C6 17 6 9 11 9 C15.5 9 14 15 19.5 14"/><path d="M11 9 C13.5 7.8 14.6 10 12.4 11.6"/><path d="M13.5 20 L20 13.5"/></symbol>
<symbol id="i-sup" viewBox="0 0 24 24"><path d="M3 18 Q12 21 21 18"/><path d="M3 18 Q12 15.6 21 18"/><path d="M14.5 3.5 L9 17"/><path d="M13 3.5 H16"/><path d="M7.5 16 L9 19 L10.7 16 Z"/></symbol>
<symbol id="i-sail" viewBox="0 0 24 24"><path d="M4 18 L20 18 L17.5 21 H6.5 Z"/><path d="M12 18 L12 3.5"/><path d="M12.8 5 L18.5 16 H12.8 Z"/><path d="M11.2 6.5 L6 16 H11.2 Z"/></symbol>
<symbol id="i-swim" viewBox="0 0 24 24"><circle cx="8" cy="8.5" r="2"/><path d="M9.6 10 Q14 8.4 17.5 11.5"/><path d="M9.6 10 Q11.5 5.5 15 7.5"/><path d="M2 18 q2.6 -2 5.2 0 t5.2 0 t5.2 0"/></symbol>
<symbol id="i-wake" viewBox="0 0 24 24"><path d="M2 18.5 q3 -1.6 6 0 t6 0 t6 0"/><path d="M5.5 16.8 L13 13.2"/><path d="M8 16.2 L8.6 14.8"/><path d="M11 15 L11.6 13.6"/><path d="M18.5 6 H21.5"/><path d="M20 6.6 L13.5 12.6"/></symbol>
<symbol id="m-wind" viewBox="0 0 24 24"><path d="M3 8h12.5a2.5 2.5 0 1 0-2.5-2.5"/><path d="M3 12h17a2.5 2.5 0 1 1-2.5 2.5"/><path d="M3 16h8.5"/></symbol>
<symbol id="m-gust" viewBox="0 0 24 24"><path d="M3 9h11a2 2 0 1 0-2-2"/><path d="M3 13h15a2 2 0 1 1-2 2"/><path d="M3 17h7"/></symbol>
<symbol id="m-wave" viewBox="0 0 24 24"><path d="M2 9c3.2 0 3.2 4 6.4 4S11.6 9 14.8 9 18 13 21 13"/><path d="M2 15c3.2 0 3.2 4 6.4 4S11.6 15 14.8 15 18 19 21 19"/></symbol>
<symbol id="m-swell" viewBox="0 0 24 24"><path d="M2 14c4-9 8-9 11 0"/><path d="M2 18c4-7 8-7 11 0"/><path d="M15 11l4-3 3 3"/></symbol>
<symbol id="m-temp" viewBox="0 0 24 24"><path d="M10 13.5V5a2 2 0 1 1 4 0v8.5a4 4 0 1 1-4 0z"/></symbol>
<symbol id="m-feels" viewBox="0 0 24 24"><path d="M10 13.5V5a2 2 0 1 1 4 0v8.5a4 4 0 1 1-4 0z"/><path d="M19 4.5l2-2M19.5 9h3"/></symbol>
<symbol id="m-rain" viewBox="0 0 24 24"><path d="M7 14a4 4 0 0 1 .4-8 5.5 5.5 0 0 1 10.4 1.3A3.3 3.3 0 0 1 17 14"/><path d="M8 18l-1 2M12 18l-1 2M16 18l-1 2"/></symbol>
<symbol id="m-uv" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></symbol>
<symbol id="m-vis" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/></symbol>
<symbol id="m-tide" viewBox="0 0 24 24"><path d="M3 16c3 0 3-3 6-3s3 3 6 3 3-3 6-3"/><path d="M12 3v7M9 7l3 3 3-3"/></symbol>
<symbol id="s-shield" viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6z"/><path d="M9 12l2 2 4-4"/></symbol>
<symbol id="s-storm" viewBox="0 0 24 24"><path d="M7 16a4 4 0 0 1 .4-8 5.5 5.5 0 0 1 10.5 1.3A3.4 3.4 0 0 1 17 16"/><path d="M12 12.5l-2 3.5h3l-2 3.5"/></symbol>
<symbol id="s-warn" viewBox="0 0 24 24"><path d="M12 3 1.5 21h21z"/><path d="M12 10v4.5"/><path d="M12 17.6v.01"/></symbol>`;

const ICON = (sport, cls = "") =>
  `<svg class="icon ${cls}"><use href="#${SYM[sport] || "i-kite"}"/></svg>`;

class SwelligenceCard extends HTMLElement {
  setConfig(config) {
    this._config = { mode: "podium", ...config };
    this._ov = null;
    this._spots = undefined;        // all spots (spot mode); undefined = not yet loaded
    this._loading = false;
    // UI state for spot mode — preserved across hass re-renders.
    this._sv = {
      sport: config.sport || null,
      view: config.default_view || "now",
      spotIdx: null,                // selected tab; resolved from config.spot on first load
      spotInit: config.spot || null,
      hour: 0,                      // scrubbed hour in the NOW outlook (0 = live now)
    };
  }
  getCardSize() { return this._config.mode === "podium" ? 7 : this._config.mode === "spot" ? 8 : 5; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._root) this._init();
    if (first || this._needsOverview()) this._loadOverview();
    if (this._config.mode === "spot" && (first || this._spots === undefined)) this._loadDetail();
    this._render();
  }

  _needsOverview() {
    return ["timeline", "podium"].includes(this._config.mode) && !this._ov;
  }

  _init() {
    this._root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = CSS;
    this._card = document.createElement("ha-card");
    this._body = document.createElement("div");
    this._body.className = "wrap";
    const defs = `<svg width="0" height="0" style="position:absolute"><defs>${ICON_DEFS}</defs></svg>`;
    this._card.innerHTML = defs;
    this._card.appendChild(this._body);
    this._root.append(style, this._card);
    // tap handling for the interactive spot mode (view toggle, sport select)
    this._body.addEventListener("click", (e) => this._onClick(e));
    // drag-scrub the 24h outlook (pointer down on bars, then move)
    this._body.addEventListener("pointerdown", (e) => {
      if (!e.target.closest(".sd-tl .bars")) return;
      this._scrubbing = true;
      try { e.target.setPointerCapture?.(e.pointerId); } catch {}
      this._onScrub(e); e.preventDefault();
    });
    this._body.addEventListener("pointermove", (e) => { if (this._scrubbing) this._onScrub(e); });
    this._body.addEventListener("pointerup", () => { this._scrubbing = false; });
    this._body.addEventListener("pointercancel", () => { this._scrubbing = false; });
    // periodic refresh of forecast data
    this._timer = setInterval(() => { this._loadOverview(); this._loadDetail(); }, 300000);
  }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

  _onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    // Changing view / sport / spot resets the scrub to "now"; scrubbing an hour
    // keeps the current view but focuses that hour across every element.
    if (el.dataset.act === "view") { this._sv.view = el.dataset.v; this._sv.hour = 0; }
    else if (el.dataset.act === "sport") { this._sv.sport = el.dataset.s; this._sv.hour = 0; }
    else if (el.dataset.act === "spot") { this._sv.spotIdx = +el.dataset.i; this._sv.sport = null; this._sv.hour = 0; }
    else if (el.dataset.act === "hour") { this._sv.hour = +el.dataset.h; }
    else return;
    this._render();
  }

  /* Drag-scrub across the 24h outlook: map pointer-x over the bars to an hour. */
  _onScrub(e) {
    const bars = e.target.closest(".sd-tl .bars");
    if (!bars) return;
    const n = bars.children.length || 24;
    const r = bars.getBoundingClientRect();
    const h = Math.max(0, Math.min(n - 1, Math.floor((e.clientX - r.left) / r.width * n)));
    if (h !== this._sv.hour) { this._sv.hour = h; this._render(); }
  }

  async _loadDetail() {
    if (!this._hass || this._loadingD || this._config.mode !== "spot") return;
    this._loadingD = true;
    try {
      // Fetch ALL spots (no filter) so the in-card tab strip can switch between
      // them client-side; `spots` config (if set) narrows which appear.
      const r = await this._hass.callService("swelligence", "get_spot_detail", {}, undefined, false, true);
      let spots = (r && r.response && r.response.spots) || [];
      if (this._config.spots) spots = spots.filter((s) => this._config.spots.includes(s.name));
      this._spots = spots;
      if (this._sv.spotIdx == null) {
        const ix = this._sv.spotInit ? spots.findIndex((s) => s.name === this._sv.spotInit) : -1;
        this._sv.spotIdx = ix >= 0 ? ix : 0;
      }
    } catch (e) { if (this._spots === undefined) this._spots = []; }
    this._loadingD = false;
    this._render();
  }

  async _loadOverview() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const data = {};
      if (this._config.spots) data.spots = this._config.spots;
      if (this._config.sports) data.sports = this._config.sports;
      if (this._config.priority && this._config.priority.length) data.priority = this._config.priority;
      const r = await this._hass.callService("swelligence", "get_overview", data, undefined, false, true);
      this._ov = (r && r.response) || null;
    } catch (e) { /* keep stale */ }
    this._loading = false;
    this._render();
  }

  _showScore() { return this._config.show_score !== false; }

  _priority() {
    // Priority is a card setting now (drag-to-reorder in the visual editor),
    // not an integration option. Fall back to the built-in ORDER.
    return (this._config.priority && this._config.priority.length)
      ? this._config.priority : ORDER;
  }
  _sortSports(list) {
    const p = this._priority();
    const rk = (s) => { const i = p.indexOf(s); return i < 0 ? 99 : i; };
    return [...list].sort((a, b) => rk(a) - rk(b) || ORDER.indexOf(a) - ORDER.indexOf(b));
  }

  _nowCells() {
    const out = [];
    for (const id in this._hass.states) {
      if (!id.startsWith("sensor.swelligence_") || !id.endsWith("_suitability")) continue;
      const s = this._hass.states[id], a = s.attributes || {};
      if (!a.spot || !a.sport) continue;
      if (this._config.spots && !this._config.spots.includes(a.spot)) continue;
      if (this._config.sports && !this._config.sports.includes(a.sport)) continue;
      out.push({ id, score: Math.round(parseFloat(s.state)), ...a });
    }
    return out;
  }

  _render() {
    if (!this._hass) return;
    const m = this._config.mode;
    const title = this._config.title;
    let html = title ? `<div class="title">${title}</div>` : "";
    html += { heatgrid: () => this._heatgrid(), medallions: () => this._nowMedallions(),
      timeline: () => this._timeline(), podium: () => this._podium(), spot: () => this._spot() }[m]?.() ||
      `<div class="muted">Unknown mode "${m}".</div>`;
    this._body.innerHTML = html;
  }

  /* ---------- NOW: heat grid ---------- */
  _heatgrid() {
    const cells = this._nowCells();
    if (!cells.length) return this._empty();
    const spots = [...new Set(cells.map((c) => c.spot))];
    const sports = this._sortSports([...new Set(cells.map((c) => c.sport))]);
    const by = {}; cells.forEach((c) => (by[c.spot + "|" + c.sport] = c));
    let h = `<table class="grid"><thead><tr><th></th>`;
    for (const sp of sports) h += `<th>${ICON(sp)}<div class="cl">${LABELS[sp] || sp}</div></th>`;
    h += `</tr></thead><tbody>`;
    for (const spot of spots) {
      h += `<tr><td class="sp">${spot}</td>`;
      for (const sp of sports) {
        const c = by[spot + "|" + sp];
        if (!c) { h += `<td class="na">·</td>`; continue; }
        const v = c.verdict || band(c.score);
        const kit = c.rig_size_m2 ? `<span class="k">${c.rig_size_m2}m²</span>` : "";
        h += `<td><div class="hc" style="background:${vc(v)};color:${vt(v)}">${ICON(sp, "gho")}<span class="sc">${isNaN(c.score) ? "–" : c.score}</span>${kit}</div></td>`;
      }
      h += `</tr>`;
    }
    return h + `</tbody></table>`;
  }

  /* ---------- NOW: medallions (card mode) ---------- */
  _nowMedallions() {
    const cells = this._nowCells();
    if (!cells.length) return this._empty();
    const spots = [...new Set(cells.map((c) => c.spot))];
    let h = `<div class="mcards">`;
    for (const spot of spots) {
      const items = this._sortSports(cells.filter((c) => c.spot === spot).map((c) => c.sport))
        .map((sp) => cells.find((c) => c.spot === spot && c.sport === sp));
      const wt = items[0]?.water_type ? `<span class="wt">${items[0].water_type}</span>` : "";
      h += `<div class="mcard"><div class="mh"><span class="nm">${spot}</span>${wt}</div><div class="meds">`;
      for (const c of items) {
        const v = c.verdict || band(c.score);
        const kit = c.rig_size_m2 ? `<div class="mk">${c.rig_size_m2}m²</div>` : "";
        const sc = this._showScore() ? `<div class="rs">${c.score}</div>` : "";
        h += `<div class="med"><div class="ring" style="--c:${vc(v)};--p:${c.score}"><div class="ri">${ICON(c.sport)}${sc}</div></div><div class="ml">${LABELS[c.sport] || c.sport}</div>${kit}</div>`;
      }
      h += `</div></div>`;
    }
    return h + `</div>`;
  }

  /* ---------- FORECAST: opportunity timeline ---------- */
  _timeline() {
    if (!this._ov) return `<div class="muted">Loading forecast…</div>`;
    let sessions = this._ov.sessions || [];
    if (this._config.spots) sessions = sessions.filter((s) => this._config.spots.includes(s.spot));
    if (this._config.sports) sessions = sessions.filter((s) => this._config.sports.includes(s.sport));
    if (!sessions.length) return `<div class="muted">No go-worthy sessions in the next 7 days.</div>`;
    let days = [...new Set(sessions.map((s) => s.day))].sort();
    if (this._config.days) days = days.slice(0, this._config.days);
    sessions = sessions.filter((s) => days.includes(s.day));
    const spots = [...new Set(sessions.map((s) => s.spot))];
    const LO = 3, HI = 22, span = HI - LO;
    const gc = `grid-template-columns:104px repeat(${days.length},1fr)`;
    let h = `<div class="tl"><div class="tlrow tlhead" style="${gc}"><div class="tlsp"></div>`;
    for (const d of days) h += `<div class="tld">${wday(d)}</div>`;
    h += `</div>`;
    for (const spot of spots) {
      h += `<div class="tlrow" style="${gc}"><div class="tlsp">${spot.split(" / ")[0]}</div>`;
      for (const d of days) {
        h += `<div class="tlc">`;
        for (const s of sessions.filter((x) => x.spot === spot && x.day === d)) {
          const left = Math.max(0, (s.start - LO) / span * 100);
          const width = Math.max(9, (s.end - s.start) / span * 100);
          h += `<div class="blk" style="left:${left}%;width:${width}%;background:${vc(s.verdict)};color:${vt(s.verdict)}" title="${s.start}:00–${s.end}:00 · ${LABELS[s.sport]} · ${s.peak}">${ICON(s.sport, "xs")}</div>`;
        }
        h += `</div>`;
      }
      h += `</div>`;
    }
    return h + `</div>`;
  }

  /* ---------- FORECAST: top-3 podium ---------- */
  _podium() {
    if (!this._ov) return `<div class="muted">Loading forecast…</div>`;
    let pod = this._ov.podium || [];
    if (this._config.days) pod = pod.slice(0, this._config.days);
    if (!pod.length) return `<div class="muted">No forecast.</div>`;
    const gc = `grid-template-columns:26px repeat(${pod.length},1fr)`;
    let h = `<div class="pod"><div class="prow phead" style="${gc}"><div class="rk"></div>`;
    for (const p of pod) h += `<div class="pd">${wday(p.day)}<span>${p.day.slice(8)}</span></div>`;
    h += `</div>`;
    for (let place = 1; place <= 3; place++) {
      h += `<div class="prow" style="${gc}"><div class="rk r${place}">${place}</div>`;
      for (const p of pod) {
        const m = (p.ranks || []).find((r) => r.place === place);
        if (!m) { h += `<div class="pc"><div class="pm empty"></div></div>`; continue; }
        const v = m.verdict || band(m.score);
        const sc = this._showScore() ? `<div class="ps">${m.score}</div>` : "";
        h += `<div class="pc"><div class="pm ${place === 1 ? "big" : ""}" style="--c:${vc(v)};--p:${m.score}"><div class="pi">${ICON(m.sport)}${sc}</div></div><div class="pl">${m.spot.split(" / ")[0].split(" ")[0]}</div></div>`;
      }
      h += `</div>`;
    }
    return h + `</div>`;
  }

  /* ---------- SPOT: multi-spot now/week detail (720-panel layout) ---------- */
  _spotList() { return this._spots || []; }
  _spot() {
    if (this._spots === undefined) return `<div class="muted">Loading spot detail…</div>`;
    const spots = this._spotList();
    if (!spots.length) return this._empty();
    let si = this._sv.spotIdx;
    if (si == null || si < 0 || si >= spots.length) si = 0;
    const d = spots[si];
    const sportsAll = (d.sports || []).filter((s) =>
      !this._config.sports || this._config.sports.includes(s.sport));
    if (!sportsAll.length) return this._empty();
    let pi = sportsAll.findIndex((s) => s.sport === this._sv.sport);
    if (pi < 0) pi = 0;
    const sp = sportsAll[pi], view = this._sv.view, c = d.current || {};
    const frame = view === "now" ? this._frame(sp, d) : null;
    const met = frame ? frame.met : c;
    this._curRef = () => met;
    const wc = cardOf(met.wind_dir_deg);
    const dl = sp.daily || [];
    const range = dl.length ? `${this._wd(dl[0].date)} – ${this._wd(dl[dl.length - 1].date)}` : "";
    const headRight = view === "now"
      ? `<div class="sd-now"><span class="pulse${frame.isNow ? "" : " off"}"></span><div><b>${frame.time || d.now_time || "--:--"}</b><span>${frame.isNow ? "now" : frame.label}</span></div></div>`
      : `<div class="sd-now"><div><b>${range || "7 days"}</b><span>7-day</span></div></div>`;
    const header = `<div class="sd-hdr">
        <div class="sd-id"><div class="sd-logo">S</div>
          <div><div class="sd-nm">${d.name}</div>
            <div class="sd-sub"><b>${d.water_type || ""}</b>${d.latitude != null ? " · " + d.latitude.toFixed(3) + ", " + d.longitude.toFixed(3) : ""} · Open-Meteo</div></div></div>
        <div class="sd-ctrl">
          ${headRight}
          <div class="sd-seg">
            <button data-act="view" data-v="now" class="${view === "now" ? "on" : ""}">Now</button>
            <button data-act="view" data-v="week" class="${view === "week" ? "on" : ""}">Week</button>
          </div>
        </div>
      </div>`;

    // NOW: the Card A single-column layout (medallions → map+readout hero →
    // full-width outlook with daylight lane). WEEK: the existing two-column.
    if (view === "now") {
      return `<div class="sd sd-cardA">
        ${header}
        ${this._medallions(sportsAll, pi, view)}
        ${this._cardAHero(d, met, wc, sp, frame)}
        ${this._cardAOutlook(sp, d, frame)}
        ${this._tabs(spots, si, view)}
      </div>`;
    }
    return `<div class="sd">
      ${header}
      <div class="sd-main">
        <div class="sd-col">${this._mapHero(d, met, wc, view, sp, frame)}${this._weekSummary(sp)}</div>
        <div class="sd-col sd-sportcol">${this._medallions(sportsAll, pi, view) + this._detail(sp, view) + this._dayRows(sp)}</div>
      </div>
      ${this._tabs(spots, si, view)}
    </div>`;
  }

  /* ---- Card A NOW hero: map + compass on the left, a 3-cell readout
     (suitability ring · kit arc · safety) over a 2-column factor list. ---- */
  _cardAHero(d, met, wc, sp, frame) {
    const col = vcw(frame.verdict);
    const kitCell = frame.kit ? this._kitArc(frame.kit, sp.sport) : `<div class="ro-na">—</div>`;
    return `<div class="sc-hero">
      ${this._mapHero(d, met, wc, "now", sp, frame)}
      <div class="sc-readcol">
        <div class="sc-read">
          <div class="sc-cell">
            <div class="ro-ring">${this._ring(frame.score ?? 0, col, 60, 7)}<span class="ro-num" style="color:${col}">${Math.round(frame.score ?? 0)}</span></div>
            <div class="gcap" style="color:${col}">${frame.verdict || ""}</div></div>
          <div class="sc-cell">${kitCell}</div>
          <div class="sc-cell">${this._safetyCell(frame)}</div>
        </div>
        <div class="sc-pills">${this._cardAPills(d, met)}</div>
      </div>
    </div>`;
  }

  /* metric pills: the full raw-conditions readout for the focused hour
     (the weather data the now-strip used to carry). Each pill = label + value
     (+ unit). Bound to frame.met so it scrubs with the timeline. */
  _cardAPills(d, met) {
    const t = d.tide || {};
    // icon-led pill: the icon IS the label (full label on hover); value is the
    // hero, unit subdued. "—" alone when a metric has no data (no dangling unit).
    const pill = (sym, label, val, unit, cls) => {
      const has = val !== "—" && val != null;
      return `<div class="mp ${cls || ""}" title="${label}">
        <svg class="mp-ic"><use href="#${sym}"/></svg>
        <div class="mp-v">${val}${has && unit ? `<small>${unit}</small>` : ""}</div></div>`;
    };
    const n = (x, dp = 1) => (x != null ? f1(x, dp) : "—");
    const waveV = met.wave_height_m != null ? n(met.wave_height_m) : (met.wind_wave_height_m != null ? n(met.wind_wave_height_m) : "—");
    return [
      pill("m-wind", "Wind", n(met.wind_speed_kn), "kn " + (cardOf(met.wind_dir_deg) || "")),
      pill("m-gust", "Gust", n(met.wind_gust_kn), "kn", "amber"),
      pill("m-wave", "Wave", waveV, "m"),
      pill("m-swell", "Swell", n(met.swell_height_m), met.swell_period_s != null ? "m · " + n(met.swell_period_s) + "s" : "m"),
      pill("m-temp", "Water", n(met.water_temp_c), "°C"),
      pill("m-feels", "Feels-like", n(met.apparent_temp_c), "°C"),
      pill("m-rain", "Rain", n(met.precip_mm), met.precip_prob_pct != null ? "mm · " + Math.round(met.precip_prob_pct) + "%" : "mm"),
      pill("m-uv", "UV index", met.uv_index != null ? String(Math.round(met.uv_index)) : "—", ""),
      pill("m-vis", "Visibility", met.visibility_m != null ? (met.visibility_m / 1000).toFixed(met.visibility_m < 10000 ? 1 : 0) : "—", "km"),
      pill("m-tide", "Tide", t.now != null ? n(t.now) + "m" : (cap(t.state) || "—"), t.now != null ? (t.state || "") : ""),
    ].join("");
  }

  /* ---- Card A outlook: daylight lane (sun-elevation curve) over the 24h
     score bars; tap/drag scrubs. ---- */
  _cardAOutlook(sp, d, frame) {
    const ser = (sp.hourly || []).slice(0, 24);
    if (!ser.length) return `<div class="chartwrap"><div class="ch-h"><span class="k">Outlook · next 24h</span></div><div class="none">no hourly forecast</div></div>`;
    const selH = this._sv.hour || 0, bestI = sp.best ? sp.best.in_hours : null;
    const bars = ser.map((p, i) => `<button class="bar ${i === 0 ? "now" : ""} ${i === bestI ? "best" : ""} ${i === selH ? "sel" : ""}" data-act="hour" data-h="${i}" style="height:${Math.max(6, Math.round(p.score ?? 0))}%;background:${vcw(p.verdict)}" title="${(p.datetime || "").slice(11, 16)} · ${Math.round(p.score ?? 0)}"></button>`).join("");
    let axis = ""; ser.forEach((p, i) => { axis += `<span>${i % 3 === 0 ? (p.datetime || "").slice(11, 16) : ""}</span>`; });
    return `<div class="chartwrap">
      <div class="ch-h"><span class="k">Outlook · next 24h</span><span class="hint"><b>${frame.time || "--:--"}</b><span>${frame.isNow ? "NOW" : frame.label}</span></span></div>
      <div class="chart">
        ${this._dayLane(d, ser.length)}
        <div class="barwrap"><div class="bars">${bars}</div></div>
      </div>
      <div class="axis">${axis}</div>
    </div>`;
  }

  /* daylight lane: sun-elevation curve + sunrise/sunset ticks + a sun/moon mark
     at the scrubbed hour. Reads d.daylight.sunrise/sunset and now_time. */
  _dayLane(d, n) {
    const dl = d.daylight || {};
    const toH = (t) => { const m = /^(\d{1,2}):(\d{2})/.exec(t || ""); return m ? +m[1] + +m[2] / 60 : null; };
    const start = parseInt((d.now_time || "").slice(0, 2), 10);
    const sr = toH(dl.sunrise), ss = toH(dl.sunset);
    if (isNaN(start) || sr == null || ss == null) return `<div class="daylane plain"><span class="dl-lbl">Daylight</span></div>`;
    const dlen = ss - sr;
    const elev = (rel) => { let t = (start + rel) % 24; if (t >= sr && t <= ss) return Math.sin(Math.PI * (t - sr) / dlen); const nt = t < sr ? t + 24 : t; return -0.5 * Math.sin(Math.PI * (nt - ss) / ((sr + 24) - ss)); };
    const yOf = (e) => (50 - e * 30).toFixed(1), xOf = (r) => (r / 24 * 100).toFixed(1);
    const pts = []; for (let r = 0; r <= 24; r += 0.5) pts.push(`${xOf(r)},${yOf(elev(r))}`);
    const ssRel = ((ss - start) + 24) % 24, srRel = ((sr - start) + 24) % 24;
    const selH = this._sv.hour || 0, e = elev(selH + 0.5), day = e >= 0;
    return `<div class="daylane">
      <span class="dl-lbl">Daylight</span>
      <svg class="sky" viewBox="0 0 100 100" preserveAspectRatio="none">
        <line class="sky-horizon" x1="0" y1="${yOf(0)}" x2="100" y2="${yOf(0)}"/>
        <line class="sky-tick" x1="${xOf(ssRel)}" y1="2" x2="${xOf(ssRel)}" y2="98"/>
        <line class="sky-tick" x1="${xOf(srRel)}" y1="2" x2="${xOf(srRel)}" y2="98"/>
        <polyline class="sky-line" points="${pts.join(" ")}"/></svg>
      <span class="dl-t" style="left:${xOf(ssRel)}%">↓ ${dl.sunset}</span>
      <span class="dl-t" style="left:${xOf(srRel)}%">↑ ${dl.sunrise}</span>
      <span class="sunmark ${day ? "" : "night"}" style="left:${((selH + 0.5) / n * 100).toFixed(1)}%;top:${yOf(e)}%">${day ? "☀" : "☾"}</span>
    </div>`;
  }

  _wd(date) { try { return new Date(date).toLocaleDateString(undefined, { weekday: "short" }); } catch { return date; } }
  _peak(sp) { const d = sp.daily || []; return d.length ? d.reduce((a, b) => (b.score > a.score ? b : a), d[0]) : null; }

  /* Focused-hour view model for the NOW scrubber. Hour 0 reads the richest
     "now" payload (+ live current met, reasons, full kit object); a scrubbed
     hour reads that hourly slot (kit from its flat kit_* fields, met from its
     own fields). Every NOW renderer binds to this so the whole card follows. */
  _frame(sp, d) {
    const hourly = sp.hourly || [];
    let h = this._sv.hour || 0;
    if (h < 0) h = 0;
    if (hourly.length && h >= hourly.length) h = hourly.length - 1;
    const slot = hourly[h] || {};
    const time = (slot.datetime || "").slice(11, 16);
    if (h === 0) {
      const now = sp.now || {}, c = d.current || {};
      return {
        hour: 0, isNow: true, label: "NOW", time: d.now_time || time,
        score: now.score, verdict: now.verdict, factors: now.factors || {},
        safety_flags: now.safety_flags || [], hard_gated: !!now.hard_gated,
        warnings: now.warnings || [],
        kit: now.kit || null, reasons: now.reasons || [], met: { ...c },
      };
    }
    const kit = slot.kit_power
      ? { power: slot.kit_power, rig_m2: slot.kit_rig_m2, ideal_m2: slot.kit_ideal_m2 } : null;
    return {
      hour: h, isNow: false, label: "+" + h + "h", time,
      score: slot.score, verdict: slot.verdict, factors: slot.factors || {},
      safety_flags: slot.safety_flags || [], hard_gated: !!slot.hard_gated,
      warnings: slot.warnings || [],
      kit, reasons: [],
      met: {
        wind_speed_kn: slot.wind_speed_kn, wind_gust_kn: slot.wind_gust_kn,
        wind_dir_deg: slot.wind_bearing, wave_height_m: slot.wave_height_m,
        wind_wave_height_m: slot.wind_wave_height_m, swell_height_m: slot.swell_height_m,
        swell_period_s: slot.swell_period_s, water_temp_c: slot.water_temp_c,
        apparent_temp_c: slot.apparent_temp_c, precip_mm: slot.precip_mm,
        precip_prob_pct: slot.precip_prob_pct, weather_code: slot.weather_code,
      },
    };
  }

  /* Safety cell: advisory safety_flags for the focused hour + a tier glyph.
     Glyph severity: hard weather gate -> storm; else a danger flag -> warning;
     else a caution flag -> caution; else clear. */
  _safetyCell(frame) {
    const flags = frame.safety_flags || [];
    const short = { too_strong: "too strong", too_big: "too big", too_choppy: "choppy", gusty: "gusty" };
    const sym = { too_strong: "m-wind", gusty: "m-gust", too_big: "m-wave", too_choppy: "m-wave" };
    let icon = "s-shield", cls = "ok", cap = "clear", title = "no safety flags";
    if (frame.hard_gated) {
      icon = "s-storm"; cls = "danger"; cap = "storm"; title = "hard weather hazard";
    } else if (flags.length) {
      const danger = flags.find((f) => f.severity === "danger");
      const lead = danger || flags[0];
      icon = sym[lead.kind] || "s-warn";
      cls = danger ? "danger" : "caution";
      cap = (short[lead.kind] || lead.kind) + (flags.length > 1 ? ` +${flags.length - 1}` : "");
      title = flags.map((f) => f.message).join(" · ");
    }
    return `<div class="sd-safety ${cls}" title="${title}">
      <div class="sf-grid"><svg class="sf-ic"><use href="#${icon}"/></svg></div>
      <div class="gcap">${cap}</div></div>`;
  }

  /* SVG progress ring (stroke-dasharray) — 720-panel gauge. */
  _ring(score, col, size = 80, sw = 8) {
    const r = size / 2 - sw, circ = 2 * Math.PI * r, off = circ * (1 - (score || 0) / 100);
    return `<svg class="sd-ring-svg" viewBox="0 0 ${size} ${size}">
      <circle class="gt" cx="${size / 2}" cy="${size / 2}" r="${r}" style="stroke-width:${sw}"/>
      <circle class="ga" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke="${col}" style="stroke-width:${sw}" stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/></svg>`;
  }

  _factors(now) {
    const order = ["wind", "gust", "direction", "wave", "swell", "temp", "tide", "kit"];
    const f = now.factors || {};
    return order.filter((k) => f[k] != null).map((k) =>
      `<div class="sd-fac"><span class="fl">${k}</span><span class="fb"><i style="width:${f[k]}%"></i></span><span class="fn">${Math.round(f[k])}</span></div>`).join("");
  }

  /* ---- map hero: static OSM tile mosaic centred on the spot (no JS dep) ---- */
  _isDark() {
    try {
      const cs = getComputedStyle(this._card);
      const bg = (cs.getPropertyValue("--card-background-color").trim() || cs.backgroundColor);
      const m = bg.match(/\d+(\.\d+)?/g);
      if (!m || m.length < 3) return true;
      const [r, g, b] = m.map(Number);
      return (0.299 * r + 0.587 * g + 0.114 * b) < 128;
    } catch { return true; }
  }
  _tileMosaic(lat, lon, zoom = 11) {
    const n = 2 ** zoom;
    const xf = (lon + 180) / 360 * n;
    const lr = lat * Math.PI / 180;
    const yf = (1 - Math.log(Math.tan(lr) + 1 / Math.cos(lr)) / Math.PI) / 2 * n;
    const xt = Math.floor(xf), yt = Math.floor(yf);
    const mx = 256 + (xf - xt) * 256, my = 256 + (yf - yt) * 256;   // marker px within 3×3 mosaic
    let imgs = "";
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const tx = ((xt + dx) % n + n) % n, ty = yt + dy;
      if (ty < 0 || ty >= n) continue;
      imgs += `<img alt="" loading="lazy" src="https://tile.openstreetmap.org/${zoom}/${tx}/${ty}.png" style="left:${(dx + 1) * 256}px;top:${(dy + 1) * 256}px"/>`;
    }
    return `<div class="lmap${this._isDark() ? " dark" : ""}">
      <div class="mos" style="margin-left:${(-mx).toFixed(1)}px;margin-top:${(-my).toFixed(1)}px">${imgs}</div>
      <svg class="pin" viewBox="0 0 24 24"><path d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7z"/><circle cx="12" cy="9" r="2.6"/></svg>
      <a class="osm" href="https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=${zoom}/${lat.toFixed(4)}/${lon.toFixed(4)}" target="_blank" rel="noopener noreferrer">© OSM</a>
    </div>`;
  }
  _mapHero(d, c, wc, view, sp, frame) {
    const lat = d.latitude, lon = d.longitude;
    const map = (lat == null || lon == null) ? `<div class="sd-nomap">no location</div>` : this._tileMosaic(lat, lon);
    let compass = "";
    if (view === "now" && c.wind_dir_deg != null) {
      const dirFac = frame ? frame.factors?.direction : sp?.now?.factors?.direction;
      const col = facCol(dirFac);
      const rot = (c.wind_dir_deg + 180) % 360;
      compass = `<svg class="sd-windc" viewBox="0 0 100 100">
        <g transform="translate(50 50)">
          <circle r="34" class="sd-windc-dial"/>
          <text x="0" y="-25" class="sd-windc-n">N</text>
          <g transform="rotate(${rot.toFixed(0)})" stroke="${col}" fill="${col}">
            <line x1="0" y1="22" x2="0" y2="-16" stroke-width="5" stroke-linecap="round"/>
            <path d="M0 -28 L8 -11 L0 -16 L-8 -11 Z"/>
          </g>
        </g></svg>`;
    }
    const band = view === "now"
      ? `<div class="wband"><div class="wfrom">${wc ? `Wind from <span>${wc}</span>` : "Calm"}</div><div class="wxy">${c.wind_speed_kn != null ? f1(c.wind_speed_kn) + " kn" : ""}${c.wind_gust_kn != null ? " · gust " + f1(c.wind_gust_kn) : ""}</div></div>`
      : `<div class="wband"><div class="wfrom">${d.name}</div><div class="wxy">${lat != null ? lat.toFixed(3) + ", " + lon.toFixed(3) : ""}</div></div>`;
    return `<div class="sd-map">${map}<div class="vign"></div>${compass}${band}</div>`;
  }

  /* ---- tide module: state + next high/low + 24h modelled sea-level curve ---- */
  _tideHours(nowTime, n) {
    let h = parseInt((nowTime || "").slice(0, 2), 10); if (isNaN(h)) h = 0;
    const out = []; for (let i = 0; i < n; i++) out.push(String((h + i) % 24).padStart(2, "0") + ":00");
    return out;
  }
  _tideModule(d) {
    const t = d.tide;
    if (!t || this._config.show_tide === false) {
      return `<div class="sd-tidep t-slack"><div class="th"><span class="k">Tide</span></div><div class="nxt">no tide model</div></div>`;
    }
    const arrow = t.state === "rising" ? "▲" : t.state === "falling" ? "▼" : "—", nx = t.next;
    const lv = t.levels || [], n = lv.length, lo = t.min, hi = t.max, rng = (hi - lo) || 1;
    const W = 268, H = 86, hours = this._tideHours(d.now_time, n);
    const X = (i) => i / Math.max(1, n - 1) * W, Y = (v) => v == null ? H / 2 : H - 6 - ((v - lo) / rng) * (H - 12);
    let dp = ""; lv.forEach((v, i) => { if (v == null) return; dp += (dp ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1) + " "; });
    const fillp = n ? `M0 ${H} L` + lv.map((v, i) => X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(" L") + ` L${W} ${H} Z` : "";
    const nowX = X(0), nxX = nx && nx.in_h != null ? X(nx.in_h) : null, nxY = nx && nx.level != null ? Y(nx.level) : null;
    let labs = ""; for (let i = 0; i < n; i += 6) labs += `<text class="clab" x="${(X(i) + 2).toFixed(1)}" y="${H - 1}">${hours[i] || ""}</text>`;
    return `<div class="sd-tidep t-${t.state}">
      <div class="th"><span class="k">Tide</span><span class="model">${t.source || "modelled"}</span></div>
      <div class="state"><span class="arrow">${arrow}</span><span class="word">${cap(t.state)}</span></div>
      <div class="nxt">${nx ? `next <b>${nx.type}</b> at <b>${nx.time}</b>${nx.level != null ? ` <span class="dim">(${f1(nx.level, 2)}m)</span>` : ""}` : "between turning points"}</div>
      <div class="curve"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        ${fillp ? `<path class="cfill" d="${fillp}"/>` : ""}<path class="cpath" d="${dp}"/>
        <line class="cnow" x1="${nowX.toFixed(1)}" y1="2" x2="${nowX.toFixed(1)}" y2="${H - 2}"/>
        ${lv[0] != null ? `<circle class="cnowdot" cx="${nowX.toFixed(1)}" cy="${Y(lv[0]).toFixed(1)}" r="3"/>` : ""}
        ${nxX != null ? `<circle class="cdot" cx="${nxX.toFixed(1)}" cy="${nxY.toFixed(1)}" r="3.5"/>` : ""}
        ${labs}
      </svg></div>
    </div>`;
  }

  /* ---- daylight arc (NOW view only) ---- */
  _daylight(d) {
    const dl = d.daylight;
    if (!dl || dl.remaining_min == null) return "";
    const h = Math.floor(dl.remaining_min / 60), m = dl.remaining_min % 60;
    const left = h > 0 ? `${h}h ${m}m` : `${m}m`;
    // Sun position along the top semicircle (centre 55,46 r47) by daylight progress.
    const p = dl.progress == null ? 1 : Math.min(1, Math.max(0, dl.progress));
    const ang = p * Math.PI;
    const sx = (55 - 47 * Math.cos(ang)).toFixed(1), sy = (46 - 47 * Math.sin(ang)).toFixed(1);
    const elapsed = p > 0 ? `<path d="M8 46 A47 47 0 0 1 ${sx} ${sy}" class="sd-day-arc"/>` : "";
    return `<div class="sd-day">
      <svg viewBox="0 0 110 52" class="sd-day-svg">
        <path d="M8 46 A47 47 0 0 1 102 46" class="sd-day-track"/>
        ${elapsed}
        <circle cx="${sx}" cy="${sy}" r="5" class="sd-day-sun"/>
      </svg>
      <div class="sd-day-meta"><span class="k">Daylight</span><b>${left}</b><span class="s">light left · sunset ${dl.sunset}</span></div>
    </div>`;
  }

  /* ---- now-view pieces ---- */
  _nowStrip(c) {
    const cell = (amber, k, v, sub) => `<div class="ns ${amber ? "amber" : ""}"><div class="k">${k}</div><div class="v">${v}${sub ? `<small> ${sub}</small>` : ""}</div></div>`;
    const [wg] = WMO(c.weather_code);
    const rain = c.precip_mm != null ? f1(c.precip_mm) : "—";
    const rainSub = c.precip_prob_pct != null ? `mm · ${Math.round(c.precip_prob_pct)}%` : "mm";
    return cell(false, "Wind", f1(c.wind_speed_kn), "kn " + (cardOf(c.wind_dir_deg) || ""))
      + cell(true, "Gust", f1(c.wind_gust_kn), "kn")
      + cell(false, "Wave", c.wave_height_m != null ? f1(c.wave_height_m) : (c.wind_wave_height_m != null ? f1(c.wind_wave_height_m) : "—"), "m")
      + cell(false, "Swell", c.swell_height_m != null ? f1(c.swell_height_m) : "—", c.swell_period_s != null ? f1(c.swell_period_s) + "s" : "m")
      + cell(false, `Rain ${wg}`, rain, rainSub)
      + cell(false, "Feels", c.apparent_temp_c != null ? f1(c.apparent_temp_c) : "—", "°C");
  }
  _hourlyTL(sp) {
    const ser = (sp.hourly || []).slice(0, 24);
    if (!ser.length) return `<div class="sd-tl"><div class="tlh"><span class="k">Next 24h</span></div><div class="none">no hourly forecast</div></div>`;
    const bestI = sp.best ? sp.best.in_hours : null;
    const selH = this._sv.hour || 0;
    const bars = ser.map((p, i) => `<div class="b ${i === 0 ? "now" : ""} ${i === bestI ? "best" : ""} ${i === selH ? "sel" : ""}" data-act="hour" data-h="${i}" style="height:${Math.max(6, Math.round(p.score ?? 0))}%;background:${vcw(p.verdict)}" title="${(p.datetime || "").slice(11, 16)} · ${Math.round(p.score ?? 0)}"></div>`).join("");
    let axis = ""; ser.forEach((p, i) => { axis += `<div class="x">${i % 6 === 0 ? (p.datetime || "").slice(11, 16) : ""}</div>`; });
    return `<div class="sd-tl"><div class="tlh"><span class="k">Outlook · next 24h</span><span class="span">tap / drag to scrub</span></div>
      <div class="bars">${bars}</div><div class="axis">${axis}</div></div>`;
  }

  /* ---- week-view pieces ---- */
  _dayRows(sp) {
    const dl = sp.daily || [];
    if (!dl.length) return `<div class="sd-drows"><div class="none">no daily forecast</div></div>`;
    const pk = this._peak(sp), today = dl[0] && dl[0].date;
    return `<div class="sd-drows">${dl.map((e) => {
      const isP = e === pk, c2 = vcw(e.verdict);
      return `<div class="sd-drow ${e.date === today ? "today" : ""} ${isP ? "best" : ""}">
        <div class="dd">${e.date === today ? "Today" : this._wd(e.date)}</div>
        <div class="dbar"><i style="width:${Math.max(4, e.score)}%;background:${c2}"></i></div>
        <div class="dt">${(e.datetime || "").slice(11, 16)}</div>
        <div class="dsc" style="color:${c2}">${isP ? `<span class="star">★</span>` : ""}${Math.round(e.score)}</div>
      </div>`;
    }).join("")}</div>`;
  }
  _weekSummary(sp) {
    const dl = sp.daily || [], pk = this._peak(sp), good = dl.filter((e) => !["poor", "marginal"].includes(e.verdict)).length;
    const col = pk ? vcw(pk.verdict) : vc("good"), cc = pk || {}, wc = cardOf(cc.wind_bearing);
    const today = dl[0] && dl[0].date, tide = cc.tide || {};
    const met = (cls, k, v, sub) => `<div class="st ${cls || ""}"><div class="sk">${k}</div><div class="sv">${v}${sub ? `<small> ${sub}</small>` : ""}</div></div>`;
    return `<div class="sd-wsum">
      <div class="k">Best day · ${sp.label}</div>
      <div class="bigday"><span class="dn" style="color:${col}">${pk ? (pk.date === today ? "Today" : this._wd(pk.date)) : "—"}</span><span class="ds">${pk ? Math.round(pk.score) : "—"}</span><span class="dv" style="color:${col}">${pk ? pk.verdict : ""}</span></div>
      <div class="psub">peak <b>${pk ? (pk.datetime || "").slice(11, 16) : "—"}</b> · ${good}/${dl.length} good+ days</div>
      <div class="wgrid">
        ${met("", "Wind", f1(cc.wind_speed_kn), "kn" + (wc ? " " + wc : ""))}
        ${met("amber", "Gust", f1(cc.wind_gust_kn), "kn")}
        ${met("", "Wave", cc.wave_height_m != null ? f1(cc.wave_height_m) : "—", "m")}
        ${met("", "Swell", cc.swell_height_m != null ? f1(cc.swell_height_m) : "—", cc.swell_period_s != null ? f1(cc.swell_period_s) + "s" : "m")}
        ${this._config.show_tide === false ? "" : met(tide.state ? "t-" + tide.state : "", "Tide", cap(tide.state), tide.height != null ? f1(tide.height, 2) + " m" : "")}
        ${met("", "Water", cc.water_temp_c != null ? f1(cc.water_temp_c) : "—", "°C")}
        ${met("", "Rain", cc.precip_mm != null ? f1(cc.precip_mm) : "—", "mm")}
      </div>
    </div>`;
  }

  /* ---- sport medallion ring-row selector ---- */
  _medallions(sports, active, view) {
    return `<div class="sd-meds">${sports.map((s, i) => {
      const pk = this._peak(s);
      const sc = view === "week" ? (pk ? Math.round(pk.score) : null) : Math.round(s.now?.score ?? 0);
      const verdict = (view === "week" ? pk?.verdict : s.now?.verdict) || "poor";
      const col = vcw(verdict);
      const num = sc == null ? "–" : sc;
      return `<div class="sd-med ${i === active ? "on" : ""}" data-act="sport" data-s="${s.sport}">
        <div class="sd-medr">${this._ring(sc ?? 0, col, 58, 5)}
          <div class="sd-medi">${ICON(s.sport)}<span class="sd-meds-n" style="color:${col}">${num}</span></div></div>
        <div class="sd-medl">${s.label || LABELS[s.sport] || s.sport}</div>
      </div>`;
    }).join("")}</div>`;
  }

  /* ---- arc-gauge kit indicator ---- */
  _kitArc(kit, sport) {
    const power = kit?.power || "no_kit";
    const col = powerCol(power);
    // Needle fraction along the arc: under .2, ideal .5, over .8, none centre/grey.
    const frac = power === "underpowered" ? 0.22 : power === "overpowered" ? 0.78
               : power === "ideal" ? 0.5 : 0.5;
    const a = Math.PI * (1 - frac);                 // 180deg (left) .. 0deg (right)
    const cx = 50, cy = 56, r = 40;
    const nx = (cx + Math.cos(a) * (r - 6)).toFixed(1), ny = (cy - Math.sin(a) * (r - 6)).toFixed(1);
    const fillEnd = power === "no_kit"
      ? "M10 56 A40 40 0 0 0 10 56"                 // empty fill for no-kit
      : `M10 56 A40 40 0 0 1 ${(cx + Math.cos(a) * r).toFixed(1)} ${(cy - Math.sin(a) * r).toFixed(1)}`;
    const size = kit?.rig_m2 != null ? `${kit.rig_m2}m²` : "—";
    const label = power === "no_kit" ? "no kit" : power === "ideal" ? "suitable" : power;
    return `<div class="sd-kit">
      <svg viewBox="0 0 100 64" class="sd-kit-svg">
        <path d="M10 56 A40 40 0 0 1 90 56" class="sd-kit-track"/>
        <path d="${fillEnd}" fill="none" stroke="${col}" stroke-width="9" stroke-linecap="round"/>
        ${power === "no_kit" ? "" : `<line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" class="sd-kit-needle"/>`}
        <circle cx="${cx}" cy="${cy}" r="4" class="sd-kit-hub"/>
        <use href="#${SYM[sport] || "i-kite"}" x="39" y="33" width="22" height="22" fill="none" stroke="${col}" stroke-width="1.6"/>
      </svg>
      <div class="sd-kit-n" style="color:${col}">${size}</div>
      <div class="sd-kit-c">rig · ${label}</div>
    </div>`;
  }

  /* ---- detail card: verdict + best + kit arc + limiting factor + factor bars ---- */
  _detail(sp, view, frame) {
    // NOW view binds to the scrubbed-hour frame; WEEK view to the daily peak.
    const f = view === "now" ? (frame || {}) : {};
    let col, verdictWord, secondLine;
    if (view === "week") {
      const pk = this._peak(sp);
      col = vcw(pk?.verdict);
      verdictWord = pk?.verdict ? pk.verdict.toUpperCase() : "—";
      const pkDay = pk ? (pk.date === (sp.daily && sp.daily[0] && sp.daily[0].date) ? "Today" : this._wd(pk.date)) : "—";
      const pkScore = pk ? Math.round(pk.score) : "—";
      secondLine = `peak <b>${pkDay}</b> · ${pkScore}`;
    } else {
      col = vcw(f.verdict);
      verdictWord = (f.verdict || "—").toUpperCase();
      // When scrubbed off "now", the second line names the focused hour; at now
      // it points at the best upcoming slot (unchanged behaviour).
      if (f.isNow) {
        const best = sp.best;
        const bestT = best ? (best.time || (best.in_hours != null ? "+" + best.in_hours + "h" : "—")) : "—";
        secondLine = best ? `best <b>${bestT}</b> · ${Math.round(best.score)} ${best.verdict || ""}` : "";
      } else {
        secondLine = `at <b>${f.time || f.label}</b> · ${Math.round(f.score ?? 0)} ${f.verdict || ""}`;
      }
    }
    // Limiting factor: first reason (now only), else lowest-scoring factor name.
    let limit = (f.reasons && f.reasons[0]) || "";
    if (!limit && f.factors) {
      const ent = Object.entries(f.factors).filter(([, v]) => v != null);
      if (ent.length) { const [k] = ent.sort((a, b) => a[1] - b[1])[0]; limit = `limited by ${k}`; }
    }
    const facs = (view === "now" && this._config.show_factors !== false) ? this._factors({ factors: f.factors }) : "";
    const readout = view === "now"
      ? `<div class="sd-readout">
          <div class="ro-cell"><div class="ro-k">Suitability</div>
            <div class="ro-ring">${this._ring(f.score ?? 0, col, 72, 7)}<span class="ro-num" style="color:${col}">${Math.round(f.score ?? 0)}</span></div></div>
          <div class="ro-cell"><div class="ro-k">Kit</div>${f.kit ? this._kitArc(f.kit, sp.sport) : `<div class="ro-na">—</div>`}</div>
          <div class="ro-cell">${this._safetyCell(f)}</div>
        </div>`
      : "";
    return `<div class="sd-detail">
      <div class="sd-detail-top">
        <div><div class="sd-detail-sp">${sp.label || LABELS[sp.sport] || sp.sport}</div>
          <div class="sd-detail-vd" style="color:${col}">${verdictWord}</div>
          ${view === "now" && (f.warnings || []).length
            ? `<div class="sd-detail-warn">⚠️ ${f.warnings.map((w) => w.split("_").join(" ")).join(", ")}</div>`
            : ""}
          <div class="sd-detail-best">${secondLine}</div></div>
      </div>
      ${readout}
      ${view === "now" && limit ? `<div class="sd-detail-lf"><span class="dot" style="background:${col}"></span>${limit}</div>` : ""}
      ${view === "now" ? this._wxLine() : ""}
      ${view === "now" && facs ? `<div class="sd-detail-facs">${facs}</div>` : ""}
    </div>`;
  }

  /* compact now-conditions line: weather glyph + UV + visibility */
  _wxLine() {
    const c = (this._curRef && this._curRef()) || {};
    const [wg, wl] = WMO(c.weather_code);
    const bits = [];
    if (wg) bits.push(`${wg} ${wl}`);
    if (c.uv_index != null) bits.push(`UV ${Math.round(c.uv_index)}`);
    if (c.visibility_m != null) bits.push(`${(c.visibility_m / 1000).toFixed(c.visibility_m < 10000 ? 1 : 0)}km vis`);
    return bits.length ? `<div class="sd-detail-wx">${bits.join(" · ")}</div>` : "";
  }

  /* ---- shared chrome: spot tabs ---- */
  _tabs(spots, active, view) {
    if (spots.length < 2) return "";
    return `<div class="sd-tabs">${spots.map((x, i) => {
      const scores = (x.sports || []).map((y) => view === "week" ? (this._peak(y)?.score ?? 0) : (y.now?.score ?? 0));
      const v = scores.length ? Math.max(...scores) : 0;
      return `<div class="sd-tab ${i === active ? "on" : ""}" data-act="spot" data-i="${i}">
        <div class="tn"><span class="tdot"></span>${x.name}</div>
        <div class="tw"><span>${x.water_type || ""}</span><b>${Math.round(v)}</b></div></div>`;
    }).join("")}</div>`;
  }

  _empty() { return `<div class="muted">No Swelligence sensors found. Add spots in the integration options.</div>`; }

  static getConfigElement() { return document.createElement("swelligence-card-editor"); }
  static getStubConfig(hass) {
    // Default the spot-detail stub to the first configured spot, if any.
    let spot;
    for (const id in (hass && hass.states) || {}) {
      if (id.startsWith("sensor.swelligence_") && id.endsWith("_suitability")) {
        spot = hass.states[id].attributes?.spot; if (spot) break;
      }
    }
    return spot ? { mode: "spot", spot } : { mode: "podium", title: "Conditions" };
  }
}

/* ---------- visual editor (ha-form) ---------- */
class SwelligenceCardEditor extends HTMLElement {
  setConfig(config) { this._config = { mode: "podium", ...config }; this._update(); }
  set hass(hass) { this._hass = hass; this._update(); }
  connectedCallback() { this._update(); }

  _opts() {
    const spots = new Set(), sports = new Set();
    const st = (this._hass && this._hass.states) || {};
    for (const id in st) {
      if (!id.startsWith("sensor.swelligence_") || !id.endsWith("_suitability")) continue;
      const a = st[id].attributes || {};
      if (a.spot) spots.add(a.spot);
      if (a.sport) sports.add(a.sport);
    }
    return {
      spots: [...spots].map((s) => ({ value: s, label: s })),
      sports: this._sortKeys([...sports]).map((s) => ({ value: s, label: LABELS[s] || s })),
    };
  }
  _sortKeys(list) { return list.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b)); }

  _schema() {
    const o = this._opts();
    const base = [
      { name: "title", selector: { text: {} } },
      { name: "mode", required: true, selector: { select: { mode: "dropdown", options: [
        { value: "spot", label: "Spot detail — now/week (multi-spot tabs)" },
        { value: "podium", label: "Podium — top 3 per day" },
        { value: "timeline", label: "Opportunity timeline (7 days)" },
        { value: "heatgrid", label: "Heat-grid — now" },
        { value: "medallions", label: "Medallions — now" },
      ] } } },
    ];
    if (this._config.mode === "spot") {
      base.push(
        { name: "spot", selector: { select: { mode: "dropdown", options: o.spots } } },
        { name: "default_view", selector: { select: { mode: "dropdown", options: [
          { value: "now", label: "Now" }, { value: "week", label: "Week" } ] } } },
        { name: "show_tide", selector: { boolean: {} } },
        { name: "show_factors", selector: { boolean: {} } },
        { name: "sports", selector: { select: { multiple: true, options: o.sports } } },
      );
      return base;
    }
    base.push(
      { name: "days", selector: { number: { min: 1, max: 7, mode: "slider", step: 1 } } },
      { name: "show_score", selector: { boolean: {} } },
      { name: "spots", selector: { select: { multiple: true, options: o.spots } } },
      { name: "sports", selector: { select: { multiple: true, options: o.sports } } },
    );
    return base;
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._style) {
      this._style = document.createElement("style");
      this._style.textContent = EDITOR_CSS;
      this.appendChild(this._style);
    }
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => ({
        title: "Title", mode: "Mode", days: "Days to show (forecast modes)",
        show_score: "Show score number (rings)",
        spot: "Initial spot (spot-detail — switch via tabs)",
        default_view: "Default view (spot-detail)",
        show_tide: "Show tide module",
        show_factors: "Show factor breakdown (Now)",
        spots: "Spots (filter — leave empty for all)",
        sports: "Sports (filter — leave empty for all)",
      }[s.name] || s.name);
      this._form.addEventListener("value-changed", (e) => {
        e.stopPropagation();
        this._emit(e.detail.value);
      });
      this.appendChild(this._form);
    }
    if (!this._prio) {
      this._prio = document.createElement("div");
      this._prio.className = "spr";
      this.appendChild(this._prio);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { show_score: true, ...this._config };
    this._renderPriority();
  }

  _emit(patch) {
    this._config = { ...this._config, ...patch };
    this.dispatchEvent(new CustomEvent("config-changed",
      { detail: { config: this._config }, bubbles: true, composed: true }));
  }

  /* sport-priority drag editor — the integration no longer stores this. */
  _sportUniverse() {
    const found = this._opts().sports.map((o) => o.value);
    const base = found.length ? found : ORDER.slice();
    // Keep any saved-priority sports even if no sensor for them exists right now.
    const extra = (this._config.priority || []).filter((s) => !base.includes(s));
    return [...base, ...extra];
  }
  _priorityOrder() {
    const universe = this._sportUniverse();
    const pri = (this._config.priority || []).filter((s) => universe.includes(s));
    return [...pri, ...universe.filter((s) => !pri.includes(s))];
  }
  _renderPriority() {
    const rows = this._priorityOrder().map((s, i) =>
      `<div class="spr-row" draggable="true" data-sport="${s}">`
      + `<span class="spr-hnd">⠿</span>`
      + `<span class="spr-lbl">${LABELS[s] || s}</span>`
      + `<span class="spr-rk">${i + 1}</span></div>`).join("");
    this._prio.innerHTML =
      `<div class="spr-ttl">Sport priority</div>`
      + `<div class="spr-sub">Drag to reorder — most-wanted first. Nudges the podium and ranked views when scores are close; never hides anything.</div>`
      + `<div class="spr-list">${rows}</div>`;
    this._wireDrag();
  }
  _wireDrag() {
    const list = this._prio.querySelector(".spr-list");
    let drag = null;
    list.querySelectorAll(".spr-row").forEach((row) => {
      row.addEventListener("dragstart", (e) => {
        drag = row; row.classList.add("drag");
        e.dataTransfer.effectAllowed = "move";
      });
      row.addEventListener("dragend", () => { row.classList.remove("drag"); drag = null; });
      row.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (!drag || drag === row) return;
        const r = row.getBoundingClientRect();
        list.insertBefore(drag, (e.clientY - r.top) > r.height / 2 ? row.nextSibling : row);
      });
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        const order = [...list.querySelectorAll(".spr-row")].map((x) => x.dataset.sport);
        this._emit({ priority: order });
      });
    });
  }
}

const CSS = `
:host{--c-line:var(--divider-color,#444);--c-ink:var(--primary-text-color,#eee);--c-dim:var(--secondary-text-color,#999);--c-track:var(--divider-color,#333);}
ha-card{padding:14px 16px 16px;overflow-x:auto;}
.title{font-size:1.25rem;font-weight:600;margin:0 0 12px;color:var(--c-ink);}
.muted{color:var(--c-dim);font-size:.9rem;padding:6px 0;}
svg.icon{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;}
svg.icon.sm{width:14px;height:14px;} svg.icon.xs{width:13px;height:13px;}
/* heatgrid */
table.grid{border-collapse:separate;border-spacing:6px;width:100%;}
.grid th{color:var(--c-dim);font-weight:500;} .grid th .icon{color:var(--c-dim);} .grid th .cl{font-size:9.5px;margin-top:1px;}
.grid td.sp{font-weight:600;font-size:13px;color:var(--c-ink);text-align:left;white-space:nowrap;padding-right:4px;}
.grid td.na{color:var(--c-dim);opacity:.4;}
.hc{border-radius:10px;height:46px;min-width:50px;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;}
.hc .gho{position:absolute;left:5px;top:5px;width:15px;height:15px;opacity:.34;}
.hc .sc{font-weight:800;font-size:16px;line-height:1;} .hc .k{font-size:9px;opacity:.85;}
/* medallions */
.mcards{display:flex;flex-direction:column;gap:12px;}
.mcard{border:1px solid var(--c-line);border-radius:12px;padding:10px 12px;}
.mh{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:10px;}
.mh .nm{font-weight:600;font-size:14px;color:var(--c-ink);}
.mh .wt{font-size:10.5px;color:var(--c-dim);text-transform:uppercase;letter-spacing:.05em;}
.meds{display:flex;gap:16px;flex-wrap:wrap;}
.med{text-align:center;width:62px;}
.ring{width:56px;height:56px;border-radius:50%;margin:0 auto 5px;position:relative;background:conic-gradient(var(--c) calc(var(--p)*1%),var(--c-track) 0);}
.ring::after{content:'';position:absolute;inset:5px;border-radius:50%;background:var(--card-background-color,#1b1e25);}
.ri{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1;gap:1px;}
.ri .icon{width:26px;height:26px;color:var(--c-ink);}
.rs{font-weight:600;font-size:10px;color:var(--c-dim);line-height:1;}
.ml{font-size:11px;color:var(--c-ink);} .mk{font-size:9.5px;color:var(--c-dim);}
/* timeline */
.tl{min-width:560px;}
.tlrow{display:grid;grid-template-columns:104px repeat(7,1fr);gap:5px;align-items:center;margin-bottom:5px;}
.tlhead{margin-bottom:7px;} .tld{text-align:center;font-size:11px;color:var(--c-dim);font-weight:600;}
.tlsp{font-size:12px;color:var(--c-ink);font-weight:500;}
.tlc{position:relative;height:26px;background:var(--c-track);opacity:.95;border-radius:5px;}
.tlc{background:color-mix(in srgb,var(--c-track) 40%,transparent);}
.blk{position:absolute;top:2px;bottom:2px;border-radius:4px;display:flex;align-items:center;justify-content:center;}
/* podium */
.pod{min-width:560px;}
.prow{display:grid;grid-template-columns:26px repeat(7,1fr);gap:6px;align-items:center;margin-bottom:8px;}
.phead{margin-bottom:10px;} .pd{text-align:center;font-size:12px;font-weight:700;color:var(--c-ink);}
.pd span{display:block;font-size:9.5px;color:var(--c-dim);font-weight:400;}
.rk{font-weight:700;font-size:15px;color:var(--c-dim);text-align:center;}
.rk.r1{color:#e8c451;} .rk.r2{color:#c2c8d2;} .rk.r3{color:#cd8e5a;}
.pc{text-align:center;}
.pm{width:46px;height:46px;border-radius:50%;margin:0 auto 4px;position:relative;background:conic-gradient(var(--c) calc(var(--p)*1%),var(--c-track) 0);}
.pm.big{width:54px;height:54px;}
.pm::after{content:'';position:absolute;inset:4px;border-radius:50%;background:var(--card-background-color,#1b1e25);}
.pm.empty{background:var(--c-track);opacity:.4;} .pm.empty::after{background:var(--card-background-color,#1b1e25);}
.pi{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1;gap:1px;}
.ps{font-weight:600;font-size:10px;color:var(--c-dim);line-height:1;} .pm.big .ps{font-size:11px;}
.pi .icon{width:22px;height:22px;color:var(--c-ink);} .pm.big .pi .icon{width:26px;height:26px;}
.pl{font-size:9.5px;color:var(--c-dim);}
/* ---------- spot detail (720-panel layout, theme-aware) ---------- */
.sd{--ac:var(--primary-color,#03a9f4);--ink:var(--primary-text-color,#eaf2f6);--mut:var(--secondary-text-color,#8ba4b3);
  --dim:color-mix(in srgb,var(--secondary-text-color,#8ba4b3) 65%,transparent);
  --line:var(--divider-color,rgba(150,178,198,.18));--line2:color-mix(in srgb,var(--secondary-text-color,#8ba4b3) 35%,transparent);
  --panel:color-mix(in srgb,var(--primary-text-color,#fff) 4%,transparent);
  --panel2:color-mix(in srgb,var(--primary-text-color,#fff) 6%,transparent);
  --raise:color-mix(in srgb,var(--primary-text-color,#fff) 9%,transparent);
  container-type:inline-size;display:flex;flex-direction:column;gap:12px;font-variant-numeric:tabular-nums;}
/* header */
.sd-hdr{display:flex;align-items:center;justify-content:space-between;gap:12px;}
.sd-id{display:flex;align-items:center;gap:10px;min-width:0;}
.sd-logo{width:38px;height:38px;border-radius:10px;flex:0 0 auto;display:grid;place-items:center;font-weight:800;font-size:18px;color:#04201c;background:radial-gradient(circle at 35% 30%,var(--ac),color-mix(in srgb,var(--ac) 55%,#000));}
.sd-nm{font-size:20px;font-weight:800;color:var(--ink);line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sd-sub{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin-top:3px;}
.sd-sub b{color:var(--ac);}
.sd-ctrl{display:flex;align-items:center;gap:11px;flex:0 0 auto;}
.sd-seg{display:flex;border:1px solid var(--line2);border-radius:10px;overflow:hidden;}
.sd-seg button{font:inherit;cursor:pointer;border:0;background:transparent;color:var(--mut);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;padding:8px 14px;}
.sd-seg button.on{background:var(--ac);color:#04201c;}
.sd-now{display:flex;align-items:center;gap:8px;text-align:right;}
.sd-now b{display:block;font-size:17px;font-weight:800;color:var(--ink);line-height:1;}
.sd-now span{font-size:9px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--ac);}
.sd-now .pulse{width:8px;height:8px;border-radius:50%;background:var(--ac);animation:sdpulse 2.4s infinite;}
.sd-now .pulse.off{background:var(--mut);animation:none;}
@keyframes sdpulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--ac) 50%,transparent)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
/* main split */
.sd-main{display:grid;grid-template-columns:minmax(0,290px) minmax(0,1fr);gap:12px;align-items:start;}
.sd-col{min-width:0;display:flex;flex-direction:column;gap:11px;}
/* ===== Card A NOW layout (single-column scrubber) ===== */
.sd-cardA{gap:10px;}
.sd-cardA .sd-meds{margin:0;}
.sc-hero{display:grid;grid-template-columns:minmax(200px,240px) minmax(0,1fr);gap:10px;}
.sc-hero{align-items:stretch;}
.sc-hero .sd-map{height:200px;min-height:0;}
.sc-readcol{min-width:0;display:flex;flex-direction:column;gap:8px;}
/* readout = 50% of the 200px map; no headings, just the three gauges */
.sc-read{flex:0 0 100px;display:grid;grid-template-columns:repeat(3,1fr);background:var(--panel2);border:1px solid var(--line);border-radius:14px;overflow:hidden;}
.sc-cell{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;padding:6px;min-width:0;}
.sc-cell + .sc-cell{border-left:1px solid var(--line);}
/* shared gauge caption (verdict / kit power / safety state) */
.sc-cell .gcap{font-size:9.5px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;line-height:1;}
.sc-cell .ro-ring{width:60px;height:60px;}
/* metric pills: full raw-conditions readout (scrubs with the timeline) */
/* icon-led metric pills: icon (the label) + value-hero + subdued unit */
.sc-pills{flex:1 1 auto;display:grid;grid-template-columns:repeat(5,1fr);grid-auto-rows:1fr;gap:5px;}
.sc-pills .mp{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:6px 9px;min-width:0;display:flex;align-items:center;gap:7px;}
.sc-pills .mp-ic{width:16px;height:16px;flex:0 0 auto;color:var(--mut);fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}
.sc-pills .mp.amber .mp-ic{color:#f6a623;}
.sc-pills .mp-v{font-size:13.5px;font-weight:800;color:var(--ink);line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;}
.sc-pills .mp.amber .mp-v{color:#f6a623;}
.sc-pills .mp-v small{font-size:8.5px;font-weight:600;color:var(--mut);margin-left:2px;}
/* outlook */
.chartwrap{display:flex;flex-direction:column;gap:7px;background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:10px 12px 8px;}
.chartwrap .ch-h{display:flex;align-items:baseline;justify-content:space-between;}
.chartwrap .ch-h .k{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--mut);}
.chartwrap .ch-h .hint{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ac);display:flex;align-items:baseline;gap:6px;}
.chartwrap .ch-h .hint b{color:var(--ink);font-weight:800;font-size:14px;letter-spacing:0;}
.chartwrap .chart{display:flex;flex-direction:column;gap:6px;}
.daylane{flex:0 0 46px;height:46px;position:relative;border-radius:8px;overflow:hidden;border:1px solid var(--line);background:linear-gradient(180deg,rgba(86,194,224,.18),rgba(9,18,34,.5));}
.daylane.plain{background:var(--panel);}
.daylane .dl-lbl{position:absolute;left:9px;top:50%;transform:translateY(-50%);z-index:2;font-size:9px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.85);pointer-events:none;text-shadow:0 1px 3px rgba(0,0,0,.85);}
.daylane .dl-t{position:absolute;bottom:4px;z-index:2;transform:translateX(-50%);font-size:8px;font-weight:700;color:rgba(255,255,255,.85);pointer-events:none;white-space:nowrap;text-shadow:0 1px 2px rgba(0,0,0,.7);}
.daylane .sky{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1;}
.daylane .sky-horizon{stroke:rgba(255,255,255,.2);stroke-width:1;stroke-dasharray:3 4;vector-effect:non-scaling-stroke;}
.daylane .sky-line{fill:none;stroke:rgba(255,233,180,.85);stroke-width:1.6;stroke-linejoin:round;vector-effect:non-scaling-stroke;}
.daylane .sky-tick{stroke:rgba(255,255,255,.26);stroke-width:1;vector-effect:non-scaling-stroke;}
.daylane .sunmark{position:absolute;transform:translate(-50%,-50%);font-size:13px;line-height:1;pointer-events:none;color:#ffe08a;z-index:3;filter:drop-shadow(0 0 4px rgba(255,210,120,.9));}
.daylane .sunmark.night{color:#cdd7ea;filter:drop-shadow(0 0 4px rgba(170,200,240,.7));}
.chartwrap .barwrap{flex:1 1 auto;min-height:120px;position:relative;border-radius:8px;background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--mut) 8%,transparent));}
.chartwrap .bars{position:absolute;inset:0;display:flex;align-items:flex-end;gap:2px;touch-action:none;}
.chartwrap .bar{flex:1;border:0;padding:0;border-radius:3px 3px 0 0;min-height:4px;align-self:flex-end;opacity:.6;cursor:pointer;transition:opacity .1s;position:relative;}
.chartwrap .bar.now{outline:1.5px solid var(--ink);outline-offset:1px;}
.chartwrap .bar.sel{opacity:1;outline:2px solid var(--ink);outline-offset:1px;}
.chartwrap .bar.best::before{content:"★";position:absolute;top:-13px;left:50%;transform:translateX(-50%);font-size:10px;color:#f6a623;}
.chartwrap .axis{display:flex;padding:0 2px;} .chartwrap .axis span{flex:1;text-align:center;font-size:9px;font-weight:700;color:var(--dim);}
/* map hero */
.sd-map{position:relative;height:200px;border-radius:14px;overflow:hidden;border:1px solid var(--line);background:var(--panel2);}
.sd-map .lmap{position:absolute;inset:0;overflow:hidden;}
.sd-map .mos{position:absolute;left:50%;top:50%;width:768px;height:768px;}
.sd-map .mos img{position:absolute;width:256px;height:256px;display:block;}
.sd-map .lmap.dark .mos{filter:invert(1) hue-rotate(180deg) brightness(.85) contrast(.95) saturate(.7);}
.sd-map .pin{position:absolute;left:50%;top:50%;width:26px;height:26px;transform:translate(-50%,-100%);fill:var(--ac);stroke:var(--card-background-color,#0d151d);stroke-width:1.2;z-index:2;filter:drop-shadow(0 2px 4px rgba(0,0,0,.6));}
.sd-map .pin circle{fill:var(--card-background-color,#0d151d);stroke:none;}
.sd-map .vign{position:absolute;inset:0;z-index:1;pointer-events:none;box-shadow:inset 0 0 46px 6px rgba(0,0,0,.45);}
.sd-map .wband{position:absolute;left:0;right:0;bottom:0;z-index:3;pointer-events:none;padding:18px 12px 8px;display:flex;align-items:flex-end;justify-content:space-between;gap:8px;background:linear-gradient(0deg,rgba(0,0,0,.72),transparent);}
.sd-map .wband .wfrom{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:#fff;}
.sd-map .wband .wfrom span{color:var(--ac);}
.sd-map .wband .wxy{font-size:10px;color:rgba(255,255,255,.82);}
.sd-map .osm{position:absolute;right:3px;top:3px;z-index:3;font-size:8px;color:var(--mut);background:color-mix(in srgb,var(--card-background-color,#000) 55%,transparent);padding:1px 4px;border-radius:4px;text-decoration:none;}
.sd-nomap{position:absolute;inset:0;display:grid;place-items:center;color:var(--dim);font-size:12px;}
.sd-map .sd-windc{position:absolute;left:50%;top:46%;width:88px;height:88px;transform:translate(-50%,-50%);z-index:3;pointer-events:none;}
.sd-windc-dial{fill:rgba(0,0,0,.32);stroke:rgba(255,255,255,.22);stroke-width:1.5;}
.sd-windc-n{fill:var(--mut);font-size:10px;text-anchor:middle;font-family:inherit;}
/* tide module */
.sd-tidep{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column;min-height:150px;}
.sd-tidep .th{display:flex;align-items:center;justify-content:space-between;}
.sd-tidep .th .k{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--mut);}
.sd-tidep .th .model{font-size:8.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:2px 6px;}
.sd-tidep .state{display:flex;align-items:baseline;gap:9px;margin-top:7px;}
.sd-tidep .state .arrow,.sd-tidep .state .word{font-size:22px;font-weight:800;color:var(--ink);}
.sd-tidep.t-rising .arrow,.sd-tidep.t-rising .word{color:#39bdf8;}
.sd-tidep.t-falling .arrow,.sd-tidep.t-falling .word{color:#f6a623;}
.sd-tidep .nxt{font-size:12px;color:var(--mut);margin-top:5px;} .sd-tidep .nxt b{color:var(--ink);font-weight:800;} .sd-tidep .nxt .dim{color:var(--dim);}
.sd-tidep .curve{flex:1;min-height:54px;margin-top:8px;position:relative;}
.sd-tidep .curve svg{position:absolute;inset:0;width:100%;height:100%;}
.sd-tidep .cpath{fill:none;stroke:var(--ac);stroke-width:2;stroke-linejoin:round;}
.sd-tidep .cfill{fill:color-mix(in srgb,var(--ac) 12%,transparent);}
.sd-tidep .cnow{stroke:var(--ink);stroke-width:1.4;stroke-dasharray:3 3;opacity:.6;}
.sd-tidep .cdot{fill:#f6a623;} .sd-tidep .cnowdot{fill:var(--ink);}
.sd-tidep .clab{fill:var(--dim);font:700 9px sans-serif;}
/* daylight arc panel */
.sd-day{background:var(--panel,#0f1519);border:1px solid var(--line,#283036);border-radius:12px;padding:11px 12px;display:flex;align-items:center;gap:12px;}
.sd-day-svg{width:104px;height:50px;flex:0 0 auto;}
.sd-day-track{fill:none;stroke:color-mix(in srgb,var(--mut) 25%,transparent);stroke-width:3;}
.sd-day-arc{fill:none;stroke:#4ab6ff;stroke-width:3;}
.sd-day-sun{fill:var(--ac);}
.sd-day-meta{display:flex;flex-direction:column;}
.sd-day-meta .k{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);font-weight:700;}
.sd-day-meta b{font-size:15px;font-weight:800;color:var(--ink);}
.sd-day-meta .s{font-size:10px;color:var(--mut);}
/* sports column */
.sd-sportcol{min-width:0;display:flex;flex-direction:column;gap:11px;}
/* medallion ring-row sport selector */
/* equal-width chips, centred; the active one tints rather than resizing */
.sd-meds{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;}
.sd-med{flex:1 1 0;min-width:84px;max-width:140px;display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;padding:5px 2px;border-radius:12px;border:1px solid transparent;transition:background .15s;}
.sd-med.on{border-color:color-mix(in srgb,var(--ac) 38%,transparent);background:color-mix(in srgb,var(--ac) 9%,transparent);}
.sd-medr{position:relative;width:58px;height:58px;display:grid;place-items:center;}
.sd-medr .sd-ring-svg{position:absolute;inset:0;width:100%;height:100%;}
.sd-medi{display:grid;place-items:center;z-index:2;}
.sd-medi .icon{width:13px;height:13px;color:var(--mut);}
.sd-med.on .sd-medi .icon{color:var(--ink);}
.sd-meds-n{font-weight:800;font-size:15px;line-height:1;}
.sd-medl{font-size:10px;font-weight:600;color:var(--mut);}
.sd-med.on .sd-medl{color:var(--ink);}
/* ring svg base (used by _ring()) */
.sd-ring-svg{width:80px;height:80px;transform:rotate(-90deg);}
.sd-ring-svg .gt{fill:none;stroke:color-mix(in srgb,var(--mut) 26%,transparent);}
.sd-ring-svg .ga{fill:none;stroke-linecap:round;}
/* detail card */
.sd-detail{background:var(--panel,#0f1519);border:1px solid var(--line,#283036);border-radius:12px;padding:12px;}
.sd-detail-top{display:flex;align-items:center;justify-content:space-between;gap:10px;}
.sd-detail-sp{font-size:15px;font-weight:800;color:var(--ink);}
.sd-detail-vd{font-weight:700;margin:2px 0 6px;}
.sd-detail-best{font-size:11px;color:var(--mut);} .sd-detail-best b{color:var(--ink);}
.sd-detail-warn{font-size:10.5px;color:#f6a623;font-weight:700;margin:2px 0 4px;}
/* NOW readout row: suitability ring · kit arc · safety cell */
.sd-readout{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:9px 8px;}
.sd-readout .ro-cell{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:5px;min-width:0;}
.sd-readout .ro-cell + .ro-cell{border-left:1px solid var(--line);}
.ro-k{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);}
.ro-ring{position:relative;width:62px;height:62px;}
.ro-ring .sd-ring-svg{width:100%;height:100%;}
.ro-num{position:absolute;inset:0;display:grid;place-items:center;font-size:20px;font-weight:800;}
.ro-na{font-size:13px;font-weight:800;color:var(--mut);height:62px;display:grid;place-items:center;}
/* safety as a single readout gauge — icon sized to match the ring/kit + caption */
.sd-safety{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;width:100%;}
.sd-safety .sf-grid{width:60px;height:60px;display:grid;place-items:center;}
.sd-safety .sf-ic{width:44px;height:44px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;}
.sd-safety.ok{color:#5cb85c;} .sd-safety.caution{color:#f6a623;} .sd-safety.danger{color:#e8593a;}
.sd-safety.danger .sf-ic{filter:drop-shadow(0 0 4px rgba(232,89,58,.45));}
.sd-kit{display:flex;flex-direction:column;align-items:center;flex:0 0 auto;}
.sd-kit-svg{width:92px;height:58px;}
.sd-kit-track{fill:none;stroke:color-mix(in srgb,var(--mut) 25%,transparent);stroke-width:9;stroke-linecap:round;}
.sd-kit-needle{stroke:var(--ink);stroke-width:2.5;stroke-linecap:round;}
.sd-kit-hub{fill:var(--ink);}
.sd-kit-n{font-weight:800;font-size:14px;line-height:1;}
.sd-kit-c{font-size:8px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:700;}
.sd-detail-lf{display:flex;align-items:center;gap:7px;margin-top:10px;padding-top:10px;border-top:1px solid var(--line,#283036);font-size:11px;color:var(--ink);}
.sd-detail-lf .dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;}
.sd-detail-facs{margin-top:9px;}
/* hourly timeline */
.sd-tl{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:10px 12px 8px;}
.sd-tl .tlh{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}
.sd-tl .tlh .k{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--mut);}
.sd-tl .tlh .span{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:2px 7px;}
.sd-tl .bars{display:flex;align-items:flex-end;gap:2px;height:74px;}
.sd-tl .b{flex:1;position:relative;border-radius:3px 3px 0 0;min-height:3px;align-self:flex-end;cursor:pointer;opacity:.62;transition:opacity .1s;}
.sd-tl .bars{touch-action:none;}
.sd-tl .b.now{outline:1.5px solid var(--ink);outline-offset:1px;}
.sd-tl .b.sel{opacity:1;outline:2px solid var(--ink);outline-offset:1px;}
.sd-tl .b.best::before{content:"★";position:absolute;top:-13px;left:50%;transform:translateX(-50%);font-size:10px;color:#f6a623;}
.sd-tl .axis{display:flex;margin-top:6px;} .sd-tl .axis .x{flex:1;text-align:center;font-size:9px;font-weight:600;color:var(--dim);}
.sd-tl .none,.sd-drows .none{height:74px;display:grid;place-items:center;color:var(--dim);font-size:12px;}
/* now strip + factors */
.sd-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;}
.ns{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:7px 9px;}
.ns .k{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);}
.ns .v{font-size:17px;font-weight:800;color:var(--ink);margin-top:2px;} .ns .v small{font-size:10px;font-weight:600;color:var(--mut);}
.ns.amber .v{color:#f6a623;}
.sd-facs{display:grid;gap:6px;}
.sd-fac{display:grid;grid-template-columns:64px 1fr 28px;align-items:center;gap:8px;font-size:10.5px;}
.sd-fac .fl{color:var(--mut);text-transform:capitalize;font-weight:600;}
.sd-fac .fb{height:6px;border-radius:4px;background:color-mix(in srgb,var(--mut) 18%,transparent);overflow:hidden;}
.sd-fac .fb i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,color-mix(in srgb,var(--ac) 55%,#000),var(--ac));}
.sd-fac .fn{text-align:right;color:var(--mut);font-weight:700;}
/* week summary */
.sd-wsum{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:13px 14px;display:flex;flex-direction:column;gap:10px;}
.sd-wsum .k{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--mut);}
.sd-wsum .bigday{display:flex;align-items:baseline;gap:10px;} .sd-wsum .bigday .dn{font-size:24px;font-weight:800;} .sd-wsum .bigday .ds{font-size:24px;font-weight:800;color:var(--ink);} .sd-wsum .bigday .dv{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-left:auto;}
.sd-wsum .psub{font-size:11px;font-weight:600;color:var(--mut);} .sd-wsum .psub b{color:var(--ink);font-weight:800;}
.sd-wsum .wgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:auto;}
.sd-wsum .st{background:var(--raise);border:1px solid var(--line);border-radius:11px;padding:9px 11px;position:relative;overflow:hidden;}
.sd-wsum .st::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--ac);opacity:.5;}
.sd-wsum .st.amber::before{background:#f6a623;} .sd-wsum .st.t-rising::before{background:#39bdf8;} .sd-wsum .st.t-falling::before{background:#f6a623;}
.sd-wsum .st .sk{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);}
.sd-wsum .st .sv{font-size:20px;font-weight:800;color:var(--ink);margin-top:3px;} .sd-wsum .st.amber .sv{color:#f6a623;} .sd-wsum .st .sv small{font-size:10px;font-weight:600;color:var(--mut);}
/* day rows */
.sd-drows{display:flex;flex-direction:column;gap:6px;}
.sd-drow{display:grid;grid-template-columns:52px 1fr 46px 40px;align-items:center;gap:10px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:8px 12px;}
.sd-drow.best{border-color:color-mix(in srgb,var(--ac) 50%,transparent);}
.sd-drow .dd{font-size:12.5px;font-weight:800;color:var(--ink);} .sd-drow.today .dd{color:var(--ac);}
.sd-drow .dbar{height:8px;border-radius:5px;background:color-mix(in srgb,var(--mut) 18%,transparent);overflow:hidden;} .sd-drow .dbar i{display:block;height:100%;border-radius:5px;}
.sd-drow .dt{font-size:10.5px;color:var(--mut);text-align:right;}
.sd-drow .dsc{font-size:16px;font-weight:800;text-align:right;} .sd-drow .dsc .star{color:#f6a623;font-size:10px;}
/* bottom spot tabs */
.sd-tabs{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:10px;}
.sd-tab{cursor:pointer;border-radius:13px;padding:10px 13px;display:flex;flex-direction:column;gap:4px;background:var(--panel2);border:1px solid var(--line);}
.sd-tab.on{border-color:var(--ac);background:color-mix(in srgb,var(--ac) 12%,transparent);box-shadow:0 0 0 1px color-mix(in srgb,var(--ac) 32%,transparent);}
.sd-tab .tn{font-size:15px;font-weight:800;color:var(--ink);display:flex;align-items:center;gap:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sd-tab .tdot{width:8px;height:8px;border-radius:50%;background:var(--mut);flex:0 0 auto;} .sd-tab.on .tdot{background:var(--ac);box-shadow:0 0 8px var(--ac);}
.sd-tab .tw{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);display:flex;justify-content:space-between;gap:8px;} .sd-tab .tw b{font-size:13px;font-weight:800;color:var(--ink);}
/* responsive: stack columns when the card is narrow */
@container (max-width:540px){
  .sd-main{grid-template-columns:1fr;}
  .sd-strip{grid-template-columns:repeat(2,1fr);}
  .sd-tabs{grid-auto-flow:row;grid-auto-columns:auto;}
}
`;

/* visual-editor priority list (light DOM — class-scoped with spr-) */
const EDITOR_CSS = `
.spr{margin-top:18px;}
.spr-ttl{font-size:.95rem;font-weight:600;color:var(--primary-text-color,#eee);}
.spr-sub{font-size:.78rem;color:var(--secondary-text-color,#999);margin:2px 0 8px;}
.spr-list{display:flex;flex-direction:column;gap:5px;}
.spr-row{display:flex;align-items:center;gap:10px;padding:9px 11px;border:1px solid var(--divider-color,#444);border-radius:9px;background:var(--card-background-color,#1b1e25);cursor:grab;user-select:none;}
.spr-row.drag{opacity:.5;border-style:dashed;}
.spr-hnd{color:var(--secondary-text-color,#999);font-size:15px;line-height:1;cursor:grab;}
.spr-lbl{flex:1;font-size:.9rem;color:var(--primary-text-color,#eee);}
.spr-rk{font-size:.8rem;font-weight:700;color:var(--secondary-text-color,#999);min-width:1.2em;text-align:center;}
`;

// Guarded so a stale manual `/local/…` resource loading alongside the bundled
// copy can't crash with "already defined" during migration.
if (!customElements.get("swelligence-card")) customElements.define("swelligence-card", SwelligenceCard);
if (!customElements.get("swelligence-card-editor")) customElements.define("swelligence-card-editor", SwelligenceCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "swelligence-card",
  name: "Swelligence Card",
  description: "Conditions: spot detail (now/week), podium, opportunity timeline, heat-grid, or medallions.",
  preview: true,
  documentationURL: "https://git.bagofholding.co.uk/foolycooly/swelligence",
});
console.info("%c SWELLIGENCE-CARD ", "background:#1f9d57;color:#fff", "v14 loaded (bundled with integration)");
