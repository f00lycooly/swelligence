# Swelligence Data Model — what the integration exposes

The data surface a dashboard (e.g. the spot-detail card) consumes. Three layers:

1. **Entities** — one suitability sensor + one `*_suitable` binary sensor per
   `(spot, sport)`, plus a per-spot diagnostic. State + attributes update every
   poll cycle.
2. **Services** — `swelligence.get_forecast` (per-entity hourly timeline) and
   `swelligence.get_overview` (ranked good-windows summary). Forecasts are served
   by services, not entity state, per HA weather best-practice.
3. **Raw `ForecastPoint`** — the normalised forecast each score is derived from;
   surfaced per-timestep by `get_forecast`.

> **Real samples** (live, from the Southbourne spot) live in
> [`mockups/research/sample/`](../mockups/research/sample/):
> `southbourne-sensors.json` (real recorder states + attributes) and
> `southbourne-forecast.json` (raw point + per-sport scores + 24h timeline).
> Regenerate with `python3 scripts/sample_spot.py <name> <lat> <lon> <water> <sports>`.

All examples below are **real values** for *Southbourne · surf* at a flat,
near-windless low-tide hour (score 35.8 / "marginal").

---

## 1. Entities

| Entity | `entity_id` pattern | State | Notes |
|---|---|---|---|
| Suitability | `sensor.swelligence_<spot>_<sport>_suitability` | `0`–`100` score (`%`, `measurement`) | the headline; attributes carry the breakdown. One per (spot, sport); `unavailable` for a sport the spot doesn't score |
| Suitable now | `binary_sensor.swelligence_<spot>_<sport>_suitable_now` | `on`/`off` | `on` ⇔ score ≥ 55 (`SUITABLE_THRESHOLD`) |
| Source advice | `sensor.swelligence_<spot>_source_advice` | count of "better source available" nudges (`0` = best) | diagnostic, one per spot |
| Panel detail | `sensor.swelligence_<spot>_panel_detail` | spot's best current score | one per spot; full now/week payload flattened to flat/CSV attributes for the ESPHome panel. Full contract: [panel-contract.md](panel-contract.md) |
| Config | `sensor.swelligence_config` | `"<n> spots · <m> sports"` summary | diagnostic, **one per entry** on the `Swelligence` hub device; install topology (spots/sports/kit + derived entity-ids + pill slots) in nested attributes; the `config_hash` attribute is the precise change-detection signal. Contract: [panel-config-sensor-spec.md](panel-config-sensor-spec.md) |

`<spot>` and `<sport>` are slugified (`Wing foil` → `wing_foil`).

### Suitability sensor attributes

| Attribute | Type | Meaning | Example |
|---|---|---|---|
| `spot` / `sport` / `sport_label` | str | identity | `"Southbourne"` / `"surf"` / `"Surf"` |
| `verdict` | str | band of the score | `"marginal"` (`epic≥85 · great≥70 · good≥55 · marginal≥35 · poor`) |
| `suitable` | bool | score ≥ 55 | `false` |
| `factors` | dict[str,float] | per-factor contribution, `0`–`100`, only the **applicable** factors | `{"wind":66.4,"gust":100.0,"wave":23.3,"swell":0.0}` |
| `reasons` | list[str] | human condition notes | `["1kn","flat (0.3m)","short-period swell (3s)"]` |
| `completeness` | dict[str,str] | factors that are **not** plainly scored: `not_configured` (spot metadata gap) or `missing_data` (provider gap). See [scoring.md §2a](scoring.md). | `{"direction":"not_configured"}` |
| `nudges` | list[str] | actionable config hints (separate from `reasons`) | `["set offshore wind directions for sharper scoring","set swell directions for sharper surf scoring"]` |
| `best_score` / `best_in_hours` / `best_verdict` / `best_time` | float / int / str / `HH:MM` | best timestep in the next 24 h (`best_*` present only when a best slot exists; `best_time` is its local clock) | `42.1` / `3` / `"marginal"` / `"15:00"` |
| `data_sources` | dict[str,str] | provider per domain | `{"wind":"open_meteo","wave":"open_meteo","air":"open_meteo","water":"open_meteo"}` |
| `data_quality` | dict | provenance summary, issues, grid-cell distance | `{"summary":"wind: open_meteo; swell: open_meteo","issues":[],"grid_distance_km":1.3}` |
| `confidence` / `confidence_label` | float / str | model-agreement signal — **only when** multi-model is sourced (dormant single-source) | *(absent here)* |
| `recommended_size_m2` / `rig_size_m2` / `power` / `kit_summary` | — | quiver power-match — **only** kite/wing with a rider profile | *(absent here)* |
| `ai_rating` / `ai_summary` | int / str | LLM verdict — **only** when an AI Task agent is configured | *(absent here)* |

