# Rounded Weather + Tunable Safety Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the full Open-Meteo weather picture on the card + ESPHome panel, and add a per-hazard user-tunable (hard/warn/off) weather safety gate.

**Architecture:** Most weather data is already fetched into `ForecastPoint` and dropped at the surfacing layer — the bulk of this is plumbing (`detail.py`/`forecast.py`/card). The safety gate is an **override layer** evaluated per `ForecastPoint` and applied **inside `score_point`** — the exact pattern the tide gate already uses (`point.tide_factor`) — so every consumer (now, `best_window`, hourly/daily timelines) gates uniformly with no weight recalibration.

**Tech Stack:** Python 3 (Home Assistant custom integration), pytest (HA-stubbed pure suite via `tests/conftest.py`), `pytest_homeassistant_custom_component` (HA guard suite `tests_ha/`), dependency-free vanilla JS Lovelace card.

**Spec:** `docs/superpowers/specs/2026-06-29-weather-rounding-safety-gate-design.md`
**Epic:** swelligence-0no (tasks below map to children .1–.8)

## Global Constraints

- **Units are normalised:** speeds = knots, heights = metres, temps = °C, directions = degrees ("from"). Providers convert at the edge. (`CLAUDE.md`)
- **Unknown is `None`, never `0`.** Any field a provider can't supply stays `None`.
- **Pure logic, HA at the edges.** `hazards.py`, `scoring.py`, `detail.py`, `forecast.py` must NOT import `homeassistant`. New modules MUST be added to `tests_ha/test_ha_guard.py`'s `HA_MODULES` list.
- **Tests import the package as `swelligence.*`** (aliased in `tests/conftest.py`), e.g. `from swelligence.hazards import ...`.
- **No weight recalibration:** the gate must not alter any scoring weight or factor math. Existing `tests/test_scoring.py` assertions must remain green unchanged.
- **Panel contract is published:** any new flat attribute in `flatten_detail` MUST be documented in `docs/panel-contract.md` (cross-posted to the HomeAutomation panel repo).
- **Commit style:** conventional commits; end body with the Co-Authored-By / Claude-Session trailers used in this repo.

---

### Task 1 (bead swelligence-0no.1 — A1): Fetch `precipitation_probability` + `cape`

**Files:**
- Modify: `custom_components/swelligence/providers/base.py:46-56` (add two `ForecastPoint` fields)
- Modify: `custom_components/swelligence/providers/open_meteo.py:32-43` (`_FORECAST_HOURLY`) and `:256-294` (`_merge`)
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `ForecastPoint.precip_prob_pct: float | None`, `ForecastPoint.cape_jkg: float | None`, populated by `OpenMeteoProvider._merge` from the `precipitation_probability` and `cape` hourly arrays.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_providers.py`:

```python
def test_merge_parses_precip_prob_and_cape():
    from swelligence.providers.open_meteo import OpenMeteoProvider

    wind = {
        "hourly": {
            "time": ["2026-06-29T12:00"],
            "precipitation_probability": [70],
            "cape": [1500.0],
        }
    }
    points = OpenMeteoProvider._merge(wind, None)
    assert len(points) == 1
    assert points[0].precip_prob_pct == 70
    assert points[0].cape_jkg == 1500.0


def test_merge_missing_precip_prob_and_cape_are_none():
    from swelligence.providers.open_meteo import OpenMeteoProvider

    wind = {"hourly": {"time": ["2026-06-29T12:00"]}}
    points = OpenMeteoProvider._merge(wind, None)
    assert points[0].precip_prob_pct is None
    assert points[0].cape_jkg is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_providers.py::test_merge_parses_precip_prob_and_cape -v`
Expected: FAIL — `AttributeError: 'ForecastPoint' object has no attribute 'precip_prob_pct'` (or TypeError on the kwarg).

- [ ] **Step 3a: Add the model fields**

In `custom_components/swelligence/providers/base.py`, after the `weather_code` field (line 56), add:

```python
    #: Probability of precipitation (%) and convective available potential
    #: energy (J/kg) — rain likelihood and thunderstorm-instability signals.
    precip_prob_pct: float | None = None
    cape_jkg: float | None = None
```

- [ ] **Step 3b: Request the two variables**

In `custom_components/swelligence/providers/open_meteo.py`, extend `_FORECAST_HOURLY` (after `"weather_code",` on line 42):

```python
    "weather_code",
    "precipitation_probability",
    "cape",
```

- [ ] **Step 3c: Map them in `_merge`**

In `_merge`, in the `ForecastPoint(...)` constructor (after the `weather_code=...` line, ~line 270), add:

```python
                    weather_code=_at(wh.get("weather_code", []), i),
                    precip_prob_pct=_at(wh.get("precipitation_probability", []), i),
                    cape_jkg=_at(wh.get("cape", []), i),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_providers.py -v`
Expected: PASS (both new tests + existing).

- [ ] **Step 5: Commit**

```bash
git add custom_components/swelligence/providers/base.py custom_components/swelligence/providers/open_meteo.py tests/test_providers.py
git commit -m "feat(provider): fetch precipitation_probability + cape (A1)"
```

---

### Task 2 (bead swelligence-0no.2 — B1): Surface weather through detail + forecast builders

**Files:**
- Modify: `custom_components/swelligence/detail.py:24-30` (`NOW_FIELDS`), `:38-44` (`_ARRAY_SUFFIXES`), `:163-195` (`flatten_detail` spot attrs), `:258-270` (per-sport week CSVs)
- Modify: `custom_components/swelligence/forecast.py:115-133` (`_slot` dict)
- Test: `tests/test_panel_detail.py`, `tests/test_forecast.py`

**Interfaces:**
- Consumes: `ForecastPoint.precip_prob_pct`, `ForecastPoint.cape_jkg` (Task 1); existing `precip_mm`, `cloud_pct`, `air_temp_c`, etc.
- Produces: new flat attrs `precip_mm`, `precip_prob_pct`, `air_temp_c`, `apparent_temp_c`, `uv_index`, `visibility_m`, `cloud_pct`, `weather_code`, `wave_period_s`, `wave_dir_deg`, `swell_dir_deg`, `current_speed_kn`, `current_dir_deg`; per-sport `<s>_week_rain`, `<s>_week_rain_prob`, `<s>_week_air`. New `_slot` keys `precip_mm`, `precip_prob_pct`, `air_temp_c`, `cloud_pct`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_panel_detail.py` (it already builds a `spot_detail`-shaped dict and calls `flatten_detail`; follow the existing fixture style in that file):

