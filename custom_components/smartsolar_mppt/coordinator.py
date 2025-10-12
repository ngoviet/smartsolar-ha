"""Data update coordinator for SmartSolar MPPT."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartSolarAPI, SmartSolarAPIError
from .const import DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SmartSolarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the SmartSolar API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SmartSolarAPI,
        entry: ConfigEntry,
        update_interval=None,
    ) -> None:
        """Initialize the coordinator."""
        if update_interval is None:
            update_interval = DEFAULT_UPDATE_INTERVAL
            
        super().__init__(
            hass,
            _LOGGER,
            name="SmartSolar MPPT",
            update_interval=update_interval,
        )
        self.api = api
        self.entry = entry
        self.discovered_devices: set[str] = set()
        self._device_discovery_callbacks: list[callable] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Get configuration from entry
            device_type = self.entry.data["device_type"]
            chipset_ids = self.entry.data.get("chipset_ids")
            mode = self.entry.data["mode"]
            project_id = self.entry.data.get("project_id")

            _LOGGER.debug("Fetching metrics - device_type: %s, chipset_ids: %s, mode: %s, project_id: %s", 
                         device_type, chipset_ids, mode, project_id)

            # Fetch metrics from API
            if project_id:
                # Use project ID for project mode
                data = await self.api.get_project_metrics(project_id)
            else:
                # Use existing logic for device mode or device IDs project mode
                if not chipset_ids:
                    # Get localized error message
                    try:
                        translations = await self.hass.helpers.translation.async_get_translations(
                            self.hass.config.language, "config", {"smartsolar_mppt"}
                        )
                        error_msg = translations.get("config.error.no_configuration", "No chipset_ids or project_id found in configuration")
                    except (ImportError, KeyError, AttributeError):
                        # Fallback to English if translation fails
                        error_msg = "No chipset_ids or project_id found in configuration"
                    raise UpdateFailed(error_msg)
                
                data = await self.api.get_metrics(
                    device_type=device_type,
                    chipset_ids=chipset_ids,
                    mode=mode,
                )

            _LOGGER.debug("API response data: %s", data)
            
            # Track discovered devices for project mode
            if mode == "project" and "deviceLogs" in data:
                current_devices = {str(log.get("deviceGuid")) for log in data.get("deviceLogs", []) if log.get("deviceGuid")}
                new_devices = current_devices - self.discovered_devices
                
                if new_devices:
                    _LOGGER.info("New devices discovered: %s", list(new_devices))
                    self.discovered_devices.update(new_devices)
                    # Trigger device discovery callbacks
                    for callback in self._device_discovery_callbacks:
                        try:
                            callback(list(new_devices))
                        except (ValueError, TypeError, AttributeError) as e:
                            _LOGGER.error("Error in device discovery callback: %s", e)

            # Add metadata to the data
            data["_mode"] = mode
            data["_device_type"] = device_type
            data["_chipset_ids"] = chipset_ids

            return data

        except SmartSolarAPIError as err:
            _LOGGER.error("SmartSolar API error: %s", err)
            raise UpdateFailed(f"SmartSolar API error: {err}") from err
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Data processing error: %s", err, exc_info=True)
            raise UpdateFailed(f"Data processing error: {err}") from err

    def add_device_discovery_callback(self, callback: callable) -> None:
        """Add a callback to be called when new devices are discovered."""
        self._device_discovery_callbacks.append(callback)

    def get_discovered_devices(self) -> list[str]:
        """Get list of currently discovered devices."""
        return list(self.discovered_devices)