### Source-advice sensor attributes
`{ "ok": bool, "summary": str, "recommendations": [ {domain, current, suggested, current_name, suggested_name, message} ] }`.
`ok:true` / empty `recommendations` ⇒ on the best reachable source for every domain.

### Config sensor attributes

The install topology as a single source of truth for Lovelace/automations and a
build-time panel generator (**not** consumed live by the LVGL panel). Nested
attributes (the big ones — `spots`/`sports`/`rider` — are excluded from the
recorder). The **state** is a legible `"<n> spots · <m> sports"` summary; the
`config_hash` attribute is the precise change-detection signal.

| Attribute | Type | Meaning |
|---|---|---|
| `config_hash` | str | 8-char hash over the topology; changes iff the topology changes — for change-detection (trigger automations on it) / codegen cache-bust |
| `generated_at` | ISO | when this payload was built (excluded from the hash) |
| `manifest_version` | str | integration version, for the generator to pin against |
| `sports` | list | enabled sports in priority order: `{key, label, slug}` |
| `rider` | dict | `{weight_kg, quiver}` — kit only; **no** secrets |
| `spots` | list | per spot: `{id, name, slug, water_type, latitude, longitude, tide_state, sports, detail_entity_id, pills}` |
| `spots[].pills` | list | fixed superset of sport slots: `{sport, label, slug, entity_id, configured}` — `entity_id` resolved from the registry (derived-slug fallback); `configured=false` ⇒ hide/omit the slot |

Secrets (API keys, the AI-task entity, provider credentials) are **never** in this
payload. Full rationale + consumption: [panel-config-sensor-spec.md](panel-config-sensor-spec.md).

---

## 2. Services

### `swelligence.get_forecast`
Target a suitability entity → `{ "spot", "sport", "slots": [ … ] }`. Each slot is
an hourly timestep (daylight-padded window):

| Field | Unit | | Field | Unit |
|---|---|---|---|---|
| `datetime` | ISO local | | `swell_period_s` | s |
| `score` / `verdict` / `suitable` | 0–100 / band / bool | | `swell_peak_period_s` | s (surf-power proxy) |
| `wind_speed_kn` / `wind_gust_kn` | kn | | `wind_wave_height_m` | m (wind-sea vs swell) |
| `wind_bearing` | ° from | | `current_speed_kn` | kn |
| `wave_height_m` | m | | `sea_level_m` | m (tidal level) |
| `swell_height_m` | m | | `water_temp_c` / `apparent_temp_c` | °C |
| `weather_code` | WMO | | `kit_ideal_m2`/`kit_rig_m2`/`kit_power` | m²/m²/label (kite/wing + rider only) |

Real slot (Southbourne · surf, midnight): `score 35.8 · wind 0.8kn gust 2.1 @336° ·
wave 0.28m · swell 0.28m/3.0s (peak 10.15s) · current 0.2kn · sea_level −0.59m ·
water 19.4°C · apparent 28.3°C · weather_code 0`.

### `swelligence.get_overview`
A ranked **good-windows** summary across spots/sports for the dashboard: per day,
the placed (ranked) sessions `{day, ranks:[{place, spot, sport, score, verdict,
kit, time}]}`, plus per-(spot,sport) windows `{spot, sport, day, start, end, peak,
verdict, kit, time}`. Driven by the same scores + the user's sport priority order.

---

## 3. Raw `ForecastPoint` (normalised forecast)

Units are **fixed**: speeds knots, heights metres, temps °C, directions degrees
("from"). A field a provider can't supply is `None` (never `0`). The 27 fields
captured from Open-Meteo:

| Field | Unit | Field | Unit |
|---|---|---|---|
| `time` | ISO | `wind_wave_height_m` / `wind_wave_period_s` | m / s |
| `wind_speed_kn` / `wind_gust_kn` | kn | `secondary_swell_height_m` / `_period_s` / `_dir_deg` | m / s / ° |
| `wind_dir_deg` | ° from | `air_temp_c` / `apparent_temp_c` | °C |
| `wave_height_m` / `wave_period_s` / `wave_dir_deg` | m / s / ° | `water_temp_c` | °C |
| `swell_height_m` / `swell_period_s` / `swell_dir_deg` | m / s / ° | `precip_mm` / `cloud_pct` | mm / % |
| `swell_peak_period_s` | s | `uv_index` / `visibility_m` | – / m |
| `current_speed_kn` / `current_dir_deg` | kn / ° (toward) | `weather_code` | WMO |
| `sea_level_m` | m (provider datum) | `tide_factor` | 0–1 (stamped by coordinator) |

`source_confidence` (per-field model agreement) is populated only when a
multi-model request is made (dormant single-source). Which raw fields drive the
score, and how, is in [scoring.md](scoring.md); a chunk of these (peak period,
wind-wave split, secondary swell, currents, sea level) are **captured but not yet
scored** — tracked under bead `swelligence-48w.7`.