```python
def test_flatten_surfaces_comfort_and_marine_now_fields():
    from swelligence.detail import flatten_detail

    d = {
        "name": "X", "water_type": "sea", "now_time": "12:00",
        "latitude": 1.0, "longitude": 2.0,
        "current": {
            "precip_mm": 2.1, "precip_prob_pct": 70, "air_temp_c": 14.0,
            "apparent_temp_c": 11.0, "uv_index": 3, "visibility_m": 8000,
            "cloud_pct": 40, "weather_code": 61, "wave_period_s": 7.0,
            "wave_dir_deg": 220, "swell_dir_deg": 230, "current_speed_kn": 0.5,
            "current_dir_deg": 180,
        },
        "sports": [],
    }
    a = flatten_detail(d)
    assert a["precip_mm"] == 2.1
    assert a["precip_prob_pct"] == 70
    assert a["apparent_temp_c"] == 11.0
    assert a["visibility_m"] == 8000
    assert a["wave_period_s"] == 7.0
    assert a["current_speed_kn"] == 0.5


def test_flatten_emits_weekly_weather_csvs():
    from swelligence.detail import flatten_detail

    daily = [
        {"date": "2026-06-29", "datetime": "2026-06-29T12:00", "score": 60,
         "verdict": "good", "precip_mm": 0.0, "precip_prob_pct": 10, "air_temp_c": 15.0},
        {"date": "2026-06-30", "datetime": "2026-06-30T12:00", "score": 40,
         "verdict": "marginal", "precip_mm": 3.4, "precip_prob_pct": 80, "air_temp_c": 12.0},
    ]
    d = {
        "name": "X", "water_type": "sea", "now_time": "12:00",
        "latitude": 1.0, "longitude": 2.0, "current": {},
        "sports": [{"sport": "surf", "label": "Surf", "now": {}, "best": {},
                    "hourly": [], "daily": daily}],
    }
    a = flatten_detail(d)
    assert a["surf_week_rain"] == "0.0,3.4"
    assert a["surf_week_rain_prob"] == "10,80"
    assert a["surf_week_air"] == "15.0,12.0"
```

Add to `tests/test_forecast.py` (it builds an hourly/daily forecast — follow its existing `ForecastPoint`/`SportProfile` fixtures):

```python
def test_slot_carries_precip_and_air():
    from swelligence.forecast import _slot
    from swelligence.providers.base import ForecastPoint
    from datetime import datetime
    from swelligence.sports import SPORT_PROFILES

    profile = next(iter(SPORT_PROFILES.values()))
    p = ForecastPoint(time=datetime(2026, 6, 29, 12), wind_speed_kn=15,
                      precip_mm=1.2, precip_prob_pct=55, air_temp_c=13.0)
    slot = _slot(p, profile, profile.key, 0, None)
    assert slot["precip_mm"] == 1.2
    assert slot["precip_prob_pct"] == 55
    assert slot["air_temp_c"] == 13.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_panel_detail.py::test_flatten_surfaces_comfort_and_marine_now_fields tests/test_forecast.py::test_slot_carries_precip_and_air -v`
Expected: FAIL with `KeyError`/`AssertionError` (attrs/slot keys absent).

- [ ] **Step 3a: Extend `NOW_FIELDS`**

In `custom_components/swelligence/detail.py`, add `precip_mm`, `precip_prob_pct`, `cloud_pct` to the `NOW_FIELDS` tuple (the rest are already present):

```python
NOW_FIELDS = (
    "wind_speed_kn", "wind_gust_kn", "wind_dir_deg", "wave_height_m", "wave_period_s",
    "wave_dir_deg", "swell_height_m", "swell_period_s", "swell_peak_period_s",
    "swell_dir_deg", "wind_wave_height_m", "current_speed_kn", "current_dir_deg",
    "sea_level_m", "water_temp_c", "air_temp_c", "apparent_temp_c", "uv_index",
    "visibility_m", "weather_code", "precip_mm", "precip_prob_pct", "cloud_pct",
)
```

- [ ] **Step 3b: Add the comfort/safety + marine flat attrs**

In `flatten_detail`, inside the `attrs` dict literal, after the `"swell_period_s": cur.get("swell_period_s"),` line (line 184) add:

```python
        "swell_period_s": cur.get("swell_period_s"),
        # Comfort/safety weather (now).
        "precip_mm": cur.get("precip_mm"),
        "precip_prob_pct": cur.get("precip_prob_pct"),
        "air_temp_c": cur.get("air_temp_c"),
        "apparent_temp_c": cur.get("apparent_temp_c"),
        "uv_index": cur.get("uv_index"),
        "visibility_m": cur.get("visibility_m"),
        "cloud_pct": cur.get("cloud_pct"),
        "weather_code": cur.get("weather_code"),
        # Marine quality (now).
        "wave_period_s": cur.get("wave_period_s"),
        "wave_dir_deg": cur.get("wave_dir_deg"),
        "swell_dir_deg": cur.get("swell_dir_deg"),
        "current_speed_kn": cur.get("current_speed_kn"),
        "current_dir_deg": cur.get("current_dir_deg"),
```

- [ ] **Step 3c: Add the weekly weather CSVs**

