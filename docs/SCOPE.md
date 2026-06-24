# Swelligence — Scope & Architecture

Water- and wind-sports suitability intelligence for Home Assistant.

## Goal

Given a user's **favourite spots**, the **sports** they care about, and their
**per-sport preferences**, answer: *which spots are suitable for which sports,
now and over the next 24h?* Output is a sensor suite plus an optional
LLM-written verdict, suitable for a dashboard card and automations.

## Non-goals (v1)

- Not a general weather integration — it consumes forecasts, it doesn't replace
  HA's `weather` platform.
- No bespoke map rendering — pair with `lovelace-windy-card` for maps.
- No historical analytics / session logging in v1 (candidate for later).

## Users & key flows

1. **Setup**: choose sports + default provider; optionally wire an AI Task agent.
2. **Add spots**: name + place-name search (geocoded) or coordinates + water
   type + which sports apply there. Edit sports/water type later.
3. **Tune preferences**: per-sport wind/wave/direction/temperature windows
   (defaults shipped; overrides are a near-term milestone).
4. **Consume**: read `sensor`/`binary_sensor` per (spot × sport); build a matrix
   card; fire notifications when a spot goes green for a sport.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              Config / Options            │
                    │  sports · default provider · AI entity   │
                    │  spots[] (name, lat/lon, water, sports)  │
                    └───────────────────┬─────────────────────┘
                                        │
                          one SpotCoordinator per spot
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                                ▼                                ▼
  ┌───────────┐                   ┌────────────┐                  ┌────────────┐
  │ Provider  │  normalised       │  Scoring   │  ScoreResult     │  AI Task   │
  │ (Open-    │ ───────────────►  │ (per sport │ ───────────────► │ (optional, │
  │  Meteo …) │  SpotForecast     │  profile)  │  per (spot×sport)│  structured│
  └───────────┘                   └────────────┘                  │  verdict)  │
                                        │                          └────────────┘
                                        ▼
                         sensor + binary_sensor per (spot × sport)
```

### Layers

- **Providers** (`providers/`): turn `(lat, lon)` into a normalised
  `SpotForecast` (list of `ForecastPoint`, SI-normalised: knots, metres, °C,
  degrees). The registry in `providers/__init__.py` is the single extension
  point. **Open-Meteo** ships first (keyless; merges the forecast + marine
  APIs). The provider resolving the nearest grid cell *is* the "lock onto a
  nearby provider" behaviour.
- **Scoring** (`scoring.py`): pure functions. A `SportProfile` + a
  `ForecastPoint` → a 0–100 score with a per-factor breakdown and human notes.
  Deterministic, testable, no I/O. Hard-fail factors (wind over max, gust over
  ceiling, wave over max) cap the score. `best_window()` scans the horizon for
  the best upcoming slot.
- **Sports** (`sports.py`): built-in `SportProfile`s with sensible UK defaults.
  Distinct profiles for windsurf vs wing foil, surf vs SUP, and wakeboard
  inland vs sea — they score differently.
- **AI layer** (`llm.py`): calls `ai_task.generate_data` with a JSON `structure`
  so the agent returns a structured `{sport, rating, summary}` per spot. The
  deterministic score is passed in as context; the LLM interprets, it does not
  silently override. Best-effort — failure degrades to numbers-only.
- **Entities** (`sensor.py`, `binary_sensor.py`, `entity.py`): one device per
  spot; a score sensor + a `suitable now` binary sensor per enabled sport.

## Provider interface

```python
class ForecastProvider:
    key: str               # registry key stored in config
    requires_api_key: bool
    supports_marine: bool
    async def async_fetch(self, lat, lon, *, hours=48) -> SpotForecast: ...
