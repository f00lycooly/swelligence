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

from datetime import timezone

from ..geo import haversine_km
from .base import ForecastPoint, ForecastProvider, SpotForecast, TideEvent, TideProvider
from .domains import AIR, TIDE, WATER, WAVE, WIND

_LOGGER = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

_MS_TO_KN = 1.943_84
_KMH_TO_KN = 0.539_957

_FORECAST_HOURLY = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "cloud_cover",
    "uv_index",
    "visibility",
    "weather_code",
    "precipitation_probability",
    "cape",
]
_MARINE_HOURLY = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "swell_wave_period",
    "swell_wave_direction",
    "swell_wave_peak_period",
    "wind_wave_height",
    "wind_wave_period",
    "secondary_swell_wave_height",
    "secondary_swell_wave_period",
    "secondary_swell_wave_direction",
    "ocean_current_velocity",
    "ocean_current_direction",
    "sea_level_height_msl",
    "sea_surface_temperature",
]


class OpenMeteoProvider(ForecastProvider):
    """Keyless Open-Meteo forecast + marine provider."""

    key = "open_meteo"
    label = "Open-Meteo (free, no key)"
    requires_api_key = False
    supports_marine = True
    provides_domains = frozenset({WIND, AIR, WAVE, WATER})
    # Baseline marine authority: a valid swell source everywhere, but the lowest
    # rank — a keyed model resolving exposed-coast swell outranks it.
    authority_rank = {WAVE: 0}

    async def async_fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
        marine: bool = True,
    ) -> SpotForecast:
        wind = await self._get(
            _FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(_FORECAST_HOURLY),
                "daily": "sunrise,sunset",
                "wind_speed_unit": "ms",
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        marine_data = None
        if marine:
            marine_data = await self._get(
                _MARINE_URL,
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "hourly": ",".join(_MARINE_HOURLY),
                    "forecast_days": days,
                    "timezone": "auto",
                },
                optional=True,
            )
        return self._build_forecast(latitude, longitude, wind, marine_data, marine)

    async def async_fetch_many(
        self, coords: list[tuple[float, float, bool]], *, days: int = 7
    ) -> list[SpotForecast]:
        """Fetch many coordinates in (at most) two batched calls.

        ``coords`` is ``[(lat, lon, marine), ...]``. Open-Meteo accepts
        comma-separated latitude/longitude lists and returns a JSON array of
        per-location results (a single object when only one coord is requested).
        One forecast call + one marine call cover *all* coords, replacing two
        calls per spot. The marine call is made once for every coord (and skipped
        entirely if no coord wants marine); its data is applied only to coords
        whose ``marine`` flag is set, so inland spots stay marine-free. Results
        are matched back to inputs by array index — snapped grid coords differ
        from inputs and between the two grids, so equality matching would be
        wrong. Returns one SpotForecast per input coord, in order.
        """
        if not coords:
            return []
        lats = ",".join(str(lat) for lat, _, _ in coords)
        lons = ",".join(str(lon) for _, lon, _ in coords)
        wind = await self._get(
            _FORECAST_URL,
            {
                "latitude": lats,
                "longitude": lons,
                "hourly": ",".join(_FORECAST_HOURLY),
                "daily": "sunrise,sunset",
                "wind_speed_unit": "ms",
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        marine_data = None
        if any(want_marine for _, _, want_marine in coords):
            marine_data = await self._get(
                _MARINE_URL,
                {
                    "latitude": lats,
                    "longitude": lons,
                    "hourly": ",".join(_MARINE_HOURLY),
                    "forecast_days": days,
                    "timezone": "auto",
                },
                optional=True,
            )
        winds = _as_list(wind)
        marines = _as_list(marine_data)
        out: list[SpotForecast] = []
        for i, (lat, lon, want_marine) in enumerate(coords):
            marine_i = _at(marines, i) if want_marine else None
            out.append(self._build_forecast(lat, lon, _at(winds, i), marine_i, want_marine))
        return out

    def _build_forecast(
        self,
        latitude: float,
        longitude: float,
        wind: dict | None,
        marine_data: dict | None,
        marine: bool,
    ) -> SpotForecast:
        """Assemble a SpotForecast from a coord's wind + marine payloads.

        Shared by the single-coord :meth:`async_fetch` and the batched
        :meth:`async_fetch_many` so both normalise identically.
        """
        points = self._merge(wind, marine_data)
        meta = {
            "model": (wind or {}).get("timezone_abbreviation", "open-meteo"),
            # Point times are naive *local*; this lets tide scoring align them
            # with UTC tide events.
            "utc_offset_seconds": (wind or {}).get("utc_offset_seconds", 0),
        }
        if not marine:
            meta["marine"] = "skipped (inland spot)"
        elif not marine_data:
            meta["marine"] = "unavailable (unsupported grid)"
        # Open-Meteo snaps the request to the nearest model grid cell and echoes
        # that cell's coordinates back. The offset is a data-quality signal: a
        # coarse cell far from the spot (especially offshore for the marine grid)
        # is less representative. Prefer the marine cell where it resolved.
        dist = _grid_distance_km(latitude, longitude, marine_data or wind)
        if dist is not None:
            meta["grid_distance_km"] = round(dist, 1)
        forecast = SpotForecast(
            provider=self.key,
            latitude=latitude,
            longitude=longitude,
            points=points,
            daily_sun=self._parse_sun(wind),
            source_meta=meta,
        )
        # When the marine grid is missing, only wind/air actually came back.
        self._stamp_sources(forecast, marine=bool(marine and marine_data))
        return forecast

    @staticmethod
    def _parse_sun(wind: dict | None) -> dict:
        """Map each forecast date to its sunrise/sunset datetimes."""
        daily = (wind or {}).get("daily", {})
        dates = daily.get("time", [])
        sunrise = daily.get("sunrise", [])
        sunset = daily.get("sunset", [])
        out: dict = {}
        for i, day in enumerate(dates):
            sr = _at(sunrise, i)
            ss = _at(sunset, i)
            out[day] = {
                "sunrise": datetime.fromisoformat(sr) if sr else None,
                "sunset": datetime.fromisoformat(ss) if ss else None,
            }
        return out

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

        def kmh_kn(values: list, i: int | None) -> float | None:
            v = _at(values, i)
            return round(v * _KMH_TO_KN, 1) if v is not None else None

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
                    apparent_temp_c=_at(wh.get("apparent_temperature", []), i),
                    precip_mm=_at(wh.get("precipitation", []), i),
                    cloud_pct=_at(wh.get("cloud_cover", []), i),
                    uv_index=_at(wh.get("uv_index", []), i),
                    visibility_m=_at(wh.get("visibility", []), i),
                    weather_code=_at(wh.get("weather_code", []), i),
                    precip_prob_pct=_at(wh.get("precipitation_probability", []), i),
                    cape_jkg=_at(wh.get("cape", []), i),
                    wave_height_m=_at(mh.get("wave_height", []), mi),
                    wave_period_s=_at(mh.get("wave_period", []), mi),
                    wave_dir_deg=_at(mh.get("wave_direction", []), mi),
                    swell_height_m=_at(mh.get("swell_wave_height", []), mi),
                    swell_period_s=_at(mh.get("swell_wave_period", []), mi),
                    swell_dir_deg=_at(mh.get("swell_wave_direction", []), mi),
                    swell_peak_period_s=_at(mh.get("swell_wave_peak_period", []), mi),
                    wind_wave_height_m=_at(mh.get("wind_wave_height", []), mi),
                    wind_wave_period_s=_at(mh.get("wind_wave_period", []), mi),
                    secondary_swell_height_m=_at(
                        mh.get("secondary_swell_wave_height", []), mi
                    ),
                    secondary_swell_period_s=_at(
                        mh.get("secondary_swell_wave_period", []), mi
                    ),
                    secondary_swell_dir_deg=_at(
                        mh.get("secondary_swell_wave_direction", []), mi
                    ),
                    current_speed_kn=kmh_kn(mh.get("ocean_current_velocity", []), mi),
                    current_dir_deg=_at(mh.get("ocean_current_direction", []), mi),
                    sea_level_m=_at(mh.get("sea_level_height_msl", []), mi),
                    water_temp_c=_at(mh.get("sea_surface_temperature", []), mi),
                )
            )
        return points


