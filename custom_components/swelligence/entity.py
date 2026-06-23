"""Shared entity base for swelligence."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SpotCoordinator


class SwelligenceEntity(CoordinatorEntity[SpotCoordinator]):
    """Base entity bound to a spot coordinator; one HA device per spot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SpotCoordinator, key_suffix: str) -> None:
        super().__init__(coordinator)
        spot = coordinator.spot
        self._attr_unique_id = f"{DOMAIN}_{spot['id']}_{key_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spot["id"])},
            name=f"Swelligence: {spot['name']}",
            manufacturer="Swelligence",
            model="Spot forecast",
            configuration_url="https://git.bagofholding.co.uk/foolycooly/swelligence",
        )
