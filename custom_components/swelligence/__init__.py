"""The swelligence integration."""

from __future__ import annotations

import logging
from collections import Counter

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_API_KEY,
    CONF_DEFAULT_PROVIDER,
    CONF_FREE_TIER,
    CONF_PROVIDERS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SPORTS,
    CONF_SPOT_PREFS,
    CONF_SPOT_SPORTS,
    CONF_SPOTS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    PLATFORMS,
)
from .authority import advice_message
from .confidence import aggregate_confidence
from .coordinator import SpotCoordinator
from .overview import build_podium, build_sessions
from .providers import free_tier_min_interval_minutes, get_provider
from .sports import SPORT_PROFILES, SportProfile, apply_overrides

_LOGGER = logging.getLogger(__name__)


SERVICE_GET_OVERVIEW = "get_overview"
SERVICE_GET_FORECAST = "get_forecast"
_GET_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Optional("type", default="daily"): vol.In(["hourly", "daily"]),
    }
)


class SwelligenceRuntime:
    """Holds the per-entry coordinators, keyed by spot id."""

    def __init__(self) -> None:
        self.coordinators: dict[str, SpotCoordinator] = {}
        # suitability sensor entity_id -> (coordinator, sport)
        self.forecast_targets: dict[str, tuple[SpotCoordinator, str]] = {}


def _enabled_sports(entry: ConfigEntry) -> list[str]:
    """Sports enabled for this entry (falls back to all built-ins)."""
    return (
        entry.options.get(CONF_SPORTS)
        or entry.data.get(CONF_SPORTS)
        or list(SPORT_PROFILES)
    )


def _provider_interval(
    provider_key: str,
    provider_cfg: dict,
    base_interval: int,
    spots_on_provider: int,
) -> int:
    """Effective poll interval (minutes) for a spot's provider.

    When the provider's "Free tier" toggle is on, never poll faster than the
    safe interval derived from its free daily request budget (shared across the
    spots using it). Otherwise use the user's configured interval.
    """
    if not provider_cfg.get(CONF_FREE_TIER):
        return base_interval
    cls = get_provider(provider_key)
    if cls is None:
        return base_interval
    safe = free_tier_min_interval_minutes(cls, spots_on_provider)
    return max(base_interval, safe) if safe else base_interval


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
    # How many spots poll each provider — needed to share a free-tier budget.
    spots_per_provider = Counter(
        spot.get("provider", default_provider) for spot in spots
    )
    base_interval = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
    )
    for spot in spots:
        provider_key = spot.get("provider", default_provider)
        provider_cfg = providers_cfg.get(provider_key, {}) or {}
        api_key = provider_cfg.get(CONF_API_KEY)
        interval = _provider_interval(
            provider_key, provider_cfg, base_interval, spots_per_provider[provider_key]
        )
        coordinator = SpotCoordinator(
            hass,
            entry,
            spot=spot,
            provider_key=provider_key,
            api_key=api_key,
            profiles=_profiles_for_spot(spot, enabled),
            scan_interval_minutes=interval,
        )
        await coordinator.async_config_entry_first_refresh()
        runtime.coordinators[spot["id"]] = coordinator

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_forecast_service(hass)
    _async_register_overview_service(hass)
    return True


def _async_register_overview_service(hass: HomeAssistant) -> None:
    """Register swelligence.get_overview — ranked now/sessions/podium for cards."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_OVERVIEW):
        return

    async def _handle_get_overview(call: ServiceCall) -> dict:
        spots_f = set(call.data.get("spots") or [])
        sports_f = set(call.data.get("sports") or [])
        # Sport priority now comes from the calling card (the options-flow step
        # was removed). Fall back to the entry's enabled-sports order so the
        # podium still ranks sensibly when a card passes no priority.
        priority = call.data.get("priority") or None
        entries: list[dict] = []
        now: list[dict] = []
        source_advice: list[dict] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if not runtime:
                continue
            if priority is None:
                priority = entry.options.get(CONF_SPORTS)
            for coordinator in runtime.coordinators.values():
                data = coordinator.data
                if not data:
                    continue
                if spots_f and coordinator.spot["name"] not in spots_f:
                    continue
                if data.source_advice:
                    source_advice.append({
                        "spot": coordinator.spot["name"],
                        "recommendations": [
                            {**r, "message": advice_message(r)}
                            for r in data.source_advice
                        ],
                    })
                for sport, res in data.results.items():
                    if sports_f and sport not in sports_f:
                        continue
                    entries.append({
                        "spot": coordinator.spot["name"],
                        "sport": sport,
                        "slots": coordinator.build_forecast(sport, "hourly"),
                    })
                    kit = res.kit
                    profile = coordinator.profile(sport)
                    current = data.forecast.current()
                    conf = (
                        aggregate_confidence(current, profile)
                        if current and profile
                        else None
                    )
                    now.append({
                        "spot": coordinator.spot["name"],
                        "sport": sport,
                        "score": round(res.now.score),
                        "verdict": res.now.verdict,
                        "suitable": res.now.suitable,
                        "best_in_hours": res.best_offset_h,
                        "best_score": round(res.best.score) if res.best else None,
                        "kit_rig_m2": kit.owned_size_m2 if kit else None,
                        "kit_power": kit.power if kit else None,
                        "confidence": conf["value"] if conf else None,
                        "confidence_label": conf["label"] if conf else None,
                    })
        return {
            "sport_priority": priority or [],
            "now": now,
            "sessions": build_sessions(entries),
            "podium": build_podium(entries, priority),
            "source_advice": source_advice,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_OVERVIEW,
        _handle_get_overview,
        schema=vol.Schema(
            {
                vol.Optional("spots"): [cv.string],
                vol.Optional("sports"): [cv.string],
                vol.Optional("priority"): [cv.string],
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


def _async_register_forecast_service(hass: HomeAssistant) -> None:
    """Register swelligence.get_forecast once (mirrors weather.get_forecasts)."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_FORECAST):
        return

    async def _handle_get_forecast(call: ServiceCall) -> dict:
        kind = call.data["type"]
        result: dict[str, dict] = {}
        for entity_id in call.data["entity_id"]:
            for entry in hass.config_entries.async_entries(DOMAIN):
                runtime = getattr(entry, "runtime_data", None)
                target = runtime and runtime.forecast_targets.get(entity_id)
                if target:
                    coordinator, sport = target
                    result[entity_id] = {
                        "spot": coordinator.spot["name"],
                        "sport": sport,
                        "forecast": coordinator.build_forecast(sport, kind),
                    }
                    break
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FORECAST,
        _handle_get_forecast,
        schema=_GET_FORECAST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


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
