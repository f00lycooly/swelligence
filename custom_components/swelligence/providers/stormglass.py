"""Stormglass provider — keyed global marine + weather + tides.

Stormglass (https://stormglass.io) is a paid API keyed by an ``Authorization``
header. It serves wind/wave/swell/temperature on one ``weather/point`` endpoint
and tidal extremes on ``tide/extremes/point`` — so a single provider supplies
both the hourly forecast and the tide overlay.

Each weather parameter comes back as ``{"sg": value, "noaa": value, ...}`` keyed
by source model; we prefer the Stormglass blend (``"sg"``) and fall back to the
first available source. Wind speed is metres/second, heights metres, temps °C.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .base import ForecastPoint, ForecastProvider, SpotForecast, TideEvent, TideProvider

_LOGGER = logging.getLogger(__name__)

_WEATHER_URL = "https://api.stormglass.io/v2/weather/point"
_TIDE_URL = "https://api.stormglass.io/v2/tide/extremes/point"

_MS_TO_KN = 1.943_84

# Stormglass parameter name -> ForecastPoint field + whether it is a wind speed
# (needs m/s -> kn conversion).
_WEATHER_PARAMS: dict[str, tuple[str, bool]] = {
    "windSpeed": ("wind_speed_kn", True),
    "gust": ("wind_gust_kn", True),
    "windDirection": ("wind_dir_deg", False),
    "waveHeight": ("wave_height_m", False),
    "wavePeriod": ("wave_period_s", False),
    "waveDirection": ("wave_dir_deg", False),
    "swellHeight": ("swell_height_m", False),
    "swellPeriod": ("swell_period_s", False),
    "airTemperature": ("air_temp_c", False),
    "waterTemperature": ("water_temp_c", False),
    "precipitation": ("precip_mm", False),
    "cloudCover": ("cloud_pct", False),
}
_MARINE_FIELDS = {
    "wave_height_m",
    "wave_period_s",
    "wave_dir_deg",
    "swell_height_m",
    "swell_period_s",
    "water_temp_c",
}


class StormglassProvider(ForecastProvider, TideProvider):
    """Keyed Stormglass forecast + tide provider."""

    key = "stormglass"
    label = "Stormglass (key required, marine + tides)"
    requires_api_key = True
    supports_marine = True

    async def async_fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
        marine: bool = True,
    ) -> SpotForecast:
        params = [p for p in _WEATHER_PARAMS if marine or _WEATHER_PARAMS[p][0] not in _MARINE_FIELDS]
        start, end = _window(days)
        weather = await self._get(
            _WEATHER_URL,
            {
                "lat": latitude,
                "lng": longitude,
                "params": ",".join(params),
                "start": start,
                "end": end,
            },
        )
        tides: list[TideEvent] = []
        if marine:
            tides = await self.async_fetch_tides(
                latitude, longitude, days=days, _optional=True
            )

        points = self._parse_weather(weather)
        meta = {"model": "stormglass:sg"}
        if not marine:
            meta["marine"] = "skipped (inland spot)"
        return SpotForecast(
            provider=self.key,
            latitude=latitude,
            longitude=longitude,
            points=points,
            tide_events=tides,
            source_meta=meta,
        )

    async def async_fetch_tides(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
        _optional: bool = False,
    ) -> list[TideEvent]:
        start, end = _window(days)
        payload = await self._get(
            _TIDE_URL,
            {"lat": latitude, "lng": longitude, "start": start, "end": end},
            optional=_optional,
        )
        return self._parse_tides(payload)

    @staticmethod
    def _pick(param: dict | None):
        """Pick the preferred source value from a Stormglass parameter dict."""
        if not isinstance(param, dict) or not param:
            return None
        if "sg" in param and param["sg"] is not None:
            return param["sg"]
        for value in param.values():
            if value is not None:
                return value
        return None

    @classmethod
    def _parse_weather(cls, payload: dict | None) -> list[ForecastPoint]:
        hours = (payload or {}).get("hours") or []
        points: list[ForecastPoint] = []
        for hour in hours:
            iso = hour.get("time")
            if not iso:
                continue
            kwargs: dict = {}
            for sg_name, (field, is_wind) in _WEATHER_PARAMS.items():
                value = cls._pick(hour.get(sg_name))
                if value is None:
                    continue
                kwargs[field] = round(value * _MS_TO_KN, 1) if is_wind else value
            points.append(ForecastPoint(time=_parse_dt(iso), **kwargs))
        return points

    @staticmethod
    def _parse_tides(payload: dict | None) -> list[TideEvent]:
        out: list[TideEvent] = []
        for item in (payload or {}).get("data") or []:
            iso = item.get("time")
            if not iso:
                continue
            kind = "high" if str(item.get("type", "")).lower().startswith("high") else "low"
            out.append(
                TideEvent(time=_parse_dt(iso), kind=kind, height_m=item.get("height"))
            )
        return out

    async def _get(
        self, url: str, params: dict, *, optional: bool = False
    ) -> dict | None:
        if not self._api_key:
            if optional:
                return None
            raise RuntimeError("Stormglass requires an API key")
        try:
            async with self._session.get(
                url, params=params, headers={"Authorization": self._api_key}, timeout=30
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:  # noqa: BLE001 - normalise to None for optional calls
            if optional:
                _LOGGER.debug("Optional Stormglass call failed (%s): %s", url, err)
                return None
            raise


def _window(days: int) -> tuple[str, str]:
    """Return (start, end) as second-precision UTC ISO-8601 strings.

    Computed from the first forecast point would need a clock; Stormglass accepts
    ISO timestamps, so we ask for ``now`` .. ``now + days`` using a UTC anchor.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat(), (now + timedelta(days=days)).isoformat()


def _parse_dt(iso: str) -> datetime:
    """Parse a Stormglass ISO time (``...Z`` or offset) to a datetime."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
