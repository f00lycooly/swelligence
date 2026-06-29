# Rounded weather + tunable safety gate — design

**Date:** 2026-06-29
**Status:** approved (brainstorming) — ready for implementation plan
**Epic:** _(beads epic id to be filled in on creation)_

## Problem

The card and ESPHome wall panel show only a thin slice of the available
forecast: wind, gust, wave, swell, water temp, tide. Two gaps:

1. **Rainfall and other weather are absent** from the card — even though
   Open-Meteo data for most of them is *already fetched* into the normalised
   model and silently dropped at the `detail.py` surfacing layer.
2. **No weather safety signal.** Thunderstorms, fog, violent gusts and heavy
   rain are get-off-the-water conditions for water sports, but nothing in the
   scoring or display reflects them.

This design rounds out the weather picture and adds a **user-tunable safety
gate** without disturbing the deterministic scoring weights.

## Key finding that shapes the design

Most of the "missing" data is a **plumbing problem, not a fetching problem**.
`ForecastPoint` already carries `precip_mm`, `weather_code`, `visibility_m`,
`cloud_pct`, `air_temp_c`, `apparent_temp_c`, `uv_index`, `wave_period_s`,
`wave_dir_deg`, `swell_dir_deg`, `current_speed_kn`, `current_dir_deg` — all
populated by Open-Meteo every cycle, none surfaced past `NOW_FIELDS` in
`detail.py`. Only two genuinely new fields need fetching.

## Architecture principle preserved

The safety gate is an **override layer**, sized like the existing tide gate —
it sits *outside* the weighted scorer. It can force `suitable=False` or attach a
warning, but it never edits a weight. Consequence: **no recalibration**
(`validate_spots.py` / `analyze_history.py` not triggered). Pure logic stays
HA-free and unit-tested; HA touches only the config flow + coordinator edges.

---

## A. Data layer — fetch

Two new Open-Meteo hourly request variables and two new model fields.

| New request var (hourly) | New `ForecastPoint` field | Unit | Notes |
|---|---|---|---|
| `precipitation_probability` | `precip_prob_pct` | % | likelihood alongside the mm amount |
| `cape` | `cape_jkg` | J/kg | convective instability, backs `weather_code` for thunderstorm detection |

Changes:
- `providers/open_meteo.py` — append both vars to the **forecast** hourly request
  string in `async_fetch()` and `async_fetch_many()`; map into the merged points.
- `providers/base.py` — add `precip_prob_pct` and `cape_jkg` to `ForecastPoint`
  (default `None`, per the "unknown is None, never 0" convention).

Already-present fields requiring **no fetch change**: `precip_mm`,
`weather_code`, `visibility_m`, `cloud_pct`, `air_temp_c`, `apparent_temp_c`,
`uv_index`, `wave_period_s`, `wave_dir_deg`, `swell_dir_deg`, `current_speed_kn`,
`current_dir_deg`.

## B. Display layer — surface it (no scoring impact)

### `detail.py`
Extend `NOW_FIELDS` and `flatten_detail` with:
- **Comfort/safety set:** `precip_mm`, `precip_prob_pct`, `apparent_temp_c`,
  `air_temp_c`, `uv_index`, `visibility_m`, `cloud_pct`, `weather_code`.
- **Marine-quality set:** `wave_period_s`, `wave_dir_deg`, `swell_dir_deg`,
  `current_speed_kn`, `current_dir_deg`.
- **Weekly aggregates** (only fields that vary day-to-day and matter):
  `<s>_week_rain` (daytime precip total or peak-hour mm), `<s>_week_rain_prob`,
  `<s>_week_air` (air temp). Aligned to `week_days`/`week_dates` like existing
  weekly CSVs.

Encoding follows the existing panel-contract rules (1 dp for mm/temp, integer
%/directions/weather_code; `None`→empty string).

### `swelligence-card.js`
- NOW detail: rain (`mm` + `%` prob), feels-like (`apparent_temp_c`), UV,
  visibility, cloud.
- A **WMO weather-code → glyph/label** map (☀️ / ⛅ / 🌧️ / ⛈️ / 🌫️ …) rendered
  as a small now-conditions glyph.
- Marine readout: wave period + direction, swell direction, current
  speed/direction.
- Week summary: a rain column.
- Graceful degradation: any missing attribute renders blank, never errors.

