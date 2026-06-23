"""Open-Meteo provider — keyless default (forecast + marine APIs).

Open-Meteo resolves the nearest model grid cell from the coordinate itself, so
"locking onto a nearby provider" is implicit. Two endpoints are merged:

* https://api.open-meteo.com/v1/forecast  — wind, gust, temp, precip, cloud
* https://marine-api.open-meteo.com/v1/marine — wave/swell height, period, dir

The marine call is best-effort: inland spots (and some regions) have no marine
grid, in which case wave fields stay ``None`` and only wind-based sports score.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base import ForecastPoint, ForecastProvider, SpotForecast

_LOGGER = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

_MS_TO_KN = 1.943_84

_FORECAST_HOURLY = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
    "precipitation",
    "cloud_cover",
]
_MARINE_HOURLY = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "swell_wave_period",
    "sea_surface_temperature",
]


class OpenMeteoProvider(ForecastProvider):
    """Keyless Open-Meteo forecast + marine provider."""

    key = "open_meteo"
    label = "Open-Meteo (free, no key)"
    requires_api_key = False
    supports_marine = True

    async def async_fetch(
        self, latitude: float, longitude: float, *, hours: int = 48
    ) -> SpotForecast:
        wind = await self._get(
            _FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(_FORECAST_HOURLY),
                "wind_speed_unit": "ms",
                "forecast_hours": hours,
                "timezone": "auto",
            },
        )
        marine = await self._get(
            _MARINE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(_MARINE_HOURLY),
                "forecast_hours": hours,
                "timezone": "auto",
            },
            optional=True,
        )

        points = self._merge(wind, marine)
        meta = {"model": (wind or {}).get("timezone_abbreviation", "open-meteo")}
        if not marine:
            meta["marine"] = "unavailable (inland or unsupported grid)"
        return SpotForecast(
            provider=self.key,
            latitude=latitude,
            longitude=longitude,
            points=points,
            source_meta=meta,
        )

    async def _get(
        self, url: str, params: dict, *, optional: bool = False
    ) -> dict | None:
        try:
            async with self._session.get(url, params=params, timeout=30) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:  # noqa: BLE001 - normalise to None for caller
            if optional:
                _LOGGER.debug("Optional Open-Meteo call failed (%s): %s", url, err)
                return None
            raise

    @staticmethod
    def _merge(wind: dict | None, marine: dict | None) -> list[ForecastPoint]:
        if not wind or "hourly" not in wind:
            return []
        wh = wind["hourly"]
        times = wh.get("time", [])
        mh = (marine or {}).get("hourly", {}) if marine else {}
        # Index marine values by time so grids with differing lengths still align.
        m_index = {t: i for i, t in enumerate(mh.get("time", []))}

        def kn(values: list, i: int) -> float | None:
            v = _at(values, i)
            return round(v * _MS_TO_KN, 1) if v is not None else None

        points: list[ForecastPoint] = []
        for i, iso in enumerate(times):
            mi = m_index.get(iso)
            points.append(
                ForecastPoint(
                    time=datetime.fromisoformat(iso),
                    wind_speed_kn=kn(wh.get("wind_speed_10m", []), i),
                    wind_gust_kn=kn(wh.get("wind_gusts_10m", []), i),
                    wind_dir_deg=_at(wh.get("wind_direction_10m", []), i),
                    air_temp_c=_at(wh.get("temperature_2m", []), i),
                    precip_mm=_at(wh.get("precipitation", []), i),
                    cloud_pct=_at(wh.get("cloud_cover", []), i),
                    wave_height_m=_at(mh.get("wave_height", []), mi),
                    wave_period_s=_at(mh.get("wave_period", []), mi),
                    wave_dir_deg=_at(mh.get("wave_direction", []), mi),
                    swell_height_m=_at(mh.get("swell_wave_height", []), mi),
                    swell_period_s=_at(mh.get("swell_wave_period", []), mi),
                    water_temp_c=_at(mh.get("sea_surface_temperature", []), mi),
                )
            )
        return points


def _at(values: list, i: int | None):
    """Safe list access returning None for missing index/value."""
    if i is None or not values or i >= len(values):
        return None
    return values[i]
