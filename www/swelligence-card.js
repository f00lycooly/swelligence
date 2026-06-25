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
    this._detail = null;
    this._loading = false;
    // UI state for spot mode — preserved across hass re-renders.
    this._sv = { sport: config.sport || null, view: config.default_view || "now" };
  }
  getCardSize() { return this._config.mode === "podium" ? 7 : this._config.mode === "spot" ? 8 : 5; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._root) this._init();
    if (first || this._needsOverview()) this._loadOverview();
    if (this._config.mode === "spot" && (first || !this._detail)) this._loadDetail();
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
    // periodic refresh of forecast data
    this._timer = setInterval(() => { this._loadOverview(); this._loadDetail(); }, 300000);
  }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

  _onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    if (el.dataset.act === "view") this._sv.view = el.dataset.v;
    else if (el.dataset.act === "sport") this._sv.sport = el.dataset.s;
    else return;
    this._render();
  }

  async _loadDetail() {
    if (!this._hass || this._loadingD || this._config.mode !== "spot") return;
    this._loadingD = true;
    try {
      const data = this._config.spot ? { spots: [this._config.spot] } : {};
      const r = await this._hass.callService("swelligence", "get_spot_detail", data, undefined, false, true);
      const spots = (r && r.response && r.response.spots) || [];
      this._detail = this._config.spot
        ? (spots.find((s) => s.name === this._config.spot) || spots[0]) : spots[0];
    } catch (e) { /* keep stale */ }
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
    html += { heatgrid: () => this._heatgrid(), medallions: () => this._medallions(),
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

  /* ---------- SPOT: single-spot now/week detail ---------- */
  _spot() {
    const d = this._detail;
    if (!d) return `<div class="muted">Loading spot detail…</div>`;
    const sports = (d.sports || []).filter((s) =>
      !this._config.sports || this._config.sports.includes(s.sport));
    if (!sports.length) return this._empty();
    let si = sports.findIndex((s) => s.sport === this._sv.sport);
    if (si < 0) si = 0;
    const sp = sports[si], view = this._sv.view;
    const wc = cardOf(d.current?.wind_dir_deg);
    const dl = sp.daily || [];
    const range = dl.length ? `${this._wd(dl[0].date)} – ${this._wd(dl[dl.length - 1].date)}` : "";
    const right = view === "now"
      ? `<div class="sd-now"><b>${d.now_time || "--:--"}</b><span>now</span></div>`
      : `<div class="sd-now"><b>${range || "7 days"}</b><span>7-day</span></div>`;

    let h = `<div class="sd">
      <div class="sd-hdr">
        <div class="sd-id"><div class="sd-nm">${d.name}</div>
          <div class="sd-sub">${d.water_type || ""}${wc && view === "now" ? " · wind from " + wc : ""}</div></div>
        <div class="sd-ctrl">
          <div class="sd-seg">
            <button data-act="view" data-v="now" class="${view === "now" ? "on" : ""}">Now</button>
            <button data-act="view" data-v="week" class="${view === "week" ? "on" : ""}">Week</button>
          </div>${right}
        </div>
      </div>
      <div class="sd-pills">${sports.map((s) => {
        const val = view === "week" ? this._peak(s)?.score ?? "—" : Math.round(s.now?.score ?? 0);
        return `<div class="sd-pill ${s === sp ? "on" : ""}" data-act="sport" data-s="${s.sport}">
          ${ICON(s.sport)}<span class="pn">${s.label || LABELS[s.sport] || s.sport}</span>
          <span class="pv" style="color:${vcw((view === "week" ? this._peak(s)?.verdict : s.now?.verdict) || "poor")}">${val}</span></div>`;
      }).join("")}</div>`;

    h += view === "now" ? this._spotNow(d, sp) : this._spotWeek(d, sp);
    return h + `</div>`;
  }

  _wd(date) { try { return new Date(date).toLocaleDateString(undefined, { weekday: "short" }); } catch { return date; } }
  _peak(sp) { const d = sp.daily || []; return d.length ? d.reduce((a, b) => (b.score > a.score ? b : a), d[0]) : null; }
  _gauge(score, col, lbl) {
    const s = Math.max(0, Math.min(100, Math.round(score ?? 0)));
    return `<div class="sd-ring" style="--c:${col};--p:${s}"><div class="sd-ri">
      <b style="color:${col}">${score == null ? "—" : Math.round(score)}</b><i>${lbl}</i></div></div>`;
  }
  _factors(now) {
    const order = ["wind", "gust", "direction", "wave", "swell", "temp", "tide", "kit"];
    const f = now.factors || {};
    return order.filter((k) => f[k] != null).map((k) =>
      `<div class="sd-fac"><span>${k}</span><span class="fb"><i style="width:${f[k]}%"></i></span><b>${Math.round(f[k])}</b></div>`).join("");
  }
  _compass(deg, kn, gust) {
    const calm = kn == null || deg == null, flow = deg == null ? 0 : (deg + 180) % 360;
    const op = calm ? 0 : Math.max(0.5, Math.min(1, kn / 14));
    return `<svg class="sd-rose ${calm ? "calm" : ""}" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="48" fill="none" stroke="var(--divider-color,#444)"/>
      <text class="t" x="60" y="22">N</text><text class="t" x="60" y="106">S</text>
      <text class="t" x="104" y="64">E</text><text class="t" x="16" y="64">W</text>
      <g transform="rotate(${flow} 60 60)" style="opacity:${op}"><polygon class="nd" points="60,16 67,64 60,55 53,64"/></g>
      <circle class="hub" cx="60" cy="60" r="23"/>
      ${calm ? `<text class="spd" x="60" y="65">Calm</text>`
        : `<text class="spd" x="60" y="60">${f1(kn)}</text><text class="u" x="60" y="74">kn${gust != null ? " · g" + f1(gust) : ""}</text>`}
    </svg>`;
  }
  _tide(d) {
    const t = d.tide;
    if (!t || this._config.show_tide === false) return "";
    const ar = t.state === "rising" ? "▲" : t.state === "falling" ? "▼" : "—", nx = t.next;
    let spark = "";
    if (t.levels && t.levels.length) {
      const lv = t.levels, n = lv.length, lo = t.min, hi = t.max, rng = (hi - lo) || 1, W = 130, H = 30;
      const X = (i) => i / (n - 1) * W, Y = (v) => v == null ? H / 2 : H - 3 - ((v - lo) / rng) * (H - 6);
      let dp = ""; lv.forEach((v, i) => { if (v == null) return; dp += (dp ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1) + " "; });
      spark = `<svg class="sd-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <path d="${dp}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="1.6"/>
        <line x1="${X(0)}" y1="1" x2="${X(0)}" y2="${H - 1}" stroke="var(--secondary-text-color,#999)" stroke-dasharray="2 2"/></svg>`;
    }
    return `<div class="sd-tide t-${t.state}">
      <div class="sd-th"><span>Tide</span><span class="src">${t.source || "modelled"}</span></div>
      <div class="sd-ts"><span class="ar">${ar}</span><span class="w">${cap(t.state)}</span></div>
      ${nx ? `<div class="sd-tn">next <b>${nx.type}</b> ${nx.time}${nx.level != null ? ` · ${f1(nx.level, 2)}m` : ""}</div>` : ""}
      ${spark}</div>`;
  }

  _spotNow(d, sp) {
    const c = d.current || {}, now = sp.now || {}, col = vcw(now.verdict);
    const best = sp.best, bestT = best?.time || (best?.in_hours != null ? "+" + best.in_hours + "h" : "—");
    const ser = sp.hourly || [];
    const bars = ser.slice(0, 24).map((p, i) => {
      const sc = Math.max(4, Math.round(p.score ?? 0));
      return `<div class="b ${i === 0 ? "now" : ""}" style="height:${sc}%;background:${vcw(p.verdict)}" title="${(p.datetime || "").slice(11, 16)} · ${Math.round(p.score ?? 0)}"></div>`;
    }).join("");
    const strip = (k, v, sub) => `<div class="sd-ns"><span class="k">${k}</span><b>${v}</b>${sub ? `<span class="s">${sub}</span>` : ""}</div>`;
    return `<div class="sd-row2">
        <div class="sd-wind">${this._compass(c.wind_dir_deg, c.wind_speed_kn, c.wind_gust_kn)}</div>
        ${this._tide(d)}
      </div>
      <div class="sd-sel">
        ${this._gauge(now.score, col, "now")}
        <div class="sd-selr"><div class="nm">${sp.label}</div><div class="vd" style="color:${col}">${now.verdict || "—"}</div></div>
        <div class="sd-best"><span class="bk">Best · 24h</span><b>${bestT}</b><span class="bs">${best ? Math.round(best.score) + " · " + (best.verdict || "") : ""}</span></div>
      </div>
      ${ser.length ? `<div class="sd-tl"><div class="tlh">Next 24h</div><div class="bars">${bars}</div></div>` : ""}
      <div class="sd-strip">
        ${strip("Wind", f1(c.wind_speed_kn), (cardOf(c.wind_dir_deg) || "") + " kn")}
        ${strip("Gust", f1(c.wind_gust_kn), "kn")}
        ${strip("Wave", c.wave_height_m != null ? f1(c.wave_height_m) : (c.wind_wave_height_m != null ? f1(c.wind_wave_height_m) : "—"), "m")}
        ${strip("Swell", c.swell_height_m != null ? f1(c.swell_height_m) : "—", c.swell_period_s != null ? f1(c.swell_period_s) + "s" : "m")}
      </div>
      ${this._config.show_factors !== false && this._factors(now) ? `<div class="sd-facs">${this._factors(now)}</div>` : ""}`;
  }

  _spotWeek(d, sp) {
    const dl = sp.daily || [], pk = this._peak(sp), col = pk ? vcw(pk.verdict) : vc("good");
    const today = d.now_time != null ? (dl[0] && dl[0].date) : null;
    const cc = pk || {}, wc = cardOf(cc.wind_bearing);
    const good = dl.filter((e) => !["poor", "marginal"].includes(e.verdict)).length;
    const tide = cc.tide || {};
    const m = (k, v, sub) => `<div class="sd-st"><span class="k">${k}</span><b>${v}</b>${sub ? `<span class="s">${sub}</span>` : ""}</div>`;
    const rows = dl.map((e) => {
      const isP = e === pk, c2 = vcw(e.verdict);
      return `<div class="sd-drow ${isP ? "best" : ""}">
        <span class="dd">${e.date === today ? "Today" : this._wd(e.date)}</span>
        <span class="db"><i style="width:${Math.max(4, e.score)}%;background:${c2}"></i></span>
        <span class="dt">${(e.datetime || "").slice(11, 16)}</span>
        <span class="ds" style="color:${c2}">${isP ? "★ " : ""}${Math.round(e.score)}</span></div>`;
    }).join("");
    return `<div class="sd-sel">
        ${this._gauge(pk?.score, col, "peak")}
        <div class="sd-selr"><div class="nm">${sp.label}</div><div class="vd" style="color:${col}">${pk?.verdict || "—"}</div></div>
        <div class="sd-best"><span class="bk">Peak day</span><b>${pk ? (pk.date === today ? "Today" : this._wd(pk.date)) : "—"}</b><span class="bs">${pk ? (pk.datetime || "").slice(11, 16) : ""}</span></div>
      </div>
      <div class="sd-bestpane">
        <div class="bp-h">Best day${pk ? " · " + (pk.date === today ? "Today" : this._wd(pk.date)) + " " + (pk.datetime || "").slice(11, 16) : ""} · ${good}/${dl.length} good+ days</div>
        <div class="sd-strip wrap">
          ${m("Wind", f1(cc.wind_speed_kn), (wc || "") + " kn")}
          ${m("Gust", f1(cc.wind_gust_kn), "kn")}
          ${m("Wave", cc.wave_height_m != null ? f1(cc.wave_height_m) : "—", "m")}
          ${m("Swell", cc.swell_height_m != null ? f1(cc.swell_height_m) : "—", cc.swell_period_s != null ? f1(cc.swell_period_s) + "s" : "m")}
          ${this._config.show_tide === false ? "" : m("Tide", cap(tide.state), tide.height != null ? f1(tide.height, 2) + " m" : "")}
          ${m("Water", cc.water_temp_c != null ? f1(cc.water_temp_c) : "—", "°C")}
        </div>
      </div>
      <div class="sd-drows">${rows}</div>`;
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
        { value: "spot", label: "Spot detail — now/week (one spot)" },
        { value: "podium", label: "Podium — top 3 per day" },
        { value: "timeline", label: "Opportunity timeline (7 days)" },
        { value: "heatgrid", label: "Heat-grid — now" },
        { value: "medallions", label: "Medallions — now" },
      ] } } },
    ];
    if (this._config.mode === "spot") {
      base.push(
        { name: "spot", required: true, selector: { select: { mode: "dropdown", options: o.spots } } },
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
        spot: "Spot (spot-detail mode)",
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
/* ---------- spot detail ---------- */
.sd{display:flex;flex-direction:column;gap:12px;}
.sd-hdr{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.sd-nm{font-size:18px;font-weight:700;color:var(--c-ink);}
.sd-sub{font-size:11px;color:var(--c-dim);text-transform:capitalize;margin-top:2px;}
.sd-ctrl{display:flex;align-items:center;gap:10px;}
.sd-seg{display:flex;border:1px solid var(--c-line);border-radius:9px;overflow:hidden;}
.sd-seg button{font:inherit;cursor:pointer;border:0;background:transparent;color:var(--c-dim);font-size:12px;font-weight:700;padding:7px 13px;}
.sd-seg button.on{background:var(--primary-color,#03a9f4);color:#fff;}
.sd-now{text-align:right;} .sd-now b{display:block;font-size:15px;color:var(--c-ink);} .sd-now span{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--c-dim);}
.sd-pills{display:flex;gap:6px;flex-wrap:wrap;}
.sd-pill{cursor:pointer;flex:1 1 auto;min-width:84px;display:flex;align-items:center;gap:6px;border:1px solid var(--c-line);border-radius:10px;padding:7px 9px;}
.sd-pill.on{border-color:var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 12%,transparent);}
.sd-pill .icon{width:16px;height:16px;color:var(--c-ink);} .sd-pill .pn{font-size:12px;font-weight:600;color:var(--c-ink);} .sd-pill .pv{font-size:14px;font-weight:800;margin-left:auto;}
.sd-row2{display:flex;gap:10px;flex-wrap:wrap;}
.sd-wind{flex:1 1 130px;display:flex;align-items:center;justify-content:center;min-width:120px;}
.sd-rose{width:130px;height:130px;} .sd-rose .t{fill:var(--c-dim);font:700 11px sans-serif;text-anchor:middle;} .sd-rose .nd{fill:var(--primary-color,#03a9f4);} .sd-rose .hub{fill:var(--card-background-color,#1b1e25);stroke:var(--c-line);} .sd-rose .spd{fill:var(--c-ink);font:800 22px sans-serif;text-anchor:middle;} .sd-rose .u{fill:var(--c-dim);font:600 9px sans-serif;text-anchor:middle;}
.sd-tide{flex:1 1 150px;min-width:150px;border:1px solid var(--c-line);border-radius:12px;padding:9px 11px;}
.sd-th{display:flex;justify-content:space-between;font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--c-dim);} .sd-th .src{opacity:.7;}
.sd-ts{display:flex;align-items:baseline;gap:7px;margin-top:3px;} .sd-ts .ar,.sd-ts .w{font-size:19px;font-weight:800;color:var(--c-ink);}
.t-rising .ar,.t-rising .w{color:#39bdf8;} .t-falling .ar,.t-falling .w{color:#f0a83d;}
.sd-tn{font-size:11px;color:var(--c-dim);margin-top:2px;} .sd-tn b{color:var(--c-ink);text-transform:capitalize;}
.sd-spark{width:100%;height:30px;margin-top:5px;display:block;}
.sd-sel{display:flex;align-items:center;gap:13px;border:1px solid var(--c-line);border-radius:12px;padding:11px 13px;}
.sd-ring{width:60px;height:60px;border-radius:50%;flex:0 0 auto;position:relative;background:conic-gradient(var(--c) calc(var(--p)*1%),var(--c-track) 0);}
.sd-ring::after{content:'';position:absolute;inset:5px;border-radius:50%;background:var(--card-background-color,#1b1e25);}
.sd-ri{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;}
.sd-ri b{font-size:20px;font-weight:800;line-height:1;} .sd-ri i{font-size:8px;font-style:normal;text-transform:uppercase;letter-spacing:.1em;color:var(--c-dim);}
.sd-selr .nm{font-size:16px;font-weight:700;color:var(--c-ink);} .sd-selr .vd{font-size:12px;font-weight:700;text-transform:capitalize;}
.sd-best{margin-left:auto;text-align:right;} .sd-best .bk{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--c-dim);display:block;} .sd-best b{font-size:15px;color:var(--c-ink);} .sd-best .bs{display:block;font-size:11px;color:var(--c-dim);}
.sd-tl{border:1px solid var(--c-line);border-radius:12px;padding:9px 11px;} .sd-tl .tlh{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--c-dim);margin-bottom:7px;}
.sd-tl .bars{display:flex;align-items:flex-end;gap:2px;height:60px;} .sd-tl .b{flex:1;border-radius:3px 3px 0 0;min-height:3px;align-self:flex-end;} .sd-tl .b.now{outline:1.5px solid var(--c-ink);outline-offset:1px;}
.sd-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;} .sd-strip.wrap{grid-template-columns:repeat(3,1fr);}
.sd-ns,.sd-st{border:1px solid var(--c-line);border-radius:10px;padding:7px 9px;} .sd-ns .k,.sd-st .k{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--c-dim);display:block;} .sd-ns b,.sd-st b{font-size:16px;font-weight:800;color:var(--c-ink);display:block;} .sd-ns .s,.sd-st .s{font-size:10px;color:var(--c-dim);}
.sd-facs{display:grid;gap:5px;} .sd-fac{display:grid;grid-template-columns:64px 1fr 28px;align-items:center;gap:8px;font-size:11px;color:var(--c-dim);text-transform:capitalize;} .sd-fac .fb{height:6px;border-radius:4px;background:var(--c-track);overflow:hidden;} .sd-fac .fb i{display:block;height:100%;background:var(--primary-color,#03a9f4);} .sd-fac b{text-align:right;color:var(--c-ink);}
.sd-bestpane{border:1px solid var(--c-line);border-radius:12px;padding:10px 12px;} .bp-h{font-size:11px;font-weight:600;color:var(--c-dim);margin-bottom:8px;}
.sd-drows{display:flex;flex-direction:column;gap:6px;} .sd-drow{display:grid;grid-template-columns:46px 1fr 44px 40px;align-items:center;gap:9px;border:1px solid var(--c-line);border-radius:9px;padding:7px 11px;}
.sd-drow.best{border-color:var(--primary-color,#03a9f4);} .sd-drow .dd{font-size:12px;font-weight:700;color:var(--c-ink);} .sd-drow .db{height:7px;border-radius:4px;background:var(--c-track);overflow:hidden;} .sd-drow .db i{display:block;height:100%;} .sd-drow .dt{font-size:10px;color:var(--c-dim);text-align:right;} .sd-drow .ds{font-size:15px;font-weight:800;text-align:right;}
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

customElements.define("swelligence-card", SwelligenceCard);
customElements.define("swelligence-card-editor", SwelligenceCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "swelligence-card",
  name: "Swelligence Card",
  description: "Conditions: spot detail (now/week), podium, opportunity timeline, heat-grid, or medallions.",
  preview: true,
  documentationURL: "https://git.bagofholding.co.uk/foolycooly/swelligence",
});
console.info("%c SWELLIGENCE-CARD ", "background:#1f9d57;color:#fff", "v11 loaded (spot-detail now/week mode)");