class OpenMeteoTideProvider(TideProvider):
    """Keyless, global *modeled* tide fallback (priority 0).

    The lowest-authority tide source: it derives high/low water from Open-Meteo's
    modeled ``sea_level_height_msl`` series rather than harmonic predictions, so
    it is *indicative*, not authority-grade — a regional authority (UKHO, NOAA
    CO-OPS) outranks it wherever one covers the coordinate. Its value is being
    keyless and global, so every tide-dependent spot gets *something* with no
    config. As the priority-0 entry it is exactly the fallback the resolver lands
    on when nothing better is available.
    """

    key = "open_meteo_tide"
    label = "Open-Meteo (modeled tide, no key)"
    requires_api_key = False
    authority_rank = {TIDE: 0}

    async def async_fetch_tides(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
    ) -> list[TideEvent]:
        # Request in UTC (no timezone= -> GMT) so derived event times share the
        # UTC basis the coordinator normalises against.
        payload = await self._get(
            _MARINE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "sea_level_height_msl",
                "forecast_days": days,
            },
            optional=True,
        )
        hourly = (payload or {}).get("hourly") or {}
        return _derive_tide_extremes(
            hourly.get("time") or [], hourly.get("sea_level_height_msl") or []
        )

    async def _get(self, url: str, params: dict, *, optional: bool = False):
        try:
            async with self._session.get(url, params=params, timeout=30) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:  # noqa: BLE001 - tide fallback is best-effort
            if optional:
                _LOGGER.debug("Optional Open-Meteo tide call failed: %s", err)
                return None
            raise


