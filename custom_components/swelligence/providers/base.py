"""Base types for forecast providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .domains import MARINE_DOMAINS, TIDE, stamp_sources

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
    swell_dir_deg: float | None = None
    #: Peak (vs mean) swell period — the better surf-power proxy (long-period
    #: groundswell vs short-period windsea).
    swell_peak_period_s: float | None = None
    #: Local wind-sea, separated from swell. High wind-wave + low swell = messy
    #: onshore slop; clean swell + low wind-wave = quality surf.
    wind_wave_height_m: float | None = None
    wind_wave_period_s: float | None = None
    #: Secondary (crossed) swell — flags confused/dangerous seas.
    secondary_swell_height_m: float | None = None
    secondary_swell_period_s: float | None = None
    secondary_swell_dir_deg: float | None = None
    air_temp_c: float | None = None
    #: "Feels-like" air temperature — informs wetsuit choice given wind chill.
    apparent_temp_c: float | None = None
    water_temp_c: float | None = None
    precip_mm: float | None = None
    cloud_pct: float | None = None
    #: UV index (exposure) and horizontal visibility (m, offshore safety).
    uv_index: float | None = None
    visibility_m: float | None = None
    #: WMO weather code — compact condition for the card/LLM summary.
    weather_code: int | None = None
    #: Ocean surface current — rip/drift safety (speed in knots, "toward" bearing).
    current_speed_kn: float | None = None
    current_dir_deg: float | None = None
    #: Tidal sea level (metres, provider datum) at this timestep, if supplied.
    sea_level_m: float | None = None
    #: Precomputed tide-suitability multiplier (0..1) for the spot's tide
    #: preference at this timestep; ``None`` when the spot isn't tide-dependent
    #: or no tide data is available. Stamped by the coordinator before scoring.
    tide_factor: float | None = None
    #: Per-field model-agreement confidence (0..1), keyed by ForecastPoint field
    #: name (e.g. ``"wave_height_m"``). Populated when a provider retains the
    #: spread across multiple source models for a field (e.g. Open-Meteo's
    #: multi-model ``models=`` request). ``None``/absent = single source, no
    #: agreement signal. Tight agreement -> high; wide divergence -> low.
    source_confidence: dict[str, float] | None = None


@dataclass(slots=True)
class TideEvent:
    """A predicted tidal extreme (high or low water).

    Populated by tide overlays (UKHO, NOAA CO-OPS, Open-Meteo modeled). The
    deterministic scorer's tide awareness (M5) consumes this list; until then it
    is carried through untouched on :class:`SpotForecast`.
    """

    time: datetime
    #: ``"high"`` or ``"low"``.
    kind: str
    height_m: float | None = None


@dataclass(slots=True)
class SpotForecast:
    """Normalised forecast for one spot from one provider."""

    provider: str
    latitude: float
    longitude: float
    points: list[ForecastPoint] = field(default_factory=list)
    # date ISO (YYYY-MM-DD) -> {"sunrise": datetime, "sunset": datetime}
    daily_sun: dict = field(default_factory=dict)
    # Predicted high/low water events (chronological), if a tide source applied.
    tide_events: list[TideEvent] = field(default_factory=list)
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
    #: Free-tier daily request budget, if the provider has a known free quota
    #: (``None`` = no free tier / unmetered). Drives the "Free tier" safe-poll
    #: interval in the options flow.
    free_tier_daily_requests: int | None = None
    #: API requests consumed per :meth:`async_fetch` — used to size the
    #: free-tier poll interval so continuous polling stays under the budget.
    requests_per_fetch: int = 1
    #: Data domains (see :mod:`.domains`) this provider can supply. Drives
    #: per-domain source provenance and the composite-merge routing.
    provides_domains: frozenset[str] = frozenset()
    #: Domains this provider is an *authority* for, mapped to a rank (higher =
    #: more authoritative). Drives the metadata-derived "better source" nudges
    #: and overlay resolution (:func:`..authority.resolve_overlay`). Empty = this
    #: provider is never proposed as a better source and never auto-resolved —
    #: which is why adding a provider is a declaration here, not a table edit.
    authority_rank: dict[str, int] = {}

    def __init__(self, session: ClientSession, api_key: str | None = None) -> None:
        self._session = session
        self._api_key = api_key

    @classmethod
    def covers(cls, latitude: float, longitude: float) -> bool:
        """Whether this provider is authoritative at a coordinate.

        Region-gated providers (e.g. UKHO = UK) override this; the default is
        global. Keeps region applicability *on the provider* so the resolver and
        authority map never hardcode a provider's bounding box.
        """
        return True

    def _stamp_sources(self, forecast: SpotForecast, *, marine: bool) -> None:
        """Record this provider as the source of each domain it supplied.

        Marine domains are dropped when ``marine`` is False (inland / no-marine
        spots); TIDE is only claimed when tide events were actually produced.
        """
        domains = set(self.provides_domains)
        if not marine:
            domains -= MARINE_DOMAINS
        if not forecast.tide_events:
            domains.discard(TIDE)
        stamp_sources(forecast, self.key, domains)

    @abstractmethod
    async def async_fetch(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
        marine: bool = True,
    ) -> SpotForecast:
        """Fetch and normalise the forecast for a coordinate.

        ``days`` is the forecast horizon in days (hourly resolution within).
        When ``marine`` is False the provider must skip any marine (wave/swell/
        sea-temperature) request — used for inland spots where that data is
        meaningless. Wave/swell fields are then left ``None``.
        """


class TideProvider(ABC):
    """Fetches predicted tidal events for a coordinate.

    Tide is an *overlay*: it does not produce a full forecast, only a list of
    high/low water events that augment a :class:`SpotForecast` from any
    :class:`ForecastProvider`. Region authorities (UKHO for the UK, NOAA CO-OPS
    for the US) and the keyless global modeled fallback implement this same shape
    so the coordinator can attach tides independently of the wind/wave provider,
    resolved by region/priority (see :func:`..authority.resolve_overlay`).
    """

    #: Registry key stored in config (e.g. ``"ukho"``).
    key: str = ""
    #: Human label shown in the UI.
    label: str = ""
    #: Whether this tide source needs an API key.
    requires_api_key: bool = False
    #: Domains this source is an authority for, mapped to a rank (higher = more
    #: authoritative). Tide sources declare ``{TIDE: rank}``; the resolver picks
    #: the highest-ranked covering, available source. See :class:`ForecastProvider`.
    authority_rank: dict[str, int] = {}

    def __init__(self, session: ClientSession, api_key: str | None = None) -> None:
        self._session = session
        self._api_key = api_key

    @classmethod
    def covers(cls, latitude: float, longitude: float) -> bool:
        """Whether this tide source is authoritative at a coordinate (default global)."""
        return True

    @abstractmethod
    async def async_fetch_tides(
        self,
        latitude: float,
        longitude: float,
        *,
        days: int = 7,
    ) -> list[TideEvent]:
        """Return predicted high/low water events for a coordinate."""
