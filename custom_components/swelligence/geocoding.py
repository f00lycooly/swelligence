"""Place-name geocoding via the keyless Open-Meteo geocoding API.

Lets the add-spot flow resolve a place name ("Christchurch") to coordinates
instead of forcing manual lat/lon entry. The HTTP call is thin; the response
normalisation (:func:`_parse`) is pure so it unit-tests without a network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass(slots=True)
class GeocodeResult:
    """A single geocoding match."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None  # region / state / county

    @property
    def label(self) -> str:
        """Human-readable disambiguation label, e.g. 'Christchurch, Dorset, UK'."""
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


def _parse(payload: dict | None) -> list[GeocodeResult]:
    """Normalise an Open-Meteo geocoding response into GeocodeResults."""
    out: list[GeocodeResult] = []
    for r in (payload or {}).get("results") or []:
        lat, lon = r.get("latitude"), r.get("longitude")
        if lat is None or lon is None:
            continue
        out.append(
            GeocodeResult(
                name=r.get("name", "?"),
                latitude=lat,
                longitude=lon,
                country=r.get("country"),
                admin1=r.get("admin1"),
            )
        )
    return out


async def async_geocode(
    session: ClientSession,
    query: str,
    *,
    count: int = 5,
    language: str = "en",
) -> list[GeocodeResult]:
    """Geocode a place name to a ranked list of coordinate matches.

    Returns an empty list on no match or any transport error (the caller treats
    that as "no results" and falls back to manual coordinate entry).
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        async with session.get(
            _GEOCODE_URL,
            params={
                "name": query,
                "count": count,
                "language": language,
                "format": "json",
            },
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json()
    except Exception as err:  # noqa: BLE001 - any failure -> "no results"
        _LOGGER.warning("Geocoding '%s' failed: %s", query, err)
        return []
    return _parse(payload)
