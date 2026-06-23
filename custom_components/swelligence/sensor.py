"""Sensor platform: one suitability-score sensor per (spot, sport)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SwelligenceEntity
from .sports import SPORT_PROFILES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up score sensors for every scored (spot, sport)."""
    runtime = entry.runtime_data
    entities: list[SuitabilitySensor] = []
    for coordinator in runtime.coordinators.values():
        for sport in coordinator.data.results:
            entities.append(SuitabilitySensor(coordinator, sport))
    async_add_entities(entities)


class SuitabilitySensor(SwelligenceEntity, SensorEntity):
    """0-100 suitability score for one sport at a spot."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, sport: str) -> None:
        super().__init__(coordinator, f"{sport}_score")
        self._sport = sport
        profile = SPORT_PROFILES.get(sport)
        self._attr_name = f"{profile.label if profile else sport} suitability"
        if profile:
            self._attr_icon = profile.icon

    @property
    def _result(self):
        return self.coordinator.data.results.get(self._sport)

    @property
    def native_value(self) -> float | None:
        res = self._result
        return res.now.score if res else None

    @property
    def extra_state_attributes(self) -> dict:
        res = self._result
        if not res:
            return {}
        attrs = {
            "verdict": res.now.verdict,
            "suitable": res.now.suitable,
            "factors": res.now.factors,
            "reasons": res.now.reasons,
        }
        if res.best is not None:
            attrs["best_score"] = res.best.score
            attrs["best_in_hours"] = res.best_offset_h
            attrs["best_verdict"] = res.best.verdict
        if res.llm_rating is not None:
            attrs["ai_rating"] = res.llm_rating
            attrs["ai_summary"] = res.llm_summary
        return attrs
