"""The swelligence integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEFAULT_PROVIDER,
    CONF_PROVIDERS,
    CONF_SPORTS,
    CONF_SPOT_PREFS,
    CONF_SPOT_SPORTS,
    CONF_SPOTS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SpotCoordinator
from .sports import SPORT_PROFILES, SportProfile, apply_overrides

_LOGGER = logging.getLogger(__name__)


class SwelligenceRuntime:
    """Holds the per-entry coordinators, keyed by spot id."""

    def __init__(self) -> None:
        self.coordinators: dict[str, SpotCoordinator] = {}


def _enabled_sports(entry: ConfigEntry) -> list[str]:
    """Sports enabled for this entry (falls back to all built-ins)."""
    return (
        entry.options.get(CONF_SPORTS)
        or entry.data.get(CONF_SPORTS)
        or list(SPORT_PROFILES)
    )


def _profiles_for_spot(spot: dict, enabled: list[str]) -> dict[str, SportProfile]:
    """Build the spot's sport profiles: defaults with per-spot overrides applied.

    A spot scores the intersection of its own sports and the entry's enabled
    sports; each profile is the built-in default with the spot's stored
    overrides (offshore wind directions, wind/wave windows) merged on top.
    """
    spot_sports = spot.get(CONF_SPOT_SPORTS) or enabled
    prefs = spot.get(CONF_SPOT_PREFS, {})
    profiles: dict[str, SportProfile] = {}
    for sport in spot_sports:
        if sport not in enabled or sport not in SPORT_PROFILES:
            continue
        profiles[sport] = apply_overrides(SPORT_PROFILES[sport], prefs.get(sport))
    return profiles


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up swelligence from a config entry."""
    runtime = SwelligenceRuntime()
    enabled = _enabled_sports(entry)

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
            profiles=_profiles_for_spot(spot, enabled),
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