```

Adding a provider (e.g. a tide authority) = implement this + register in the
relevant registry. Nothing in scoring or entities changes.

## Data model

- `ForecastPoint` — one timestep, all fields optional/normalised.
- `SpotForecast` — provider + coords + points + `source_meta` (model, nearest
  station/distance).
- `ScoreResult` — score, verdict band, suitable flag, factor map, reasons.
- `SportResult` — now + best-window results + optional LLM rating/summary.
- `RiderProfile` — the single local rider: weight (kg), optional ability level,
  and a `Quiver` of available kit (see Personalisation).
- `Quiver` — owned kit per powered sport: kite sizes (m²), wing sizes (m²),
  optional boards/foils. Drives the kit recommendation and quiver-aware scoring.
- `KitRecommendation` — ideal size + the best-matching *owned* size + a power
  verdict (under/ideal/over) for a forecast timestep.

## Personalisation — rider profile & quiver

For powered sports (kitesurf, wing foil, and to a degree windsurf), "is it
suitable?" is rider-specific: a 95 kg rider and a 60 kg rider need different kit
in the same wind, and a spot is only *actually* rideable if you own a size that
matches. Swelligence personalises the recommendation:

- **Rider profile**: weight (kg), optional ability level. Single local rider —
  one profile, one quiver (no multi-user modelling).
- **Quiver**: the sizes you actually own per sport — e.g. kites `[7, 9, 12]` m²,
  wings `[3, 4, 5]` m². Optional boards/foils for finer advice.
- **Sizing model** (`sizing.py`, calibratable like the sport profiles): a simple
  weight/wind relationship gives an *ideal* size for the forecast wind, e.g.
  `ideal_kite_m² ≈ C_kite · weight_kg / wind_kn` (default `C_kite ≈ 2.25`),
  `ideal_wing_m² ≈ C_wing · weight_kg / wind_kn` (default `C_wing ≈ 1.0`).
  Constants are defaults to tune against real sessions, not gospel.
- **Quiver-aware scoring**: pick the nearest *owned* size to the ideal, derive a
  power-match factor (ideal → full credit; off-size → under/over-powered penalty;
  nothing usable in the quiver → caps suitability low even if the raw wind is
  great). This feeds the kite/wing score as an extra factor.
- **Output**: each powered-sport sensor gains a recommendation —
  `recommended_size`, `owned_size_to_rig`, and a `power` verdict
  ("rig your 9m — ideal 8.5m", or "underpowered: smallest you own is 7m, ideal
  5m"). Surfaces on the matrix card as the suggested rig.

This keeps the deterministic core honest (wind/wave still scored as now) and
layers personal feasibility on top; the LLM verdict is given the rider context
too, so "go ride your 12m" reads naturally. Scoped to a single local rider —
one profile + quiver in config — so there's no per-rider entity multiplication.

## Roadmap

- **M0 — Scaffold (this commit)**: provider abstraction + Open-Meteo, scoring,
  sports profiles, coordinator, config/options flow, sensors, AI Task hook.
- **M1 — Per-sport preference overrides** in the options flow (UI for wind/wave
  windows + offshore directions per spot). Structure already supports it via
  `dataclasses.replace` on defaults.
- **M2 — Geocoding** *(done)*: add spots by place-name search (Open-Meteo
  geocoding API) with a disambiguation step when several places match; raw
  coordinates remain as a fallback. Plus an **edit-spot** step to add/remove a
  spot's sports and change its water type after creation.
- **M3 — Custom Lovelace card** *(done)*: `www/swelligence-card.js` — one theme-
  aware element, four `mode`s: **podium** (day's preference-ranked top-3),
  **timeline** (per-spot opportunity windows, 7d), **heatgrid** (spot×sport now),
  **medallions** (per-spot rings now). NOW modes read sensor states; forecast
  modes call `get_overview`. Bespoke SVG sport icons; verdict colours; rig size
  from quiver; ordering by sport priority.
- **M10 — Sport preference + overview** *(done)*: sport priority (drag-to-reorder
  in the card's visual editor; passed to `get_overview` as `priority`, no longer
  an integration option) + pure `ranking.py` (preference-weighted ranking, raw
  score untouched) + `overview.py` (sessions/podium) behind the `get_overview`
  service.
- **M4 — More providers** *(provider layer done)*: Windy (keyed; u/v wind + GFS
  wave) and Stormglass (keyed; marine + tide) implemented as `ForecastProvider`s
  and registered in `PROVIDERS`; UKHO implemented as a `TideProvider` overlay in
  the new `TIDE_PROVIDERS` registry (Stormglass doubles as a tide source).
  Per-provider API keys are entered in the options flow; `ForecastPoint` gained
  `sea_level_m` and `SpotForecast` a `tide_events` list. Wiring the tide overlay
  into the coordinator is M5's job. **Stormglass is live-verified** against the
  real API (weather + tide events normalise correctly). A **"Free tier"** toggle
  per keyed provider auto-throttles polling to the provider's daily request
  budget (`free_tier_daily_requests`/`requests_per_fetch`, shared across spots on
  that provider) so a free plan can't be exhausted — Stormglass free = 10/day →
  6 h min interval for one spot. UKHO live verification still pending keys.
  **Note:** the **Windy** and **Stormglass** providers were later removed in the
  single-source simplification (epic `swelligence-48w`) — they served the same
  public wave models Open-Meteo already provides keyless, while requiring a paid
  key. Tides moved to a region-resolved overlay (UKHO/NOAA CO-OPS/Open-Meteo
  modeled fallback); the free-tier throttle is now dormant (no metered provider).
- **M5 — Tide awareness** *(done)*: per-spot tide preference (any/high/low/mid +
  window hours) gates the score via a precomputed `ForecastPoint.tide_factor`
  (pure `tide.py`), so it flows through now/best/forecast uniformly. Tides come
  from a region-resolved tide overlay (UKHO / NOAA CO-OPS / Open-Meteo modeled
  fallback) attached by the coordinator with a 12 h TTL cache (budget-safe).
  Point (naive-local) and event (UTC) times are reconciled to one UTC basis.
  This coordinator overlay-attach is the shared wiring al8.2 reuses for marine.
- **M6 — Notification blueprint**: "tell me when <spot> is good for <sport>".
- **M7 — Tests & CI** *(done)*: pytest for the scorer, profile overrides, the
  water-type policy, and Open-Meteo normalisation (HA-free via a stub package);
  CI runs tests + hassfest + HACS in `.github/workflows`. Config-flow/coordinator
  tests needing the HA harness are deferred to the live-HA smoke test.
- **M8 — Rider personalisation** *(done)*: single-rider profile (weight) + quiver
  (kite/wing sizes) in options; calibratable sizing model (`sizing.py`); quiver-
  aware scoring folds the power-match into kite/wing scores (great wind + wrong
  kit -> capped + "rig your 9m²"); recommendation surfaced on sensor attributes
  and fed to the LLM. Ability-level weighting + windsurf-sail sizing deferred.
- **M9 — Forecast timeline**: serve future suitability per (spot × sport) the way
  HA serves weather forecasts. See "Forecast delivery" below.

## Forecast delivery (M9)

Today the sensor state is **now** plus a single look-ahead (`best_in_hours`).
M9 adds the full timeline, following **HA weather best-practice (2024.4+)**:

- **No forecast in entity attributes.** The `forecast` attribute was deprecated
  and removed in HA 2024.4 — forecasts are *not* part of entity state. So we do
  **not** stuff hourly/daily arrays onto sensors, and we do **not** create a
  Day+0..Day+N sensor per (spot × sport) (that would be ~9 entities × 12 combos).
- **A service delivers the forecast**, mirroring `weather.get_forecasts`:
  `swelligence.get_forecast` (`SupportsResponse.ONLY`), target the suitability
  entity (or `{spot, sport}`), pass `type: hourly | daily`. Returns:
  - **hourly**: `[{datetime, score, verdict, suitable, wind_speed_kn,
    wind_gust_kn, wind_bearing, wave_height_m, water_temp_c, kit_ideal_m2,
    kit_rig_m2, kit_power}]`
  - **daily**: one entry per day = that day's **best** slot:
    `[{date, datetime, score, verdict, suitable, kit_*}]`
  - Kit recommendation is computed **per timestep** (wind varies through the day).
- **Horizon 7 days**; slots restricted to **sunrise−2h … sunset+2h** (from
  Open-Meteo daily `sunrise`/`sunset`) so dawn-patrol/evening sessions are kept
  but the dead of night is dropped. Requires extending the fetch from 48h to 7
  days (wind + marine + daily sun times).
- **The M3 card renders the timeline** by calling the service (daily tiles +
  hourly drill-down) — exactly how the built-in weather forecast card consumes
  `weather.get_forecasts`. No per-day entities needed.
- **Optional/secondary**: expose one real `weather` entity per spot
  (`WeatherEntityFeature.FORECAST_HOURLY|DAILY`, `async_forecast_*`) for the raw
  conditions, so standard HA weather cards work for free. Suitability stays in
  the custom service.

## Deployment & secrets (live HA smoke test)

Full runbook: [`DEPLOY.md`](DEPLOY.md). Target is the Tower HA Docker container
`homeassistant` (config at `/appdata/homeassistant`, API
`http://192.168.1.3:8123`, v2026.6.4, `ai_task` present). The integration has no
pip requirements, so deployment is a file copy + restart.

HA access tokens live in **Vault** (admin token authenticates; values are never
committed):

| Secret | Vault path | Field |
| --- | --- | --- |
| HA service/API token | `knowledge/homeautomation/dev/env` | `HA_TOKEN` |
| HA base URL | `knowledge/homeautomation/dev/env` | `HA_URL` |
| HA long-lived token | `knowledge/homeautomation/dev/api-keys` | `HA_LONG_LIVED_TOKEN` |

## Testing strategy

- `scoring.py` is pure → unit-test bands, hard-fails, direction wrap-around,
  missing-field handling.
- Providers → test normalisation against recorded JSON fixtures (no live calls).
- Config/options flow → HA's `pytest-homeassistant-custom-component` harness.

## Open questions

- Preference UX: per-spot overrides vs global per-sport defaults vs both? (Lean:
  global defaults + optional per-spot override.)
- How aggressively should the AI rating be allowed to diverge from the
  deterministic score before we flag a mismatch?
- Tide provider selection per region (UKHO for UK; what elsewhere?).
- Sizing-model calibration: ship rough defaults and let users tune `C_kite`/
  `C_wing`, or seed per-ability presets? Should board/foil volume feed wing
  sizing, or keep it wind+weight only for v1?
