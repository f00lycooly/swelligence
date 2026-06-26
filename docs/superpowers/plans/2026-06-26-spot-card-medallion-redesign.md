# Spot Card Redesign — Medallion Selector + Graphical Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the already-computed wing/kite-size recommendation on the `spot` Lovelace card and consolidate the sport selector + hero into one medallion, with a graphical colour-coded kit gauge, a wind-direction compass on the map, and data-backed fillers for the blank space.

**Architecture:** The Home Assistant integration computes everything and exposes ready-to-render data points via the `swelligence.get_spot_detail` service; the card is a thin renderer (vanilla JS, no build step). Two Python edits widen the service payload (kit + daylight); four card edits restructure the right column (medallion selector, detail card) and enrich the left column (daylight arc) and map (wind compass).

**Tech Stack:** Python 3.10+ (HA custom integration, pure-logic core), dependency-free vanilla JS + SVG/CSS for the card. Tests: `pytest` (pure suite, HA stubbed via `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-06-26-spot-card-medallion-redesign-design.md`

## Global Constraints

- **Thin renderer:** all semantics (kit fields, daylight remaining, wind suitability) are produced by the integration as data points; the card only formats/colours. No new derivation in card JS beyond layout + colour mapping.
- **Pure logic stays pure:** new computation goes in modules with no `homeassistant` import (`forecast.py`) and is unit-tested in `tests/`. HA-touching code stays in `__init__.py` (already guarded by `tests_ha/test_ha_guard.py`).
- **Units:** sizes in **m²**, speeds **knots**, heights **metres**, temps **°C**, directions **degrees ("from")**. Unknown = `None`, never `0`.
- **Colours (card):** use existing verdict palette + theme accent — `vc("good")`=`#9bcf5f`, `vc("marg")`=`#f0a83d`, `vc("poor")`=`#e8593a`, accent `var(--ac)` (= HA `--primary-color`). Kit/direction grey = `var(--mut)`. (The companion mockups used orange as their own theme accent; the real card uses the HA theme accent — do not hard-code orange.)
- **Card bundling:** `custom_components/swelligence/frontend/swelligence-card.js` ships inside the integration and is auto-served + cache-busted by manifest version. No separate copy.
- **Run `pytest` green before every commit that touches Python.** Commit `.tool-output/` updates alongside per repo M9 discipline if present.

---

## File Structure

- `custom_components/swelligence/forecast.py` — **modify**: add pure `daylight_remaining()` helper alongside `anchor_to_now`/`_in_daylight`.
- `custom_components/swelligence/__init__.py` — **modify** `_spot_detail()`: add `now.kit` per sport + spot-level `daylight`.
- `custom_components/swelligence/frontend/swelligence-card.js` — **modify**: replace `_pills`+`_selNow`/`_selWeek` with `_medallions`+`_detail`; add `_kitArc`, `_daylight`, colour helpers; extend `_mapHero` with the wind compass; add CSS.
- `tests/test_forecast.py` — **modify**: add tests for `daylight_remaining()`.

---

## Task 1: Pure `daylight_remaining()` helper

**Files:**
- Modify: `custom_components/swelligence/forecast.py` (add function near `_in_daylight`, ~line 57)
- Test: `tests/test_forecast.py`

**Interfaces:**
- Consumes: `SpotForecast.current()`, `SpotForecast.daily_sun` (dict keyed by `YYYY-MM-DD` → `{"sunrise": datetime|None, "sunset": datetime|None}`, naive-local datetimes), `SpotForecast.source_meta["utc_offset_seconds"]`.
- Produces: `daylight_remaining(forecast, *, now=None) -> dict | None` returning `{"sunrise": "HH:MM", "sunset": "HH:MM", "remaining_min": int}` or `None` when no sun data.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast.py` (reuse the module's existing forecast-builder helpers; construct a `SpotForecast` the same way the existing tests in this file do — match their fixture style):

```python
from datetime import datetime, timezone, timedelta
from custom_components.swelligence.forecast import daylight_remaining
from custom_components.swelligence.providers.base import ForecastPoint, SpotForecast


def _sun_forecast():
    # Naive-local points starting "now" (07:00 local); +1h utc offset.
    pts = [ForecastPoint(time=datetime(2026, 6, 26, 7, 0)),
           ForecastPoint(time=datetime(2026, 6, 26, 8, 0))]
    return SpotForecast(
        points=pts,
        daily_sun={"2026-06-26": {"sunrise": datetime(2026, 6, 26, 5, 0),
                                  "sunset": datetime(2026, 6, 26, 21, 18)}},
        source_meta={"utc_offset_seconds": 3600},
    )


def test_daylight_remaining_counts_minutes_to_sunset():
    fc = _sun_forecast()
    # Real UTC now = 16:06Z -> +1h offset -> 17:06 local; sunset 21:18 -> 4h12m = 252 min.
    now = datetime(2026, 6, 26, 16, 6, tzinfo=timezone.utc)
    out = daylight_remaining(fc, now=now)
    assert out == {"sunrise": "05:00", "sunset": "21:18", "remaining_min": 252}


def test_daylight_remaining_clamps_after_sunset():
    fc = _sun_forecast()
    now = datetime(2026, 6, 26, 22, 0, tzinfo=timezone.utc)  # 23:00 local, past sunset
    assert daylight_remaining(fc, now=now)["remaining_min"] == 0


def test_daylight_remaining_none_without_sun_data():
    fc = SpotForecast(points=[ForecastPoint(time=datetime(2026, 6, 26, 7, 0))],
                      daily_sun={}, source_meta={})
    assert daylight_remaining(fc, now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)) is None
