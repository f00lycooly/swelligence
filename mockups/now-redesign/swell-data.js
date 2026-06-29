/* ============================================================================
   Swelligence — shared data harness + helpers for the NOW-view redesign study.

   Re-uses the SHIPPED card's verdict palette, sport icons, compass + format
   helpers verbatim, and the same dummy spots (Hurst / Avon / Sandbanks).

   KEY CHANGE vs the shipped harness: a per-hour MET series drives a per-hour
   FACTOR breakdown -> SCORE -> KIT recommendation through one small physical
   model (SPORT_MODEL). The production get_spot_detail returns exactly this
   per-hour shape; the old harness only kept a per-hour score, which is why the
   factor bars / kit arc could only ever show "now" and the timeline was static.
   Now every element follows the scrub coherently.
   ========================================================================== */
(function () {
  const VERDICT = {
    epic: { c: "#1f9d57", t: "#fff" }, great: { c: "#5cb85c", t: "#08230f" },
    good: { c: "#9bcf5f", t: "#0c2208" }, marg: { c: "#f0a83d", t: "#241600" },
    poor: { c: "#e8593a", t: "#fff" },
  };
  const LABELS = { kitesurf: "Kite", windsurf: "Windsurf", wingfoil: "Wing", surf: "Surf", sup: "SUP", sailing: "Sail", seaswim: "Swim" };
  const SYM = { kitesurf: "i-kite", windsurf: "i-windsurf", wingfoil: "i-wing", surf: "i-surf", sup: "i-sup", sailing: "i-sail", seaswim: "i-swim" };
  const COMPASS16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];

  const vc = (v) => (VERDICT[v] || VERDICT.poor).c;
  const vkey = (v) => (v === "marginal" ? "marg" : v);
  const vcw = (v) => vc(vkey(v) in VERDICT ? vkey(v) : "poor");
  const cardOf = (deg) => (deg == null ? null : COMPASS16[Math.round(((deg % 360) / 22.5)) % 16]);
  const f1 = (n, d = 1) => (n == null ? "—" : Math.round(n * 10 ** d) / 10 ** d);
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "—");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const vword = (s) => s >= 85 ? "epic" : s >= 70 ? "great" : s >= 55 ? "good" : s >= 35 ? "marginal" : "poor";
  const facCol = (n) => (n == null ? "var(--mut)" : n >= 67 ? vc("good") : n >= 34 ? vc("marg") : vc("poor"));

  const ICON_DEFS = `
<symbol id="i-kite" viewBox="0 0 24 24"><path d="M2.5 7 Q12 1 21.5 7"/><path d="M5.5 7.6 L11 15.5"/><path d="M18.5 7.6 L13 15.5"/><path d="M10.5 15.6 H13.5"/><path d="M7 20 Q12 22.5 17 20"/></symbol>
<symbol id="i-windsurf" viewBox="0 0 24 24"><path d="M3 19.5 Q12 22.5 21 19.5"/><path d="M12 19 L12 3.5"/><path d="M12 4 Q20 9.5 12 15"/><path d="M12 9.5 L17.5 9"/></symbol>
<symbol id="i-wing" viewBox="0 0 24 24"><path d="M3.5 8 Q12 2.5 20.5 8 Q12 10.5 3.5 8 Z"/><path d="M12 10.5 L12 16"/><path d="M7.5 17.5 Q12 15.5 16.5 17.5"/></symbol>
<symbol id="i-surf" viewBox="0 0 24 24"><path d="M2 17 C6 17 6 9 11 9 C15.5 9 14 15 19.5 14"/><path d="M11 9 C13.5 7.8 14.6 10 12.4 11.6"/><path d="M13.5 20 L20 13.5"/></symbol>
<symbol id="i-sup" viewBox="0 0 24 24"><path d="M3 18 Q12 21 21 18"/><path d="M3 18 Q12 15.6 21 18"/><path d="M14.5 3.5 L9 17"/><path d="M13 3.5 H16"/><path d="M7.5 16 L9 19 L10.7 16 Z"/></symbol>
<symbol id="i-sail" viewBox="0 0 24 24"><path d="M4 18 L20 18 L17.5 21 H6.5 Z"/><path d="M12 18 L12 3.5"/><path d="M12.8 5 L18.5 16 H12.8 Z"/><path d="M11.2 6.5 L6 16 H11.2 Z"/></symbol>
<symbol id="i-swim" viewBox="0 0 24 24"><circle cx="8" cy="8.5" r="2"/><path d="M9.6 10 Q14 8.4 17.5 11.5"/><path d="M9.6 10 Q11.5 5.5 15 7.5"/><path d="M2 18 q2.6 -2 5.2 0 t5.2 0 t5.2 0"/></symbol>`;
  const ICON = (sport, cls = "") => `<svg class="ic ${cls}"><use href="#${SYM[sport] || "i-kite"}"/></svg>`;

  function ring(score, col, size = 80, sw = 8) {
    const r = size / 2 - sw, circ = 2 * Math.PI * r, off = circ * (1 - (score || 0) / 100);
    return `<svg class="ringsvg" viewBox="0 0 ${size} ${size}" data-r="${r}" data-sz="${size}">
      <circle class="rt" cx="${size/2}" cy="${size/2}" r="${r}" style="stroke-width:${sw}"/>
      <circle class="ra" cx="${size/2}" cy="${size/2}" r="${r}" stroke="${col}" style="stroke-width:${sw}"
        stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/></svg>`;
  }
  function compass(dir, col, size = 64) {
    const rot = ((dir ?? 0) + 180) % 360;
    return `<svg class="cmp" viewBox="0 0 100 100" width="${size}" height="${size}">
      <g transform="translate(50 50)"><circle r="40" class="cmp-d"/>
      <text x="0" y="-29" class="cmp-n">N</text>
      <g class="needle" transform="rotate(${rot})" stroke="${col}" fill="${col}">
        <line x1="0" y1="26" x2="0" y2="-18" stroke-width="6" stroke-linecap="round"/>
        <path d="M0 -32 L9 -13 L0 -18 L-9 -13 Z"/></g></g></svg>`;
  }
  /* arc-gauge kit indicator (verbatim shape from the shipped _kitArc) */
  function kitArc(kit, sport) {
    const power = kit && kit.power || "no_kit";
    const col = power === "ideal" ? vc("good") : power === "underpowered" ? vc("marg") : power === "overpowered" ? vc("poor") : "var(--mut)";
    const frac = power === "underpowered" ? 0.22 : power === "overpowered" ? 0.78 : 0.5;
    const a = Math.PI * (1 - frac), cx = 50, cy = 56, r = 40;
    const nx = (cx + Math.cos(a) * (r - 6)).toFixed(1), ny = (cy - Math.sin(a) * (r - 6)).toFixed(1);
    const fillEnd = power === "no_kit" ? "M10 56 A40 40 0 0 0 10 56" : `M10 56 A40 40 0 0 1 ${(cx + Math.cos(a) * r).toFixed(1)} ${(cy - Math.sin(a) * r).toFixed(1)}`;
    const size = kit && kit.rig_m2 != null ? `${kit.rig_m2}m²` : "—";
    const label = power === "no_kit" ? "no kit" : power === "ideal" ? "ideal" : power;
    return `<svg viewBox="0 0 100 64" class="kit-svg"><path d="M10 56 A40 40 0 0 1 90 56" class="kit-track"/>
      <path d="${fillEnd}" fill="none" stroke="${col}" stroke-width="9" stroke-linecap="round"/>
      ${power === "no_kit" ? "" : `<line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" class="kit-needle"/>`}
      <circle cx="${cx}" cy="${cy}" r="4" class="kit-hub"/>
      <use href="#${SYM[sport] || "i-kite"}" x="39" y="33" width="22" height="22" fill="none" stroke="${col}" stroke-width="1.6"/></svg>
      <div class="kit-meta"><b style="color:${col}">${size}</b><span>rig · ${label}</span></div>`;
  }
  /* static dark basemap tile mosaic centred on the spot (no JS map dep). CARTO
     dark tiles match the ocean theme; OSM is used by the shipped card in HA. */
  function mapMosaic(lat, lon, zoom = 12) {
    const n = 2 ** zoom, xf = (lon + 180) / 360 * n, lr = lat * Math.PI / 180;
    const yf = (1 - Math.log(Math.tan(lr) + 1 / Math.cos(lr)) / Math.PI) / 2 * n;
    const xt = Math.floor(xf), yt = Math.floor(yf), mx = 256 + (xf - xt) * 256, my = 256 + (yf - yt) * 256;
    const subs = "abcd";
    let imgs = "";
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const tx = ((xt + dx) % n + n) % n, ty = yt + dy;
      if (ty < 0 || ty >= n) continue;
      const s = subs[(Math.abs(tx + ty)) % 4];
      imgs += `<img alt="" loading="lazy" src="https://${s}.basemaps.cartocdn.com/dark_all/${zoom}/${tx}/${ty}.png" style="left:${(dx + 1) * 256}px;top:${(dy + 1) * 256}px"/>`;
    }
    return `<div class="lmap"><div class="mos" style="margin-left:${(-mx).toFixed(1)}px;margin-top:${(-my).toFixed(1)}px">${imgs}</div></div>`;
  }

  /* ---- per-hour MET series (deterministic): sea-breeze daytime wind, slow
     wave drift, tide level/state read off the modelled curve. ---- */
  const rnd = (n) => { const x = Math.sin(n * 127.1) * 43758.5453; return x - Math.floor(x); };
  const pad2 = (n) => String(n).padStart(2, "0");
  const isoDate = (i) => new Date(2026, 5, 29 + i).toISOString().slice(0, 10);
  function mkTide(state, source, nextType, nextTime, nextLevel, nextIn) {
    const mid = 2.0, amp = 1.5, levels = [];
    for (let i = 0; i < 24; i++) levels.push(+(mid + amp * Math.sin(i / 12.42 * Math.PI * 2 + 1.1)).toFixed(2));
    return { state, source, next: { type: nextType, time: nextTime, level: nextLevel, in_h: nextIn }, levels, min: Math.min(...levels), max: Math.max(...levels) };
  }
  function mkHourlyMet(o) {
    const startHH = parseInt(o.now_time.slice(0, 2), 10), lv = o.tide ? o.tide.levels : null, out = [];
    for (let i = 0; i < 24; i++) {
      const hod = (startHH + i) % 24, day = Math.sin((hod - 9) / 14 * Math.PI);
      const wf = clamp(0.72 + 0.42 * day + (rnd(o.seed + i) * 0.12 - 0.06), 0.4, 1.3);
      const wind = +(o.wind_kn * wf).toFixed(1), gust = +(wind * (1.28 + rnd(o.seed + i + 5) * 0.2)).toFixed(1);
      const dir = Math.round((o.wind_dir + (rnd(o.seed + i + 9) - 0.5) * 34 + 360) % 360);
      const wave = o.wave == null ? null : +Math.max(0.1, o.wave * (0.8 + 0.45 * Math.max(0, day)) * (0.9 + rnd(o.seed + i + 2) * 0.2)).toFixed(1);
      const swell = o.swell == null ? null : +Math.max(0.1, o.swell * (0.92 + rnd(o.seed + i + 4) * 0.16)).toFixed(1);
      const period = o.swellP == null ? null : +(o.swellP * (0.95 + rnd(o.seed + i + 6) * 0.12)).toFixed(1);
      const wt = o.waterT == null ? null : +(o.waterT + Math.sin((hod - 15) / 24 * Math.PI * 2) * 0.8).toFixed(1);
      let tlevel = null, tstate = null;
      if (lv) { const a = lv[hod % 24], b = lv[(hod + 1) % 24]; tlevel = a; tstate = b >= a ? "rising" : "falling"; }
      out.push({ hh: pad2(hod) + ":00", rel: i, wind_kn: wind, gust_kn: gust, wind_dir_deg: dir,
        wave_height_m: wave, swell_height_m: swell, swell_period_s: period, water_temp_c: wt, tide_level: tlevel, tide_state: tstate });
    }
    return out;
  }

  /* ---- the model: factors (0-100) -> weighted score -> kit ---- */
  const SPORT_MODEL = {
    kitesurf: { windy: true, ideal: [15, 30], div: 170, w: { wind: .30, gust: .12, direction: .20, wave: .12, temp: .10, tide: .16 } },
    wingfoil: { windy: true, ideal: [11, 26], div: 95, w: { wind: .30, gust: .12, direction: .18, wave: .12, temp: .10, tide: .18 } },
    windsurf: { windy: true, ideal: [15, 30], div: 120, w: { wind: .32, gust: .10, direction: .20, wave: .12, temp: .10, tide: .16 } },
    surf: { windy: false, w: { wind: .20, wave: .28, swell: .32, temp: .20 } },
    sup: { windy: false, w: { wind: .36, gust: .14, wave: .30, temp: .20 } },
    seaswim: { windy: false, w: { wind: .24, wave: .24, temp: .32, tide: .20 } },
  };
  const angDiff = (a, b) => { let d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
  const cF = (v) => clamp(Math.round(v), 3, 99);
  const facWind = (kn, lo, hi) => kn < lo ? clamp(40 + kn / lo * 55, 5, 95) : kn <= hi ? clamp(98 - (kn - lo) / (hi - lo) * 6, 80, 98) : clamp(92 - (kn - hi) * 6, 12, 92);
  const facCalm = (kn) => clamp(100 - kn / 22 * 78, 8, 100);
  const facGust = (kn, g) => clamp(100 - (g - kn) * 6, 18, 100);
  const facChop = (m) => clamp(100 - (m || 0) / 1.1 * 72, 15, 100);
  const facWaveSurf = (m) => clamp((m || 0) / 1.3 * 100, 8, 100);
  const facSwell = (m, p) => clamp((m || 0) / 0.9 * 55 + ((p || 4) - 4) * 9, 8, 100);
  const facTemp = (c) => clamp(((c == null ? 14 : c) - 10) / 12 * 100, 5, 100);
  const facTide = (lvl) => clamp(38 + (lvl == null ? 2 : lvl) / 3.5 * 58, 28, 96);
  const facDir = (dir, base, baseFac) => clamp(baseFac - angDiff(dir, base) * 0.7, 20, 99);

  function hourFactors(key, met, baseDir) {
    const M = SPORT_MODEL[key], f = {};
    if (M.windy) {
      f.wind = facWind(met.wind_kn, M.ideal[0], M.ideal[1]);
      f.gust = facGust(met.wind_kn, met.gust_kn);
      f.direction = facDir(met.wind_dir_deg, baseDir, 90);
      f.wave = facChop(met.wave_height_m);
      f.temp = facTemp(met.water_temp_c);
      f.tide = facTide(met.tide_level);
    } else if (key === "surf") {
      f.wind = facCalm(met.wind_kn); f.wave = facWaveSurf(met.wave_height_m);
      f.swell = facSwell(met.swell_height_m, met.swell_period_s); f.temp = facTemp(met.water_temp_c);
    } else {
      f.wind = facCalm(met.wind_kn); f.gust = facGust(met.wind_kn, met.gust_kn);
      f.wave = facChop(met.wave_height_m); f.temp = facTemp(met.water_temp_c); f.tide = facTide(met.tide_level);
    }
    for (const k in f) f[k] = cF(f[k]);
    return f;
  }
  function scoreFrom(f, key) {
    const w = SPORT_MODEL[key].w; let s = 0, tw = 0;
    for (const k in w) if (f[k] != null) { s += f[k] * w[k]; tw += w[k]; }
    return cF(tw ? s / tw : 30);
  }
  function kitFrom(key, kn) {
    const M = SPORT_MODEL[key]; if (!M.windy) return null;
    return { power: kn < M.ideal[0] ? "underpowered" : kn > M.ideal[1] ? "overpowered" : "ideal", rig_m2: clamp(Math.round(M.div / Math.max(6, kn)), 3, 18) };
  }

  function mkSpot(o) {
    const startHH = parseInt(o.now_time.slice(0, 2), 10);
    const met = mkHourlyMet(o);
    const sports = o.sportKeys.map((key) => {
      const hourly = [];
      for (let i = 0; i < 24; i++) {
        const f = hourFactors(key, met[i], o.wind_dir), sc = scoreFrom(f, key);
        hourly.push({ hh: met[i].hh, rel: i, score: sc, verdict: vword(sc), factors: f, kit: kitFrom(key, met[i].wind_kn) });
      }
      let bi = 0; for (let i = 1; i < 24; i++) if (hourly[i].score > hourly[bi].score) bi = i;
      const h0 = hourly[0];
      return {
        sport: key, label: LABELS[key] || key,
        now: { score: h0.score, verdict: h0.verdict, factors: h0.factors, kit: h0.kit },
        best: { hh: hourly[bi].hh, in_hours: bi, score: hourly[bi].score, verdict: hourly[bi].verdict },
        hourly,
      };
    });
    return {
      name: o.name, water_type: o.water_type, latitude: o.lat, longitude: o.lon, now_time: o.now_time,
      current: { wind_dir_deg: o.wind_dir, wind_speed_kn: o.wind_kn, wind_gust_kn: o.gust_kn, wave_height_m: o.wave, swell_height_m: o.swell, swell_period_s: o.swellP, water_temp_c: o.waterT },
      tide: o.tide, daylight: o.daylight, sports, hourly_met: met,
    };
  }

  const SPOTS = [
    mkSpot({ name: "Hurst Spit / Keyhaven", water_type: "sea", lat: 50.715, lon: -1.553, now_time: "13:00", seed: 11,
      wind_dir: 225, wind_kn: 18.4, gust_kn: 24.1, wave: 0.8, swell: 0.6, swellP: 7.2, waterT: 16.5,
      tide: mkTide("rising", "UKHO", "High", "15:42", 3.10, 2.7), daylight: { remaining_min: 392, progress: 0.56, sunset: "21:18", sunrise: "05:08" },
      sportKeys: ["kitesurf", "wingfoil", "windsurf", "surf", "sup", "seaswim"] }),
    mkSpot({ name: "Avon Beach", water_type: "sea", lat: 50.736, lon: -1.733, now_time: "13:00", seed: 37,
      wind_dir: 96, wind_kn: 11.5, gust_kn: 17.2, wave: 0.6, swell: 0.4, swellP: 5.4, waterT: 18.3,
      tide: mkTide("falling", "UKHO", "Low", "14:20", 0.70, 1.3), daylight: { remaining_min: 402, progress: 0.54, sunset: "21:19", sunrise: "05:09" },
      sportKeys: ["wingfoil", "kitesurf", "surf", "seaswim", "sup"] }),
    mkSpot({ name: "Sandbanks", water_type: "sea", lat: 50.687, lon: -1.943, now_time: "13:00", seed: 59,
      wind_dir: 110, wind_kn: 9.0, gust_kn: 15.5, wave: 0.5, swell: 0.35, swellP: 5.0, waterT: 17.5,
      tide: mkTide("rising", "Open-Meteo", "High", "16:05", 2.20, 3.0), daylight: { remaining_min: 410, progress: 0.53, sunset: "21:20", sunrise: "05:10" },
      sportKeys: ["wingfoil", "seaswim", "sup", "kitesurf", "surf"] }),
  ];

  /* sun elevation (-1..1) at rel-hour from now, from the spot's sun times */
  function sunElev(spot, rel) {
    const start = parseInt(spot.now_time, 10);
    const toH = (t) => { const [h, m] = t.split(":").map(Number); return h + m / 60; };
    const sr = toH(spot.daylight.sunrise), ss = toH(spot.daylight.sunset), dl = ss - sr;
    let t = (start + rel) % 24;
    if (t >= sr && t <= ss) return Math.sin(Math.PI * (t - sr) / dl);
    const nt = t < sr ? t + 24 : t;
    return -0.5 * Math.sin(Math.PI * (nt - ss) / ((sr + 24) - ss));
  }

  const FAC_ORDER = ["wind", "gust", "direction", "wave", "swell", "temp", "tide"];
  const FAC_LABEL = { wind: "Wind", gust: "Gust", direction: "Direction", wave: "Wave", swell: "Swell", temp: "Water", tide: "Tide" };
  function facVal(key, met) {
    switch (key) {
      case "wind": return f1(met.wind_kn) + " kn";
      case "gust": return f1(met.gust_kn) + " kn";
      case "direction": return cardOf(met.wind_dir_deg) || "—";
      case "wave": return met.wave_height_m != null ? f1(met.wave_height_m) + " m" : "—";
      case "swell": return met.swell_height_m != null ? f1(met.swell_height_m) + " m" + (met.swell_period_s != null ? " · " + f1(met.swell_period_s) + "s" : "") : "—";
      case "temp": return met.water_temp_c != null ? f1(met.water_temp_c) + "°" : "—";
      case "tide": return cap(met.tide_state) + (met.tide_level != null ? " · " + f1(met.tide_level, 1) + "m" : "");
      default: return "";
    }
  }

  window.SW = { SPOTS, VERDICT, LABELS, SYM, ICON, ICON_DEFS, vc, vcw, cardOf, f1, cap, facCol, ring, compass, kitArc, mapMosaic, sunElev, FAC_ORDER, FAC_LABEL, facVal };
})();
