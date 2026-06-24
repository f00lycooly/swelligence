# Swelligence API Field Mapping

Evidence-based reference of the EXACT raw API fields each provider requests, how
they normalise into the integration's internal domain model, and how that model
surfaces in Home Assistant.

Sources of truth:
- `custom_components/swelligence/providers/{open_meteo,stormglass,windy,ukho}.py`
- `custom_components/swelligence/providers/base.py` (`ForecastPoint`, `TideEvent`, `SpotForecast`)
- `custom_components/swelligence/providers/domains.py` (canonical domain → field map)
- `custom_components/swelligence/sensor.py`, `binary_sensor.py`, `forecast.py`
- Live Open-Meteo calls confirmed 2026-06-24 at lat=50.73, lon=-1.74 (Hengistbury Head / Christchurch Bay, UK).

Unit conventions in the normalised model (`base.ForecastPoint` docstring):
speeds = **knots**, heights = **metres**, temperatures = **°C**, directions =
**degrees, meteorological "from" convention**. Any field a provider cannot
supply is left `None`.

---

## 1. Raw API fields per provider

### 1.1 Open-Meteo (`open_meteo.py`) — keyless default

Two endpoints, merged by timestamp. Wind requested in m/s (`wind_speed_unit=ms`);
the provider converts m/s → kn (`_MS_TO_KN = 1.94384`).

**Endpoint A — Forecast:** `https://api.open-meteo.com/v1/forecast`
(`hourly=` list `_FORECAST_HOURLY`, plus `daily=sunrise,sunset`)

| Raw field (`hourly`) | Unit (live) | Notes |
|---|---|---|
| `wind_speed_10m` | m/s | requested in m/s, converted to kn |
| `wind_gusts_10m` | m/s | converted to kn |
| `wind_direction_10m` | ° | |
| `temperature_2m` | °C | |
| `precipitation` | mm | |
| `cloud_cover` | % | |
| `time` | iso8601 | naive **local** time (timezone=auto) |

| Raw field (`daily`) | Unit | Notes |
|---|---|---|
| `sunrise` | iso8601 | drives daylight-window filtering |
| `sunset` | iso8601 | |

Top-level echoed fields used as metadata: `timezone_abbreviation` (→ model),
`utc_offset_seconds` (→ tide alignment), `latitude`/`longitude` (snapped grid
cell → `grid_distance_km` data-quality signal).

**Endpoint B — Marine:** `https://marine-api.open-meteo.com/v1/marine`
(`hourly=` list `_MARINE_HOURLY`). Best-effort/optional — inland grids return
nothing and wave fields stay `None`.

| Raw field (`hourly`) | Unit (live) | Notes |
|---|---|---|
| `wave_height` | m | combined sea (total significant wave height) |
| `wave_period` | s | mean period |
| `wave_direction` | ° | |
| `swell_wave_height` | m | swell component |
| `swell_wave_period` | s | |
| `swell_wave_direction` | ° | |
| `sea_surface_temperature` | °C | |

### 1.2 Stormglass (`stormglass.py`) — keyed, marine + weather + tides

`Authorization` header. Wind in m/s → kn. Each parameter returns a per-source
dict `{"sg": v, "noaa": v, ...}`; `_pick` prefers `sg`, the discarded spread
feeds per-field confidence.

**Endpoint A — Weather:** `https://api.stormglass.io/v2/weather/point`
(`params=` keys of `_WEATHER_PARAMS`; marine params dropped for inland spots)

| Raw param | Unit | Wind? (m/s→kn) |
|---|---|---|
| `windSpeed` | m/s | yes |
| `gust` | m/s | yes |
| `windDirection` | ° | no |
| `waveHeight` | m | no |
| `wavePeriod` | s | no |
| `waveDirection` | ° | no |
| `swellHeight` | m | no |
| `swellPeriod` | s | no |
| `swellDirection` | ° | no |
| `airTemperature` | °C | no |
| `waterTemperature` | °C | no |
| `precipitation` | mm/h | no |
| `cloudCover` | % | no |

**Endpoint B — Tides:** `https://api.stormglass.io/v2/tide/extremes/point`
returns `data[]` items with `time`, `type` (high/low), `height` (m) → `TideEvent`.

