"""The swelligence integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEFAULT_PROVIDER,
    CONF_PROVIDERS,
    CONF_SPORTS,
    CONF_SPOTS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SpotCoordinator
from .sports import SPORT_PROFILES, SportProfile

_LOGGER = logging.getLogger(__name__)


class SwelligenceRuntime:
    """Holds the per-entry coordinators, keyed by spot id."""

    def __init__(self) -> None:
        self.coordinators: dict[str, SpotCoordinator] = {}


def _resolve_profiles(entry: ConfigEntry) -> dict[str, SportProfile]:
    """Return profiles for the entry's enabled sports (defaults for now).

    Per-spot/per-sport preference overrides land here in a later milestone; the
    structure is ready for them via dataclasses.replace on the defaults.
    """
    enabled = entry.options.get(CONF_SPORTS) or entry.data.get(CONF_SPORTS) or list(
        SPORT_PROFILES
    )
    return {k: SPORT_PROFILES[k] for k in enabled if k in SPORT_PROFILES}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up swelligence from a config entry."""
    runtime = SwelligenceRuntime()
    profiles = _resolve_profiles(entry)

    providers_cfg = entry.options.get(CONF_PROVIDERS) or entry.data.get(
        CONF_PROVIDERS, {}
    )
    default_provider = entry.options.get(
        CONF_DEFAULT_PROVIDER
    ) or entry.data.get(CONF_DEFAULT_PROVIDER, "open_meteo")

    spots = entry.options.get(CONF_SPOTS) or entry.data.get(CONF_SPOTS, [])
    for spot in spots:
        provider_key = spot.get("provider", default_provider)
        api_key = providers_cfg.get(provider_key, {}).get("api_key")
        coordinator = SpotCoordinator(
            hass,
            entry,
            spot=spot,
            provider_key=provider_key,
            api_key=api_key,
            profiles=profiles,
        )
        await coordinator.async_config_entry_first_refresh()
        runtime.coordinators[spot["id"]] = coordinator

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when options change (spots/sports/providers)."""
    await hass.config_entries.async_reload(entry.entry_id)