### `docs/panel-contract.md`
Document every new flat attribute (published contract — kept in lockstep with
`flatten_detail`; cross-posted to the HomeAutomation panel repo).

## C. Safety gate — pure logic + 3-tier-per-hazard config

### New pure module `hazards.py`
No `homeassistant` import. Unit-tested under `tests/`; **added to the
`tests_ha/test_ha_guard.py` import list** per the convention for new modules.

```
evaluate_hazards(point: ForecastPoint, config: HazardConfig) -> list[Hazard]
```

- Evaluated **per `ForecastPoint`** — same granularity as the tide gate, so a
  stormy afternoon does not poison a clear morning.
- A `Hazard` carries `kind` (thunderstorm/fog/squall/heavy_rain), `tier`
  (hard/warn) and a short human reason.
- `off`-tier hazards are never produced.

### Default thresholds (constants in `const.py`)

| Hazard | Trigger | Tunable? |
|---|---|---|
| thunderstorm | `weather_code ∈ {95,96,99}` **or** `cape_jkg > 1000` | fixed (v1) |
| fog | `visibility_m < 1000` | fixed (v1) |
| squall | `wind_gust_kn ≥ <beaufort threshold>` | **tunable** (Beaufort dropdown) |
| heavy rain | `precip_mm ≥ 7.5` (per hour) | fixed (v1) |

### Options flow (`config_flow.py`)
Per-hazard **tier** select — `hard` / `warn` / `off` — for each of the four
hazards. Defaults: thunderstorm = **hard**; fog, squall, heavy rain = **warn**.

Squall additionally gets a **Beaufort threshold** dropdown. Each option label
shows the force name with knots in parentheses; the **stored value is the
lower-bound knots** of the chosen force (gate logic stays in pure knots,
consistent with the model). Default **Force 8**.

```
Squall threshold:  [ Force 8 — Gale (34–40 kn) ▾ ]   → stores 34
  Force 6 — Strong breeze (22–27 kn)   → 22
  Force 7 — Near gale (28–33 kn)       → 28
  Force 8 — Gale (34–40 kn)            → 34   (default)
  Force 9 — Severe gale (41–47 kn)     → 41
  Force 10 — Storm (48–55 kn)          → 48
  Force 11 — Violent storm (56–63 kn)  → 56
  Force 12 — Hurricane (64+ kn)        → 64
```

New options appear only after an HA restart and must be opted into (per the
deploy note in CLAUDE.md). All options default to safe values, so behaviour is
sensible with zero configuration.

### `coordinator.py`
A `safety_gate` step in the per-hour scoring loop, **immediately after the tide
gate**:
- `hard` hazard present → `suitable = False`, verdict forced to poor (overrides
  wind/wave). Records the hazard reason.
- `warn` hazard present → score & suitability untouched; hazard appended to a
  `warnings` list on the per-hour result.
- no active hazard → unchanged.

### Surfacing warnings
- Entities (`sensor.py` / `binary_sensor.py`): a `warnings` attribute on the
  per-sport result.
- `detail.py`: `<s>_now_warnings` and `<s>_warnings` flat attrs (delimited
  hazard codes), documented in panel-contract.
- Card: a warning badge — ⛈️ on a hard-gated slot, ⚠️ on a warned slot.

---

## D. Sequencing — three phases

Each phase is independently shippable; the card degrades gracefully if a panel
attribute is absent.

1. **Fetch (A)** — small, additive, safe. Two request vars + two model fields.
2. **Display (B)** — pure plumbing, high user value, zero scoring risk.
3. **Safety gate (C)** — the behavioural change, isolated. Pure `hazards.py` +
   config flow + coordinator gate + warning surfacing. No recalibration.

## Testing

- `tests/` (HA-stubbed pure suite): `hazards.evaluate_hazards` truth table for
  each hazard at/around its threshold and each tier; Beaufort-threshold mapping;
  `flatten_detail` emits the new keys with correct encoding and `None` handling.
- `tests_ha/`: import guard updated for `hazards.py`; options-flow schema guard
  covers the new selects.
- Existing scoring tests must be **unchanged** — proof the gate didn't perturb
  weights.

## Out of scope (deferred / fast-follow)

- Tunable fog / heavy-rain / CAPE thresholds (only squall is tunable in v1).
- Soft weather penalties that shave points off the weighted score (this round is
  display + gate only).
- Re-sourcing `source_confidence` from Open-Meteo `models=` (separate bead
  `swelligence-48w.1`).
