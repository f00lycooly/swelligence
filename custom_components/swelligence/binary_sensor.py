"""Binary sensor platform: 'suitable now' per (spot, sport)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SwelligenceEntity
from .sports import SPORT_PROFILES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 'suitable now' binary sensors for every scored (spot, sport)."""
    runtime = entry.runtime_data
    entities: list[SuitableBinarySensor] = []
    for coordinator in runtime.coordinators.values():
        for sport in coordinator.data.results:
            entities.append(SuitableBinarySensor(coordinator, sport))
    async_add_entities(entities)


class SuitableBinarySensor(SwelligenceEntity, BinarySensorEntity):
    """On when current conditions clear the suitability threshold."""

    def __init__(self, coordinator, sport: str) -> None:
        super().__init__(coordinator, f"{sport}_suitable")
        self._sport = sport
        profile = SPORT_PROFILES.get(sport)
        self._attr_name = f"{profile.label if profile else sport} suitable now"
        self._attr_icon = profile.icon if profile else "mdi:check-decagram"

    @property
    def is_on(self) -> bool | None:
        res = self.coordinator.data.results.get(self._sport)
        return res.now.suitable if res else None
