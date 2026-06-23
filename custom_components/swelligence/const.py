"""Constants for the swelligence integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "swelligence"

# Config / options keys ------------------------------------------------------
CONF_SPOTS: Final = "spots"
CONF_SPORTS: Final = "sports"
CONF_PROVIDERS: Final = "providers"
CONF_DEFAULT_PROVIDER: Final = "default_provider"
CONF_AI_TASK_ENTITY: Final = "ai_task_entity_id"
CONF_USE_LLM: Final = "use_llm"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

# Single local rider personalisation
CONF_RIDER: Final = "rider"
CONF_RIDER_WEIGHT: Final = "weight_kg"
CONF_QUIVER: Final = "quiver"  # {sport: [sizes_m2]}

# Per-provider API key field (nested under CONF_PROVIDERS[key]["api_key"])
CONF_API_KEY: Final = "api_key"
# Per-provider free-tier flag — when set, polling is auto-throttled to the
# provider's free daily request budget (nested under CONF_PROVIDERS[key]).
CONF_FREE_TIER: Final = "free_tier"

# add_spot: optional place-name search resolved via Open-Meteo geocoding.
CONF_PLACE_QUERY: Final = "place_query"

# Per-spot keys
CONF_SPOT_ID: Final = "id"
CONF_SPOT_NAME: Final = "name"
# Per-spot primary provider (wind/air/base). Falls back to the entry default.
# Marine/tide sources also accept per-spot overrides (CONF_MARINE_SOURCE /
# CONF_TIDE_SOURCE on the spot dict) — that's per-domain source routing.
CONF_SPOT_PROVIDER: Final = "provider"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_SPOT_SPORTS: Final = "sports"  # subset of enabled sports relevant to this spot
CONF_WATER_TYPE: Final = "water_type"  # "sea" | "sheltered" | "inland"
CONF_TIDE_STATE: Final = "tide_state"  # "any"|"high"|"low"|"mid" — spot tide pref
CONF_TIDE_WINDOW_H: Final = "tide_window_h"  # hours either side of the ideal state

# Entry-level tide overlay: which TideProvider supplies tides when the spot's
# forecast provider doesn't (key under CONF_PROVIDERS[source]["api_key"]).
CONF_TIDE_SOURCE: Final = "tide_source"

# Entry-level marine overlay: a keyed provider whose waves/swell/sea-temp are
# layered onto the (keyless) base where it lacks them ("gap-fill") or always
# ("prefer"). Budget-throttled by the same free-tier interval as polling.
CONF_MARINE_SOURCE: Final = "marine_source"
CONF_MARINE_PREFER: Final = "marine_prefer"
CONF_SPOT_PREFS: Final = "prefs"  # {sport: {field: value}} per-spot profile overrides

# Per-sport preference keys
PREF_WIND_MIN: Final = "wind_min_kn"
PREF_WIND_MAX: Final = "wind_max_kn"
PREF_WIND_IDEAL: Final = "wind_ideal_kn"
PREF_GUST_MAX: Final = "gust_max_kn"
PREF_WIND_DIRS: Final = "wind_dirs"  # list of compass sectors, e.g. ["SW", "W"]
PREF_WAVE_MIN_M: Final = "wave_min_m"
PREF_WAVE_IDEAL_M: Final = "wave_ideal_m"
PREF_WAVE_MAX_M: Final = "wave_max_m"
PREF_SWELL_PERIOD: Final = "swell_period_ideal_s"  # ideal swell period (groundswell)
PREF_SWELL_DIRS: Final = "swell_dirs"  # spot's swell window (compass sectors)
PREF_WATER_TEMP_MIN_C: Final = "water_temp_min_c"

# Profile fields a user may override per spot/sport. These string values match
# SportProfile field names exactly so overrides map straight to dataclasses.replace.
OVERRIDE_FIELDS: Final = [
    PREF_WIND_MIN,
    PREF_WIND_IDEAL,
    PREF_WIND_MAX,
    PREF_GUST_MAX,
    PREF_WIND_DIRS,
    PREF_WAVE_MIN_M,
    PREF_WAVE_IDEAL_M,
    PREF_WAVE_MAX_M,
    PREF_SWELL_PERIOD,
    PREF_SWELL_DIRS,
    PREF_WATER_TEMP_MIN_C,
]

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 30

WATER_TYPE_SEA: Final = "sea"
WATER_TYPE_SHELTERED: Final = "sheltered"  # harbour/estuary: flat, no open-sea swell
WATER_TYPE_INLAND: Final = "inland"  # lake/cable park: no marine data at all

WATER_TYPES: Final = [WATER_TYPE_SEA, WATER_TYPE_SHELTERED, WATER_TYPE_INLAND]

# Compass sectors used for wind-direction matching
COMPASS_SECTORS: Final = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

PLATFORMS: Final = ["sensor", "binary_sensor"]
