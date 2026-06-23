"""Sensor platform: one suitability-score sensor per (spot, sport)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .confidence import aggregate_confidence
from .entity import SwelligenceEntity
from .quality import data_quality
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

    async def async_added_to_hass(self) -> None:
        """Register this entity as a get_forecast target."""
        await super().async_added_to_hass()
        self.coordinator.entry.runtime_data.forecast_targets[self.entity_id] = (
            self.coordinator,
            self._sport,
        )

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.entry.runtime_data.forecast_targets.pop(self.entity_id, None)
        await super().async_will_remove_from_hass()

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
        profile = SPORT_PROFILES.get(self._sport)
        attrs = {
            "spot": self.coordinator.spot["name"],
            "sport": self._sport,
            "sport_label": profile.label if profile else self._sport,
            "verdict": res.now.verdict,
            "suitable": res.now.suitable,
            "factors": res.now.factors,
            "reasons": res.now.reasons,
        }
        if res.best is not None:
            attrs["best_score"] = res.best.score
            attrs["best_in_hours"] = res.best_offset_h
            attrs["best_verdict"] = res.best.verdict
        if res.kit is not None:
            attrs["recommended_size_m2"] = res.kit.ideal_size_m2
            attrs["rig_size_m2"] = res.kit.owned_size_m2
            attrs["power"] = res.kit.power
            attrs["kit_summary"] = res.kit.summary
        if res.llm_rating is not None:
            attrs["ai_rating"] = res.llm_rating
            attrs["ai_summary"] = res.llm_summary
        forecast = self.coordinator.data.forecast
        sources = forecast.source_meta.get("sources")
        if sources:
            attrs["data_sources"] = sources
        profile = self.coordinator.profile(self._sport)
        if profile is not None:
            attrs["data_quality"] = data_quality(forecast, profile)
            current = forecast.current()
            conf = aggregate_confidence(current, profile) if current else None
            if conf is not None:
                attrs["confidence"] = conf["value"]
                attrs["confidence_label"] = conf["label"]
        return attrs