Free tier: 10 requests/day; 2 requests per fetch (weather + tide).

### 1.3 Windy (`windy.py`) — keyed Point Forecast (POST)

`https://api.windy.com/api/point-forecast/v2`. Two POSTs merged by epoch-ms
timestamp. Components in m/s → kn; temps in **Kelvin** → °C; wind direction
**derived** from u/v vector (`(270 - atan2(v,u)°) % 360`).

**Request A — model `gfs`, parameters `["wind","windGust","temp","precip","lclouds"]`.**
Response series keys consumed:

| Response series key | Unit | Maps to |
|---|---|---|
| `ts` | epoch ms | timestamp |
| `wind_u-surface` | m/s | u component → speed/dir |
| `wind_v-surface` | m/s | v component → speed/dir |
| `gust-surface` | m/s | gust → kn |
| `temp-surface` | K | air temp → °C |
| `past3hprecip-surface` | mm | precip (3h accumulation) |
| `lclouds-surface` | % | low cloud cover |

**Request B — model `gfsWave`, parameters `["waves","swell1"]`** (optional/marine).

| Response series key | Unit | Maps to |
|---|---|---|
| `ts` | epoch ms | wave timestamp (indexed) |
| `waves_height-surface` | m | wave height |
| `waves_period-surface` | s | wave period |
| `waves_direction-surface` | ° | wave direction |
| `swell1_height-surface` | m | primary swell height |
| `swell1_period-surface` | s | primary swell period |
| `swell1_direction-surface` | ° | primary swell direction |

Note: Windy returns `lclouds` (low cloud) only, and precip as a 3-hour accumulation.

### 1.4 UKHO Admiralty (`ukho.py`) — UK-only tide overlay (keyed)

`Ocp-Apim-Subscription-Key` header. Base `https://admiraltyapi.azure-api.net/uktidalapi/api/V1`.
Tides only — no wind/wave.

| Call | Raw fields consumed | Maps to |
|---|---|---|
| `GET /Stations` (cached) | `features[].geometry.coordinates [lon,lat]`, `features[].properties.Id` | nearest-station resolution |
| `GET /Stations/{id}/TidalEvents?duration=` | `DateTime` (iso8601 Z), `EventType` (High/Low Water), `Height` (m) | `TideEvent(time, kind, height_m)` |

---

## 2. Canonical normalised model

`ForecastPoint` (one per hourly timestep) and `TideEvent` (per extreme). The
domain → field grouping lives in `domains.DOMAIN_FIELDS`.

| Domain | `ForecastPoint` field | Unit | Fed by raw fields |
|---|---|---|---|
| WIND | `wind_speed_kn` | kn | OM `wind_speed_10m`; SG `windSpeed`; Windy `wind_u/v-surface` |
| WIND | `wind_gust_kn` | kn | OM `wind_gusts_10m`; SG `gust`; Windy `gust-surface` |
| WIND | `wind_dir_deg` | ° | OM `wind_direction_10m`; SG `windDirection`; Windy (derived from u/v) |
| WAVE | `wave_height_m` | m | OM `wave_height`; SG `waveHeight`; Windy `waves_height-surface` |
| WAVE | `wave_period_s` | s | OM `wave_period`; SG `wavePeriod`; Windy `waves_period-surface` |
| WAVE | `wave_dir_deg` | ° | OM `wave_direction`; SG `waveDirection`; Windy `waves_direction-surface` |
| WAVE | `swell_height_m` | m | OM `swell_wave_height`; SG `swellHeight`; Windy `swell1_height-surface` |
| WAVE | `swell_period_s` | s | OM `swell_wave_period`; SG `swellPeriod`; Windy `swell1_period-surface` |
| WAVE | `swell_dir_deg` | ° | OM `swell_wave_direction`; SG `swellDirection`; Windy `swell1_direction-surface` |
| AIR | `air_temp_c` | °C | OM `temperature_2m`; SG `airTemperature`; Windy `temp-surface` (K→°C) |
| AIR | `precip_mm` | mm | OM `precipitation`; SG `precipitation`; Windy `past3hprecip-surface` |
| AIR | `cloud_pct` | % | OM `cloud_cover`; SG `cloudCover`; Windy `lclouds-surface` |
| WATER | `water_temp_c` | °C | OM `sea_surface_temperature`; SG `waterTemperature` |
| WATER | `sea_level_m` | m | **declared in model but NO provider currently populates it** (see §4) |
| (scoring) | `tide_factor` | 0..1 | computed by coordinator from TideEvents |
| (confidence) | `source_confidence` | dict 0..1 | SG intra-model spread; cross-provider ensemble |