```

> If `ForecastPoint`/`SpotForecast` require more fields, copy the construction pattern already used by other tests in `tests/test_forecast.py` rather than inventing fields.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_forecast.py -k daylight -v`
Expected: FAIL — `ImportError: cannot import name 'daylight_remaining'`.

- [ ] **Step 3: Write minimal implementation**

Add to `custom_components/swelligence/forecast.py` after `_in_daylight`:

```python
def daylight_remaining(forecast: SpotForecast, *, now: datetime | None = None) -> dict | None:
    """Sunrise/sunset (HH:MM) and minutes of daylight left, for the current day.

    Now-anchored: mirrors ``anchor_to_now``'s offset handling so the "now"
    reference is in the forecast's naive-local frame. Returns ``None`` when the
    day has no sun data. ``remaining_min`` is clamped at 0 after sunset.
    """
    if forecast.current() is None:
        return None
    offset = (forecast.source_meta or {}).get("utc_offset_seconds", 0) or 0
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    now_local = (base.astimezone(timezone.utc) + timedelta(seconds=offset)).replace(tzinfo=None)
    info = forecast.daily_sun.get(now_local.date().isoformat())
    if not info or not info.get("sunrise") or not info.get("sunset"):
        return None
    sunrise, sunset = _naive(info["sunrise"]), _naive(info["sunset"])
    remaining = int(max(0, (sunset - now_local).total_seconds() // 60))
    return {
        "sunrise": sunrise.strftime("%H:%M"),
        "sunset": sunset.strftime("%H:%M"),
        "remaining_min": remaining,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_forecast.py -k daylight -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full pure suite**

Run: `pytest`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add custom_components/swelligence/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): add pure daylight_remaining helper"
```

---

## Task 2: Surface kit + daylight into the spot-detail payload

**Files:**
- Modify: `custom_components/swelligence/__init__.py` — `_spot_detail()` (~lines 219–268) and its imports.

**Interfaces:**
- Consumes: `res.kit` (a `KitRecommendation` with `.owned_size_m2`, `.ideal_size_m2`, `.power`), `POWER_NA` from `.sizing`, `daylight_remaining` from `.forecast`.
- Produces: each sport's `now` dict gains `"kit"` = `{"rig_m2", "ideal_m2", "power"}` or `None`; the spot dict gains `"daylight"` = the `daylight_remaining()` result (or `None`).

- [ ] **Step 1: Add imports**

At the top of `custom_components/swelligence/__init__.py`, extend the existing imports:

```python
from .forecast import daylight_remaining  # add to the existing .forecast import line
from .sizing import POWER_NA              # add to the existing .sizing import line
```

