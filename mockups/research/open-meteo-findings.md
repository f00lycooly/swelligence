# Open-Meteo API research — Swelligence

All calls below are **real live calls** made on 2026-06-24 with `curl`, no API
key. Test spot: Avon Beach / Christchurch UK area (`lat=50.73, lon=-1.74`).

## Context: what the Swelligence integration requests today

From `custom_components/swelligence/providers/open_meteo.py`:

- **Forecast endpoint** `https://api.open-meteo.com/v1/forecast`
  - `hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,precipitation,cloud_cover`
  - `daily=sunrise,sunset`
  - `wind_speed_unit=ms`, `forecast_days=<days>`, `timezone=auto`
- **Marine endpoint** `https://marine-api.open-meteo.com/v1/marine`
  - `hourly=wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature`
  - `forecast_days=<days>`, `timezone=auto`
- One request **per endpoint, per spot** today (two HTTP calls per spot). The
  marine call is best-effort (`optional=True`); the response echoes the snapped
  grid-cell `latitude`/`longitude`, which the integration uses for a
  `grid_distance_km` quality signal.

---

## TASK 1 — Limited-scope (narrow-variable) requests for a single spot

**Yes.** You can request only the variables you need, and you get current +
hourly + daily back in one response. Scope is fully caller-controlled.

### Live forecast call (integration's exact variables + `current=`)

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=50.73&longitude=-1.74\
&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,precipitation,cloud_cover\
&daily=sunrise,sunset\
&wind_speed_unit=ms&forecast_days=2&timezone=auto\
&current=wind_speed_10m,temperature_2m"
```

Trimmed response (only requested fields are present):

```json
{
  "latitude": 50.75, "longitude": -1.75,
  "utc_offset_seconds": 3600, "timezone": "Europe/London",
  "timezone_abbreviation": "GMT+1", "elevation": 4.0,
  "current_units": { "wind_speed_10m": "m/s", "temperature_2m": "°C" },
  "current":  { "time": "2026-06-24T10:30", "interval": 900,
                "wind_speed_10m": 1.8, "temperature_2m": 30.5 },
  "hourly_units": { "wind_speed_10m": "m/s", "wind_gusts_10m": "m/s",
                    "wind_direction_10m": "°", "temperature_2m": "°C",
                    "precipitation": "mm", "cloud_cover": "%" },
  "hourly": { "time": ["2026-06-24T00:00", "2026-06-24T01:00", ...], ... }
}
```

### Live marine call (integration's exact variables + `current=`)

```bash
curl -s "https://marine-api.open-meteo.com/v1/marine?latitude=50.73&longitude=-1.74\
&hourly=wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature\
&forecast_days=2&timezone=auto\
&current=wave_height,swell_wave_height"
```

Trimmed response:

```json
{
  "latitude": 50.708336, "longitude": -1.7083282,
  "utc_offset_seconds": 3600, "timezone": "Europe/London",
  "current_units": { "wave_height": "m", "swell_wave_height": "m" },
  "current":  { "time": "2026-06-24T10:30", "wave_height": 0.18,
                "swell_wave_height": 0.1 },
  "hourly_units": { "wave_height": "m", "wave_period": "s",
                    "wave_direction": "°", "swell_wave_height": "m",
                    "swell_wave_period": "s", "swell_wave_direction": "°",
                    "sea_surface_temperature": "°C" },
  "hourly": { "time": ["2026-06-24T00:00", ...], ... }
}
```

**Layering / narrow-scope is fully supported.** The response contains *only* the
variables you asked for — you never have to "pull everything". You can request
just wind, just swell, or any mix. (Note: the marine endpoint echoes a different
snapped grid cell — `50.708336, -1.7083282` — than the forecast endpoint's
`50.75, -1.75`, which is exactly the divergence the integration's
`grid_distance_km` logic accounts for.)

### Query params that control scope

| Param | Controls | Notes |
|---|---|---|
| `hourly=` | Which hourly variables to return | Comma list. Omit a var → it's absent from the response. This is the primary scope lever. |
| `current=` | Real-time "now" snapshot variables | Returns a single `current` block (15-min interval). The integration does **not** use this today but it works and is cheap to add. |
| `daily=` | Daily-aggregated variables | Integration uses `sunrise,sunset`. |
| `forecast_days=` | Number of forecast days (1–16) | Integration passes `days` (default 7). |
| `past_days=` | Backfill of recent observed days (0–92) | Not used by integration. |
| `wind_speed_unit=` | `ms` / `kmh` / `mph` / `kn` | Integration uses `ms` then converts to knots itself. |
| `timezone=` | Output timestamp tz | Integration uses `auto` (resolves tz from coords). |
| `start_date=`/`end_date=` | Explicit date window | Alternative to `forecast_days`. |
| `models=` | Pin a specific weather model | Default = Open-Meteo's best-match blend. |

So scope is opt-in per-variable: each of `hourly`/`current`/`daily` is an
independent, comma-separated allow-list. There is no "all variables" default —
omitting all three returns metadata only.

### Free-tier rate limits (no key)

Open-Meteo's published free-tier limits (non-commercial use only):

- **10,000 calls / day**
- **5,000 calls / hour**
- **600 calls / minute**

Caveats:
- **Non-commercial use only** on the keyless tier; commercial use requires a
  paid API-key plan (`customer-api.open-meteo.com`).
- Limits are tracked by an **API-call weight**, not raw HTTP count: a request
  costs more when it spans many variables, long forecast ranges, or **many
  locations in one batch** (see Task 2). A single call can therefore consume
  more than one "call" against the daily budget. The figures above are the
  nominal call ceilings; a heavy batch counts as a fraction of an "API call unit"
  scaled by payload size.
- **No rate-limit headers are returned** on the free tier. A live
  `curl -D -` on the forecast endpoint showed **no** `X-RateLimit-*` /
  `RateLimit-*` / `Retry-After` headers — you only learn you're throttled when a
  request returns an HTTP 429 with a JSON `reason`. Client-side budgeting is
  required; you cannot read remaining quota from the response.

---

## TASK 2 — Batching multiple spots in one request

**Yes — confirmed live on BOTH endpoints.** Pass comma-separated `latitude` and
`longitude` lists; the response becomes a **JSON array**, one object per
location, in request order.

### Live forecast batch (3 spots)

```bash
curl -s "https://api.open-meteo.com/v1/forecast\
?latitude=50.73,50.58,51.08&longitude=-1.74,-2.46,1.18\
&hourly=wind_speed_10m,wind_direction_10m&wind_speed_unit=ms&forecast_days=1&timezone=auto"
```

Response is an **array of length 3**:

```
Top-level type: list   Array length: 3
  [0] lat=50.75 lon=-1.75  location_id=None  tz=Europe/London  first_wind=0.7
  [1] lat=50.75 lon=-2.5   location_id=1     tz=Europe/London  first_wind=1.5
  [2] lat=51.25 lon=1.25   location_id=2     tz=Europe/London  first_wind=2.3
