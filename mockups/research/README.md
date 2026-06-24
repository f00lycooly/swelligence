# Swelligence — Surf/Marine Data API Research (2026-06-24)

Live API research into how Swelligence sources marine forecast data, whether it can
be made more efficient, and where richer/alternative data lives. All Open-Meteo
claims below are backed by **real keyless `curl` calls made today**.

## Documents

| File | Covers |
|------|--------|
| [`open-meteo-findings.md`](open-meteo-findings.md) | Q1 limited-scope + Q2 multi-spot batching (live-tested) |
| [`api-field-mapping.md`](api-field-mapping.md) | Q3 exact API field defs → normalised model → HA sensors + additional-detail fields |
| [`surf-app-providers.md`](surf-app-providers.md) | Q4 how free surf apps source data + alternative provider ranking |
| [`ha-integrations.md`](ha-integrations.md) | Q5 how other HA integrations get this data |

---

## Answers to the five questions

### 1. Is limited-scope (single-spot) layering possible? — **YES**
Open-Meteo lets you request *only* the variables you ask for. `hourly=`, `current=`,
and `daily=` are independent comma-separated allow-lists — omit a variable and it's
absent from the response. There is no "fetch everything" tax. You can pull just
wind, just swell, or any subset, for one spot. Free tier (no key): **600/min,
5,000/hr, 10,000/day, non-commercial** (home automation qualifies; CC BY 4.0).
No rate-limit headers are returned, so budget client-side.

### 2. Can multiple spots be concatenated into one request? — **YES (both endpoints)**
Comma-separated `latitude=`/`longitude=` lists return a **JSON array of per-location
objects** (request order). Live-confirmed on **both** the forecast and the marine
endpoint, including `current=`. Tested 50 and 200 coords successfully; practical
limit is URL length, not a documented cap.

**Net efficiency win:** all N spots collapse to **2 batched HTTP calls total**
(1 forecast + 1 marine) instead of today's **2 calls per spot**. Two parser
changes are required to adopt it:
- Single location → top-level *object*; multiple → top-level *array*. Branch on
  `isinstance(payload, list)` (current `_merge`/`_parse_sun` assume dict).
- Match results by **array index, not coordinate equality** — snapped grid coords
  differ from inputs and differ between the forecast and marine grids.

This batching does **not** apply to Stormglass/Windy/UKHO (one request per spot
each); the win is Open-Meteo-specific.

### 3. Exact API defs → sensor mapping — see `api-field-mapping.md`
Today the public entities are **derived suitability only**: per (spot, sport) a
`{sport}_score` sensor + `{sport}_suitable` binary_sensor, plus a diagnostic
`Source advice` sensor per spot. No raw measurement is exposed as a sensor; raw
values surface only via the `swelligence.get_forecast` service (and only a subset).
`ForecastPoint.sea_level_m` is declared but populated by no provider — a ready slot.

**Recommended additional-detail fields** (all free on the existing keyless
Open-Meteo calls — just extend `_FORECAST_HOURLY` / `_MARINE_HOURLY`):
1. `swell_wave_peak_period` — best surf-power proxy (groundswell vs windswell)
2. `wind_wave_height` + `wind_wave_period` — clean-vs-messy / chop-vs-swell split
3. `secondary_swell_wave_*` — crossed-swell / confused-sea detection
4. `ocean_current_velocity` + `ocean_current_direction` — rip/drift safety
5. `sea_level_height_msl` — fills the empty `sea_level_m` for continuous tide scoring
6. `apparent_temperature` — wetsuit-thickness comfort
7. `visibility` + `uv_index` — offshore safety / exposure
8. `weather_code` — human-readable condition for the Lovelace card

### 4. How free surf apps get data + alternatives — see `surf-app-providers.md`
The richest *free* swell data lives in **NOAA GFS-Wave** (3 swell partitions, public
domain) and **Météo-France MFWAM / CMEMS** (secondary swell + direction) — and
Open-Meteo already repackages all of these as JSON, so the current backbone is the
right one. Only **Windy** and **WillyWeather** among consumer apps have public APIs
(both paid, both forbid redistribution / shared keys). Surfline/MSW have no public
API (MSW API dead since 2023; scraping violates ToS).

**Best additions, ranked:** (1) **NOAA CO-OPS Tides & Currents** — free, no key, US
public domain, no per-user key needed; fills Open-Meteo's weakest area (modeled-only
tides). (2) Copernicus Marine (heavier NetCDF; mostly redundant with Open-Meteo).
(3) WillyWeather (~$1.20/mo, best AU/NZ station tides+swell). (4) WorldTides/Marea
(global tide fallbacks). **Never bundle a shared key** for Stormglass/WorldTides/
WillyWeather/UKHO — their terms forbid it.

### 5. How other HA integrations get this data — see `ha-integrations.md`
**The headline gap:** the official Open-Meteo *core* integration exposes **no marine
data** — it only uses the atmospheric Forecast API. Open-Meteo's free, keyless,
global **Marine API is used by no HA integration**. Swelligence would be the first
key-less marine *forecast* integration that isn't US-restricted. Surf-specific
integrations are immature (Surfline scraper 0★; windy-home 0★ paid-key). Tides are
the mature corner: NOAA (US, key-less), WorldTides (global, prepaid), and **UKHO/
Admiralty (`ianByrne/HASS-ukho_tides`, 34★, free Discovery tier — strong UK fit)`.

---

## Recommended next steps (suggested beads)

1. **Open-Meteo request batching** — collapse N spots to 2 batched calls; handle
   the object-vs-array + index-matching parser changes. Biggest quota/latency win.
2. **Extend marine/forecast variable sets** — add the 8 additional-detail fields;
   wire `swell_wave_peak_period`, `wind_wave_*`, `secondary_swell_*` into scoring
   (re-calibrate per the sport-profiles memory) and `sea_level_height_msl` into tide.
3. **Evaluate NOAA CO-OPS** as a free, key-less tide/current source (region-gated to
   US spots) to complement UKHO (UK) and modeled tides elsewhere.
