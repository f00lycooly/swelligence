"""Place-name and UK-postcode geocoding for the add-spot flow.

Resolves a search term to candidate coordinates so the user doesn't hand-type
lat/lon. Two keyless sources, picked by query shape:

* **UK postcodes / outcodes** (``BH23 4AA``, ``BH6``) → postcodes.io. The
  Open-Meteo gazetteer can't resolve these at all.
* **Place / town names** (``Mudeford``) → Open-Meteo geocoding.

Both feed an interactive map in the config flow, so the search only needs to get
*near* the spot — the user drops the pin precisely. The HTTP calls are thin; the
response normalisers (``_parse*``) are pure and unit-test without a network.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_POSTCODES_URL = "https://api.postcodes.io"

# UK postcode shapes. Full: "BH23 4AA" (optional space); outcode only: "BH6".
_UK_POSTCODE = re.compile(r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$")
_UK_OUTCODE = re.compile(r"^[A-Za-z]{1,2}\d[A-Za-z\d]?$")


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


def _parse_postcode(payload: dict | None) -> list[GeocodeResult]:
    """Normalise a postcodes.io ``/postcodes`` or ``/outcodes`` response.

    Both endpoints return a single ``result`` object. ``admin_district`` /
    ``country`` are strings for postcodes but lists for outcodes.
    """
    r = (payload or {}).get("result")
    if not isinstance(r, dict):
        return []
    lat, lon = r.get("latitude"), r.get("longitude")
    if lat is None or lon is None:
        return []

    def _first(v: object) -> str | None:
        if isinstance(v, list):
            return v[0] if v else None
        return v if isinstance(v, str) else None

    name = (r.get("postcode") or r.get("outcode") or "").upper()
    return [
        GeocodeResult(
            name=name or "?",
            latitude=lat,
            longitude=lon,
            country=_first(r.get("country")),
            admin1=_first(r.get("admin_district")),
        )
    ]


async def _async_open_meteo(
    session: ClientSession, query: str, count: int, language: str
) -> list[GeocodeResult]:
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


async def _async_postcodes_io(session: ClientSession, query: str) -> list[GeocodeResult]:
    compact = query.replace(" ", "")
    if _UK_POSTCODE.match(query):
        url = f"{_POSTCODES_URL}/postcodes/{compact}"
    else:  # outcode
        url = f"{_POSTCODES_URL}/outcodes/{compact}"
    try:
        async with session.get(url, timeout=30) as resp:
            if resp.status == 404:  # unknown postcode -> no match
                return []
            resp.raise_for_status()
            payload = await resp.json()
    except Exception as err:  # noqa: BLE001 - any failure -> "no results"
        _LOGGER.warning("Postcode lookup '%s' failed: %s", query, err)
        return []
    return _parse_postcode(payload)


async def async_geocode(
    session: ClientSession,
    query: str,
    *,
    count: int = 5,
    language: str = "en",
) -> list[GeocodeResult]:
    """Resolve a search term to a ranked list of coordinate matches.

    UK postcodes/outcodes go to postcodes.io; everything else to the Open-Meteo
    gazetteer (with postcode-shaped queries falling back to it if postcodes.io
    finds nothing). Returns an empty list on no match or any transport error —
    the caller centres the map on the home location instead.
    """
    query = (query or "").strip()
    if not query:
        return []
    if _UK_POSTCODE.match(query) or _UK_OUTCODE.match(query):
        results = await _async_postcodes_io(session, query)
        if results:
            return results
    return await _async_open_meteo(session, query, count, language)
