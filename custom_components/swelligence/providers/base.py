"""Base types for forecast providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession


@dataclass(slots=True)
class ForecastPoint:
    """A single normalised forecast timestep for a spot.

    All speeds are knots, heights metres, temperatures degrees C, directions
    degrees (meteorological "from" convention). Any field a provider cannot
    supply is left ``None`` and treated as "unknown" by the scorer.
    """

    time: datetime
    wind_speed_kn: float | None = None
    wind_gust_kn: float | None = None
    wind_dir_deg: float | None = None
    wave_height_m: float | None = None
    wave_period_s: float | None = None
    wave_dir_deg: float | None = None
    swell_height_m: float | None = None
    swell_period_s: float | None = None
    air_temp_c: float | None = None
    water_temp_c: float | None = None
    precip_mm: float | None = None
    cloud_pct: float | None = None


@dataclass(slots=True)
class SpotForecast:
    """Normalised forecast for one spot from one provider."""

    provider: str
    latitude: float
    longitude: float
    points: list[ForecastPoint] = field(default_factory=list)
    # Free-form provenance: model name, nearest station id/distance, etc.
    source_meta: dict = field(default_factory=dict)

    def current(self) -> ForecastPoint | None:
        """Return the nearest-to-now forecast point, if any."""
        return self.points[0] if self.points else None


class ForecastProvider(ABC):
    """Fetches and normalises forecast data for a coordinate."""

    #: Registry key stored in config (e.g. ``"open_meteo"``).
    key: str = ""
    #: Human label shown in the UI.
    label: str = ""
    #: Whether this provider needs an API key.
    requires_api_key: bool = False
    #: Whether this provider can supply marine (wave/swell) data.
    supports_marine: bool = True

    def __init__(self, session: ClientSession, api_key: str | None = None) -> None:
        self._session = session
        self._api_key = api_key

    @abstractmethod
    async def async_fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        hours: int = 48,
        marine: bool = True,
    ) -> SpotForecast:
        """Fetch and normalise the forecast for a coordinate.

        When ``marine`` is False the provider must skip any marine (wave/swell/
        sea-temperature) request — used for inland spots where that data is
        meaningless. Wave/swell fields are then left ``None``.
        """
