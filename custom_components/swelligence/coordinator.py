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
)
from .forecast import daily_forecast, hourly_forecast
from .llm import async_semantic_verdict
from .policy import apply_water_policy, marine_wanted
from .providers import get_provider, get_tide_provider
from .providers.base import SpotForecast, TideEvent
from .scoring import ScoreResult, best_window, blend_kit, score_point
from .sizing import POWER_NA, KitRecommendation, recommend_kit
from .sports import SportProfile
from .tide import DEFAULT_TIDE_WINDOW_H, TIDE_STATE_ANY, tide_factor, to_utc_naive

_LOGGER = logging.getLogger(__name__)

# Tide extremes change slowly; refetch the overlay at most this often.
_TIDE_REFRESH_MINUTES = 720


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

        data = SpotData(forecast=forecast, results=results)
        await self._maybe_enrich_with_llm(data)
        return data

    async def _apply_tide(self, forecast, session, water_type: str) -> None:
        """Stamp each point's tide_factor for a tide-dependent spot.

        Tide-dependence is a per-spot setting (CONF_TIDE_STATE). Inland spots and
        spots set to ``any`` are skipped. Tide events come from the forecast
        provider when it supplies them (Stormglass); otherwise a configured tide
        overlay (UKHO / Stormglass) is fetched and cached.
        """
        if water_type == WATER_TYPE_INLAND:
            return
        state = self.spot.get(CONF_TIDE_STATE, TIDE_STATE_ANY)
        if state in (None, "", TIDE_STATE_ANY):
            return
        window = self.spot.get(CONF_TIDE_WINDOW_H) or DEFAULT_TIDE_WINDOW_H

        events = forecast.tide_events
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

    async def _tide_overlay_events(self, session) -> list:
        """Fetch tide events from the configured overlay, cached by TTL.

        Tide extremes for the week change slowly, so we refetch at most every
        ``_TIDE_REFRESH_MINUTES`` to stay well inside any overlay free-tier quota.
        """
        source = self.entry.options.get(CONF_TIDE_SOURCE)
        if not source or source == "none":
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
