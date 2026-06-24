# Surf / Marine Forecast Data Providers — Research

Research for the **Swelligence** Home Assistant integration: how free/freemium
surf, sailing, kitesurf, windsurf, and water-sports apps source their forecast
data, and which providers best fit a free, open-source HA integration wanting
rich surf data with generous free quotas.

Current Swelligence backends: **Open-Meteo, Stormglass, Windy, UKHO**
(`custom_components/swelligence/providers/`).

**Date:** 2026-06-24. All claims cited inline; pricing/quota figures should be
reconfirmed on live pages before relying on them (some came from search
snippets, flagged where relevant).

---

## TL;DR (decisive findings)

1. **Only Windy and WillyWeather among consumer apps offer a documented public
   API** — both are paid/usage-based, forbid redistribution, and require a
   per-user (BYO) key plus mandatory attribution. Everyone else
   (Surfline, Windguru, Windfinder, Surf-forecast, Wisuki, Glassy, Spotyride)
   is widget-embed-only or reverse-engineered, with ToS that bar automated
   access. **Magicseaweed's API is permanently dead** (shut down 15 May 2023).

2. **The data underneath nearly all of them is the same free public models:**
   NOAA **GFS / GFS-Wave (WaveWatch III family)**, DWD **ICON / GWAM / EWAM**,
   Météo-France **AROME + MFWAM**, Environment Canada **GDWPS**, plus **XTide**
   for tides. There is no point scraping consumer apps — go to the source.

3. **For a license-clean, key-less, generous-quota open-source integration, the
   clear winners are Open-Meteo (Marine API) for swell/wave/SST/currents and
   NOAA CO-OPS for US tides** — both free, both redistributable, neither needs
   a per-user key. Everything else is best offered as an optional, user-keyed
   backend.

4. **Richest free swell data:** NOAA **GFS-Wave** (up to 3 swell partitions, US
   public domain) and **Météo-France MFWAM via Copernicus Marine** (wind +
   primary + secondary swell with direction, free registration). Both are
   already repackaged as free JSON by Open-Meteo — so Swelligence effectively
   gets them today through the Open-Meteo provider.

---

## PART A — Consumer surf/wind apps: how they source data

### 1. Surfline (and Magicseaweed)

- **Models:** Proprietary **LOTUS** model (successor to LOLA), built on **NOAA
  WaveWatch III** source code + high-res bathymetry, near-shore modelling, ML,
  satellite assimilation, forecaster input. Wind from **GFS** globally, **NAM**
  in N. America/Hawaii.
- **Public API:** **None official.** Only an undocumented/reverse-engineered
  endpoint (`services.surfline.com/kbyg/...`). No key program, no documented
  limits, no pricing. Used by OSS projects (pysurfline, surfline-api) but not
  contractual.
- **Marine data:** Surf/wave height ranges, primary swell height/period/dir,
  wind, tide type & height, water temp, 0–6 surf rating. Secondary swells &
  currents in UI but not a stable public contract.
- **Licensing:** ToS **explicitly prohibits** robots/scrapers/automated access
  and any programmatic data extraction; personal non-commercial only;
  redistribution needs written permission. **Using the reverse-engineered API
  violates ToS — not a safe basis for an OSS integration.**
- **Magicseaweed:** Acquired by Surfline, **shut down 15 May 2023** (redirects
  to surfline.com). Its formerly well-documented JSON API is permanently dead.

Sources: https://www.surfline.com/lp/whatsnew/features/lotus-swell-model ·
https://support.surfline.com/hc/en-us/articles/4410495359643-What-is-LOTUS ·
https://www.surfline.com/terms-of-use ·
https://github.com/swrobel/meta-surf-forecast ·
https://www.shackedmag.com/2023/04/surfline-kills-off-magicseaweed.html

### 2. Windy.com

- **Models:** Aggregator (runs no proprietary model). Global: **ECMWF (~9km),
  GFS (~22km), ICON Global (DWD)**. Regional: ICON-EU/D2, **AROME (Météo-
  France)**, UKV, NAM, HRRR, ACCESS. Wave: **GFS-Wave (WW3 engine), ICON-Wave,
  ICON-EU-Wave, CAN-RDWPS-Wave**. (MFWAM not exposed via API.)
