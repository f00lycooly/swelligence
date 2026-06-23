"""Windy provider — keyed global wind/wave via the Point Forecast API.

Windy's Point Forecast API (https://api.windy.com/point-forecast/docs) is a
keyed POST endpoint. Wind comes as u/v components on the ``gfs`` model; waves
need a second request against the ``gfsWave`` model. We merge both by timestamp.

Components are metres/second (converted to knots), temperatures Kelvin
(converted to °C). Wind direction is derived from the u/v vector using the
meteorological "from" convention.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from .base import ForecastPoint, ForecastProvider, SpotForecast
from .domains import AIR, WAVE, WIND

_LOGGER = logging.getLogger(__name__)

_URL = "https://api.windy.com/api/point-forecast/v2"

_MS_TO_KN = 1.943_84

_WIND_PARAMS = ["wind", "windGust", "temp", "precip", "lclouds"]
_WAVE_PARAMS = ["waves", "swell1"]


class WindyProvider(ForecastProvider):
    """Keyed Windy point-forecast provider."""

    key = "windy"
    label = "Windy (key required)"
    requires_api_key = True
    supports_marine = True
    provides_domains = frozenset({WIND, AIR, WAVE})

    async def async_fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
        marine: bool = True,
    ) -> SpotForecast:
        wind = await self._post(latitude, longitude, "gfs", _WIND_PARAMS)
        wave = None
        if marine:
            wave = await self._post(
                latitude, longitude, "gfsWave", _WAVE_PARAMS, optional=True
            )
        points = self._parse(wind, wave)
        meta = {"model": "windy:gfs"}
        if not marine:
            meta["marine"] = "skipped (inland spot)"
        elif not wave:
            meta["marine"] = "unavailable (no gfsWave grid)"
        forecast = SpotForecast(
            provider=self.key,
            latitude=latitude,
            longitude=longitude,
            points=points,
            source_meta=meta,
        )
        self._stamp_sources(forecast, marine=bool(marine and wave))
        return forecast

    @staticmethod
    def _series(payload: dict | None, key: str) -> list:
        return (payload or {}).get(key) or []

    @classmethod
    def _parse(cls, wind: dict | None, wave: dict | None) -> list[ForecastPoint]:
        ts = cls._series(wind, "ts")
        if not ts:
            return []
        u = cls._series(wind, "wind_u-surface")
        v = cls._series(wind, "wind_v-surface")
        gust = cls._series(wind, "gust-surface")
        temp = cls._series(wind, "temp-surface")
        precip = cls._series(wind, "past3hprecip-surface")
        clouds = cls._series(wind, "lclouds-surface")

        # Index wave values by timestamp; the wave model may differ in length.
        wave_ts = cls._series(wave, "ts")
        w_index = {t: i for i, t in enumerate(wave_ts)}
        wh = cls._series(wave, "waves_height-surface")
        wp = cls._series(wave, "waves_period-surface")
        wd = cls._series(wave, "waves_direction-surface")
        sh = cls._series(wave, "swell1_height-surface")
        sp = cls._series(wave, "swell1_period-surface")

        points: list[ForecastPoint] = []
        for i, epoch_ms in enumerate(ts):
            speed = direction = None
            ui, vi = _at(u, i), _at(v, i)
            if ui is not None and vi is not None:
                speed = round(math.hypot(ui, vi) * _MS_TO_KN, 1)
                direction = round((270 - math.degrees(math.atan2(vi, ui))) % 360, 1)
            wi = w_index.get(epoch_ms)
            g = _at(gust, i)
            t = _at(temp, i)
            points.append(
                ForecastPoint(
                    time=datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc),
                    wind_speed_kn=speed,
                    wind_gust_kn=round(g * _MS_TO_KN, 1) if g is not None else None,
                    wind_dir_deg=direction,
                    air_temp_c=round(t - 273.15, 1) if t is not None else None,
                    precip_mm=_at(precip, i),
                    cloud_pct=_at(clouds, i),
                    wave_height_m=_at(wh, wi),
                    wave_period_s=_at(wp, wi),
                    wave_dir_deg=_at(wd, wi),
                    swell_height_m=_at(sh, wi),
                    swell_period_s=_at(sp, wi),
                )
            )
        return points

    async def _post(
        self,
        latitude: float,
        longitude: float,
        model: str,
        parameters: list[str],
        *,
        optional: bool = False,
    ) -> dict | None:
        if not self._api_key:
            if optional:
                return None
            raise RuntimeError("Windy requires an API key")
        body = {
            "lat": latitude,
            "lon": longitude,
            "model": model,
            "parameters": parameters,
            "levels": ["surface"],
            "key": self._api_key,
        }
        try:
            async with self._session.post(_URL, json=body, timeout=30) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:  # noqa: BLE001 - normalise to None for optional calls
            if optional:
                _LOGGER.debug("Optional Windy %s call failed: %s", model, err)
                return None
            raise


def _at(values: list, i: int | None):
    """Safe list access returning None for missing index/value."""
    if i is None or not values or i >= len(values):
        return None
    return values[i]
