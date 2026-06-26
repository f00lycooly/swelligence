"""The swelligence integration."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .authority import advice_message
from .batch import OpenMeteoBatchLoader
from .confidence import aggregate_confidence
from .coordinator import SpotCoordinator
from .forecast import daylight_remaining
from .overview import build_podium, build_sessions
from .policy import marine_wanted
from .providers import free_tier_min_interval_minutes, get_provider
from .sizing import kit_payload
from .sports import SPORT_PROFILES, SportProfile, apply_overrides
from .tide import tide_phase, tide_state

_LOGGER = logging.getLogger(__name__)


SERVICE_GET_OVERVIEW = "get_overview"
SERVICE_GET_FORECAST = "get_forecast"
SERVICE_GET_SPOT_DETAIL = "get_spot_detail"

# Raw now-conditions surfaced verbatim to the spot-detail card (normalised units).
_NOW_FIELDS = (
    "wind_speed_kn", "wind_gust_kn", "wind_dir_deg", "wave_height_m", "wave_period_s",
    "wave_dir_deg", "swell_height_m", "swell_period_s", "swell_peak_period_s",
    "swell_dir_deg", "wind_wave_height_m", "current_speed_kn", "current_dir_deg",
    "sea_level_m", "water_temp_c", "air_temp_c", "apparent_temp_c", "uv_index",
    "visibility_m", "weather_code",
)
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
    # Shared batched loader for all Open-Meteo spots: one forecast + one marine
    # call per cycle serve every spot, instead of two calls each. TTL ties to the
    # base interval so a cycle of coordinators triggers a single batch fetch.
    om_spots = [s for s in spots if s.get("provider", default_provider) == "open_meteo"]
    batch_loader = None
    if om_spots:
        batch_loader = OpenMeteoBatchLoader(
            async_get_clientsession(hass),
            {
                s["id"]: (s["latitude"], s["longitude"], marine_wanted(
                    s.get("water_type", "sea")
                ))
                for s in om_spots
            },
            ttl_minutes=base_interval,
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
            batch_loader=batch_loader if provider_key == "open_meteo" else None,
        )
        await coordinator.async_config_entry_first_refresh()
        runtime.coordinators[spot["id"]] = coordinator

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_forecast_service(hass)
    _async_register_overview_service(hass)
    _async_register_spot_detail_service(hass)
    await _async_register_card(hass)
    return True


# Frontend URL the bundled Lovelace card is served from (static path).
_CARD_URL = "/swelligence_frontend/swelligence-card.js"
_CARD_REGISTERED = f"{DOMAIN}_card_registered"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve + auto-load the bundled Lovelace card so it travels with the
    integration (one HACS install, no manual resource). The ``?v=<version>``
    query busts the browser cache on every release. Registered once per HA run;
    not cleared on unload so reloads don't re-register the static path.

    Best-effort: frontend/http are after_dependencies (always set up in a real
    HA, but not force-set-up — so this stays out of hassfest's hard-dep gate and
    never makes integration setup fail if the frontend isn't available)."""
    if hass.data.get(_CARD_REGISTERED):
        return
    try:
        card_path = Path(__file__).parent / "frontend" / "swelligence-card.js"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL, str(card_path), False)]
        )
        integration = await async_get_integration(hass, DOMAIN)
        add_extra_js_url(hass, f"{_CARD_URL}?v={integration.version}")
        hass.data[_CARD_REGISTERED] = True
    except Exception as err:  # noqa: BLE001 - card is a convenience, never fatal
        _LOGGER.warning("Could not register the bundled Swelligence card: %s", err)


def _spot_detail(coordinator, data, sports_f: set) -> dict:
    """One spot's full now/week detail for the spot-detail card — every
    time-varying value ready to render (the screen derives nothing). Live
    forecast is now-anchored (points[0] == now), so hourly[0]/daily[0]/tide
    all align without slicing."""
    forecast = data.forecast
    now_pt = forecast.current()
    sports: list[dict] = []
    for sport, res in data.results.items():
        if sports_f and sport not in sports_f:
            continue
        profile = coordinator.profile(sport)
        # Continuous next-24h hourly (keep every hour; large pad disables the
        # daylight filter) + the daytime-only daily peak (strict sunrise..sunset).
        hourly = coordinator.build_forecast(sport, "hourly", pad_h=999, horizon=24)
        daily = coordinator.build_forecast(sport, "daily", pad_h=0)
        for entry in daily:
            entry["tide"] = tide_phase(forecast, datetime.fromisoformat(entry["datetime"]))
        best = None
        if res.best is not None:
            offset = res.best_offset_h
            best = {
                "score": round(res.best.score),
                "in_hours": offset,
                "verdict": res.best.verdict,
                "time": hourly[offset]["datetime"][11:16]
                if offset is not None and offset < len(hourly) else None,
            }
        sports.append({
            "sport": sport,
            "label": profile.label if profile else sport,
            "now": {
                "score": round(res.now.score), "verdict": res.now.verdict,
                "suitable": res.now.suitable, "factors": res.now.factors,
                "reasons": res.now.reasons, "completeness": res.now.completeness,
                "nudges": res.now.nudges,
                "kit": kit_payload(res.kit),
            },
            "best": best,
            "hourly": hourly,
            "daily": daily,
        })
    return {
        "name": coordinator.spot["name"],
        "water_type": coordinator.spot.get("water_type", "sea"),
        "latitude": coordinator.spot["latitude"],
        "longitude": coordinator.spot["longitude"],
        "now_time": now_pt.time.strftime("%H:%M") if now_pt else None,
        "daylight": daylight_remaining(forecast),
        "tide": tide_state(forecast),
        "current": {f: getattr(now_pt, f, None) for f in _NOW_FIELDS} if now_pt else {},
        "sports": sports,
    }


def _async_register_spot_detail_service(hass: HomeAssistant) -> None:
    """Register swelligence.get_spot_detail — per-spot now/week detail for the
    spot-detail card (tide, hourly series, daytime daily outlook, conditions)."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_SPOT_DETAIL):
        return

    async def _handle_get_spot_detail(call: ServiceCall) -> dict:
        spots_f = set(call.data.get("spots") or [])
        sports_f = set(call.data.get("sports") or [])
        spots: list[dict] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if not runtime:
                continue
            for coordinator in runtime.coordinators.values():
                data = coordinator.data
                if not data:
                    continue
                if spots_f and coordinator.spot["name"] not in spots_f:
                    continue
                spots.append(_spot_detail(coordinator, data, sports_f))
        return {"spots": spots}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SPOT_DETAIL,
        _handle_get_spot_detail,
        schema=vol.Schema(
            {
                vol.Optional("spots"): [cv.string],
                vol.Optional("sports"): [cv.string],
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


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
                        "water_type": coordinator.spot.get("water_type", "sea"),
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