(Use the existing import statements for those modules — append the names, don't duplicate the lines.)

- [ ] **Step 2: Add `kit` to each sport's `now` block**

In `_spot_detail()`, inside the `for sport, res in data.results.items():` loop, the `sports.append({...})` call builds `"now": {...}`. Add a `"kit"` key to that `now` dict:

```python
            "now": {
                "score": round(res.now.score), "verdict": res.now.verdict,
                "suitable": res.now.suitable, "factors": res.now.factors,
                "reasons": res.now.reasons, "completeness": res.now.completeness,
                "nudges": res.now.nudges,
                "kit": ({
                    "rig_m2": res.kit.owned_size_m2,
                    "ideal_m2": res.kit.ideal_size_m2,
                    "power": res.kit.power,
                } if res.kit and res.kit.power != POWER_NA else None),
            },
```

- [ ] **Step 3: Add spot-level `daylight`**

In the same function, the `return { ... }` that builds the spot dict — add a `"daylight"` key:

```python
    return {
        "name": coordinator.spot["name"],
        "water_type": coordinator.spot.get("water_type", "sea"),
        "latitude": coordinator.spot["latitude"],
        "longitude": coordinator.spot["longitude"],
        "now_time": now_pt.time.strftime("%H:%M") if now_pt else None,
        "daylight": daylight_remaining(forecast),
        "tide": tide_state(forecast),
        "current": {f: getattr(now_pt, f, None) for f in _NOW_FIELDS} if now_pt else {},
        "sports": sports,
    }
```

- [ ] **Step 4: Verify the HA guard + pure suite still pass**

Run: `pytest`
Run: `pip install -r requirements-ha-test.txt && pytest tests_ha -o asyncio_mode=auto`
Expected: PASS. (`_spot_detail` is HA-glue with no dedicated unit test today; the kit fields are direct reads of the already-tested `KitRecommendation` from `tests/test_sizing.py`, and `daylight` is covered by Task 1. Functional confirmation happens in the card-render check in Task 4/5.)

- [ ] **Step 5: Commit**

```bash
git add custom_components/swelligence/__init__.py
git commit -m "feat(spot-detail): expose kit recommendation + daylight in now payload"
```

---

## Task 3: Card — medallion ring-row selector

Replaces the separate `_pills` selector and `_selNow`/`_selWeek` hero with one ring-row where each sport is a score medallion (ring + icon + score) and the active one is outlined.

**Files:**
- Modify: `custom_components/swelligence/frontend/swelligence-card.js`

**Interfaces:**
- Consumes: existing helpers `_ring(score, col, size, sw)`, `ICON(sport)`, `vcw(verdict)`, `this._peak(sp)`, the per-sport objects `sportsAll[i]` with `.sport`, `.label`, `.now.{score,verdict}`, `.daily`.
- Produces: `_medallions(sports, active, view)` returning the ring-row HTML; consumed by `_spot()`.

- [ ] **Step 1: Add the `_medallions` method**

Add near the old `_pills` method (which it replaces):

```javascript
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
```

- [ ] **Step 2: Wire `_medallions` into `_spot()` and drop the old pieces**

In `_spot()`, the `right` composition currently calls `this._pills(...)` then `this._selNow(sp)` / `this._selWeek(sp)`. Replace so the medallion row leads and the old hero blocks are gone (the detail card from Task 4 takes the hero's place):

```javascript
    const right = view === "now"
      ? this._medallions(sportsAll, pi, view) + this._detail(sp, view) + this._hourlyTL(sp)
        + `<div class="sd-strip">${this._nowStrip(c)}</div>`
        + (this._config.show_factors !== false && facs ? `<div class="sd-facs">${facs}</div>` : "")
      : this._medallions(sportsAll, pi, view) + this._detail(sp, view) + this._dayRows(sp);
```

And remove the now-unused `${this._pills(sportsAll, pi, view)}` from the `sd-sportcol` column wrapper (the column should contain only `${right}`):

```javascript
        <div class="sd-col sd-sportcol">${right}</div>
```

> Leave `_pills`, `_selNow`, `_selWeek` definitions deletable — remove them once Task 4 lands `_detail` so no reference dangles. (They are only referenced from `_spot`.)

- [ ] **Step 3: Add CSS for the medallion row**

In the card's `<style>` block (near the old `.sd-pills` rules), add:

```css
.sd-meds{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:8px;}
.sd-med{display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;padding:4px 2px;border-radius:12px;border:1px solid transparent;}
.sd-med.on{border-color:var(--ac);background:color-mix(in srgb,var(--ac) 10%,transparent);}
.sd-medr{position:relative;width:58px;height:58px;display:grid;place-items:center;}
.sd-medr .sd-ring-svg{position:absolute;inset:0;width:100%;height:100%;}
.sd-medi{display:grid;place-items:center;z-index:2;}
.sd-medi .icon{width:13px;height:13px;color:var(--mut);}
.sd-med.on .sd-medi .icon{color:var(--ink);}
.sd-meds-n{font-weight:800;font-size:15px;line-height:1;}
.sd-medl{font-size:10px;font-weight:600;color:var(--mut);}
.sd-med.on .sd-medl{color:var(--ink);}
```

- [ ] **Step 4: Render-check (deploy to live HA temp dashboard, user-gated)**

This card has no JS unit harness; verify by rendering in HA. With user confirmation to reload the integration:

```bash
rsync -a --delete --exclude='__pycache__' \
  custom_components/swelligence/ /appdata/homeassistant/custom_components/swelligence/
```

Then (user reloads the Swelligence integration), open `https://ha.bagofholding.co.uk/dashboard-temp/0` via the browser MCP and screenshot. Expected: a row of sport medallions (ring + icon + score), the selected one outlined; tapping a medallion changes the active sport. Compare against the approved mockup (`final-design.html`).

- [ ] **Step 5: Commit**

```bash
git add custom_components/swelligence/frontend/swelligence-card.js
git commit -m "feat(card): medallion ring-row sport selector (replaces pills + hero)"
```

---

## Task 4: Card — detail card with arc-gauge kit + limiting factor + factor bars

**Files:**
- Modify: `custom_components/swelligence/frontend/swelligence-card.js`

**Interfaces:**
- Consumes: `sp.now.kit` `{rig_m2, ideal_m2, power}` (from Task 2), `sp.now.reasons` (string list), `sp.now.factors` (object of name→0-100), `sp.best`, helpers `vcw`, `_factors(now)`, `ICON(sport)`.
- Produces: `_detail(sp, view)`, `_kitArc(kit, sport)`, colour helpers `_powerCol(power)` and `_facCol(n)`.

- [ ] **Step 1: Add colour helpers**

Add near the other top-level const helpers (after `vcw`):

```javascript
// kit power verdict -> palette colour
const POWER_COL = { ideal: "#9bcf5f", underpowered: "#f0a83d", overpowered: "#e8593a" };
const powerCol = (p) => POWER_COL[p] || "var(--mut)";       // no_kit / unknown -> grey
const facCol = (n) => (n == null ? "var(--mut)" : n >= 67 ? vc("good") : n >= 34 ? vc("marg") : vc("poor"));
```

- [ ] **Step 2: Add the `_kitArc` method**

A 0–270° style arc gauge; the needle angle maps the power verdict to a position (under = left, ideal = centre, over = right), coloured by `powerCol`. Renders a grey "—" state when `kit` is null.

```javascript
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
```

- [ ] **Step 3: Add the `_detail` method**

Combines verdict + best window (left), `_kitArc` (right), then a limiting-factor line (from `reasons`, falling back to the lowest `factors` entry) and the existing `_factors` bars.

```javascript
  _detail(sp, view) {
    const now = sp.now || {}, col = vcw(now.verdict), best = sp.best;
    const bestT = best ? (best.time || (best.in_hours != null ? "+" + best.in_hours + "h" : "—")) : "—";
    const bestLine = best ? `best <b>${bestT}</b> · ${Math.round(best.score)} ${best.verdict || ""}` : "";
    // Limiting factor: first reason, else lowest-scoring factor name.
    let limit = (now.reasons && now.reasons[0]) || "";
    if (!limit && now.factors) {
      const ent = Object.entries(now.factors).filter(([, v]) => v != null);
      if (ent.length) { const [k] = ent.sort((a, b) => a[1] - b[1])[0]; limit = `limited by ${k}`; }
    }
    const facs = (this._config.show_factors !== false) ? this._factors(now) : "";
    return `<div class="sd-detail">
      <div class="sd-detail-top">
        <div><div class="sd-detail-sp">${sp.label}</div>
          <div class="sd-detail-vd" style="color:${col}">${(now.verdict || "—").toUpperCase()}</div>
          <div class="sd-detail-best">${bestLine}</div></div>
        ${view === "now" ? this._kitArc(now.kit, sp.sport) : ""}
      </div>
      ${view === "now" && limit ? `<div class="sd-detail-lf"><span class="dot" style="background:${col}"></span>${limit}</div>` : ""}
      ${view === "now" && facs ? `<div class="sd-detail-facs">${facs}</div>` : ""}
    </div>`;
  }
```

> Note: this moves the factor bars *inside* the detail card. Remove the separate `<div class="sd-facs">${facs}</div>` append added to `right` in Task 3 Step 2 so factors render once — the `right` composition becomes:
> ```javascript
>     const right = view === "now"
>       ? this._medallions(sportsAll, pi, view) + this._detail(sp, view) + this._hourlyTL(sp)
>         + `<div class="sd-strip">${this._nowStrip(c)}</div>`
>       : this._medallions(sportsAll, pi, view) + this._detail(sp, view) + this._dayRows(sp);
> ```
> (The `facs`/`show_factors` handling now lives entirely in `_detail`; the `const facs = this._factors(...)` line in `_spot()` can be deleted.)

- [ ] **Step 4: Add CSS for the detail card + kit gauge**

```css
.sd-detail{background:var(--panel,#0f1519);border:1px solid var(--line,#283036);border-radius:12px;padding:12px;}
.sd-detail-top{display:flex;align-items:center;justify-content:space-between;gap:10px;}
.sd-detail-sp{font-size:15px;font-weight:800;color:var(--ink);}
.sd-detail-vd{font-weight:700;margin:2px 0 6px;}
.sd-detail-best{font-size:11px;color:var(--mut);} .sd-detail-best b{color:var(--ink);}
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
```

> The existing `.sd-facs`/`.sd-fac` rules already style the factor bars; `_factors` output is reused unchanged inside `.sd-detail-facs`.

- [ ] **Step 5: Remove the now-dead `_pills`/`_selNow`/`_selWeek` methods**

Delete the three method definitions (no remaining references after Tasks 3–4). Confirm with:

Run: `grep -n "_pills\|_selNow\|_selWeek" custom_components/swelligence/frontend/swelligence-card.js`
Expected: no matches.

- [ ] **Step 6: Render-check + commit**

Deploy (rsync as in Task 3 Step 4, user-gated reload), screenshot the temp dashboard. Expected: detail card shows verdict + best window, the arc-gauge kit (green/orange/red/grey per `power`, "Nm²" + "rig · <state>"), the limiting-factor line, and factor bars — matching `final-design.html`. Switch sports via medallions and confirm the kit gauge + limiting factor update.

```bash
git add custom_components/swelligence/frontend/swelligence-card.js
git commit -m "feat(card): detail card with arc-gauge kit, limiting factor, factor bars"
```

---

## Task 5: Card — left-column daylight arc

**Files:**
- Modify: `custom_components/swelligence/frontend/swelligence-card.js`

**Interfaces:**
- Consumes: `d.daylight` `{sunrise, sunset, remaining_min}` (from Task 2).
- Produces: `_daylight(d)` returning the panel HTML; consumed by `_spot()` left column in NOW view.

- [ ] **Step 1: Add the `_daylight` method**

```javascript
  _daylight(d) {
    const dl = d.daylight;
    if (!dl || dl.remaining_min == null) return "";
    const h = Math.floor(dl.remaining_min / 60), m = dl.remaining_min % 60;
    const left = h > 0 ? `${h}h ${m}m` : `${m}m`;
    // Sun position along the arc by fraction of remaining vs a nominal day is not
    // available here; place the sun marker near the arc's current end for a glance.
    return `<div class="sd-day">
      <svg viewBox="0 0 110 52" class="sd-day-svg">
        <path d="M8 46 A47 47 0 0 1 102 46" class="sd-day-track"/>
        <path d="M8 46 A47 47 0 0 1 76 10" class="sd-day-arc"/>
        <circle cx="76" cy="10" r="5" class="sd-day-sun"/>
      </svg>
      <div class="sd-day-meta"><span class="k">Daylight</span><b>${left}</b><span class="s">light left · sunset ${dl.sunset}</span></div>
    </div>`;
  }
```

- [ ] **Step 2: Wire into `_spot()` left column (NOW only)**

`leftLower` currently is `view === "now" ? this._tideModule(d) : this._weekSummary(d, sp)`. Append the daylight panel in NOW view:

```javascript
    const leftLower = view === "now"
      ? this._tideModule(d) + this._daylight(d)
      : this._weekSummary(d, sp);
```

- [ ] **Step 3: Add CSS**

```css
.sd-day{background:var(--panel,#0f1519);border:1px solid var(--line,#283036);border-radius:12px;padding:11px 12px;display:flex;align-items:center;gap:12px;}
.sd-day-svg{width:104px;height:50px;flex:0 0 auto;}
.sd-day-track{fill:none;stroke:color-mix(in srgb,var(--mut) 25%,transparent);stroke-width:3;}
.sd-day-arc{fill:none;stroke:#4ab6ff;stroke-width:3;}
.sd-day-sun{fill:var(--ac);}
.sd-day-meta{display:flex;flex-direction:column;}
.sd-day-meta .k{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);font-weight:700;}
.sd-day-meta b{font-size:15px;font-weight:800;color:var(--ink);}
.sd-day-meta .s{font-size:10px;color:var(--mut);}
```

- [ ] **Step 4: Render-check + commit**

Deploy + screenshot (user-gated). Expected: a daylight panel under the tide in NOW view ("Daylight · Nh Nm · light left · sunset HH:MM"); absent when no sun data. Matches `final-design.html`.

```bash
git add custom_components/swelligence/frontend/swelligence-card.js
git commit -m "feat(card): left-column daylight arc (NOW view)"
```

---

## Task 6: Card — wind compass on the map hero

**Files:**
- Modify: `custom_components/swelligence/frontend/swelligence-card.js` — `_mapHero()` and its call site in `_spot()`.

**Interfaces:**
- Consumes: `c.wind_dir_deg` (the "from" bearing, in `current`), the active sport's `sp.now.factors.direction` (0-100 or absent), helpers `facCol` (Task 4), `cardOf`, `f1`.
- Produces: an SVG compass overlay inside `.sd-map`; `_mapHero` gains a trailing `sp` parameter.

- [ ] **Step 1: Extend `_mapHero` to draw the compass (NOW view)**

Change the signature to `_mapHero(d, c, wc, view, sp)` and add the compass for NOW view. The needle points **downwind** (`wind_dir_deg + 180`, so a "from SW" wind reads as an arrow flying to NE), coloured by the active sport's direction factor:

```javascript
  _mapHero(d, c, wc, view, sp) {
    const lat = d.latitude, lon = d.longitude;
    const map = (lat == null || lon == null) ? `<div class="sd-nomap">no location</div>` : this._tileMosaic(lat, lon);
    let compass = "";
    if (view === "now" && c.wind_dir_deg != null) {
      const dirFac = sp?.now?.factors?.direction;
      const col = facCol(dirFac);
      const rot = (c.wind_dir_deg + 180) % 360;     // downwind heading
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
```

- [ ] **Step 2: Pass the active sport at the call site**

In `_spot()`, the left column currently calls `${this._mapHero(d, c, wc, view)}`. Pass `sp`:

```javascript
        <div class="sd-col">${this._mapHero(d, c, wc, view, sp)}${leftLower}</div>
```

- [ ] **Step 3: Add CSS**

```css
.sd-map .sd-windc{position:absolute;left:50%;top:46%;width:88px;height:88px;transform:translate(-50%,-50%);z-index:3;pointer-events:none;}
.sd-windc-dial{fill:rgba(0,0,0,.32);stroke:rgba(255,255,255,.22);stroke-width:1.5;}
.sd-windc-n{fill:var(--mut);font-size:10px;text-anchor:middle;font-family:inherit;}
```

> The existing `.sd-map .pin` rule (the location marker) stays; the compass sits above it. If the pin visually clashes with the dial, reduce the pin or move it — but keep both; do not remove the pin.

- [ ] **Step 4: Render-check + commit**

Deploy + screenshot (user-gated). Expected: a compass dial + needle on the map, needle coloured green/amber/red by the active sport's direction factor (grey if unconfigured), re-colouring when you switch sports; the "Wind from SW · NN kn" chip remains. Matches `final-design.html`.

```bash
git add custom_components/swelligence/frontend/swelligence-card.js
git commit -m "feat(card): wind-direction compass on map hero"
```

---

## Final verification

- [ ] `pytest` — full pure suite green.
- [ ] `pytest tests_ha -o asyncio_mode=auto` — HA import + flow guard green.
- [ ] Deploy to the live HA temp dashboard (user-gated reload), then via the browser MCP screenshot **both** NOW and WEEK views and confirm against `final-design.html`:
  - Medallion row selects sports; scores/colours correct.
  - Detail card: arc-gauge kit colour matches `power` for a suitable / under / over / no-kit sport; limiting-factor line matches `reasons`; factor bars present.
  - Daylight arc present in NOW; absent with no sun data.
  - Wind compass present in NOW; needle colour tracks active sport's direction factor.
  - WEEK view unchanged except the medallion row + detail (no kit/compass/daylight, which are NOW-only) render without errors.
- [ ] No console errors in the browser (read_console_messages).
- [ ] `git status` clean; all commits pushed per session-close protocol.

## Out of scope (separate beads)

Safety-flags strip (`swelligence-slh`), confidence badge (`swelligence-48w.1`), wetsuit recommendation (new), map shore-line (`swelligence-slh.6`), sport SVG icon rework (new), null-tile de-emphasis polish.
