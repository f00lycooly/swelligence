"""Forecast provider abstraction for swelligence.

A provider turns a (latitude, longitude) into a normalised :class:`SpotForecast`.
The deterministic scorer and the LLM layer consume only this normalised shape,
so adding a provider never touches the scoring or entity code.
"""

from __future__ import annotations

from .base import ForecastProvider, ForecastPoint, SpotForecast
from .open_meteo import OpenMeteoProvider

# Registry of available providers, keyed by the value stored in config.
# Keyed providers (Windy, Stormglass) register here once implemented; until then
# Open-Meteo is the keyless default that always works.
PROVIDERS: dict[str, type[ForecastProvider]] = {
    OpenMeteoProvider.key: OpenMeteoProvider,
}


def get_provider(key: str) -> type[ForecastProvider] | None:
    """Return the provider class for a registry key."""
    return PROVIDERS.get(key)


__all__ = [
    "ForecastProvider",
    "ForecastPoint",
    "SpotForecast",
    "OpenMeteoProvider",
    "PROVIDERS",
    "get_provider",
]