In the per-sport loop in `flatten_detail`, after `attrs[f"{k}_week_water"] = ...` (line 264) add:

```python
        attrs[f"{k}_week_rain"] = _rcsv(e.get("precip_mm") for e in daily)
        attrs[f"{k}_week_rain_prob"] = _csv(_i(e.get("precip_prob_pct")) for e in daily)
        attrs[f"{k}_week_air"] = _rcsv(e.get("air_temp_c") for e in daily)
```

- [ ] **Step 3d: Keep the new weekly arrays out of the recorder**

In `_ARRAY_SUFFIXES` (line 38), add the three new suffixes:

```python
    "week_per", "week_water", "week_tide_state", "week_tide_h",
    "week_rain", "week_rain_prob", "week_air",
```

- [ ] **Step 3e: Carry precip + air through `_slot`**

In `custom_components/swelligence/forecast.py`, in the `_slot` dict (after `"weather_code": point.weather_code,` line 132) add:

```python
        "weather_code": point.weather_code,
        "precip_mm": point.precip_mm,
        "precip_prob_pct": point.precip_prob_pct,
        "air_temp_c": point.air_temp_c,
        "cloud_pct": point.cloud_pct,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_panel_detail.py tests/test_forecast.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/swelligence/detail.py custom_components/swelligence/forecast.py tests/test_panel_detail.py tests/test_forecast.py
git commit -m "feat(panel): surface rain/comfort/marine weather fields (B1)"
```

---

### Task 3 (bead swelligence-0no.3 — B2): Render new weather on the card + WMO glyph

**Files:**
- Modify: `custom_components/swelligence/frontend/swelligence-card.js` — add a `WMO(code)` helper near the other top-level helpers (`f1`, `cardOf`, `vcw`…), extend `_nowStrip(c)` (line 471), `_detail` header (line 593), and `_weekSummary` `wgrid` (line 512).

**Interfaces:**
- Consumes: `d.current` keys now carrying `precip_mm`, `precip_prob_pct`, `apparent_temp_c`, `uv_index`, `visibility_m`, `weather_code` (from Task 2's `NOW_FIELDS`); `sp.daily[i].precip_mm` (from Task 2's `_slot`).

> The card reads the **nested `spot_detail`** payload (`d.current`, `sp.daily`), not the flat panel attrs — so Task 2's `NOW_FIELDS`/`_slot` changes are what light these up. Match the existing terse card style. Every value guards `!= null` and falls back to `—`.

- [ ] **Step 1: Add the WMO glyph helper**

Near the top-level helper functions in `swelligence-card.js`, add:

```javascript
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
```

- [ ] **Step 2: Add weather cells to the now-strip**

Replace `_nowStrip(c)` (lines 471–477) so it appends rain + feels-like cells (keep the four existing cells):

```javascript
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
```

- [ ] **Step 3: Add a weather glyph line to the now detail**

In `_detail`, in the `now` branch only, surface the condition glyph + UV + visibility. After the limiting-factor line (line 600), add a conditions line:

```javascript
      ${view === "now" && limit ? `<div class="sd-detail-lf"><span class="dot" style="background:${col}"></span>${limit}</div>` : ""}
      ${view === "now" ? this._wxLine(now, sp) : ""}
      ${view === "now" && facs ? `<div class="sd-detail-facs">${facs}</div>` : ""}
```

Then add the helper method (next to `_detail`):

```javascript
  /* compact now-conditions line: weather glyph + UV + visibility */
  _wxLine(now, sp) {
    const c = (this._curRef && this._curRef()) || {};
    const [wg, wl] = WMO(c.weather_code);
    const bits = [];
    if (wg) bits.push(`${wg} ${wl}`);
    if (c.uv_index != null) bits.push(`UV ${Math.round(c.uv_index)}`);
    if (c.visibility_m != null) bits.push(`${(c.visibility_m / 1000).toFixed(c.visibility_m < 10000 ? 1 : 0)}km vis`);
    return bits.length ? `<div class="sd-detail-wx">${bits.join(" · ")}</div>` : "";
  }
```

> Note: `_detail(sp, view)` does not currently receive `current`. The simplest wiring that matches the file's structure: in `_spot()` capture `c` (already in scope, line 308) onto the instance before rendering the right column — add `this._curRef = () => c;` immediately after `const sp = sportsAll[pi], view = this._sv.view, c = d.current || {};` (line 308). This keeps `_detail`'s signature unchanged.

- [ ] **Step 4: Add a Rain cell to the week summary grid**

In `_weekSummary`, in the `wgrid` block (after the `Water` cell, line 518), add a rain cell driven by the peak day's `precip_mm`:

```javascript
        ${met("", "Water", cc.water_temp_c != null ? f1(cc.water_temp_c) : "—", "°C")}
        ${met("", "Rain", cc.precip_mm != null ? f1(cc.precip_mm) : "—", "mm")}
```

- [ ] **Step 5: Manually verify the card renders (no test runner for vanilla JS)**

