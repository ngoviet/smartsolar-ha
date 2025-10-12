"""Number platform for SmartSolar MPPT."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .coordinator import SmartSolarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SmartSolar MPPT number entities."""
    coordinator: SmartSolarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Add update interval number entity
    async_add_entities([UpdateIntervalNumber(coordinator, entry)])


class UpdateIntervalNumber(CoordinatorEntity, NumberEntity):
    """Number entity for update interval."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-cog"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_UPDATE_INTERVAL
    _attr_native_max_value = MAX_UPDATE_INTERVAL
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "giây"

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update_interval"
        self._attr_name = "Tần suất cập nhật"

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"SmartSolar MPPT {self._entry.data.get('mode', 'Device').title()}",
            "manufacturer": "SmartSolar",
            "model": "MPPT Controller",
            "sw_version": "1.0.0",
            "hw_version": "MPPT",
            "configuration_url": "https://smartsolar.io.vn/",
        }

    @property
    def native_value(self) -> float:
        """Return current update interval in seconds."""
        if self.coordinator.update_interval:
            return self.coordinator.update_interval.total_seconds()
        return 5

    async def async_set_native_value(self, value: float) -> None:
        """Set new update interval."""
        from datetime import timedelta
        from homeassistant.helpers import config_validation as cv

        new_interval = timedelta(seconds=int(value))
        _LOGGER.info("Changing update interval from %s to %s seconds", 
                     self.coordinator.update_interval, value)
        
        # Update coordinator's update interval
        self.coordinator.update_interval = new_interval
        
        # Save to config entry
        new_data = self._entry.data.copy()
        new_data["update_interval"] = int(value)
        
        # Update the config entry
        self.hass.config_entries.async_update_entry(
            self._entry, data=new_data
        )
        
        # Trigger immediate refresh with new interval
        await self.coordinator.async_request_refresh()
        
        # Update the UI
        self.async_write_ha_state()

