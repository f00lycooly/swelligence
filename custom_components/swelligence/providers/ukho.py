"""UKHO Admiralty tide overlay — UK-only high/low water predictions.

The UK Hydrographic Office Admiralty UK Tidal API
(https://admiraltyapi.portal.azure-api.net) is station-based and keyed by an
``Ocp-Apim-Subscription-Key`` header. We resolve the nearest tidal station to
the spot's coordinate (one cached ``/Stations`` call), then fetch that station's
tidal events. It supplies tides only — no wind/wave — so it implements
:class:`TideProvider` and overlays any forecast provider.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from .base import TideEvent, TideProvider

_LOGGER = logging.getLogger(__name__)

_BASE = "https://admiraltyapi.azure-api.net/uktidalapi/api/V1"


class UKHOTideProvider(TideProvider):
    """UK-only tidal-event overlay backed by the UKHO Admiralty API."""

    key = "ukho"
    label = "UKHO Admiralty (UK tides, key required)"
    requires_api_key = True

    async def async_fetch_tides(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
    ) -> list[TideEvent]:
        stations = await self._get(f"{_BASE}/Stations")
        station_id = self._nearest_station(stations, latitude, longitude)
        if station_id is None:
            _LOGGER.debug("No UKHO tidal station near (%s, %s)", latitude, longitude)
            return []
        events = await self._get(
            f"{_BASE}/Stations/{station_id}/TidalEvents",
            params={"duration": min(days, 7)},
        )
        return self._parse_events(events)

    @staticmethod
    def _nearest_station(payload: dict | None, lat: float, lon: float) -> str | None:
        """Return the Id of the closest station by great-circle distance."""
        best_id: str | None = None
        best_dist = math.inf
        for feat in (payload or {}).get("features") or []:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            s_lon, s_lat = coords[0], coords[1]
            dist = _haversine(lat, lon, s_lat, s_lon)
            if dist < best_dist:
                best_dist = dist
                best_id = props.get("Id")
        return best_id

    @staticmethod
    def _parse_events(payload) -> list[TideEvent]:
        out: list[TideEvent] = []
        for item in payload or []:
            iso = item.get("DateTime")
            if not iso:
                continue
            event_type = str(item.get("EventType", ""))
            kind = "high" if "High" in event_type else "low"
            out.append(
                TideEvent(
                    time=datetime.fromisoformat(iso.replace("Z", "+00:00")),
                    kind=kind,
                    height_m=item.get("Height"),
                )
            )
        return out

    async def _get(self, url: str, params: dict | None = None) -> object:
        if not self._api_key:
            raise RuntimeError("UKHO requires an API key")
        async with self._session.get(
            url,
            params=params,
            headers={"Ocp-Apim-Subscription-Key": self._api_key},
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two coordinates."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