- **Public API:** **Yes — three official products.** Point Forecast API
  (`POST api.windy.com/api/point-forecast/v2`): Free/Testing tier = **500
  req/day, dev-only, returns deliberately shuffled/degraded data**;
  Professional = **€990/yr, 10,000 req/day**. **ECMWF is NOT available in Point
  Forecast** (licensing). Map Forecast API and Webcams API also exist.
- **Marine data:** Wave height/period/dir, wind-waves, wave power, **two swell
  components (primary + secondary)**, **ocean + tidal currents**, wind. **No
  SST and no astronomical tide-table heights** in the documented marine set.
- **Licensing:** **Redistribution to third parties forbidden.** Mandatory
  clickable Windy logo + data-source attribution. Free tier returns falsified
  data and bars production use → real use needs €990/yr. **Per-user key + BYO
  design**; cannot ship a shared key. (This is what Swelligence's `windy.py`
  already assumes.)

Sources: https://api.windy.com/point-forecast/docs ·
https://api.windy.com/point-forecast/pricing ·
https://account.windy.com/agreements/windy-api-map-and-point-forecast-terms-of-use ·
https://community.windy.com/topic/12/what-source-of-weather-data-windy-use

### 3. Windguru (windguru.cz)

- **Models:** **GFS 13, ICON 7 (DWD), AROME (Météo-France ~1.3km), WRF 3/9**
  (Windguru runs these itself — closest to proprietary). Wave/swell: **GFS-Wave
  16km (WW3 family), GWAM 27km (DWD WAM), EWAM 5km (DWD), GDWPS 25km (Env.
  Canada)**.
- **Public API:** **No official forecast API.** Only a **Station JSON API**
  (`windguru.cz/int/wgsapi.php`) serving *measured station observations*, needs
  station ownership/registration. Forecast distribution is **widgets only**.
  All "forecast API" projects are unofficial scrapers.
- **Marine data:** Wind/gusts/dir, air temp, cloud, precip, star rating; wave
  tables add sig wave height, swell period/dir, tides (some spots). **No water
  temp, no secondary-swell or current fields.**
- **Licensing:** No documented open API license; sanctioned channel = widgets.
  Reverse-engineered forecast use = high ToS/fragility risk.

Sources: https://stations.windguru.cz/json_api_stations.html ·
https://www.windguru.cz/help.php?sec=distr ·
https://www.windguru.cz/help.php?sec=terms

### 4. Windfinder (windfinder.com)

- **Models:** Forecast = **GFS (~13km)**. Superforecast = higher-res regional
  models (names deliberately undisclosed). Waves = "blend of regional and
  global models" (WW3/WAM not named).
- **Public API:** **Commercial B2B only — no free/public tier.** REST API
  (api.windfinder.com, docs at windfinder.docs.apiary.io). Auth = API key in
  header. Pricing = request packages by sales quote; no public price list.
  Endpoint families: Forecast, Superforecast, Tides, Reports, Search, Nearby.
- **Marine data:** Wind/gusts, air temp, waves (height), tides (worldwide),
  water temp in reports. Secondary-swell/current not confirmed.
- **Licensing:** ToS: copyright/DB-right protected; **commercial use barred
  without written consent**; **redistribution barred**; non-commercial
  publication needs visible attribution + hyperlink. No free/open tier.

Sources: https://www.windfinder.com/about/windfinder-for-businesses.htm ·
https://windfinder.docs.apiary.io/ · https://blog.windfinder.com/terms.htm

### 5. Surf-forecast.com (Meteo365 Ltd)

- **Models:** **Not publicly disclosed.** Markets "ML / proprietary algorithms
  / satellite + sensor data." Community assumption is GFS + WW3-class but this
  is unconfirmed — treat model identity as proprietary/unknown.
- **Public API:** **None.** No developer portal/docs/pricing. **Embeddable
  HTML widget only** (display embed, not a data feed).
- **Marine data:** Swell height, primary period, direction, **multiple/
  secondary swells**, wave energy (kJ), wind/gusts, tides, SST (on maps).
  Currents not found.
- **Licensing:** ToS: **no commercial use without a licence**; personal-
  reference reproduction only (no redistribution); DB rights reserved;
  attribution mandatory. Scraping into an OSS integration would breach ToS.

Sources: https://meteo365.com/ · https://www.surf-forecast.com/pages/terms ·
https://www.surf-forecast.com/pages/configure_widget

### 6. Wisuki (Spain)

- **Models:** **Confirmed from their own pages** — "Models: GFS WAVE 50km
  GFS 27km" (NOAA GFS-Wave + GFS). Tides via **XTide** (public harmonic
  constituents).
