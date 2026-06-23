"""Forecast provider abstraction for swelligence.

A provider turns a (latitude, longitude) into a normalised :class:`SpotForecast`.
The deterministic scorer and the LLM layer consume only this normalised shape,
so adding a provider never touches the scoring or entity code.

Tide overlays (:class:`TideProvider`) are a separate concern: they add high/low
water events to a forecast independently of the wind/wave provider in use.
"""

from __future__ import annotations

from .base import (
    ForecastPoint,
    ForecastProvider,
    SpotForecast,
    TideEvent,
    TideProvider,
)
from .open_meteo import OpenMeteoProvider
from .stormglass import StormglassProvider
from .ukho import UKHOTideProvider
from .windy import WindyProvider

# Registry of available forecast providers, keyed by the value stored in config.
# Open-Meteo is the keyless default that always works; Windy and Stormglass are
# keyed (their API key is stored per-provider under CONF_PROVIDERS).
PROVIDERS: dict[str, type[ForecastProvider]] = {
    OpenMeteoProvider.key: OpenMeteoProvider,
    WindyProvider.key: WindyProvider,
    StormglassProvider.key: StormglassProvider,
}

# Registry of tide overlays. Stormglass doubles as a tide source (it implements
# both ABCs); UKHO is a UK-only overlay.
TIDE_PROVIDERS: dict[str, type[TideProvider]] = {
    UKHOTideProvider.key: UKHOTideProvider,
    StormglassProvider.key: StormglassProvider,
}


def get_provider(key: str) -> type[ForecastProvider] | None:
    """Return the forecast provider class for a registry key."""
    return PROVIDERS.get(key)


def get_tide_provider(key: str) -> type[TideProvider] | None:
    """Return the tide overlay class for a registry key."""
    return TIDE_PROVIDERS.get(key)


def free_tier_min_interval_minutes(
    provider_cls: type[ForecastProvider],
    spots_on_provider: int = 1,
    *,
    safety: float = 0.8,
) -> int | None:
    """Safe minimum poll interval (minutes) to stay within a free-tier budget.

    Uses the provider's ``free_tier_daily_requests`` budget and
    ``requests_per_fetch`` cost, keeps a ``safety`` headroom (default 80% of the
    budget), and divides the remaining fetch allowance across all spots polling
    that provider. Returns ``None`` when the provider has no known free tier.
    """
    budget = provider_cls.free_tier_daily_requests
    cost = max(1, provider_cls.requests_per_fetch)
    if not budget:
        return None
    fetches_per_day = (budget * safety) / cost
    per_spot = fetches_per_day / max(1, spots_on_provider)
    if per_spot <= 0:
        return None
    return max(1, round((24 * 60) / per_spot))


__all__ = [
    "ForecastProvider",
    "ForecastPoint",
    "SpotForecast",
    "TideEvent",
    "TideProvider",
    "OpenMeteoProvider",
    "WindyProvider",
    "StormglassProvider",
    "UKHOTideProvider",
    "PROVIDERS",
    "TIDE_PROVIDERS",
    "get_provider",
    "get_tide_provider",
    "free_tier_min_interval_minutes",
]
