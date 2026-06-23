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
2. **Add spots**: name + coordinates (later: geocode by name) + water type +
   which sports apply there.
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

Adding Windy/Stormglass = implement this + register in `PROVIDERS`. Nothing in
scoring or entities changes.

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
- **M2 — Geocoding**: add spots by place name (Open-Meteo geocoding API) instead
  of raw coordinates.
- **M3 — Custom Lovelace card**: spot × sport suitability matrix (green/amber/
  red) with the "best in N hours" hint and AI summary tooltip.
- **M4 — More providers**: Windy (keyed, richer models), Stormglass (marine +
  tide), UKHO tides as a tide overlay for tide-sensitive sports/spots.
- **M5 — Tide awareness**: factor tide state/height into scoring where the spot
  is tide-dependent.
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