- **Public API:** **None** — iframe widgets only; no docs/key system. Forecast
  pages expose internal JSON (scrape feasible but unsanctioned).
- **Marine data:** Wind/gusts/dir, wave height/period, swell dir, tides +
  coefficients, **water temperature**, buoys; to 10-min resolution. No
  secondary swells or currents.
- **Licensing:** Light ToS — **no explicit clause on scraping/redistribution/
  commercial use/attribution**, only IP ownership. Underlying values are
  public-domain NOAA GFS/GFS-Wave + XTide, so the clean route is sourcing those
  directly rather than scraping Wisuki.

Sources: https://wisuki.com/forecast/6895/malibu-beach ·
https://wisuki.com/widgets · https://wisuki.com/mobile-apps/terms

### 7. Glassy (glassy.pro, Spain)

- **Models:** **Not disclosed.** Field set (wave height, swell dir, period,
  wind, tides, coefficients) is consistent with WW3/GFS-Wave + GFS, but this is
  inference.
- **Public API:** **None.** No developer portal/docs. Programmatic access =
  reverse-engineering the private backend.
- **Licensing:** No published API terms; providers undisclosed. **High risk —
  not recommended.**

Sources: https://glassy.pro/ · https://www.huckmag.com/article/glassy-pro

### 8. Spotyride (France)

- **Models:** **Not disclosed.** Spots-directory/booking platform; forecast is
  a secondary feature. No data provider named.
- **Public API:** **None found.** Spotyride Pro is closed B2B SaaS.
- **Licensing:** No API → no terms. **Not viable/safe.**

Sources: https://pro.spotyride.com/en/ · https://stormglass.io/watersports/

### 9. WillyWeather (Australia)

- **Models/sources:** Primary source **Australian BOM** + "other sources"
  (raw NWP names not exposed). Value-add = BOM-derived forecasts/obs + tide and
  swell layers. (BOM's own API bars third-party use, which is why developers
  route through WillyWeather.)
- **Public API:** **Yes — documented commercial REST API**
  (`api.willyweather.com.au` v2, JSON, API-key auth). **Pay-as-you-go /
  usage-based** (community HA integration reports ~$1.20/month typical). Weather
  types: wind, **tides (times + heights)**, **swell (height/period/dir)**,
  rainfall, forecasts, observations, UV, sun/moon, warnings.
- **Marine data:** Wind, tides, single-partition swell. **No documented
  secondary swells, water temp, or currents.**
- **Licensing:** ToS: **"will not sublicense, resell, redistribute or provide
  access to the API to any third party"** (key blocker — each user needs own
  key); **dual mandatory attribution** (WillyWeather logo + BOM attribution);
  anti-scraping. **BYO-key design required.** Strong choice for AU/NZ tides &
  swell as an optional user-keyed backend.

Sources: https://www.willyweather.com.au/info/api.html ·
https://www.willyweather.com.au/terms.html ·
https://github.com/safepay/sensor.willyweather ·
http://www.bom.gov.au/data-access/3rd-party-attribution.shtml

---

## PART B — Marine forecast API providers (aggregators & data services)

### Open-Meteo — Marine Weather API  ⭐ (current Swelligence default)

- **Models:** MFWAM (Météo-France), SMOC currents/tides (Météo-France), ECMWF
  WAM (9km) + WAM 0.25, NCEP GFS-Wave (0.25°/0.16°), DWD EWAM + GWAM, ERA5-Ocean.
- **API / limits:** **No API key for non-commercial use.** Free tier: 600/min,
  5,000/hour, **10,000 calls/day, 300,000/month** — very generous. Paid
  commercial (keyed): Standard $29/mo (1M), Professional $99/mo (5M).
- **Marine coverage:** Wave height/dir/period/peak-period; **primary +
  secondary + tertiary swell** (deepest decomposition of any provider here);
  wind-wave; SST; ocean current velocity/dir; sea-level incl. tides; wind via
  companion Forecast API. Caveat: tides/currents are *modeled* (~8km, not
  station-grade).
- **Licensing:** **CC BY 4.0** (attribution required); code AGPLv3. Free tier
  is **non-commercial** as defined by Creative Commons — and **personal home
  automation is explicitly named as a qualifying non-commercial use.** A free
  OSS HA integration fits squarely. **Best overall fit.**

