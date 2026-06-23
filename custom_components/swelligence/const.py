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

# add_spot: optional place-name search resolved via Open-Meteo geocoding.
CONF_PLACE_QUERY: Final = "place_query"

# Per-spot keys
CONF_SPOT_ID: Final = "id"
CONF_SPOT_NAME: Final = "name"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_SPOT_SPORTS: Final = "sports"  # subset of enabled sports relevant to this spot
CONF_WATER_TYPE: Final = "water_type"  # "sea" | "sheltered" | "inland"
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