`TideEvent`: `time`, `kind` ("high"/"low"), `height_m`. Sources: Stormglass
`tide/extremes`, UKHO `TidalEvents`. (TIDE domain has no `ForecastPoint` fields.)

Per-domain provenance is stamped into
`SpotForecast.source_meta["sources"]` (`{domain: provider_key}`).

---

## 3. Normalised model → Home Assistant entities

The integration deliberately does **not** expose one entity per weather field.
There is no `weather.py` entity. Instead it exposes **suitability** entities per
(spot, sport), and raw normalised fields surface either as score-sensor
**attributes** or via the `get_forecast` **service** (`forecast.py`). One HA
**device per spot** (`entity.py`).

### 3.1 Entities

| Entity | Platform | unique_id suffix | State | unit / device_class |
|---|---|---|---|---|
| `<Sport> suitability` | sensor | `{sport}_score` | 0–100 score (`res.now.score`) | `PERCENTAGE`, state_class MEASUREMENT, icon per sport |
| `<Sport> suitable now` | binary_sensor | `{sport}_suitable` | on/off (`res.now.suitable`) | no device_class; icon per sport |
| `Source advice` | sensor (diagnostic) | `source_advice` | count of "better source" nudges | EntityCategory.DIAGNOSTIC |

There is **no** `device_class` set on any entity (no temperature/wind HA device
classes are used — the public state is a score, not a measurement of a raw field).

### 3.2 Where raw normalised fields appear

**Suitability sensor `extra_state_attributes`** (not the state):
`verdict`, `suitable`, `factors`, `reasons`, `best_score`, `best_in_hours`,
`best_verdict`, `recommended_size_m2`, `rig_size_m2`, `power`, `kit_summary`,
`ai_rating`, `ai_summary`, `data_sources` (per-domain provenance),
`data_quality`, `confidence`, `confidence_label`. Raw met fields are **not**
directly attributes — they are folded into `factors`/`reasons`.

**`swelligence.get_forecast` service** (`forecast.py`, per slot) is the only place
raw normalised values are surfaced verbatim:

| Service slot key | From `ForecastPoint` |
|---|---|
| `wind_speed_kn` | `wind_speed_kn` |
| `wind_gust_kn` | `wind_gust_kn` |
| `wind_bearing` | `wind_dir_deg` |
| `wave_height_m` | `wave_height_m` |
| `water_temp_c` | `water_temp_c` |

Plus computed `score`, `verdict`, `suitable`, `kit_*`.

**Gap:** the service exposes only `wind_*`, `wave_height_m`, `water_temp_c`. It
does **not** surface period, direction, swell, air temp, precip, or cloud even
though they exist on `ForecastPoint`.

---

## 4. ADDITIONAL DETAIL FIELDS (available, NOT currently consumed)

Fields the APIs offer that would materially help the water/wind-sports use case
but are not requested or not surfaced today. All Open-Meteo entries below were
confirmed available in a live marine/forecast call on 2026-06-24.

### 4a. Marine detail not requested