def _derive_tide_extremes(times: list, levels: list) -> list[TideEvent]:
    """High/low water from a sea-level series: the turning points.

    A timestep is a high when it is a local maximum (>= both hourly neighbours,
    strictly greater than one), a low when a local minimum. Hourly sampling
    resolves the ~6 h between extremes comfortably. Times are parsed as UTC (the
    series was requested in GMT) so the coordinator's UTC normalisation aligns.
    """
    events: list[TideEvent] = []
    for i in range(1, len(levels) - 1):
        a, b, c = levels[i - 1], levels[i], levels[i + 1]
        if a is None or b is None or c is None:
            continue
        if b >= a and b >= c and b > min(a, c):
            kind = "high"
        elif b <= a and b <= c and b < max(a, c):
            kind = "low"
        else:
            continue
        when = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc)
        events.append(TideEvent(time=when, kind=kind, height_m=round(b, 2)))
    return events


def _as_list(payload) -> list:
    """Normalise a batched Open-Meteo response to a per-location list.

    A single comma-separated coordinate returns a top-level object; multiple
    return a top-level array. ``None`` (failed/optional call) -> empty list.
    """
    if payload is None:
        return []
    return payload if isinstance(payload, list) else [payload]


def _at(values: list, i: int | None):
    """Safe list access returning None for missing index/value."""
    if i is None or not values or i >= len(values):
        return None
    return values[i]


def _grid_distance_km(lat: float, lon: float, payload: dict | None) -> float | None:
    """Distance from the requested coord to the grid cell Open-Meteo resolved.

    The forecast/marine responses echo the snapped cell's ``latitude``/
    ``longitude``. ``None`` when the payload is missing or omits them.
    """
    if not payload:
        return None
    g_lat, g_lon = payload.get("latitude"), payload.get("longitude")
    if g_lat is None or g_lon is None:
        return None
    return haversine_km(lat, lon, g_lat, g_lon)