Run: `node --check custom_components/swelligence/frontend/swelligence-card.js`
Expected: no output (syntax OK). Then load the card in HA dev tools or note that visual verification happens at deploy. The card degrades gracefully — missing keys render `—`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/swelligence/frontend/swelligence-card.js
git commit -m "feat(card): show rain, feels-like, UV, visibility + WMO glyph (B2)"
```

---

### Task 4 (bead swelligence-0no.4 — B3): Document new panel-contract attributes

**Files:**
- Modify: `docs/panel-contract.md`

**Interfaces:**
- Consumes: the exact attribute names produced in Task 2.

- [ ] **Step 1: Add the now-weather attributes**

In `docs/panel-contract.md`, in the now-conditions attribute table/section, document each new flat attr with units + encoding:

| Attr | Unit | dp | Notes |
|---|---|---|---|
| `precip_mm` | mm | 1 | precipitation amount, this hour |
| `precip_prob_pct` | % | int | probability of precipitation |
| `air_temp_c` | °C | 1 | air temperature |
| `apparent_temp_c` | °C | 1 | "feels like" |
| `uv_index` | index | int | |
| `visibility_m` | m | int | horizontal visibility |
| `cloud_pct` | % | int | cloud cover |
| `weather_code` | WMO | int | condition code (card maps to glyph) |
| `wave_period_s` | s | 1 | total wave period |
| `wave_dir_deg` | ° | int | wave direction ("from") |
| `swell_dir_deg` | ° | int | swell direction ("from") |
| `current_speed_kn` | kn | 1 | ocean surface current |
| `current_dir_deg` | ° | int | current direction ("toward") |

- [ ] **Step 2: Add the weekly weather CSVs**

Document, aligned to `week_days`/`week_dates`:

- `<s>_week_rain` — CSV, mm (1 dp), peak-hour precipitation per day
- `<s>_week_rain_prob` — CSV, % (int), precipitation probability per day
- `<s>_week_air` — CSV, °C (1 dp), air temperature per day

Add a one-line note in the staleness/version banner that these landed with the weather-rounding change, and that empty fields mean `None` (unknown), per the existing alignment contract.

- [ ] **Step 3: Commit**

```bash
git add docs/panel-contract.md
git commit -m "docs(panel): document weather + weekly-rain attributes (B3)"
```

---

### Task 5 (bead swelligence-0no.5 — C1): Pure `hazards.py` module + tests

**Files:**
- Create: `custom_components/swelligence/hazards.py`
- Modify: `tests_ha/test_ha_guard.py` (add `"hazards"` to `HA_MODULES`)
- Test: `tests/test_hazards.py`

**Interfaces:**
- Produces:
  - `Hazard(kind: str, tier: str, reason: str)` dataclass
  - `HazardConfig(thunderstorm, fog, squall, heavy_rain, squall_gust_kn)` dataclass with defaults `hard/warn/warn/warn/34.0`
  - `evaluate_hazards(point, config: HazardConfig) -> list[Hazard]` (pure)
  - Tier constants `TIER_OFF/"off"`, `TIER_WARN/"warn"`, `TIER_HARD/"hard"`; kind constants `THUNDERSTORM`, `FOG`, `SQUALL`, `HEAVY_RAIN`
  - `has_hard(hazards) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hazards.py`:

```python
"""Unit tests for the weather safety-hazard evaluator (pure)."""

from __future__ import annotations

from datetime import datetime

from swelligence.hazards import (
    FOG,
    HEAVY_RAIN,
    SQUALL,
    THUNDERSTORM,
    TIER_HARD,
    TIER_OFF,
    TIER_WARN,
    Hazard,
    HazardConfig,
    evaluate_hazards,
    has_hard,
)
from swelligence.providers.base import ForecastPoint

T = datetime(2026, 6, 29, 12)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


def test_thunderstorm_from_weather_code():
    hz = evaluate_hazards(pt(weather_code=95), HazardConfig())
    assert [h.kind for h in hz] == [THUNDERSTORM]
    assert hz[0].tier == TIER_HARD


def test_thunderstorm_from_cape():
    hz = evaluate_hazards(pt(cape_jkg=1500), HazardConfig())
    assert any(h.kind == THUNDERSTORM for h in hz)


def test_cape_below_threshold_is_clear():
    assert evaluate_hazards(pt(cape_jkg=500), HazardConfig()) == []


def test_fog_below_visibility_threshold():
    hz = evaluate_hazards(pt(visibility_m=800), HazardConfig())
    assert [h.kind for h in hz] == [FOG]
    assert hz[0].tier == TIER_WARN


def test_squall_at_default_force_8():
    assert evaluate_hazards(pt(wind_gust_kn=34), HazardConfig()) != []
    assert evaluate_hazards(pt(wind_gust_kn=33), HazardConfig()) == []


def test_squall_threshold_is_tunable():
    cfg = HazardConfig(squall_gust_kn=41)  # Force 9
    assert evaluate_hazards(pt(wind_gust_kn=34), cfg) == []
    assert evaluate_hazards(pt(wind_gust_kn=41), cfg) != []


def test_heavy_rain_threshold():
    hz = evaluate_hazards(pt(precip_mm=7.5), HazardConfig())
    assert [h.kind for h in hz] == [HEAVY_RAIN]


def test_off_tier_suppresses_hazard():
    cfg = HazardConfig(thunderstorm=TIER_OFF)
    assert evaluate_hazards(pt(weather_code=99), cfg) == []


def test_none_values_never_trigger():
    assert evaluate_hazards(pt(), HazardConfig()) == []


