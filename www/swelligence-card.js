/*
 * Swelligence Lovelace card
 * Spot × sport suitability matrix with a forecast drill-down.
 *
 * Reads sensor.swelligence_*_suitability entities (grouped via their `spot` and
 * `sport_label` attributes) and, on tapping a cell, calls the
 * swelligence.get_forecast service (HA weather best-practice) to render the
 * 7-day outlook — daily best windows, with an hourly drill-down.
 *
 * Config:
 *   type: custom:swelligence-card
 *   title: "Conditions"        # optional
 *   spots: ["Avon Beach", ...] # optional filter (by spot name)
 *   sports: ["surf", ...]      # optional filter (by sport key)
 */

const VERDICT_COLOR = {
  epic: "#1a9850",
  great: "#66bd63",
  good: "#a6d96a",
  marginal: "#fdae61",
  poor: "#f46d43",
};
const VERDICT_TEXT = { epic: "#fff", great: "#fff", good: "#102", marginal: "#201", poor: "#fff" };
const SPORT_ORDER = [
  "kitesurf", "windsurf", "wingfoil", "surf", "sup",
  "sailing", "seaswim", "wakeboard_inland", "wakeboard_sea",
];

class SwelligenceCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._selected = null;
    this._forecast = null;
    this._forecastKind = "daily";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) this._init();
    this._render();
  }

  getCardSize() {
    return 6;
  }

  _init() {
    this._root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      ha-card { padding: 12px 14px 16px; }
      .title { font-size: 1.3rem; font-weight: 500; margin: 0 0 10px; }
      table { border-collapse: collapse; width: 100%; }
      th, td { text-align: center; padding: 2px; }
      th.spot, td.spot { text-align: left; white-space: nowrap; font-weight: 500; padding-right: 8px; }
      th { font-size: .72rem; color: var(--secondary-text-color); font-weight: 500; }
      td.cell { border-radius: 8px; cursor: pointer; height: 40px; min-width: 46px;
                line-height: 1.05; transition: transform .05s; }
      td.cell:hover { transform: scale(1.06); }
      td.cell.sel { outline: 2px solid var(--primary-color); outline-offset: -2px; }
      .score { font-weight: 600; font-size: .95rem; }
      .kit { font-size: .62rem; opacity: .9; }
      .na { color: var(--disabled-text-color); }
      .detail { margin-top: 14px; border-top: 1px solid var(--divider-color); padding-top: 10px; }
      .detail h3 { margin: 0 0 8px; font-size: 1rem; }
      .tiles { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; }
      .tile { flex: 0 0 auto; min-width: 64px; border-radius: 8px; padding: 6px 4px; text-align: center; }
      .tile .d { font-size: .72rem; opacity: .85; }
      .tile .s { font-weight: 700; font-size: 1.1rem; }
      .tile .t { font-size: .66rem; opacity: .85; }
      .tile .k { font-size: .6rem; opacity: .85; margin-top: 2px; }
      .toggle { margin: 10px 0 4px; }
      .toggle button { background: var(--secondary-background-color); border: none;
        color: var(--primary-text-color); padding: 4px 10px; border-radius: 14px; cursor: pointer; font-size: .75rem; }
      .toggle button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .hourly { display: flex; gap: 1px; align-items: flex-end; height: 60px; margin-top: 6px; overflow-x: auto; }
      .hbar { flex: 0 0 5px; border-radius: 1px; }
      .hday { font-size: .62rem; color: var(--secondary-text-color); margin: 6px 0 2px; }
      .muted { color: var(--secondary-text-color); font-size: .8rem; }
    `;
    this._card = document.createElement("ha-card");
    this._body = document.createElement("div");
    this._card.appendChild(this._body);
    this._root.appendChild(style);
    this._root.appendChild(this._card);
  }

  _cells() {
    const out = [];
    for (const id of Object.keys(this._hass.states)) {
      if (!id.startsWith("sensor.swelligence_") || !id.endsWith("_suitability")) continue;
      const s = this._hass.states[id];
      const a = s.attributes || {};
      if (!a.spot || !a.sport) continue;
      if (this._config.spots && !this._config.spots.includes(a.spot)) continue;
      if (this._config.sports && !this._config.sports.includes(a.sport)) continue;
      out.push({ id, state: s.state, ...a });
    }
    return out;
  }

  _render() {
    if (!this._hass) return;
    const cells = this._cells();
    const title = this._config.title || "Swelligence";
    if (!cells.length) {
      this._body.innerHTML = `<div class="title">${title}</div><div class="muted">No Swelligence suitability sensors found. Add spots in the integration options.</div>`;
      return;
    }
    const spots = [...new Set(cells.map((c) => c.spot))];
    const sports = [...new Set(cells.map((c) => c.sport))].sort(
      (a, b) => SPORT_ORDER.indexOf(a) - SPORT_ORDER.indexOf(b)
    );
    const labelOf = {};
    cells.forEach((c) => (labelOf[c.sport] = c.sport_label || c.sport));
    const byKey = {};
    cells.forEach((c) => (byKey[`${c.spot}|${c.sport}`] = c));

    let html = `<div class="title">${title}</div><table><thead><tr><th class="spot"></th>`;
    for (const sp of sports) html += `<th>${labelOf[sp]}</th>`;
    html += `</tr></thead><tbody>`;
    for (const spot of spots) {
      html += `<tr><td class="spot">${spot}</td>`;
      for (const sp of sports) {
        const c = byKey[`${spot}|${sp}`];
        if (!c) {
          html += `<td class="na">·</td>`;
          continue;
        }
        const v = c.verdict || "poor";
        const bg = VERDICT_COLOR[v] || "var(--disabled-color)";
        const fg = VERDICT_TEXT[v] || "#fff";
        const sel = this._selected === c.id ? " sel" : "";
        const kit = c.rig_size_m2 ? `<div class="kit">${c.rig_size_m2}m²</div>` : "";
        const score = Math.round(parseFloat(c.state));
        html += `<td class="cell${sel}" style="background:${bg};color:${fg}" data-id="${c.id}">
                   <div class="score">${isNaN(score) ? "–" : score}</div>${kit}</td>`;
      }
      html += `</tr>`;
    }
    html += `</tbody></table>`;
    html += this._renderDetail(byKey);
    this._body.innerHTML = html;

    this._body.querySelectorAll("td.cell").forEach((el) =>
      el.addEventListener("click", () => this._select(el.dataset.id))
    );
    const t = this._body.querySelector("#tg-daily");
    const h = this._body.querySelector("#tg-hourly");
    if (t) t.addEventListener("click", () => this._setKind("daily"));
    if (h) h.addEventListener("click", () => this._setKind("hourly"));
  }

  _renderDetail(byKey) {
    if (!this._selected) return "";
    const sel = Object.values(byKey).find((c) => c.id === this._selected);
    if (!sel) return "";
    let html = `<div class="detail"><h3>${sel.spot} — ${sel.sport_label}</h3>`;
    html += `<div class="toggle">
      <button id="tg-daily" class="${this._forecastKind === "daily" ? "on" : ""}">7-day</button>
      <button id="tg-hourly" class="${this._forecastKind === "hourly" ? "on" : ""}">Hourly</button></div>`;
    if (!this._forecast) {
      html += `<div class="muted">Loading forecast…</div></div>`;
      return html;
    }
    html += this._forecastKind === "daily"
      ? this._renderDaily(this._forecast)
      : this._renderHourly(this._forecast);
    return html + `</div>`;
  }

  _renderDaily(f) {
    if (!f.length) return `<div class="muted">No forecast.</div>`;
    let h = `<div class="tiles">`;
    for (const d of f) {
      const v = d.verdict || "poor";
      const day = new Date(d.date).toLocaleDateString(undefined, { weekday: "short" });
      const time = d.datetime ? d.datetime.slice(11, 16) : "";
      const kit = d.kit_rig_m2 ? `<div class="k">${d.kit_rig_m2}m²</div>` : "";
      h += `<div class="tile" style="background:${VERDICT_COLOR[v]};color:${VERDICT_TEXT[v]}">
              <div class="d">${day}</div><div class="s">${Math.round(d.score)}</div>
              <div class="t">@${time}</div>${kit}</div>`;
    }
    return h + `</div>`;
  }

  _renderHourly(f) {
    if (!f.length) return `<div class="muted">No forecast.</div>`;
    const byDay = {};
    for (const s of f) {
      const d = s.datetime.slice(0, 10);
      (byDay[d] = byDay[d] || []).push(s);
    }
    let h = "";
    for (const day of Object.keys(byDay)) {
      const label = new Date(day).toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
      h += `<div class="hday">${label}</div><div class="hourly">`;
      for (const s of byDay[day]) {
        const v = s.verdict || "poor";
        const ht = Math.max(4, Math.round(s.score * 0.6));
        const tip = `${s.datetime.slice(11, 16)} · ${Math.round(s.score)} ${v}` +
          (s.wind_speed_kn != null ? ` · ${Math.round(s.wind_speed_kn)}kn` : "");
        h += `<div class="hbar" title="${tip}" style="height:${ht}px;background:${VERDICT_COLOR[v]}"></div>`;
      }
      h += `</div>`;
    }
    return h;
  }

  async _select(id) {
    if (this._selected === id) {
      this._selected = null;
      this._forecast = null;
    } else {
      this._selected = id;
      this._forecast = null;
      this._render();
      await this._loadForecast(id);
    }
    this._render();
  }

  _setKind(kind) {
    if (this._forecastKind === kind) return;
    this._forecastKind = kind;
    this._forecast = null;
    this._render();
    if (this._selected) this._loadForecast(this._selected).then(() => this._render());
  }

  async _loadForecast(id) {
    try {
      const r = await this._hass.callService(
        "swelligence", "get_forecast",
        { type: this._forecastKind }, { entity_id: id }, false, true
      );
      const resp = (r && r.response && r.response[id]) || null;
      this._forecast = resp ? resp.forecast : [];
    } catch (e) {
      this._forecast = [];
    }
  }

  static getConfigElement() {
    return document.createElement("hui-generic-entity-row"); // no custom editor; YAML config
  }

  static getStubConfig() {
    return { title: "Conditions" };
  }
}

customElements.define("swelligence-card", SwelligenceCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "swelligence-card",
  name: "Swelligence Card",
  description: "Spot × sport suitability matrix with forecast drill-down.",
});
console.info("%c SWELLIGENCE-CARD ", "background:#1a9850;color:#fff", "loaded");
