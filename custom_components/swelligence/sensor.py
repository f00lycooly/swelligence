"""Sensor platform: one suitability-score sensor per (spot, sport)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .authority import advice_message, provider_name
from .confidence import aggregate_confidence
from .detail import PANEL_UNRECORDED, panel_headline, spot_panel_payload
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
    entities: list[SensorEntity] = []
    for coordinator in runtime.coordinators.values():
        # One diagnostic 'source advice' sensor per spot (not per sport).
        entities.append(SourceAdviceSensor(coordinator))
        # One panel-detail sensor per spot: the full now/week payload flattened
        # into bindable attributes for the ESPHome conditions panel.
        entities.append(SpotDetailSensor(coordinator))
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
            "water_type": self.coordinator.spot.get("water_type", "sea"),
            "sport": self._sport,
            "sport_label": profile.label if profile else self._sport,
            "verdict": res.now.verdict,
            "suitable": res.now.suitable,
            "factors": res.now.factors,
            "reasons": res.now.reasons,
        }
        if res.now.completeness:
            attrs["completeness"] = res.now.completeness
        if res.now.nudges:
            attrs["nudges"] = res.now.nudges
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


class SourceAdviceSensor(SwelligenceEntity, SensorEntity):
    """Diagnostic: how many domains could use a better-available source (o07.4).

    State is the count of 'better source available' nudges for the spot (0 = on
    the best source it can reach for every domain); the recommendations carry the
    actionable detail. One per spot, in the diagnostic category, so it never adds
    noise to the suitability entities.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:transit-connection-variant"
    _attr_name = "Source advice"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "source_advice")

    @property
    def native_value(self) -> int:
        data = self.coordinator.data
        return len(data.source_advice) if data else 0

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        recs = data.source_advice if data else []
        return {
            "ok": not recs,
            "summary": (
                "On the best available source for every domain"
                if not recs
                else "; ".join(advice_message(r) for r in recs)
            ),
            "recommendations": [
                {
                    **r,
                    "current_name": provider_name(r["current"]),
                    "suggested_name": provider_name(r["suggested"]),
                    "message": advice_message(r),
                }
                for r in recs
            ],
        }


class SpotDetailSensor(SwelligenceEntity, SensorEntity):
    """Per-spot now/week detail, flattened for the ESPHome conditions panel.

    State is the spot's best current sport score; the full payload (tide curve,
    raw conditions, next-24h timeline, 7-day peaks per sport) rides in flat /
    delimited attributes the panel binds and splits in a lambda. The high-churn
    forecast arrays are excluded from the recorder.
    """

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sail-boat"
    _unrecorded_attributes = PANEL_UNRECORDED

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "detail")
        self._attr_name = "Panel detail"

    @property
    def native_value(self) -> int | None:
        return panel_headline(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return spot_panel_payload(self.coordinator, data) if data else {}
