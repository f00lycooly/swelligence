"""NOAA CO-OPS tide overlay — US high/low water predictions (free, no key).

NOAA's Center for Operational Oceanographic Products and Services (CO-OPS)
publishes harmonic tide predictions for US stations with no API key and US
public-domain terms. Like UKHO it is station-based: resolve the nearest tide
station to the spot (one cached metadata call), then fetch that station's
high/low predictions. Tides only — implements :class:`TideProvider` and overlays
any forecast provider. It is the authoritative US tide source, region-gated to
US waters so the resolver never picks it elsewhere.

* Stations:    https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json
* Predictions: https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..geo import haversine_km
from .base import TideEvent, TideProvider
from .domains import TIDE

_LOGGER = logging.getLogger(__name__)

_STATIONS_URL = (
    "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
)
_DATA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


class NOAACoopsTideProvider(TideProvider):
    """US tidal-event overlay backed by the keyless NOAA CO-OPS API."""

    key = "noaa_coops"
    label = "NOAA CO-OPS (US tides, no key)"
    requires_api_key = False
    # Authoritative US tide source, region-gated. Same rank as UKHO — they cover
    # disjoint regions, so they never compete for the same coordinate.
    authority_rank = {TIDE: 100}

    # US coverage as a set of (lat_min, lat_max, lon_min, lon_max) boxes:
    # CONUS, Alaska (mainland + eastern Aleutians), Hawaii, Puerto Rico/USVI.
    # (Aleutians west of the antimeridian are a known small gap.)
    _US_BBOXES = (
        (24.0, 50.0, -125.0, -66.0),  # CONUS
        (50.0, 72.0, -170.0, -129.0),  # Alaska
        (18.0, 23.0, -161.0, -154.0),  # Hawaii
        (17.0, 19.0, -68.0, -64.0),  # Puerto Rico / USVI
    )

    @classmethod
    def covers(cls, latitude: float, longitude: float) -> bool:
        return any(
            la0 <= latitude <= la1 and lo0 <= longitude <= lo1
            for la0, la1, lo0, lo1 in cls._US_BBOXES
        )

    async def async_fetch_tides(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
    ) -> list[TideEvent]:
        stations = await self._get(_STATIONS_URL, {"type": "tidepredictions"})
        station_id = self._nearest_station(stations, latitude, longitude)
        if station_id is None:
            _LOGGER.debug("No NOAA CO-OPS station near (%s, %s)", latitude, longitude)
            return []
        begin, end = _window(days)
        payload = await self._get(
            _DATA_URL,
            {
                "product": "predictions",
                "interval": "hilo",  # high/low events, not the 6-min series
                "datum": "MLLW",
                "units": "metric",  # heights in metres (matches the model)
                "time_zone": "gmt",  # event times in UTC
                "format": "json",
                "station": station_id,
                "begin_date": begin,
                "end_date": end,
            },
        )
        return self._parse_predictions(payload)

    @staticmethod
    def _nearest_station(payload: dict | None, lat: float, lon: float) -> str | None:
        """Return the id of the closest CO-OPS station by great-circle distance."""
        best_id: str | None = None
        best_dist = float("inf")
        for st in (payload or {}).get("stations") or []:
            s_lat, s_lon = st.get("lat"), st.get("lng")
            if s_lat is None or s_lon is None:
                continue
            dist = haversine_km(lat, lon, s_lat, s_lon)
            if dist < best_dist:
                best_dist = dist
                best_id = st.get("id")
        return best_id

    @staticmethod
    def _parse_predictions(payload: dict | None) -> list[TideEvent]:
        out: list[TideEvent] = []
        for item in (payload or {}).get("predictions") or []:
            t = item.get("t")
            if not t:
                continue
            kind = "high" if str(item.get("type", "")).upper().startswith("H") else "low"
            try:
                height = float(item["v"])
            except (KeyError, TypeError, ValueError):
                height = None
            # "YYYY-MM-DD HH:MM" in GMT -> aware UTC.
            when = datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            out.append(TideEvent(time=when, kind=kind, height_m=height))
        return out

    async def _get(self, url: str, params: dict) -> dict | None:
        try:
            async with self._session.get(url, params=params, timeout=30) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as err:  # noqa: BLE001 - tide overlay is best-effort
            _LOGGER.debug("NOAA CO-OPS call failed (%s): %s", url, err)
            return None


def _window(days: int) -> tuple[str, str]:
    """(begin_date, end_date) as ``YYYYMMDD`` UTC strings, now .. now+days."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d"), (now + timedelta(days=days)).strftime("%Y%m%d")