```

### Live marine batch (same 3 spots)

```bash
curl -s "https://marine-api.open-meteo.com/v1/marine\
?latitude=50.73,50.58,51.08&longitude=-1.74,-2.46,1.18\
&hourly=wave_height,swell_wave_height&forecast_days=1&timezone=auto"
```

Response is an **array of length 3**:

```
Top-level type: list   Array length: 3
  [0] lat=50.708336 lon=-1.7083282  location_id=None  first_wave=0.26
  [1] lat=50.541664 lon=-2.4583282  location_id=1     first_wave=0.46
  [2] lat=51.041664 lon=1.2083435   location_id=2     first_wave=0.54
```

Both endpoints work identically. `current=` also batches (verified: a 2-spot
`current=wind_speed_10m` call returned a 2-element array each with its own
`current` block).

### Response-shape gotcha (important for the parser)

- A **single** location → top-level **object** (current integration behaviour).
- **Multiple** locations → top-level **JSON array** of those objects.

So a batched provider must branch on `isinstance(payload, list)`. The current
`open_meteo.py` `_merge`/`_parse_sun` assume a dict and would need to iterate the
array when batching is adopted.

### Per-location identification

Each array element echoes its **snapped** `latitude`/`longitude` (not your input
coords — e.g. you asked `50.73` and got `50.75` on forecast / `50.708336` on
marine). Elements after the first also carry a `location_id` (`1`, `2`, …); the
first element's `location_id` is `null`. **Match results to inputs by request
order (array index), not by coordinate equality** — the snapped coords differ
from inputs and differ between the two endpoints.

### Batch-size limit

- Live test: **50 coordinates → array of 50**, and **200 coordinates → array of
  200**, both succeeded on the forecast endpoint. No error at 200.
- Open-Meteo documents a soft cap around **1000 locations per request**; the real
  practical ceiling is URL length (GET query string) and the per-request weight
  counting against your daily budget. For a few dozen surf spots this is a
  non-issue.

### Syntax summary

```
?latitude=<lat1>,<lat2>,...&longitude=<lon1>,<lon2>,...&hourly=...&forecast_days=...
```

- `latitude` and `longitude` lists **must be equal length** (paired by index).
- Works on `https://api.open-meteo.com/v1/forecast` **and**
  `https://marine-api.open-meteo.com/v1/marine`.
- One batched HTTP call replaces N per-spot calls **per endpoint**. Marine and
  forecast are still separate endpoints, so the minimum is **2 HTTP calls total**
  to cover any number of spots (one batched forecast call + one batched marine
  call), versus today's 2 calls *per spot*.

---

## Bottom line for Swelligence

1. **Limited-scope works** — request exactly the wind/wave variables you want;
   responses contain only those. Free tier: ~600/min, 5k/hr, 10k/day,
   non-commercial, no rate-limit headers (plan budget client-side).
2. **Batching works on both endpoints** — N spots collapse to 2 batched HTTP
   calls total (1 forecast + 1 marine) instead of 2 calls per spot. The parser
   must handle the object-vs-array response shape and key results by **array
   index**, since snapped coords differ from inputs and between endpoints.
