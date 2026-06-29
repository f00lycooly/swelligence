/* ============================================================================
   NOW-view redesign — three interactive timeline treatments.
   Shared chrome (header / sport medallions / spot tabs) is identical across all
   three so the ONLY variable on show is how you focus an hour in the 24h
   outlook. Each frame owns independent state. Hour changes patch dynamic nodes
   via paint(); sport/spot/block changes do a cheap full re-render.
   ========================================================================== */
(function () {
  const SW = window.SW, SPOTS = SW.SPOTS;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  /* ---- shared builders ---- */
  function daylight(spot) {
    const dl = spot.daylight, h = Math.floor(dl.remaining_min / 60), m = dl.remaining_min % 60;
    const p = clamp(dl.progress, 0, 1), ang = p * Math.PI;
    const sx = (55 - 47 * Math.cos(ang)).toFixed(1), sy = (46 - 47 * Math.sin(ang)).toFixed(1);
    return `<div class="dayrow">
      <svg viewBox="0 0 110 52" class="day-svg"><path d="M8 46 A47 47 0 0 1 102 46" class="day-t"/>
        <path d="M8 46 A47 47 0 0 1 ${sx} ${sy}" class="day-a"/><circle cx="${sx}" cy="${sy}" r="5" class="day-s"/></svg>
      <div class="day-m"><span class="k">Daylight left</span><b>${h}h ${m}m</b><span class="s">sunset ${dl.sunset}</span></div>
    </div>`;
  }
  function chrome(spot, sportKey) {
    const meds = spot.sports.map((s) => {
      const sc = s.now.score, col = SW.vcw(s.now.verdict), on = s.sport === sportKey;
      return `<button class="med ${on ? "on" : ""}" data-sport="${s.sport}">
        <div class="med-r">${SW.ring(sc, col, 50, 5)}<div class="med-i">${SW.ICON(s.sport)}<span style="color:${col}">${sc}</span></div></div>
        <div class="med-l">${s.label}</div></button>`;
    }).join("");
    const tabs = SPOTS.map((x, i) => {
      const v = Math.max(...x.sports.map((y) => y.now.score)), on = x === spot;
      return `<button class="tab ${on ? "on" : ""}" data-spot="${i}">
        <div class="tn"><span class="tdot"></span>${x.name}</div>
        <div class="tw"><span>${x.water_type}</span><b>${v}</b></div></button>`;
    }).join("");
    const hdr = `<div class="hdr"><div class="hid"><div class="logo">S</div>
        <div><div class="hnm">${spot.name}</div>
          <div class="hsub"><b>${spot.water_type}</b> · ${spot.latitude.toFixed(3)}, ${spot.longitude.toFixed(3)} · Open-Meteo</div></div></div>
      <div class="hctrl"><div class="hnow"><span class="pulse"></span><div><b>${spot.now_time}</b><span>live</span></div></div>
        <div class="seg"><button class="on">Now</button><button>Week</button></div></div></div>`;
    return { hdr, meds: `<div class="sports">${meds}</div>`, tabs: `<div class="tabs">${tabs}</div>` };
  }
  const tile = (label, key, unit, subKey, cls) =>
    `<div class="tile ${cls || ""}"><div class="t-k">${label}</div>
      <div class="t-v"><b data-dyn="${key}">—</b>${unit ? `<small>${unit}</small>` : ""}</div>
      ${subKey ? `<div class="t-s" data-dyn="${subKey}"></div>` : ""}</div>`;
  function barRange(sport, from, to) {
    let s = "";
    for (let i = from; i <= to; i++) { const h = sport.hourly[i]; s += `<button class="bar ${i === 0 ? "now" : ""}" data-hour="${i}" style="--h:${Math.max(6, h.score)}%;--c:${SW.vcw(h.verdict)}"></button>`; }
    return s;
  }

  /* ============================ VARIANT BODIES ============================ */
  function skySvg(spot) {
    const yOf = (e) => (50 - e * 30).toFixed(2), xOf = (r) => (r / 24 * 100).toFixed(2);
    const pts = []; for (let r = 0; r <= 24; r += 0.5) pts.push(`${xOf(r)},${yOf(SW.sunElev(spot, r))}`);
    const start = parseInt(spot.now_time, 10), toH = (t) => { const [h, m] = t.split(":").map(Number); return h + m / 60; };
    const ssRel = ((toH(spot.daylight.sunset) - start) + 24) % 24, srRel = ((toH(spot.daylight.sunrise) - start) + 24) % 24;
    return `<svg class="sky" viewBox="0 0 100 100" preserveAspectRatio="none">
      <line class="sky-horizon" x1="0" y1="${yOf(0)}" x2="100" y2="${yOf(0)}"/>
      <line class="sky-tick" x1="${xOf(ssRel)}" y1="2" x2="${xOf(ssRel)}" y2="98"/>
      <line class="sky-tick" x1="${xOf(srRel)}" y1="2" x2="${xOf(srRel)}" y2="98"/>
      <polyline class="sky-line" points="${pts.join(" ")}"/></svg>`;
  }
  function dayGradient(spot) {
    const start = parseInt(spot.now_time, 10), toH = (t) => { const [h, m] = t.split(":").map(Number); return h + m / 60; };
    const ss = ((toH(spot.daylight.sunset) - start) + 24) % 24 / 24 * 100, sr = ((toH(spot.daylight.sunrise) - start) + 24) % 24 / 24 * 100;
    const day = "rgba(86,194,224,.32)", night = "rgba(9,18,34,.66)", tw = "rgba(246,170,60,.45)";
    return `linear-gradient(90deg,${day} 0%,${day} ${(ss-2.5).toFixed(1)}%,${tw} ${ss.toFixed(1)}%,${night} ${(ss+3).toFixed(1)}%,${night} ${(sr-3).toFixed(1)}%,${tw} ${sr.toFixed(1)}%,${day} ${(sr+2.5).toFixed(1)}%,${day} 100%)`;
  }

  function bodyScrubber(spot, sport) {
    const col = SW.vcw(sport.now.verdict);
    const axis = sport.hourly.map((h, i) => `<span>${i % 3 === 0 ? h.hh.slice(0, 2) : ""}</span>`).join("");
    const facRows = SW.FAC_ORDER.filter((k) => sport.now.factors[k] != null).map((k) =>
      `<div class="fac" data-fac="${k}"><span class="fac-l">${SW.FAC_LABEL[k]}</span><span class="fac-bar"><i></i></span><span class="fac-v" data-fac-v>—</span></div>`).join("");
    const kitHtml = sport.now.kit
      ? SW.kitArc(sport.now.kit, sport.sport)
      : `<div class="bestp"><span class="bp-k">No kit</span><b>best ${sport.best.hh}</b></div>`;
    const start = parseInt(spot.now_time, 10), toH = (t) => { const [h, m] = t.split(":").map(Number); return h + m / 60; };
    const ssX = ((toH(spot.daylight.sunset) - start) + 24) % 24 / 24 * 100, srX = ((toH(spot.daylight.sunrise) - start) + 24) % 24 / 24 * 100;
    return `<div class="body v-scrub">
      <div class="sc-hero">
        <div class="sc-map">
          ${SW.mapMosaic(spot.latitude, spot.longitude)}
          <div class="vign"></div>
          <div class="sc-cmp bodycmp">${SW.compass(spot.current.wind_dir_deg, col, 92)}</div>
          <div class="wband"><div class="wfrom">Wind from <span data-dyn="winddir">—</span></div>
            <div class="wxy"><i data-dyn="wind">—</i> kn · gust <i data-dyn="gust">—</i></div></div>
        </div>
        <div class="sc-readcol">
          <div class="sc-read">
            <div class="sc-cell">
              <div class="sc-cell-k">Suitability</div>
              <div class="scorering">${SW.ring(sport.now.score, col, 78, 8)}<div class="sc-num" data-dyn="score" data-color>—</div></div>
            </div>
            <div class="sc-cell">
              <div class="sc-cell-k">Kit</div>
              <div class="sc-kit" data-kit>${kitHtml}</div>
            </div>
            <div class="sc-cell">
              <div class="sc-cell-k">Safety</div>
              <div class="sc-safety"><svg viewBox="0 0 60 60" class="safety-ph"><circle cx="30" cy="30" r="24"/></svg><span class="ph-note">conditions<br>module</span></div>
            </div>
          </div>
          <div class="sc-facs">${facRows}</div>
        </div>
      </div>
      <div class="chartwrap">
        <div class="ch-h"><span class="k">Outlook · next 24h</span><span class="hint"><b data-dyn="time">--:--</b><span data-dyn="rel">NOW</span></span></div>
        <div class="chart" data-chart>
          <div class="daylane" style="background:${dayGradient(spot)}">
            <span class="dl-lbl">Daylight</span>
            ${skySvg(spot)}
            <span class="dl-t" style="left:${ssX.toFixed(1)}%">↓ ${spot.daylight.sunset}</span>
            <span class="dl-t" style="left:${srX.toFixed(1)}%">↑ ${spot.daylight.sunrise}</span>
            <div class="sunmark"></div>
          </div>
          <div class="barwrap">
            <div class="bars">${barRange(sport, 0, 23)}</div>
          </div>
        </div>
        <div class="axis">${axis}</div>
      </div>
    </div>`;
  }

  function bodyFilmstrip(spot, sport) {
    const col = SW.vcw(sport.now.verdict);
    const chips = sport.hourly.map((h, i) => {
      const c = SW.vcw(h.verdict);
      return `<button class="chip ${i === 0 ? "now" : ""}" data-hour="${i}">
        <span class="chip-h">${h.hh.slice(0, 2)}</span>
        <span class="chip-bar"><i style="height:${Math.max(8, h.score)}%;background:${c}"></i></span>
        <span class="chip-s" style="color:${c}">${h.score}</span></button>`;
    }).join("");
    return `<div class="body v-film">
      <div class="hero">
        <div class="hero-l"><div class="hero-time"><b data-dyn="time">--:--</b><span data-dyn="rel" data-color>NOW</span></div>
          <div class="hero-vd" data-dyn="verdict" data-color>—</div>
          <div class="hero-note" data-dyn="note">—</div></div>
        <div class="scorering big">${SW.ring(sport.now.score, col, 116, 10)}<div class="hero-num" data-dyn="score" data-color>—</div></div>
      </div>
      <div class="hero-met">
        ${tile("Wind", "wind", "kn", "windsub")}
        ${tile("Gust", "gust", "kn", "gustsub", "amber")}
        ${tile("Wave", "wave", "m", "wavesub")}
        ${tile("Water", "watertemp", "°C", "tidestate")}
      </div>
      <div class="ch-h film-h"><span class="k">Outlook · next 24h</span><span class="hint" data-dyn="pos">step through the hours</span></div>
      <div class="film-wrap">
        <button class="chev" data-step="-1" aria-label="earlier">‹</button>
        <div class="film" data-film>${chips}</div>
        <button class="chev" data-step="1" aria-label="later">›</button>
      </div>
    </div>`;
  }

  function bodyBlocks(spot, sport, hour) {
    const ab = Math.floor((hour || 0) / 4);
    const blocks = [];
    for (let b = 0; b < 6; b++) {
      const from = b * 4, to = from + 3;
      let peak = -1, pcol = "";
      const minis = [];
      for (let i = from; i <= to; i++) { const h = sport.hourly[i]; const c = SW.vcw(h.verdict); if (h.score > peak) { peak = h.score; pcol = c; } minis.push(`<i style="height:${Math.max(10, h.score)}%;background:${c}"></i>`); }
      const rng = `${sport.hourly[from].hh.slice(0, 2)}–${sport.hourly[to].hh.slice(0, 2) === "00" ? "24" : String((parseInt(sport.hourly[to].hh) + 1) % 24).padStart(2, "0")}`;
      blocks.push(`<button class="blk ${b === ab ? "on" : ""}" data-block="${b}">
        <span class="blk-rng">${rng}</span><span class="blk-bars">${minis.join("")}</span>
        <span class="blk-pk" style="color:${pcol}">${peak}</span></button>`);
    }
    // detail hour bars for the active block
    let hours = "";
    for (let i = ab * 4; i <= ab * 4 + 3; i++) { const h = sport.hourly[i]; hours += `<button class="bhour" data-hour="${i}" style="--c:${SW.vcw(h.verdict)}"><span class="bh-bar"><i style="height:${Math.max(8, h.score)}%"></i></span><span class="bh-h">${h.hh.slice(0, 2)}h</span></button>`; }
    return `<div class="body v-blk">
      <div class="ch-h"><span class="k">Outlook · next 24h — tap a window</span><span class="hint">then a single hour</span></div>
      <div class="blockrow">${blocks.join("")}</div>
      <div class="bd">
        <div class="bd-head"><div><div class="bd-time"><b data-dyn="time">--:--</b><span data-dyn="rel" data-color>NOW</span></div>
            <div class="bd-vd" data-dyn="verdict" data-color>—</div></div>
          <div class="bd-score" data-dyn="score" data-color>—</div></div>
        <div class="bd-hours" data-bhours>${hours}</div>
        <div class="bd-met">
          ${tile("Wind", "wind", "kn", "windsub")}
          ${tile("Gust", "gust", "kn", "gustsub", "amber")}
          ${tile("Wave", "wave", "m", "wavesub")}
          ${tile("Tide", "tidestate", "", "tidesub")}
        </div>
      </div>
    </div>`;
  }

  /* ============================ CONTROLLER ============================ */
  function mountFrame(el, variant) {
    const st = { spotIdx: 0, sport: null, hour: 0 };
    const refs = () => { const spot = SPOTS[st.spotIdx]; const sport = spot.sports.find((s) => s.sport === st.sport) || spot.sports[0]; st.sport = sport.sport; return { spot, sport }; };
    const peakHourOfBlock = (b) => { const { sport } = refs(); let bi = b * 4, bs = -1; for (let i = b * 4; i <= b * 4 + 3; i++) if (sport.hourly[i].score > bs) { bs = sport.hourly[i].score; bi = i; } return bi; };

    function render() {
      const { spot, sport } = refs();
      const c = chrome(spot, sport.sport);
      const body = variant === "scrubber" ? bodyScrubber(spot, sport) : variant === "filmstrip" ? bodyFilmstrip(spot, sport) : bodyBlocks(spot, sport, st.hour);
      el.innerHTML = `<div class="card720">${c.hdr}${c.meds}${body}${c.tabs}</div>`;
      paint();
    }
    function paint() {
      const { spot, sport } = refs();
      const met = spot.hourly_met[st.hour], hp = sport.hourly[st.hour], col = SW.vcw(hp.verdict);
      // limiting factor = lowest-scoring factor this hour
      let lk = null, lo = 999; for (const k in hp.factors) if (hp.factors[k] < lo) { lo = hp.factors[k]; lk = k; }
      const limit = lk ? "limited by " + (SW.FAC_LABEL[lk] || lk).toLowerCase() : "";
      const V = {
        time: hp.hh, rel: st.hour === 0 ? "NOW" : "+" + st.hour + "h", verdict: hp.verdict, score: hp.score,
        wind: SW.f1(met.wind_kn), gust: SW.f1(met.gust_kn),
        wave: met.wave_height_m != null ? SW.f1(met.wave_height_m) : "—",
        winddir: SW.cardOf(met.wind_dir_deg) || "—", windsub: SW.cardOf(met.wind_dir_deg) || "",
        gustsub: "peak", wavesub: met.swell_period_s != null ? SW.f1(met.swell_period_s) + " s" : "",
        tidestate: SW.cap(met.tide_state), tidesub: met.tide_level != null ? SW.f1(met.tide_level, 2) + " m" : "",
        watertemp: met.water_temp_c != null ? SW.f1(met.water_temp_c) : "—",
        limit, pos: st.hour === 0 ? "now · " + hp.hh : "+" + st.hour + "h · " + hp.hh,
        note: st.hour === 0 ? (limit || "live conditions") : "modelled · +" + st.hour + "h",
      };
      el.querySelectorAll("[data-dyn]").forEach((n) => { const k = n.dataset.dyn; if (k in V) n.textContent = V[k]; });
      el.querySelectorAll("[data-color]").forEach((n) => { n.style.color = col; });
      el.querySelectorAll("[data-color-bg]").forEach((n) => { n.style.background = col; });
      el.querySelectorAll("[data-hour]").forEach((n) => n.classList.toggle("sel", +n.dataset.hour === st.hour));
      el.querySelectorAll("[data-block]").forEach((n) => n.classList.toggle("on", +n.dataset.block === Math.floor(st.hour / 4)));
      // factor breakdown bars (per hour: score drives the bar, met drives the reading)
      el.querySelectorAll("[data-fac]").forEach((row) => {
        const k = row.dataset.fac, fv = hp.factors[k];
        const bar = row.querySelector(".fac-bar i"); if (bar) { bar.style.width = (fv || 0) + "%"; bar.style.background = SW.facCol(fv); }
        const val = row.querySelector("[data-fac-v]"); if (val) val.textContent = SW.facVal(k, met);
      });
      // kit arc (windy sports only — rebuilt per hour)
      const kitc = el.querySelector("[data-kit]");
      if (kitc && hp.kit) kitc.innerHTML = SW.kitArc(hp.kit, sport.sport);
      const arc = el.querySelector(".scorering .ra");
      if (arc) { const r = +arc.closest(".ringsvg").dataset.r, circ = 2 * Math.PI * r; arc.style.strokeDashoffset = (circ * (1 - hp.score / 100)).toFixed(1); arc.setAttribute("stroke", col); }
      const ndl = el.querySelector(".bodycmp .needle");
      if (ndl) { ndl.setAttribute("transform", `rotate(${((met.wind_dir_deg + 180) % 360)})`); ndl.setAttribute("stroke", col); ndl.setAttribute("fill", col); }
      const sm = el.querySelector(".sunmark");
      if (sm) { const e = SW.sunElev(spot, st.hour + 0.5), day = e >= 0;
        sm.style.left = ((st.hour + 0.5) / 24 * 100).toFixed(2) + "%";
        sm.style.top = (50 - e * 30).toFixed(2) + "%";
        sm.classList.toggle("night", !day); sm.textContent = day ? "☀︎" : "☾"; }
    }
    function scrollFilm() {
      const film = el.querySelector("[data-film]"); if (!film) return;
      const chip = film.querySelector(`.chip[data-hour="${st.hour}"]`); if (!chip) return;
      film.scrollTo({ left: chip.offsetLeft - film.clientWidth / 2 + chip.offsetWidth / 2, behavior: "smooth" });
    }

    el.addEventListener("click", (e) => {
      const t = e.target.closest("[data-sport],[data-spot],[data-block],[data-hour],[data-step]");
      if (!t) return;
      if (t.dataset.spot != null) { st.spotIdx = +t.dataset.spot; st.sport = null; st.hour = 0; render(); }
      else if (t.dataset.sport != null) { st.sport = t.dataset.sport; st.hour = 0; render(); }
      else if (t.dataset.step != null) { st.hour = clamp(st.hour + (+t.dataset.step), 0, 23); paint(); scrollFilm(); }
      else if (t.dataset.block != null) { st.hour = peakHourOfBlock(+t.dataset.block); render(); }
      else if (t.dataset.hour != null) { st.hour = +t.dataset.hour; paint(); if (variant === "filmstrip") scrollFilm(); }
    });

    if (variant === "scrubber") {
      let dragging = false;
      const hourAt = (clientX) => { const chart = el.querySelector("[data-chart]"); if (!chart) return st.hour; const r = chart.getBoundingClientRect(); return clamp(Math.floor((clientX - r.left) / r.width * 24), 0, 23); };
      el.addEventListener("pointerdown", (e) => {
        const chart = e.target.closest("[data-chart]"); if (!chart) return;
        dragging = true; chart.setPointerCapture?.(e.pointerId);
        st.hour = hourAt(e.clientX); paint(); e.preventDefault();
      });
      el.addEventListener("pointermove", (e) => { if (!dragging) return; const h = hourAt(e.clientX); if (h !== st.hour) { st.hour = h; paint(); } });
      el.addEventListener("pointerup", () => { dragging = false; });
      el.addEventListener("pointercancel", () => { dragging = false; });
    }

    render();
  }

  window.mountSwell = mountFrame;
})();
