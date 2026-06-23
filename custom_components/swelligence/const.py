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

# Per-spot keys
CONF_SPOT_ID: Final = "id"
CONF_SPOT_NAME: Final = "name"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_SPOT_SPORTS: Final = "sports"  # subset of enabled sports relevant to this spot
CONF_WATER_TYPE: Final = "water_type"  # "sea" | "inland"

# Per-sport preference keys
PREF_WIND_MIN: Final = "wind_min_kn"
PREF_WIND_MAX: Final = "wind_max_kn"
PREF_WIND_IDEAL: Final = "wind_ideal_kn"
PREF_GUST_MAX: Final = "gust_max_kn"
PREF_WIND_DIRS: Final = "wind_dirs"  # list of compass sectors, e.g. ["SW", "W"]
PREF_WAVE_MIN_M: Final = "wave_min_m"
PREF_WAVE_MAX_M: Final = "wave_max_m"
PREF_WATER_TEMP_MIN_C: Final = "water_temp_min_c"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 30

WATER_TYPE_SEA: Final = "sea"
WATER_TYPE_INLAND: Final = "inland"

# Compass sectors used for wind-direction matching
COMPASS_SECTORS: Final = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

PLATFORMS: Final = ["sensor", "binary_sensor"]
