"""Data update coordinator: one per spot.

Fetches the spot's forecast from the configured provider, scores every enabled
sport deterministically, and (optionally) asks the HA AI Task layer for a
structured semantic verdict layered on top of the numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_USE_LLM,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    CONF_SCAN_INTERVAL_MINUTES,
)
from .llm import async_semantic_verdict
from .providers import get_provider
from .providers.base import SpotForecast
from .scoring import ScoreResult, best_window, score_point
from .sports import SportProfile

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SportResult:
    """Scored outcome for one sport at a spot."""

    sport: str
    now: ScoreResult
    best_offset_h: int | None = None
    best: ScoreResult | None = None
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
    ) -> None:
        interval = entry.options.get(
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

    async def _async_update_data(self) -> SpotData:
        provider_cls = get_provider(self._provider_key)
        if provider_cls is None:
            raise UpdateFailed(f"Unknown provider: {self._provider_key}")

        session = async_get_clientsession(self.hass)
        provider = provider_cls(session, self._api_key)
        try:
            forecast = await provider.async_fetch(
                self.spot["latitude"], self.spot["longitude"]
            )
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Forecast fetch failed: {err}") from err

        current = forecast.current()
        results: dict[str, SportResult] = {}
        for sport in self.spot.get("sports", list(self._profiles)):
            profile = self._profiles.get(sport)
            if profile is None or current is None:
                continue
            now_res = score_point(current, profile)
            bw = best_window(forecast.points, profile)
            results[sport] = SportResult(
                sport=sport,
                now=now_res,
                best_offset_h=bw[0] if bw else None,
                best=bw[1] if bw else None,
            )

        data = SpotData(forecast=forecast, results=results)
        await self._maybe_enrich_with_llm(data)
        return data

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
