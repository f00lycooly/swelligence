"""UKHO Admiralty tide overlay — UK-only high/low water predictions.

The UK Hydrographic Office Admiralty UK Tidal API is station-based and keyed by
an ``Ocp-Apim-Subscription-Key`` header. Register for a free key on the developer
portal (https://developer.admiralty.co.uk — sign up, then subscribe to the
"UK Tidal API - Discovery" product: 607 UK stations, current + 6 days of events,
10k calls/month). The earlier Azure portal (admiraltyapi.portal.azure-api.net) is
retired; the API *gateway* below is unchanged. We resolve the nearest tidal station to
the spot's coordinate (one cached ``/Stations`` call), then fetch that station's
tidal events. It supplies tides only — no wind/wave — so it implements
:class:`TideProvider` and overlays any forecast provider.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..geo import haversine_km
from .base import TideEvent, TideProvider
from .domains import TIDE

_LOGGER = logging.getLogger(__name__)

_BASE = "https://admiraltyapi.azure-api.net/uktidalapi/api/V1"


class UKHOTideProvider(TideProvider):
    """UK-only tidal-event overlay backed by the UKHO Admiralty API."""

    key = "ukho"
    label = "UKHO Admiralty (UK tides, key required)"
    requires_api_key = True
    # The authoritative UK tide source; region-gated to the UK bounding box.
    authority_rank = {TIDE: 100}

    # UK bounding box (lat_min, lat_max, lon_min, lon_max).
    _UK_BBOX = (49.0, 61.0, -8.5, 2.0)

    @classmethod
    def covers(cls, latitude: float, longitude: float) -> bool:
        la0, la1, lo0, lo1 = cls._UK_BBOX
        return la0 <= latitude <= la1 and lo0 <= longitude <= lo1

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
        best_dist = float("inf")
        for feat in (payload or {}).get("features") or []:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            s_lon, s_lat = coords[0], coords[1]
            dist = haversine_km(lat, lon, s_lat, s_lon)
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
