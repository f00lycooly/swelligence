"""Data update coordinator: one per spot.

Fetches the spot's forecast from the configured provider, scores every enabled
sport deterministically, and (optionally) asks the HA AI Task layer for a
structured semantic verdict layered on top of the numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_API_KEY,
    CONF_FREE_TIER,
    CONF_MARINE_BLEND,
    CONF_MARINE_ENSEMBLE,
    CONF_MARINE_PREFER,
    CONF_MARINE_SOURCE,
    CONF_PROVIDERS,
    CONF_QUIVER,
    CONF_RIDER,
    CONF_RIDER_WEIGHT,
    CONF_TIDE_SOURCE,
    CONF_TIDE_STATE,
    CONF_TIDE_WINDOW_H,
    CONF_USE_LLM,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    CONF_SCAN_INTERVAL_MINUTES,
    WATER_TYPE_INLAND,
    WATER_TYPE_SEA,
)
from .forecast import daily_forecast, hourly_forecast
from .llm import async_semantic_verdict
from .authority import recommend_sources, resolve_overlay
from .overlay import ensemble_marine, filled_domains, merge_marine, resolve_route
from .policy import apply_water_policy, marine_wanted
from .providers import (
    TIDE_PROVIDERS,
    free_tier_min_interval_minutes,
    get_provider,
    get_tide_provider,
)
from .providers.base import SpotForecast, TideEvent
from .providers.domains import TIDE, stamp_sources
from .scoring import ScoreResult, best_window, blend_kit, score_point
from .sizing import POWER_NA, KitRecommendation, recommend_kit
from .sports import SportProfile
from .tide import DEFAULT_TIDE_WINDOW_H, TIDE_STATE_ANY, tide_factor, to_utc_naive

_LOGGER = logging.getLogger(__name__)

# Tide extremes change slowly; refetch the overlay at most this often.
_TIDE_REFRESH_MINUTES = 720
# Marine overlay refresh floor (raised to the free-tier interval when applicable).
_MARINE_REFRESH_MINUTES = 180


@dataclass(slots=True)
class SportResult:
    """Scored outcome for one sport at a spot."""

    sport: str
    now: ScoreResult
    best_offset_h: int | None = None
    best: ScoreResult | None = None
    kit: KitRecommendation | None = None
    llm_summary: str | None = None
    llm_rating: int | None = None


@dataclass(slots=True)
class SpotData:
    """Everything the entities for one spot need."""

    forecast: SpotForecast
    results: dict[str, SportResult] = field(default_factory=dict)
    # 'Better source available' nudges for this spot (o07.4); empty = on the
    # best source it can reach for every routed domain.
    source_advice: list[dict] = field(default_factory=list)


class SpotCoordinator(DataUpdateCoordinator[SpotData]):
    """Coordinator for a single spot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        spot: dict,
        provider_key: str,
        api_key: str | None,
        profiles: dict[str, SportProfile],
        scan_interval_minutes: int | None = None,
    ) -> None:
        interval = scan_interval_minutes or entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"swelligence:{spot['name']}",
            update_interval=timedelta(minutes=interval),
        )
        self.entry = entry
        self.spot = spot
        self._provider_key = provider_key
        self._api_key = api_key
        self._profiles = profiles
        # (fetched_at, events) cache for the tide overlay.
        self._tide_cache: tuple[datetime | None, list] = (None, [])
        # provider_key -> (fetched_at, SpotForecast) cache for overlay fetches.
        self._overlay_cache: dict[str, tuple[datetime, SpotForecast]] = {}

    async def _async_update_data(self) -> SpotData:
        provider_cls = get_provider(self._provider_key)
        if provider_cls is None:
            raise UpdateFailed(f"Unknown provider: {self._provider_key}")

        session = async_get_clientsession(self.hass)
        provider = provider_cls(session, self._api_key)
        water_type = self.spot.get("water_type", "sea")
        try:
            forecast = await provider.async_fetch(
                self.spot["latitude"],
                self.spot["longitude"],
                days=7,
                marine=marine_wanted(water_type),
            )
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Forecast fetch failed: {err}") from err

        # Suppress nearest-coastal marine data that doesn't apply to this spot.
        apply_water_policy(forecast, water_type)

        # Layer a keyed marine source onto the base where it lacks waves/swell
        # (gap-fill) or always (prefer). No-op unless a marine source is set.
        await self._apply_marine_overlay(forecast, session, water_type)

        # Tide awareness: attach a tide overlay if needed, then stamp a per-point
        # tide factor the scorer folds in (no-op for non-tide-dependent spots).
        await self._apply_tide(forecast, session, water_type)

        current = forecast.current()
        rider = self.entry.options.get(CONF_RIDER, {})
        weight = rider.get(CONF_RIDER_WEIGHT) or 0
        quiver = rider.get(CONF_QUIVER, {})

        results: dict[str, SportResult] = {}
        for sport in self.spot.get("sports", list(self._profiles)):
            profile = self._profiles.get(sport)
            if profile is None or current is None:
                continue
            now_res = score_point(current, profile)
            bw = best_window(forecast.points, profile)

            # Quiver-aware personalisation (kite/wing only; no-op if no rider).
            kit = None
            if weight:
                rec = recommend_kit(
                    sport, weight, current.wind_speed_kn, quiver.get(sport)
                )
                if rec.power != POWER_NA:
                    kit = rec
                    now_res = blend_kit(now_res, rec.factor)

            results[sport] = SportResult(
                sport=sport,
                now=now_res,
                best_offset_h=bw[0] if bw else None,
                best=bw[1] if bw else None,
                kit=kit,
            )

        data = SpotData(
            forecast=forecast,
            results=results,
            source_advice=self._source_advice(forecast, water_type),
        )
        await self._maybe_enrich_with_llm(data)
        return data

    def _source_advice(self, forecast, water_type: str) -> list[dict]:
        """'Better source available' nudges for this spot's actual routing.

        Compares the per-domain provenance (source_meta['sources']) against the
        authority map, considering only providers the user has configured (the
        keyless Open-Meteo always counts).
        """
        providers_cfg = self.entry.options.get(CONF_PROVIDERS, {}) or {}
        available = {"open_meteo"}  # the keyless default always works
        available |= {
            key
            for key, cfg in providers_cfg.items()
            if (cfg or {}).get(CONF_API_KEY)
        }
        return recommend_sources(
            sources=forecast.source_meta.get("sources"),
            water_type=water_type,
            latitude=self.spot["latitude"],
            longitude=self.spot["longitude"],
            available=available,
        )

    async def _apply_marine_overlay(self, forecast, session, water_type: str) -> None:
        """Layer a keyed marine source onto the base forecast.

        Only for open-coast (sea) spots — sheltered/inland deliberately have no
        open-sea swell. Gap-fill writes only missing wave/swell/sea-temp; prefer
        replaces them. Filled domains are re-stamped to the overlay in
        source_meta['sources'] (per-domain provenance from al8.1).

        When ensemble is enabled (o07.3) the overlay is fetched even if the base
        already has waves, so the two independent sources can be compared for
        cross-provider confidence (and an optional consensus blend).
        """
        if water_type != WATER_TYPE_SEA:
            return
        source = resolve_route(
            self.spot.get(CONF_MARINE_SOURCE),
            self.entry.options.get(CONF_MARINE_SOURCE),
        )
        if not source or source == "none" or source == self._provider_key:
            return
        prefer = bool(
            resolve_route(
                self.spot.get(CONF_MARINE_PREFER),
                self.entry.options.get(CONF_MARINE_PREFER),
            )
        )
        ensemble = bool(
            resolve_route(
                self.spot.get(CONF_MARINE_ENSEMBLE),
                self.entry.options.get(CONF_MARINE_ENSEMBLE),
            )
        )
        blend = ensemble and bool(
            resolve_route(
                self.spot.get(CONF_MARINE_BLEND),
                self.entry.options.get(CONF_MARINE_BLEND),
            )
        )
        base_has_marine = any(p.wave_height_m is not None for p in forecast.points)
        # Gap-fill has nothing to add when the base already has waves — but an
        # ensemble still needs the overlay to measure agreement against it.
        if base_has_marine and not prefer and not ensemble:
            return

        overlay = await self._overlay_forecast(source, session)
        if not overlay or not overlay.points:
            return
        offset = int(forecast.source_meta.get("utc_offset_seconds", 0) or 0)

        # Cross-provider confidence first, from the original base vs overlay pair
        # (before any merge/blend mutates the base values).
        if ensemble:
            scored = ensemble_marine(
                forecast.points,
                overlay.points,
                blend=blend,
                base_offset_seconds=offset,
            )
            if scored:
                mode = "blend" if blend else "confidence"
                forecast.source_meta["marine_ensemble"] = f"{source} ({mode})"

        filled = merge_marine(
            forecast.points, overlay.points, prefer=prefer, base_offset_seconds=offset
        )
        if filled:
            stamp_sources(forecast, source, filled_domains(filled))
            forecast.source_meta["marine_overlay"] = (
                f"{source} ({'prefer' if prefer else 'gap-fill'})"
            )

    async def _overlay_forecast(self, key: str, session):
        """A keyed provider's full forecast, TTL-cached for budget safety.

        Reused for marine gap-fill and (when the provider supplies them) tides,
        so one fetch serves both. Refetched no more often than the provider's
        free-tier interval (or the marine floor).
        """
        cls = get_provider(key)
        if cls is None:
            return None
        now = datetime.now(timezone.utc)
        cached = self._overlay_cache.get(key)
        if cached and now - cached[0] < timedelta(minutes=self._overlay_ttl(key, cls)):
            return cached[1]
        providers_cfg = self.entry.options.get(CONF_PROVIDERS, {}) or {}
        api_key = (providers_cfg.get(key, {}) or {}).get("api_key")
        try:
            provider = cls(session, api_key)
            forecast = await provider.async_fetch(
                self.spot["latitude"], self.spot["longitude"], days=7, marine=True
            )
        except Exception as err:  # noqa: BLE001 - overlay is best-effort
            _LOGGER.warning(
                "Marine overlay (%s) failed for %s: %s", key, self.spot["name"], err
            )
            return cached[1] if cached else None
        self._overlay_cache[key] = (now, forecast)
        return forecast

    def _overlay_ttl(self, key: str, cls) -> int:
        providers_cfg = self.entry.options.get(CONF_PROVIDERS, {}) or {}
        on_free_tier = (providers_cfg.get(key, {}) or {}).get(CONF_FREE_TIER)
        if cls.free_tier_daily_requests and on_free_tier:
            safe = free_tier_min_interval_minutes(cls, 1) or 0
            return max(_MARINE_REFRESH_MINUTES, safe)
        return _MARINE_REFRESH_MINUTES

    async def _apply_tide(self, forecast, session, water_type: str) -> None:
        """Stamp each point's tide_factor for a tide-dependent spot.

        Tide-dependence is a per-spot setting (CONF_TIDE_STATE). Inland spots and
        spots set to ``any`` are skipped. Tide events come from the region-resolved
        tide overlay (UKHO / NOAA CO-OPS / Open-Meteo modeled fallback), fetched
        and cached.
        """
        if water_type == WATER_TYPE_INLAND:
            return
        state = self.spot.get(CONF_TIDE_STATE, TIDE_STATE_ANY)
        if state in (None, "", TIDE_STATE_ANY):
            return
        window = self.spot.get(CONF_TIDE_WINDOW_H) or DEFAULT_TIDE_WINDOW_H

        events = forecast.tide_events
        if not events:
            # Reuse a marine-overlay forecast's tides if one carries them (e.g.
            # Stormglass already fetched for gap-fill) before a dedicated call.
            events = self._cached_overlay_tides()
        if not events:
            events = await self._tide_overlay_events(session)
        if not events:
            return

        # Collapse points (naive local) and events (UTC) to one UTC basis.
        offset = int(forecast.source_meta.get("utc_offset_seconds", 0) or 0)
        norm_events = [
            TideEvent(time=to_utc_naive(e.time), kind=e.kind, height_m=e.height_m)
            for e in events
        ]
        forecast.tide_events = norm_events
        forecast.source_meta["tide"] = f"state={state} window={window}h"
        for point in forecast.points:
            when = to_utc_naive(point.time, local_offset_seconds=offset)
            factor, _ = tide_factor(norm_events, when, state, window)
            point.tide_factor = factor

    def _cached_overlay_tides(self) -> list:
        """Tides from any cached overlay forecast that supplied them."""
        for _, forecast in self._overlay_cache.values():
            if forecast.tide_events:
                return forecast.tide_events
        return []

    def _resolve_tide_source(self) -> str | None:
        """The tide source for this spot: explicit override, else auto-resolved.

        An explicit per-spot/entry ``CONF_TIDE_SOURCE`` wins (``"none"`` disables
        tides). When unset, the region/priority resolver picks the best available
        source for the coordinate — UKHO in the UK, etc. — with no manual choice.
        Availability = keyless sources always, keyed ones only when configured.
        """
        source = resolve_route(
            self.spot.get(CONF_TIDE_SOURCE), self.entry.options.get(CONF_TIDE_SOURCE)
        )
        if source == "none":
            return None
        if source:
            return source
        providers_cfg = self.entry.options.get(CONF_PROVIDERS, {}) or {}
        available = {
            key
            for key, cls in TIDE_PROVIDERS.items()
            if not cls.requires_api_key
            or (providers_cfg.get(key, {}) or {}).get(CONF_API_KEY)
        }
        return resolve_overlay(
            TIDE, self.spot["latitude"], self.spot["longitude"], available=available
        )

    async def _tide_overlay_events(self, session) -> list:
        """Fetch tide events from the configured overlay, cached by TTL.

        Tide extremes for the week change slowly, so we refetch at most every
        ``_TIDE_REFRESH_MINUTES`` to stay well inside any overlay free-tier quota.
        """
        source = self._resolve_tide_source()
        if not source:
            return []
        now = datetime.now(timezone.utc)
        cached_at, cached = self._tide_cache
        if cached_at and now - cached_at < timedelta(minutes=_TIDE_REFRESH_MINUTES):
            return cached

        cls = get_tide_provider(source)
        if cls is None:
            return []
        providers_cfg = self.entry.options.get(CONF_PROVIDERS, {}) or {}
        api_key = (providers_cfg.get(source, {}) or {}).get("api_key")
        try:
            provider = cls(session, api_key)
            events = await provider.async_fetch_tides(
                self.spot["latitude"], self.spot["longitude"], days=7
            )
        except Exception as err:  # noqa: BLE001 - tide overlay is best-effort
            _LOGGER.warning("Tide overlay (%s) failed for %s: %s", source, self.spot["name"], err)
            return cached or []
        self._tide_cache = (now, events)
        return events

    def profile(self, sport: str) -> SportProfile | None:
        """The in-use (override-applied) profile for a sport at this spot."""
        return self._profiles.get(sport)

    def build_forecast(self, sport: str, kind: str) -> list[dict]:
        """Build a suitability forecast (kind='hourly'|'daily') for a sport.

        Uses the already-fetched 7-day SpotForecast; no new network call. Applies
        the rider's quiver per timestep when configured.
        """
        if not self.data or sport not in self._profiles:
            return []
        rider = self.entry.options.get(CONF_RIDER, {}) or {}
        weight = rider.get(CONF_RIDER_WEIGHT) or 0
        quiver = (rider.get(CONF_QUIVER, {}) or {}).get(sport)
        builder = hourly_forecast if kind == "hourly" else daily_forecast
        return builder(
            self.data.forecast, self._profiles[sport], sport, weight, quiver
        )

    async def _maybe_enrich_with_llm(self, data: SpotData) -> None:
        if not self.entry.options.get(CONF_USE_LLM):
            return
        ai_entity = self.entry.options.get(CONF_AI_TASK_ENTITY)
        if not ai_entity:
            return
        try:
            await async_semantic_verdict(
                self.hass,
                ai_entity_id=ai_entity,
                spot=self.spot,
                forecast=data.forecast,
                results=data.results,
                profiles=self._profiles,
            )
        except Exception as err:  # noqa: BLE001 - LLM is best-effort
            _LOGGER.warning("AI Task enrichment failed for %s: %s", self.spot["name"], err)
