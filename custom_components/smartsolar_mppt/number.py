"""Number platform for SmartSolar MPPT."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_UPDATE_INTERVAL,
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


class UpdateIntervalNumber(CoordinatorEntity, RestoreEntity, NumberEntity):
    """Number entity for update interval.

    Inherits :class:`RestoreEntity` so the chosen interval survives a Home
    Assistant restart even before the config entry data is re-read.
    """

    __slots__ = ("_entry",)

    _attr_has_entity_name = True
    _attr_translation_key = "update_frequency"
    _attr_icon = "mdi:timer-cog"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_UPDATE_INTERVAL
    _attr_native_max_value = MAX_UPDATE_INTERVAL
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update_interval"
        self._attr_device_info = build_device_info(
            entry.entry_id,
            entry.data.get("mode"),
            entry.data.get("project_id"),
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last known interval when the entity comes back."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            restored = int(float(last_state.state))
        except (ValueError, TypeError):
            return
        if not MIN_UPDATE_INTERVAL <= restored <= MAX_UPDATE_INTERVAL:
            return
        if self.coordinator.update_interval == timedelta(seconds=restored):
            return

        _LOGGER.debug("Restoring update interval to %s seconds", restored)
        self.coordinator.update_interval = timedelta(seconds=restored)

    @property
    def native_value(self) -> float | None:
        """Return current update interval in seconds."""
        if self.coordinator.update_interval:
            return self.coordinator.update_interval.total_seconds()
        return DEFAULT_UPDATE_INTERVAL.total_seconds()

    async def async_set_native_value(self, value: float) -> None:
        """Set new update interval."""
        new_seconds = int(value)
        if not MIN_UPDATE_INTERVAL <= new_seconds <= MAX_UPDATE_INTERVAL:
            _LOGGER.warning(
                "Rejecting update interval %s (allowed %s-%s seconds)",
                value,
                MIN_UPDATE_INTERVAL,
                MAX_UPDATE_INTERVAL,
            )
            return

        _LOGGER.info(
            "Changing update interval from %s to %s seconds",
            self.coordinator.update_interval,
            new_seconds,
        )

        # Persist so the value survives a restart/reload of this config entry.
        new_data = {**self._entry.data, "update_interval": new_seconds}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)

        self.coordinator.update_interval = timedelta(seconds=new_seconds)
        await self.coordinator.async_refresh()
        self.async_write_ha_state()
        _LOGGER.debug("Update interval changed to %s seconds", new_seconds)
