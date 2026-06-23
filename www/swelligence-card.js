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

const ICON_DEFS = `
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
<symbol id="i-windsurf" viewBox="0 0 24 24"><path d="M3 19.5 Q12 22.5 21 19.5"/><path d="M12 19 L12 3.5"/><path d="M12 4 Q20 9.5 12 15"/><path d="M12 9.5 L17.5 9"/></symbol>
<symbol id="i-wing" viewBox="0 0 24 24"><path d="M3.5 8 Q12 2.5 20.5 8 Q12 10.5 3.5 8 Z"/><path d="M12 10.5 L12 16"/><path d="M7.5 17.5 Q12 15.5 16.5 17.5"/></symbol>
<symbol id="i-surf" viewBox="0 0 24 24"><path d="M2 17 C6 17 6 9 11 9 C15.5 9 14 15 19.5 14"/><path d="M11 9 C13.5 7.8 14.6 10 12.4 11.6"/><path d="M13.5 20 L20 13.5"/></symbol>
<symbol id="i-sup" viewBox="0 0 24 24"><path d="M3 18 Q12 21 21 18"/><path d="M3 18 Q12 15.6 21 18"/><path d="M14.5 3.5 L9 17"/><path d="M13 3.5 H16"/><path d="M7.5 16 L9 19 L10.7 16 Z"/></symbol>
<symbol id="i-sail" viewBox="0 0 24 24"><path d="M4 18 L20 18 L17.5 21 H6.5 Z"/><path d="M12 18 L12 3.5"/><path d="M12.8 5 L18.5 16 H12.8 Z"/><path d="M11.2 6.5 L6 16 H11.2 Z"/></symbol>
<symbol id="i-swim" viewBox="0 0 24 24"><circle cx="8" cy="8.5" r="2"/><path d="M9.6 10 Q14 8.4 17.5 11.5"/><path d="M9.6 10 Q11.5 5.5 15 7.5"/><path d="M2 18 q2.6 -2 5.2 0 t5.2 0 t5.2 0"/></symbol>
<symbol id="i-wake" viewBox="0 0 24 24"><path d="M2 18.5 q3 -1.6 6 0 t6 0 t6 0"/><path d="M5.5 16.8 L13 13.2"/><path d="M8 16.2 L8.6 14.8"/><path d="M11 15 L11.6 13.6"/><path d="M18.5 6 H21.5"/><path d="M20 6.6 L13.5 12.6"/></symbol>`;

const ICON = (sport, cls = "") =>
  `<svg class="icon ${cls}"><use href="#${SYM[sport] || "i-kite"}"/></svg>`;

class SwelligenceCard extends HTMLElement {
  setConfig(config) {
    this._config = { mode: "podium", ...config };
    this._ov = null;
    this._loading = false;
  }
  getCardSize() { return this._config.mode === "podium" ? 7 : 5; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._root) this._init();
    if (first || this._needsOverview()) this._loadOverview();
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
    // periodic refresh of forecast data
    this._timer = setInterval(() => this._loadOverview(), 300000);
  }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

  async _loadOverview() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const data = {};
      if (this._config.spots) data.spots = this._config.spots;
      if (this._config.sports) data.sports = this._config.sports;
      const r = await this._hass.callService("swelligence", "get_overview", data, undefined, false, true);
      this._ov = (r && r.response) || null;
    } catch (e) { /* keep stale */ }
    this._loading = false;
    this._render();
  }

  _showScore() { return this._config.show_score !== false; }

  _priority() {
    return (this._ov && this._ov.sport_priority && this._ov.sport_priority.length)
      ? this._ov.sport_priority : ORDER;
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
    html += { heatgrid: () => this._heatgrid(), medallions: () => this._medallions(),
      timeline: () => this._timeline(), podium: () => this._podium() }[m]?.() ||
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

  /* ---------- NOW: medallions ---------- */
  _medallions() {
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

  _empty() { return `<div class="muted">No Swelligence sensors found. Add spots in the integration options.</div>`; }

  static getConfigElement() { return document.createElement("swelligence-card-editor"); }
  static getStubConfig() { return { mode: "podium", title: "Conditions" }; }
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
    return [
      { name: "title", selector: { text: {} } },
      { name: "mode", required: true, selector: { select: { mode: "dropdown", options: [
        { value: "podium", label: "Podium — top 3 per day" },
        { value: "timeline", label: "Opportunity timeline (7 days)" },
        { value: "heatgrid", label: "Heat-grid — now" },
        { value: "medallions", label: "Medallions — now" },
      ] } } },
      { name: "days", selector: { number: { min: 1, max: 7, mode: "slider", step: 1 } } },
      { name: "show_score", selector: { boolean: {} } },
      { name: "spots", selector: { select: { multiple: true, options: o.spots } } },
      { name: "sports", selector: { select: { multiple: true, options: o.sports } } },
    ];
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => ({
        title: "Title", mode: "Mode", days: "Days to show (forecast modes)",
        show_score: "Show score number (rings)",
        spots: "Spots (filter — leave empty for all)",
        sports: "Sports (filter — leave empty for all)",
      }[s.name] || s.name);
      this._form.addEventListener("value-changed", (e) => {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent("config-changed",
          { detail: { config: e.detail.value }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { show_score: true, ...this._config };
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
`;

customElements.define("swelligence-card", SwelligenceCard);
customElements.define("swelligence-card-editor", SwelligenceCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "swelligence-card",
  name: "Swelligence Card",
  description: "Conditions: podium, opportunity timeline, heat-grid, or medallions.",
  preview: true,
  documentationURL: "https://git.bagofholding.co.uk/foolycooly/swelligence",
});
console.info("%c SWELLIGENCE-CARD ", "background:#1f9d57;color:#fff", "v9 loaded (optional score)");