Sources: https://open-meteo.com/en/docs/marine-weather-api ·
https://open-meteo.com/en/pricing · https://open-meteo.com/en/licence ·
https://open-meteo.com/en/terms

### Stormglass.io  (current Swelligence backend)

- **Models/sources (aggregator):** NOAA, Météo-France, UK Met Office, DWD/ICON,
  ECMWF (incl. AIFS, ERA5), FCOO, FMI, Met.no/YR, SMHI + an "AI best-source"
  grid. Global Tide API gives station-based high/low extremes.
- **API / limits:** API key required on all tiers. **Free: 10 requests/day
  (very tight), non-commercial, no support.** Paid: Small €19/mo (500/day),
  Medium €49/mo (5,000/day), Large €129/mo (25,000/day).
- **Marine coverage:** Wave + **secondary swell** (no tertiary), wind-wave,
  tide extremes + sea level, water temp, currents, wind, ocean chemistry.
- **Licensing:** Proprietary; **free tier prohibits commercial use**, eval-only;
  10/day makes a shared key impossible. **Keep as optional user-keyed backend**
  — chiefly valuable for station-based tide extremes where Open-Meteo's modeled
  tides are weak.

Sources: https://docs.stormglass.io/ · https://stormglass.io/global-tide-api/ ·
https://stormglass.io/faq/

### WorldTides (worldtides.info)

- **Sources:** Tides only — FES2014/FES2022 tidal atlas (Aviso+/CNES) blended
  with national gauge data. **No wave/swell/weather.**
- **API / limits:** API key required. **100 free credits one-time**, then
  credit-based (≈$2/1,000 credits; subs ~$0.99–4.99/mo up). *(Figures varied
  between dev page & snippets — reconfirm.)*
- **Coverage:** Tide heights, high/low extremes, datums, station metadata, plot
  images.