def test_has_hard():
    assert has_hard([Hazard(THUNDERSTORM, TIER_HARD, "x")]) is True
    assert has_hard([Hazard(FOG, TIER_WARN, "x")]) is False
    assert has_hard([]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hazards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swelligence.hazards'`.

- [ ] **Step 3: Implement `hazards.py`**

Create `custom_components/swelligence/hazards.py`:

```python
"""Weather safety hazards — pure, config-driven gate signals.

Evaluated per :class:`ForecastPoint` (same granularity as the tide gate). Each
active hazard carries a *tier*: ``hard`` (the scorer caps the slot to "poor" /
not-suitable), ``warn`` (advisory only, surfaced on the card/panel) or ``off``
(never produced). Thresholds are fixed constants except the squall gust, which
the options flow exposes via a Beaufort dropdown.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tiers (string values are what the options flow stores).
TIER_OFF = "off"
TIER_WARN = "warn"
TIER_HARD = "hard"

# Hazard kinds.
THUNDERSTORM = "thunderstorm"
FOG = "fog"
SQUALL = "squall"
HEAVY_RAIN = "heavy_rain"

# Fixed thresholds (v1). Only the squall gust is user-tunable (Beaufort).
THUNDER_WEATHER_CODES = frozenset({95, 96, 99})
THUNDER_CAPE_JKG = 1000.0
FOG_VISIBILITY_M = 1000.0
HEAVY_RAIN_MM = 7.5
DEFAULT_SQUALL_GUST_KN = 34.0  # Beaufort Force 8 (gale)


@dataclass(slots=True)
class Hazard:
    """One active weather hazard at a timestep."""

    kind: str
    tier: str
    reason: str


@dataclass(slots=True)
class HazardConfig:
    """Per-hazard tier + the tunable squall gust threshold (knots)."""

    thunderstorm: str = TIER_HARD
    fog: str = TIER_WARN
    squall: str = TIER_WARN
    heavy_rain: str = TIER_WARN
    squall_gust_kn: float = DEFAULT_SQUALL_GUST_KN


def _is_thunderstorm(point) -> bool:
    code = point.weather_code
    if code is not None and int(code) in THUNDER_WEATHER_CODES:
        return True
    cape = point.cape_jkg
    return cape is not None and cape > THUNDER_CAPE_JKG


def evaluate_hazards(point, config: HazardConfig) -> list[Hazard]:
    """Active hazards for one forecast point under ``config`` (empty if none).

    A ``None`` field never triggers (unknown is not a hazard). ``off``-tier
    hazards are never produced.
    """
    out: list[Hazard] = []
    if config.thunderstorm != TIER_OFF and _is_thunderstorm(point):
        out.append(Hazard(THUNDERSTORM, config.thunderstorm, "thunderstorm risk"))
    if (
        config.fog != TIER_OFF
        and point.visibility_m is not None
        and point.visibility_m < FOG_VISIBILITY_M
    ):
        out.append(Hazard(FOG, config.fog, f"low visibility ({point.visibility_m:.0f}m)"))
    if (
        config.squall != TIER_OFF
        and point.wind_gust_kn is not None
        and point.wind_gust_kn >= config.squall_gust_kn
    ):
        out.append(Hazard(SQUALL, config.squall, f"violent gusts ({point.wind_gust_kn:.0f}kn)"))
    if (
        config.heavy_rain != TIER_OFF
        and point.precip_mm is not None
        and point.precip_mm >= HEAVY_RAIN_MM
    ):
        out.append(Hazard(HEAVY_RAIN, config.heavy_rain, f"heavy rain ({point.precip_mm:.1f}mm)"))
    return out


def has_hard(hazards) -> bool:
    """Whether any hazard in the list is hard-tier."""
    return any(h.tier == TIER_HARD for h in (hazards or []))
```

- [ ] **Step 4: Add `hazards` to the HA guard list**

In `tests_ha/test_ha_guard.py`, add `"hazards",` to the `HA_MODULES` list (alphabetically near `geocoding`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_hazards.py -v`
Expected: PASS (all 10).

- [ ] **Step 6: Commit**

```bash
git add custom_components/swelligence/hazards.py tests/test_hazards.py tests_ha/test_ha_guard.py
git commit -m "feat(hazards): pure weather-hazard evaluator (C1)"
```

---

### Task 6 (bead swelligence-0no.6 — C2): Options-flow controls (tiers + Beaufort)

**Files:**
- Modify: `custom_components/swelligence/const.py:9-16` (new CONF keys + option lists)
- Modify: `custom_components/swelligence/config_flow.py` (imports + `async_step_settings`, lines 833-853)
- Test: `tests/test_config_export.py` or a small new `tests/test_hazard_config.py` for default resolution; HA guard already renders the settings step.

**Interfaces:**
- Consumes: `hazards` tier constants.
- Produces: option keys `CONF_HAZARD_THUNDERSTORM`, `CONF_HAZARD_FOG`, `CONF_HAZARD_SQUALL`, `CONF_HAZARD_HEAVY_RAIN`, `CONF_SQUALL_BEAUFORT_KN`; `HAZARD_TIERS`; `BEAUFORT_SQUALL_OPTIONS`; `DEFAULT_SQUALL_BEAUFORT_KN`. The options dict (after the user saves the settings step) carries these keys — read by the coordinator in Task 7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hazard_config.py`:

```python
"""The coordinator's HazardConfig is built from option keys with safe defaults."""

from __future__ import annotations

from swelligence.const import (
    CONF_HAZARD_FOG,
    CONF_HAZARD_HEAVY_RAIN,
    CONF_HAZARD_SQUALL,
    CONF_HAZARD_THUNDERSTORM,
    CONF_SQUALL_BEAUFORT_KN,
    DEFAULT_SQUALL_BEAUFORT_KN,
    HAZARD_TIERS,
)
from swelligence.hazards import TIER_HARD, TIER_OFF, TIER_WARN


def test_tier_values_are_known():
    assert set(HAZARD_TIERS) == {TIER_OFF, TIER_WARN, TIER_HARD}


def test_default_squall_is_force_8():
    assert DEFAULT_SQUALL_BEAUFORT_KN == 34


def test_conf_keys_are_distinct_strings():
    keys = {
        CONF_HAZARD_THUNDERSTORM, CONF_HAZARD_FOG, CONF_HAZARD_SQUALL,
        CONF_HAZARD_HEAVY_RAIN, CONF_SQUALL_BEAUFORT_KN,
    }
    assert len(keys) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hazard_config.py -v`
Expected: FAIL — `ImportError` (const keys absent).

- [ ] **Step 3a: Add the const keys + option lists**

In `custom_components/swelligence/const.py`, after `CONF_SCAN_INTERVAL_MINUTES` (line 16) add:

```python

# Weather safety gate — per-hazard tier ("off"|"warn"|"hard"), shown in the
# options "settings" step and consumed by hazards.evaluate_hazards via the
# coordinator. Only the squall gust threshold is tunable (Beaufort dropdown);
# the stored value is the lower-bound gust (knots) of the chosen force.
CONF_HAZARD_THUNDERSTORM: Final = "hazard_thunderstorm"
CONF_HAZARD_FOG: Final = "hazard_fog"
CONF_HAZARD_SQUALL: Final = "hazard_squall"
CONF_HAZARD_HEAVY_RAIN: Final = "hazard_heavy_rain"
CONF_SQUALL_BEAUFORT_KN: Final = "squall_beaufort_kn"

HAZARD_TIERS: Final = ["off", "warn", "hard"]

# Beaufort force -> lower-bound gust (knots) that triggers a squall. The select
# shows the force + range; the value stored/compared is the lower-bound knots.
BEAUFORT_SQUALL_OPTIONS: Final = [
    ("22", "Force 6 — Strong breeze (22–27 kn)"),
    ("28", "Force 7 — Near gale (28–33 kn)"),
    ("34", "Force 8 — Gale (34–40 kn)"),
    ("41", "Force 9 — Severe gale (41–47 kn)"),
    ("48", "Force 10 — Storm (48–55 kn)"),
    ("56", "Force 11 — Violent storm (56–63 kn)"),
    ("64", "Force 12 — Hurricane (64+ kn)"),
]
DEFAULT_SQUALL_BEAUFORT_KN: Final = 34
```

- [ ] **Step 3b: Add the controls to the settings step**

In `config_flow.py`, extend the imports from `.const` (the big import block, lines 28-70) with the five new keys + `HAZARD_TIERS`, `BEAUFORT_SQUALL_OPTIONS`, `DEFAULT_SQUALL_BEAUFORT_KN`. Then in `async_step_settings` (lines 833-853), add the hazard fields to the schema. Replace the schema body with:

```python
        opts = self.config_entry.options
        tier_opts = [selector.SelectOptionDict(value=t, label=t) for t in HAZARD_TIERS]
        beaufort_opts = [
            selector.SelectOptionDict(value=v, label=lbl)
            for v, lbl in BEAUFORT_SQUALL_OPTIONS
        ]

        def tier(key, default):
            return (
                vol.Optional(key, default=opts.get(key, default)),
                selector.SelectSelector(selector.SelectSelectorConfig(options=tier_opts)),
            )

        fields = {
            vol.Optional(
                CONF_USE_LLM, default=opts.get(CONF_USE_LLM, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_AI_TASK_ENTITY,
                description={"suggested_value": opts.get(CONF_AI_TASK_ENTITY)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task")),
        }
        for key, default in (
            (CONF_HAZARD_THUNDERSTORM, "hard"),
            (CONF_HAZARD_FOG, "warn"),
            (CONF_HAZARD_SQUALL, "warn"),
            (CONF_HAZARD_HEAVY_RAIN, "warn"),
        ):
            m, s = tier(key, default)
            fields[m] = s
        fields[
            vol.Optional(
                CONF_SQUALL_BEAUFORT_KN,
                default=str(opts.get(CONF_SQUALL_BEAUFORT_KN, DEFAULT_SQUALL_BEAUFORT_KN)),
            )
        ] = selector.SelectSelector(selector.SelectSelectorConfig(options=beaufort_opts))
        schema = vol.Schema(fields)
        return self.async_show_form(step_id="settings", data_schema=schema)
```

> The existing `async_step_settings` save path is `return self._save(user_input)` (line 837) — the new keys are saved verbatim, so no save-side change is needed. The Beaufort value is stored as a numeric string (e.g. `"34"`); the coordinator coerces with `float(...)` in Task 7.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hazard_config.py -v`
Expected: PASS.

- [ ] **Step 5: Run the HA guard to confirm the schema is valid**

Run: `pip install -r requirements-ha-test.txt && pytest tests_ha -o asyncio_mode=auto -k settings -v`
Expected: PASS (the settings step renders against real HA).

- [ ] **Step 6: Commit**

```bash
git add custom_components/swelligence/const.py custom_components/swelligence/config_flow.py tests/test_hazard_config.py
git commit -m "feat(config): per-hazard safety-gate tiers + Beaufort squall threshold (C2)"
```

---

### Task 7 (bead swelligence-0no.7 — C3): Apply the safety gate in scoring + coordinator

**Files:**
- Modify: `custom_components/swelligence/providers/base.py` (add `hazards` field to `ForecastPoint`)
- Modify: `custom_components/swelligence/scoring.py:62-78` (`ScoreResult.warnings`), `:339-411` (`score_point` gate), `:414-433` (`blend_kit`)
- Modify: `custom_components/swelligence/coordinator.py` (imports + `_apply_safety` + call site)
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `evaluate_hazards`, `HazardConfig`, `has_hard` (Task 5); the CONF keys (Task 6).
- Produces: `ForecastPoint.hazards: list | None`; `ScoreResult.warnings: list[str]`; `HARD_GATE_CAP` constant; coordinator stamps `point.hazards` before scoring.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scoring.py`:

```python
def test_hard_hazard_caps_score_and_unsuitable():
    from swelligence.hazards import Hazard, TIER_HARD, THUNDERSTORM
    from swelligence.scoring import HARD_GATE_CAP

    p = wind_only()
    pt_great = pt(wind_speed_kn=20)  # would score well
    pt_great.hazards = [Hazard(THUNDERSTORM, TIER_HARD, "thunderstorm risk")]
    res = score_point(pt_great, p)
    assert res.score <= HARD_GATE_CAP
    assert res.suitable is False
    assert res.verdict == "poor"
    assert "thunderstorm" in res.warnings


def test_warn_hazard_is_advisory_only():
    from swelligence.hazards import Hazard, TIER_WARN, HEAVY_RAIN

    p = wind_only()
    base = score_point(pt(wind_speed_kn=20), p).score
    pw = pt(wind_speed_kn=20)
    pw.hazards = [Hazard(HEAVY_RAIN, TIER_WARN, "heavy rain")]
    res = score_point(pw, p)
    assert res.score == base          # score untouched
    assert "heavy_rain" in res.warnings


def test_no_hazards_no_warnings():
    res = score_point(pt(wind_speed_kn=20), wind_only())
    assert res.warnings == []


def test_blend_kit_preserves_warnings():
    from swelligence.hazards import Hazard, TIER_WARN, FOG

    p = wind_only()
    pw = pt(wind_speed_kn=20)
    pw.hazards = [Hazard(FOG, TIER_WARN, "fog")]
    res = blend_kit(score_point(pw, p), 0.5)
    assert "fog" in res.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring.py -k "hazard or warnings" -v`
Expected: FAIL — `AttributeError`/`ImportError` (`hazards` attr, `HARD_GATE_CAP`, `warnings`).

- [ ] **Step 3a: Add the `hazards` field to `ForecastPoint`**

In `custom_components/swelligence/providers/base.py`, after the `source_confidence` field (line 71) add:

```python
    #: Active weather hazards at this timestep, stamped by the coordinator from
    #: ``hazards.evaluate_hazards`` before scoring (mirrors ``tide_factor``).
    #: ``None``/empty = no hazard. Typed loosely to keep this module free of a
    #: ``hazards`` import.
    hazards: list | None = None
```

- [ ] **Step 3b: Add `warnings` to `ScoreResult` + the cap constant**

In `scoring.py`, add to `ScoreResult` (after `nudges`, line 77):

```python
    #: Active weather-hazard kind codes for this slot (e.g. ``"thunderstorm"``),
    #: from the safety gate. Hard-tier hazards also cap the score; warn-tier are
    #: advisory only.
    warnings: list[str] = field(default_factory=list)
```

After `INCOMPLETE_CAP = 50.0` (line 34) add:

```python
# A hard safety hazard (e.g. thunderstorm) overrides conditions: the slot is
# capped into the "poor" band and reads not-suitable regardless of wind/wave.
HARD_GATE_CAP = 20.0
```

- [ ] **Step 3c: Apply the gate in `score_point`**

In `score_point`, after the tide-gate block (lines 396-401, ends before `return ScoreResult(`), insert:

```python
    # Safety gate: weather hazards stamped per point by the coordinator. A hard
    # hazard overrides conditions (capped to "poor", not suitable); a warn hazard
    # is advisory only. Mirrors the tide gate's per-point application — this is
    # the single choke point every consumer (now / best_window / timelines) hits.
    warnings: list[str] = []
    for hz in point.hazards or []:
        warnings.append(hz.kind)
        if hz.tier == "hard":
            score = min(score, HARD_GATE_CAP)
            reasons.append(hz.reason)
```

Then add `warnings=warnings,` to the `ScoreResult(...)` return (the `score`/`verdict`/`suitable` already derive from the capped `score`):

```python
    return ScoreResult(
        score=score,
        verdict=_band(score),
        suitable=score >= SUITABLE_THRESHOLD,
        factors=factors,
        reasons=reasons,
        completeness=completeness,
        nudges=nudges,
        warnings=warnings,
    )
```

- [ ] **Step 3d: Carry warnings through `blend_kit`**

In `blend_kit`, add `warnings=list(result.warnings)` to the reconstructed `ScoreResult` (after `nudges=...`, line 432). The early `if kit_factor >= 1.0: return result` path already preserves them.

- [ ] **Step 3e: Stamp hazards in the coordinator**

In `coordinator.py`, add to the `.const` import block (lines 19-39):

```python
    CONF_HAZARD_THUNDERSTORM,
    CONF_HAZARD_FOG,
    CONF_HAZARD_SQUALL,
    CONF_HAZARD_HEAVY_RAIN,
    CONF_SQUALL_BEAUFORT_KN,
    DEFAULT_SQUALL_BEAUFORT_KN,
```

Add a new import near the other local imports (after line 40):

```python
from .hazards import HazardConfig, TIER_HARD, TIER_WARN, evaluate_hazards
```

In `_async_update_data`, after `await self._apply_tide(forecast, session, water_type)` (line 175) add:

```python
        # Weather safety gate: stamp each point's active hazards so score_point
        # applies the (user-tunable) gate uniformly across now / best / timelines.
        self._apply_safety(forecast)
```

Add the two methods (e.g. after `_apply_tide`'s helpers, near line 403):

```python
    def _hazard_config(self) -> HazardConfig:
        """Build the per-hazard gate config from entry options (safe defaults)."""
        o = self.entry.options
        return HazardConfig(
            thunderstorm=o.get(CONF_HAZARD_THUNDERSTORM, TIER_HARD),
            fog=o.get(CONF_HAZARD_FOG, TIER_WARN),
            squall=o.get(CONF_HAZARD_SQUALL, TIER_WARN),
            heavy_rain=o.get(CONF_HAZARD_HEAVY_RAIN, TIER_WARN),
            squall_gust_kn=float(
                o.get(CONF_SQUALL_BEAUFORT_KN, DEFAULT_SQUALL_BEAUFORT_KN)
            ),
        )

    def _apply_safety(self, forecast) -> None:
        """Stamp each forecast point with its active weather hazards."""
        cfg = self._hazard_config()
        for point in forecast.points:
            point.hazards = evaluate_hazards(point, cfg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring.py -v`
Expected: PASS — new gate tests AND all pre-existing scoring tests (proving no recalibration: a point with `hazards=None` scores exactly as before).

- [ ] **Step 5: Commit**

```bash
git add custom_components/swelligence/providers/base.py custom_components/swelligence/scoring.py custom_components/swelligence/coordinator.py tests/test_scoring.py
git commit -m "feat(scoring): per-point weather safety gate (hard caps, warn advisory) (C3)"
```

---

### Task 8 (bead swelligence-0no.8 — C4): Surface hazard warnings (detail + card)

**Files:**
- Modify: `custom_components/swelligence/detail.py:95-108` (`now` dict gains `warnings`), `:228-247` (per-sport flat attrs)
- Modify: `custom_components/swelligence/forecast.py:115-133` (`_slot` gains `warnings`)
- Modify: `custom_components/swelligence/frontend/swelligence-card.js` (`_detail` badge)
- Test: `tests/test_panel_detail.py`

**Interfaces:**
- Consumes: `ScoreResult.warnings` (Task 7).
- Produces: nested `now.warnings`; flat `<s>_now_warnings` (pipe-delimited codes); `headline_warnings`; `_slot["warnings"]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panel_detail.py`:

```python
def test_flatten_emits_now_warnings():
    from swelligence.detail import flatten_detail

    d = {
        "name": "X", "water_type": "sea", "now_time": "12:00",
        "latitude": 1.0, "longitude": 2.0, "current": {},
        "sports": [{
            "sport": "surf", "label": "Surf",
            "now": {"score": 10, "verdict": "poor", "suitable": False,
                    "warnings": ["thunderstorm", "heavy_rain"]},
            "best": {}, "hourly": [], "daily": [],
        }],
    }
    a = flatten_detail(d)
    assert a["surf_now_warnings"] == "thunderstorm|heavy_rain"
    assert a["headline_warnings"] == "thunderstorm|heavy_rain"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_panel_detail.py::test_flatten_emits_now_warnings -v`
Expected: FAIL — `KeyError: 'surf_now_warnings'`.

- [ ] **Step 3a: Add `warnings` to the nested `now` dict**

In `detail.py` `spot_detail`, in the `"now": {...}` dict (lines 98-104), add:

```python
                "nudges": res.now.nudges,
                "warnings": res.now.warnings,
                "kit": kit_payload(res.kit),
```

- [ ] **Step 3b: Emit the flat warning attrs**

In `flatten_detail`, in the headline block (after `attrs["headline_suitable"] = ...`, line 227) add:

```python
        attrs["headline_warnings"] = "|".join(hnow.get("warnings") or [])
```

In the per-sport loop (after `attrs[f"{k}_now_suitable"] = ...`, line 236) add:

```python
        attrs[f"{k}_now_warnings"] = "|".join(now.get("warnings") or [])
```

- [ ] **Step 3c: Carry warnings on hourly/daily slots**

In `forecast.py` `_slot`, add to the slot dict (after `"suitable": res.suitable,`, line 119):

```python
        "warnings": res.warnings,
```

- [ ] **Step 4: Run the panel tests**

Run: `pytest tests/test_panel_detail.py -v`
Expected: PASS.

- [ ] **Step 5: Add the card warning badge**

In `swelligence-card.js` `_detail`, render a badge in the now branch when `now.warnings` is non-empty. After the `<div class="sd-detail-vd">…` verdict line (line 596), add a badge; place it inside `sd-detail-top`'s left column:

```javascript
          <div class="sd-detail-vd" style="color:${col}">${verdictWord}</div>
          ${view === "now" && (now.warnings && now.warnings.length)
            ? `<div class="sd-detail-warn">${(now.suitable === false ? "⛈️" : "⚠️")} ${now.warnings.map((w) => w.replace("_", " ")).join(", ")}</div>`
            : ""}
```

> ⛈️ (red/hard) shows when the slot is gated unsuitable with a warning present; ⚠️ for advisory-only warnings. Degrades to nothing when `warnings` is absent/empty.

- [ ] **Step 6: Syntax-check the card**

Run: `node --check custom_components/swelligence/frontend/swelligence-card.js`
Expected: no output.

- [ ] **Step 7: Document the warning attrs in panel-contract**

In `docs/panel-contract.md`, document `<s>_now_warnings` and `headline_warnings` (pipe-delimited hazard codes: `thunderstorm|fog|squall|heavy_rain`; empty = none).

- [ ] **Step 8: Commit**

```bash
git add custom_components/swelligence/detail.py custom_components/swelligence/forecast.py custom_components/swelligence/frontend/swelligence-card.js docs/panel-contract.md tests/test_panel_detail.py
git commit -m "feat(panel): surface weather-hazard warnings on card + panel (C4)"
```

---

## Final verification (after all tasks)

- [ ] **Full pure suite:** `pytest` → all green (includes unchanged scoring assertions = no recalibration).
- [ ] **HA guard:** `pip install -r requirements-ha-test.txt && pytest tests_ha -o asyncio_mode=auto` → `hazards` imports cleanly; every flow step (incl. settings with the new selects) renders.
- [ ] **Card syntax:** `node --check custom_components/swelligence/frontend/swelligence-card.js`.
- [ ] **Close beads:** `bd close swelligence-0no.1 … .8` as each lands; `bd close swelligence-0no` when all children are done.
- [ ] **Session-end:** commit `.beads/issues.jsonl`, `git pull --rebase`, `git push`, confirm `git status` clean.

## Self-Review notes

- **Spec coverage:** A→Task1; B→Tasks2-4; C(hazards)→Task5; C(config)→Task6; C(gate)→Task7; C(warnings surfacing)→Task8. All spec sections mapped.
- **Type consistency:** `HazardConfig` field names (`thunderstorm/fog/squall/heavy_rain/squall_gust_kn`) are used identically in Tasks 5 and 7; tier string literals `"hard"/"warn"/"off"` match `HAZARD_TIERS` and the `TIER_*` constants; `ScoreResult.warnings` (list[str] of `Hazard.kind`) flows base→scoring→detail→card unchanged.
- **No recalibration:** the gate caps/annotates after the weighted mean + tide gate; with `hazards=None` (the default for every existing test's `ForecastPoint`) `score_point` is byte-for-byte equivalent.
