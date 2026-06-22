"""Number platform for SmartSolar MPPT."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    build_device_info,
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


class UpdateIntervalNumber(CoordinatorEntity, NumberEntity):  # type: ignore[misc]
    """Number entity for update interval."""

    __slots__ = ("_entry", "_attr_unique_id", "_attr_name", "_attr_native_unit_of_measurement")

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-cog"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_UPDATE_INTERVAL
    _attr_native_max_value = MAX_UPDATE_INTERVAL
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update_interval"
        self._attr_name = "Update Frequency"
        self._attr_native_unit_of_measurement = "seconds"

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        await self._update_translations()

    async def _update_translations(self) -> None:
        """Update entity name and unit from translations."""
        try:
            translations = await translation.async_get_translations(
                self.hass, self.hass.config.language, "config", {"smartsolar_mppt"}
            )
            name_key = "entity.number.update_frequency.name"
            if name_key in translations:
                self._attr_name = translations[name_key]
            unit_key = "entity.number.update_frequency.unit"
            if unit_key in translations:
                self._attr_native_unit_of_measurement = translations[unit_key]
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            _LOGGER.warning("Could not load translations: %s", e)

    @property
    def device_info(self) -> dict[str, Any] | None:
        """Return device info."""
        return build_device_info(
            self._entry.entry_id,
            self._entry.data.get("mode"),
            self._entry.data.get("project_id"),
        )

    @property  # type: ignore[override]
    def native_value(self) -> float | None:
        """Return current update interval in seconds."""
        if self.coordinator.update_interval:
            return self.coordinator.update_interval.total_seconds()
        return 5.0

    async def async_set_native_value(self, value: float) -> None:
        """Set new update interval."""
        new_interval = timedelta(seconds=int(value))
        _LOGGER.info("Changing update interval from %s to %s seconds",
                     self.coordinator.update_interval, value)

        new_data = self._entry.data.copy()
        new_data["update_interval"] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)

        self.coordinator.update_interval = new_interval
        await self.coordinator.async_refresh()
        self.async_write_ha_state()
        _LOGGER.info("Update interval changed to %s seconds successfully", value)