- **Licensing:** Commercial use OK; **mandatory attribution** (Brainware LLC);
  **caching/redistribution across multiple users prohibited** → key-per-user
  mandatory, no shared key. (Same pattern as HA's `worldtidesinfo`.)

Sources: https://www.worldtides.info/apidocs ·
http://www.worldtides.info/copyright · https://www.worldtides.info/terms

### Marea (marea.ooo)

- **Sources:** Tides only (today) — global models from gauges + altimetry,
  5,000+ stations; model names (FES/TPXO) not disclosed. **Wave predictions
  "in testing," not in the production API.**
- **API / limits:** Token required. **100 free requests one-time**, then
  pre-paid (10k=$4 … 500k=$100) or subs ($5/mo 20k up).
- **Licensing:** **Terms silent** — no attribution/commercial/caching clause.
  The *absence* of an explicit grant is itself a risk. Confirm with
  api@marea.ooo; use key-per-user regardless.

Sources: https://api.marea.ooo/doc/v1 · https://api.marea.ooo/pricing ·
https://api.marea.ooo/terms-and-privacy

### Meteomatics

- **Sources (aggregator, 110+):** ECMWF (9km), GFS, DWD ICON, HRRR, downscaled
  to proprietary EURO1k/US1k 1km grids. Wave model unnamed but spectrum +
  1st/2nd/3rd swell partitioning matches ECMWF WAM convention (inferred).
- **API / limits:** Free Basic: **1,000 calls/month, 15 basic params only
  (marine NOT included)**. Auth = HTTP basic per account. Paid = quote-only.
- **Coverage (excellent but paid):** Sig/max wave height, period/dir, total +
  **1st/2nd/3rd swell**, wind waves, SST, currents, salinity, tides, wind.
- **Licensing:** Free Basic **non-commercial AND excludes marine params**.
  **Not viable as a free default.**

Sources: https://www.meteomatics.com/en/api/ ·
https://www.meteomatics.com/en/api/available-parameters/marine-parameters/

### Visual Crossing

- **Sources:** Not published; 100k+ stations + satellite/RADAR + 50yr history;
  inferred GFS + ERA5-style reanalysis. **Primarily land weather.**
- **API / limits:** Free: **1,000 records/day** (key required). Metered:
  $0.0001/record.
- **Coverage:** Marketing claims wave height/swell/period, but the dedicated
  marine docs page **404'd** — unverifiable; free tier is documented as basic
  land elements only. No evidence of secondary swell/tides/currents/SST as
  first-class params.
- **Licensing:** **Free tier permits commercial use** + attribution. **Marine
  coverage unconfirmed and likely paid → not recommended for marine.**

Sources: https://www.visualcrossing.com/weather-api/ ·
https://www.visualcrossing.com/weather-data-pricing/

### Government / specialist tide APIs

All three are **tide / water-level only — no wave/swell.**

- **NOAA Tides & Currents / CO-OPS** — US/Great Lakes/territories. **Free, no
  API key**, soft throttling only. Coverage: water level, tide predictions
  (extremes + intervals), currents, **water temp, air temp, wind, pressure,
  salinity**. **US-government public domain — no key, no per-user gating, no
  redistribution restriction → a shared/keyless model is fine.** **Cleanest OSS
  fit for tides** (in US waters). Attribution is a norm not a requirement.
  Source: https://api.tidesandcurrents.noaa.gov/api/prod/ ·
  https://tidesandcurrents.noaa.gov/disclaimers.html
- **UKHO Admiralty Tidal API** — UK + Ireland + Crown dependencies (607
  stations). Per-user Azure-portal key: **Discovery free (~10,000 calls/mo,
  current + 6 days events)**, Foundation (~£144), Premium (£300+VAT/yr, 100k/mo
  + heights/streams). Data licensed **Open Government Licence v3.0**
  (commercial use + redistribution allowed with attribution, CC-BY-4.0
  compatible) — but access is gated behind a **per-user free key**. (This is
  Swelligence's existing `ukho.py` backend.) Source:
  https://www.api.gov.uk/ukho/uk-tidal-api-discovery/ ·
  https://admiraltyapi.portal.azure-api.net/products/uk-tidal-api ·
  https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- **WorldTides** — global fallback (see above); user-keyed only due to its
  no-multi-user-caching clause.

---

## PART C — Underlying numerical models (the raw sources)

Surf forecasting needs **swell partitions** (separating distinct swell trains
by height/period/direction), not just combined significant wave height. The
practical split among freely available models:

| Model | 2nd swell partition (h/T/dir)? | 3rd? | License | Native format | Easy in Python? |
|---|---|---|---|---|---|
| **GFS-Wave (NOAA)** | ✅ yes | ✅ yes | **Public domain** | GRIB2 | Hard raw; easy via Open-Meteo |
| GFS (atmos/wind) | n/a (wind) | — | Public domain | GRIB2 | Easy via Open-Meteo |
| ECMWF open data | ⚠️ partitions exist but **NOT in free tier** (combined + period-banded only) | ❌ | CC-BY-4.0 | GRIB2 | Hard raw; JSON via Open-Meteo |
| **MFWAM (Météo-France/CMEMS)** | ✅ yes (cleanest) | ❌ | Copernicus (free, attribution) | NetCDF-4 | Toolbox/auth; JSON via Open-Meteo |
| CMEMS (currents/SST) | adds context | — | Copernicus (free) | NetCDF-4 | Toolbox/auth |
| ICON-Wave / GWAM / EWAM (DWD) | wind/swell split; partitions less exposed | ❌ | CC-BY-4.0 | GRIB2 | Hard raw; JSON via Open-Meteo |

Key points:

- **NOAA GFS-Wave** is the only model here that openly gives a **tertiary**
  swell partition, all in US public domain — the best license possible. Native
  GRIB2 (heavy `cfgrib`/`eccodes` deps).
- **MFWAM via Copernicus Marine** is the cleanest free source of a true
  **secondary swell with direction**; free registration; NetCDF-4.
- **ECMWF's free open-data tier carries only combined SWH + period-banded
  heights — not the swell partitions** (those are in the licensed catalogue).
- **Do NOT parse raw GRIB2/NetCDF inside the HA component** — eccodes/cfgrib are
  fragile native deps inside Home Assistant. **Open-Meteo already repackages all
  of these into a single free JSON API**, which is why it is the pragmatic
  backbone. (Open-Meteo is also open source and self-hostable if commercial
  redistribution ever becomes a concern.)

Sources: https://polar.ncep.noaa.gov/waves/download.shtml ·
https://nomads.ncep.noaa.gov/ ·
https://www.ecmwf.int/en/forecasts/datasets/open-data ·
https://confluence.ecmwf.int/download/attachments/59774192/wave_parameters.pdf ·
https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_WAV_001_027/description ·
https://marine.copernicus.eu/user-corner/service-commitments-and-licence ·
https://opendata.dwd.de ·
https://open-meteo.com/en/docs/marine-weather-api ·
https://openmeteo.substack.com/p/new-meteofrance-wave-models-and-knmi-dmi-uk-metoffice-models

---

## PART D — RECOMMENDATION

**Goal:** rich surf data, generous free quotas, license-clean for an
open-source HA integration. Ranked for what to add/keep *beyond* the current
Open-Meteo / Stormglass / Windy / UKHO set.

### Keep as the backbone

1. **Open-Meteo Marine API** — already the default; nothing beats it for an OSS
   integration. Keyless, 10k/day free, CC BY 4.0, home automation explicitly
   blessed, and it transparently delivers GFS-Wave (incl. tertiary swell),
   MFWAM (secondary swell w/ direction), ECMWF-WAM, DWD GWAM/EWAM, plus SST and
   modeled currents/tides — i.e. you already consume the richest free models
   without touching GRIB. **No reason to replace it.**

### Strongest additions to consider (ranked)

1. **NOAA CO-OPS (Tides & Currents)** — *add this.* Best free upgrade
   available. **Free, no key, public domain, no redistribution restriction**
   (so unlike UKHO/WorldTides it needs no per-user key), giving **station-grade**
   tide predictions + observed water level, **water temperature, currents,
   wind** for US/Great Lakes/territories. Fills Open-Meteo's weakest area
   (modeled-only tides) with real station data, and complements UKHO's
   UK-only coverage. Easiest, cheapest, cleanest win.

2. **Copernicus Marine (CMEMS) — direct MFWAM/currents/SST** — *optional, for
   richness/robustness.* Free (single registration), broadly permissive
   licence, and the authoritative source of MFWAM secondary swell + ocean
   currents + SST. Downside: NetCDF-4 + the `copernicusmarine` toolbox (auth +
   heavier deps) — and you largely already get MFWAM via Open-Meteo. Worth it
   only as a redundancy/cross-check backend or if you want raw-model fidelity.

3. **WillyWeather** — *add as optional user-keyed backend for AU/NZ.* The only
   clean, documented, cheap (~$1.20/mo) way to get **station-grade tides +
   swell** for Australia/NZ (BOM-derived). BYO-key + dual attribution required.
   Highest-value regional gap-filler outside Europe/US.

4. **WorldTides / Marea** — *optional global tide fallbacks, user-keyed.* Cover
   the gaps NOAA (US) and UKHO (UK/IE) leave. WorldTides has clearer terms but
   a no-multi-user-caching clause; Marea is cheaper but its silent terms are a
   risk — confirm before shipping. Use only where neither free government API
   reaches.

### Explicitly NOT recommended

- **Surfline / Magicseaweed, Windguru, Windfinder, Surf-forecast, Wisuki,
  Glassy, Spotyride** — no free public API; ToS bar automated access /
  redistribution (Surfline, Windfinder, Surf-forecast explicitly). Scraping or
  reverse-engineering these is a licensing and stability liability for an OSS
  project. The data underneath is the same free public models you already get.
- **Meteomatics** — free tier excludes marine params and is non-commercial;
  marine = paid quote only.
- **Visual Crossing** — marine coverage unverified (docs 404), likely paid;
  land-weather focused.

### Recommended target stack

> **Open-Meteo Marine** (swell incl. secondary/tertiary, wave, SST, modeled
> currents — keyless default) **+ NOAA CO-OPS** (US station tides/currents/water
> temp — keyless) **+ UKHO** (UK tides — user key, already present) **+
> WillyWeather** (AU/NZ tides+swell — user key) **+ Stormglass / WorldTides /
> Marea** (optional global tide/secondary-swell fallbacks — user key).

This maximises free, license-clean coverage with no GRIB parsing, keeps the
default experience key-less and generous, and isolates every restrictive
provider behind an opt-in, per-user key with proper attribution.

### Cross-cutting design rules

- **Default tier must be key-less and redistributable** → Open-Meteo + NOAA
  CO-OPS only. Everything else is opt-in BYO-key.
- **Attribution obligations to honour:** Open-Meteo (CC BY 4.0), NOAA
  ("Data: NOAA/NOS/CO-OPS"), UKHO (OGL v3.0 string), Windy (logo + source),
  WillyWeather (WillyWeather logo + BOM), WorldTides (Brainware LLC string).
- **Never bundle a shared key** for Stormglass/WorldTides/WillyWeather/UKHO —
  their terms forbid it; each user supplies their own.
