# HA Integrations: Surf, Swell, Tide & Marine Weather

Research survey of how existing Home Assistant integrations (core + HACS custom)
obtain surf / swell / tide / marine-weather data, conducted for the Swelligence
project. Date: 2026-06-24.

---

## TL;DR

- **No mature, surf-specific HA integration exists.** The two that target surfers
  (`surf-forecast-integration` via Surfline, `windy-home` via Windy) are both
  nascent (0 stars, single-digit commits) and depend on either an undocumented/
  scraped API (Surfline) or a paid API key (Windy).
- **The official Open-Meteo core integration does NOT expose any marine/wave
  variables** — it only consumes Open-Meteo's *Forecast* (atmospheric) API. The
  Open-Meteo **Marine API** (wave height/period/direction, swell, ocean currents)
  is free and key-less but is **unused by any HA integration today.** This is the
  single biggest gap Swelligence fills.
- **Tides are the most mature corner of the ecosystem**: a core integration
  (NOAA, US-only) plus well-maintained HACS components for WorldTides (global,
  paid credits) and UKHO/Admiralty (UK, free Discovery tier).
- **Buoy observations (NDBC)** are key-less and well covered by HACS, but are
  *observations* (real-time, point sources), not *forecasts*, and US-centric.

---

## Comparison Table

