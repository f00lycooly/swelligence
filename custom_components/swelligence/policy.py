"""Water-type policy for forecast normalisation.

Open-Meteo's marine API resolves to the nearest *coastal* grid cell, so it
returns plausible-but-wrong wave/swell/sea-temperature for spots that aren't on
the open coast:

* **inland** (lake / cable park) — there is no marine data; the nearest-coastal
  cell is irrelevant. Don't fetch marine at all, and null any stray fields.
* **sheltered** (harbour / estuary) — flat water with no open-sea swell, but the
  marine grid reports the swell of the open sea offshore, badly over-penalising
  flat-water sports. Null the wave/swell fields (treat as flat) but keep
  sea-surface temperature, which is a fair proxy for harbour water temp.
* **sea** (open coast) — the marine grid is representative; keep everything.

This module is pure (no Home Assistant imports) so the coordinator and the
standalone validation runner apply the exact same rule.
"""

from __future__ import annotations

from .const import WATER_TYPE_INLAND, WATER_TYPE_SHELTERED
from .providers.base import SpotForecast


def marine_wanted(water_type: str) -> bool:
    """Whether the provider should bother fetching marine data for this spot."""
    return water_type != WATER_TYPE_INLAND


def _clear_waves(point) -> None:
    point.wave_height_m = None
    point.wave_period_s = None
    point.wave_dir_deg = None
    point.swell_height_m = None
    point.swell_period_s = None


def apply_water_policy(forecast: SpotForecast, water_type: str) -> None:
    """Mutate ``forecast`` in place to honour the spot's water type."""
    if water_type == WATER_TYPE_INLAND:
        for point in forecast.points:
            _clear_waves(point)
            point.water_temp_c = None
        forecast.source_meta["water_policy"] = "inland: marine suppressed"
    elif water_type == WATER_TYPE_SHELTERED:
        for point in forecast.points:
            _clear_waves(point)  # flat water; keep water_temp_c as a proxy
        forecast.source_meta["water_policy"] = "sheltered: waves suppressed, temp kept"
    # WATER_TYPE_SEA (and anything else): leave the forecast untouched.