| Field | Provider(s) | Unit | Why it helps |
|---|---|---|---|
| `wind_wave_height` | OM marine | m | Separating **wind-wave** (local chop) from **swell** is the core surf-quality distinction. High wind-wave + low swell = messy/onshore slop; clean swell + low wind-wave = quality surf. Today only combined `wave_height` + one swell are kept. |
| `wind_wave_period` / `wind_wave_direction` | OM marine | s / ° | Quantifies chop steepness and where the local sea is coming from (comfort + paddle planning). |
| `wind_wave_peak_period` | OM marine | s | Peak (vs mean) period — better surf-energy indicator than mean. |
| `swell_wave_peak_period` | OM marine | s | Peak swell period is the single best surf-power proxy (>12 s = groundswell, powerful; <8 s = weak windswell). Today only mean `swell_wave_period` is stored. |
| `secondary_swell_wave_height/period/direction` | OM marine | m / s / ° | A crossed secondary swell flags confused/dangerous seas and explains "why it's bad despite good primary swell". Windy exposes `swell2` similarly. |
| Stormglass `secondarySwell*`, `windWave*`, `wavePeak`, `swellPeak` | Stormglass | m/s/° | Same wind-wave vs swell and peak-period detail, keyed/global. |
| Windy `swell2`, `wwaves` (wind waves) | Windy | m/s/° | Secondary swell + wind-wave split on `gfsWave`. |

### 4b. Currents

| Field | Provider | Unit | Why it helps |
|---|---|---|---|
| `ocean_current_velocity` | OM marine | km/h | **Safety**: strong currents/rip risk; affects launch/return for SUP, foil, kite, swim. |
| `ocean_current_direction` | OM marine | ° | Drift direction — downwinder planning and safety. |
| Stormglass `currentSpeed` / `currentDirection` | Stormglass | m/s / ° | Same, keyed/global. |

### 4c. Sea level / tide height time-series

| Field | Provider | Unit | Why it helps |
|---|---|---|---|
| `sea_level_height_msl` | OM marine | m | **The model already declares `sea_level_m` (WATER domain) but no provider populates it.** A continuous tide-height series (vs just high/low extremes) enables exact "X m above datum at this hour" scoring for tide-gated spots (estuary bars, reefs that only work at a tidal window). |
| Stormglass `tide/sea-level/point` (`seaLevel`) | Stormglass | m | Hourly sea-level series to fill the declared `sea_level_m`. |

### 4d. Comfort / safety atmosphere

| Field | Provider | Unit | Why it helps |
|---|---|---|---|
| `uv_index` | OM forecast | (index) | Sunburn/exposure planning for long sessions. |
| `visibility` | OM forecast | m | **Safety**: fog/haze offshore — relevant for foil/SUP/kite far from shore. |
| `surface_pressure` | OM forecast | hPa | Trend (rising/falling) hints at incoming fronts → wind shifts. |
| `relative_humidity_2m` | OM forecast | % | Comfort; feeds apparent-temperature / wetsuit choice. |
| `apparent_temperature` | OM forecast | °C | "Feels-like" — directly informs wetsuit thickness given wind chill. |
| `weather_code` | OM forecast | WMO code | Compact human-readable condition (rain/storm) for the card/UI. |
| Stormglass `gust`, `humidity`, `pressure`, `visibility`, `seaLevel` | Stormglass | various | Same comfort/safety set, keyed/global. |
| Windy higher-altitude winds (`wind` at 950h/925h) | Windy | m/s | Gradient wind for thermals/sea-breeze nuance (advanced). |

### Recommended additions (priority order)

1. **`swell_wave_peak_period`** (OM) — biggest surf-quality lever for the least effort; populates a missing peak-period signal.
2. **`wind_wave_height` + `wind_wave_period`** (OM) — clean-vs-messy distinction; the core surf-quality split.
3. **`secondary_swell_wave_height/period/direction`** (OM) — crossed-swell / confused-sea detection (quality + safety).
4. **`ocean_current_velocity` + `ocean_current_direction`** (OM) — rip/drift **safety** for SUP/foil/kite/swim.
5. **`sea_level_height_msl`** (OM) / Stormglass `seaLevel` — fills the already-declared-but-empty `sea_level_m`; enables continuous tide-height scoring.
6. **`apparent_temperature`** (OM) — wetsuit-thickness comfort; cheap win on the existing forecast call.
7. **`visibility`** + **`uv_index`** (OM) — offshore safety + exposure.
8. **`weather_code`** (OM) — human-readable condition for the Lovelace card.

All of items 1–8 ride on the existing keyless Open-Meteo calls (just extend the
`_FORECAST_HOURLY` / `_MARINE_HOURLY` lists), so they add **no** new key or quota
cost. Stormglass/Windy equivalents would extend their `params`/`parameters` lists
(Stormglass counts against the 10/day free budget).