| Integration | Repo / Source | Provider / API | API key & free tier | Data exposed | Maintenance |
|---|---|---|---|---|---|
| **Open-Meteo (core)** | [home-assistant.io/integrations/open_meteo](https://www.home-assistant.io/integrations/open_meteo/) | Open-Meteo **Forecast** API | None (free, no account) | Atmospheric only: condition, temp, wind, precip (current/daily/hourly). **No marine/wave data.** | Core — actively maintained |
| **WorldTides** (core `worldtidesinfo`, legacy) | [home-assistant.io/integrations/worldtidesinfo](https://www.home-assistant.io/integrations/worldtidesinfo/) | WorldTides.info | Required; prepaid **credits** (~3/day static, 5/new position) | Tide predictions, current height, hi/lo timing | Core legacy (YAML sensor) |
| **WorldTidesInfo Custom** | [jugla/worldtidesinfocustom](https://github.com/jugla/worldtidesinfocustom) | WorldTides.info | Required; prepaid credits | Tide height/timing, current + 1h forecast height, tendency, amplitude, tidal coefficients; camera viz + calendar | **Active** — 33★, v13.2.0 (Sep 2024), 82 releases |
| **NOAA Tides (core)** | [home-assistant.io/integrations/noaa_tides](https://www.home-assistant.io/integrations/noaa_tides/) | NOAA CO-OPS (Tides & Currents) | None | Tide predictions, water level (US stations only) | Core — maintained but basic |
| **HA NOAA Tides (rewrite)** | [Flight-Lab/HA_Noaa_Tides](https://github.com/Flight-Lab/HA_Noaa_Tides) | NOAA CO-OPS **+** NDBC | None | Water level, tide pred, current speed/dir, water/air temp, wind, pressure, humidity; NDBC: wave chars, spectral wave, currents | Active, pre-1.0 — 9★, 170 commits, UI config + async |
| **NOAA Tides (fork)** | [jshufro/home_assistant_noaa_tides](https://github.com/jshufro/home_assistant_noaa_tides) | NOAA CO-OPS + NDBC | None | Tides, water temp, buoy types | Maintained fork of core sensor |
| **NOAA NDBC Ocean Weather** | [cofabri-dev/noaa-ndbc-hacs-integration](https://github.com/cofabri-dev/noaa-ndbc-hacs-integration) | NOAA **NDBC** realtime2 text files | None | Water/air temp, wind (dir/speed/gust), **wave height/period/direction**, pressure, dew point; swim-comfort templates | Active (Feb 2026 launch) — ~30 min poll |
| **UKHO Tides** | [ianByrne/HASS-ukho_tides](https://github.com/ianByrne/HASS-ukho_tides) | UK Admiralty Tidal API (`ukhotides` PyPI) | Required; **free "Discovery" tier** sufficient | Tide rising/falling, time to next hi/lo, heights + timestamps, history for charts (ApexCharts) | 34★; maintenance cadence unclear (no recent release shown) |
| **Surf Forecast** | [victorigualada/surf-forecast-integration](https://github.com/victorigualada/surf-forecast-integration) | **Surfline** (no official public API — scraped/reverse-engineered) | No documented key | Surf rating (current/next), date good conditions met; config-flow spot search; select + notify blueprint | Nascent — 0★, ~32 commits |
| **Windy Home** | [udjamaflip/windy-home](https://github.com/udjamaflip/windy-home) | Windy.com API (GFS Wave model) | Required (`api.windy.com/keys`); tier unspecified | Temp/humidity/wind/pressure/dewpoint/precip; **wave height/period/direction, wind waves, primary & secondary swell**; CAPE, gusts, cloud. No water temp | Nascent — 0★, v0.1.2 (Apr 2026), 3 commits |
| **Tomorrow.io (core)** | [home-assistant.io/integrations/tomorrowio](https://www.home-assistant.io/integrations/tomorrowio/) | Tomorrow.io | Required (free tier exists) | Weather, air quality, pollen, fire. **No wave/marine exposed in HA.** | Core — ~3147 installs |
| **Stormglass.io** | No native integration — [community thread](https://community.home-assistant.io/t/stormglass-io-integration/431379) | Stormglass.io marine API | Required; **free 10 req/day** (non-commercial) | (Via REST sensors) tides, sea conditions, air temp, pressure, wind | DIY only (REST/Pipedream); no published HACS component |

---

## Notes per topic

### Open-Meteo — the key finding
- Core HA integration: **no API key, no account**, but only atmospheric data.
  Source confirms current/daily/hourly = condition, temp, wind, precip only.
- Open-Meteo's separate **Marine Weather API** (open-meteo.com/en/docs/marine-weather-api)
  is **free, key-less**, and exposes wave height/period/direction, wind-wave and
  swell components, and (via Copernicus/MeteoFrance models) ocean currents and
  sea-surface temperature. **Nothing in the HA ecosystem wires this in.**

### Tides
- **Most mature category.** Three providers in active use:
  - **NOAA CO-OPS** — free, US-only, observations + predictions.
  - **WorldTides.info** — global, prepaid-credit model.
  - **UK Admiralty/UKHO** — UK, free Discovery tier (good fit for a UK user).
- WorldTidesInfo Custom is the gold-standard for "how a polished tide integration
  looks" (camera/graph viz, calendar events, config flow).

### Buoys / observations (NDBC)
- Key-less, but these are **point observations**, not gridded forecasts, and
  heavily US/Great-Lakes biased. Good for "what's happening now at buoy X",
  poor for "what will the surf be at my UK beach on Saturday".

### Surf-specific
- **Surfline** integration relies on Surfline having *no public API*; it
  scrapes/reverse-engineers — fragile, ToS-risky, US-leaning rating model.
- **Windy** integration gives real swell decomposition (primary/secondary swell)
  but needs a paid key and is barely started.

---

## Lessons for Swelligence

**What the ecosystem favours**
1. **Key-less, free providers win adoption.** Open-Meteo and NOAA/NDBC dominate
   precisely because there's no signup. Paid-credit (WorldTides) and paid-key
   (Windy, Stormglass) integrations exist but stay niche.
2. **Config-flow + UI config is now table stakes.** The maintained components
   (WorldTidesInfo Custom, Flight-Lab NOAA, UKHO) are all UI-configurable; the
   legacy YAML-only core ones are seen as dated.
3. **Tides and surf are treated as separate problems** — no integration unifies
   forecast surf + tide + marine weather in one coherent device/entity model.

**The gap Swelligence fills**
- **Open-Meteo Marine API is free, key-less, global — and completely unused by
  HA.** A surf/swell forecast integration built on it would be the first key-less
  *forecast* (not observation) marine integration, and not US-restricted.
- No existing integration **combines** swell-forecast + tide + marine weather +
  (optionally) buoy observations into one surf-readiness view. Swelligence's
  multi-provider, confidence-scored, authority-ranked model (per repo history:
  o07 confidence, provider-authority map) has **no equivalent** in the ecosystem.
- UK coverage is weak for surf specifically: Surfline is US-leaning, NDBC is US.
  Open-Meteo Marine + UKHO tides is a strong UK-first stack.

**Reusable patterns to borrow**
- **Provider-as-data-source, decoupled from entity model** — exactly Swelligence's
  existing `providers/` design; matches Flight-Lab's CO-OPS+NDBC split.
- **WorldTidesInfo Custom's UX surface**: ApexCharts-friendly history attributes,
  camera/graph entity for tide curves, calendar events for hi/lo. Swelligence's
  Lovelace card can mirror this.
- **NDBC swim-comfort / Surfline "min rating + notify blueprint"** patterns: ship
  a notification blueprint and a derived "surf-readiness" scoring sensor, not just
  raw numbers — this is what drives adoption of the surf integrations.
- **Free-tier-respectful polling** (NDBC ~30 min; Stormglass DIY budgets 8/10
  daily calls). Swelligence should keep Open-Meteo polling conservative and make
  any paid provider (Stormglass/Windy) optional, key-gated fallbacks.

---

## Sources
- https://www.home-assistant.io/integrations/open_meteo/
- https://open-meteo.com/en/docs/marine-weather-api
- https://www.home-assistant.io/integrations/worldtidesinfo/
- https://github.com/jugla/worldtidesinfocustom
- https://www.home-assistant.io/integrations/noaa_tides/
- https://github.com/Flight-Lab/HA_Noaa_Tides
- https://github.com/jshufro/home_assistant_noaa_tides
- https://github.com/cofabri-dev/noaa-ndbc-hacs-integration
- https://community.home-assistant.io/t/noaa-ndbc-ocean-weather-buoy-data-in-ha-for-swimming-conditions-notifications-no-api-key/988642
- https://github.com/ianByrne/HASS-ukho_tides
- https://github.com/victorigualada/surf-forecast-integration
- https://github.com/udjamaflip/windy-home
- https://www.home-assistant.io/integrations/tomorrowio/
- https://community.home-assistant.io/t/stormglass-io-integration/431379
- https://stormglass.io/marine-weather/
