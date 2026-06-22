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

    __slots__ = ("api", "entry", "discovered_devices")

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
            always_update=False,
        )
        self.api = api
        self.entry = entry
        self.discovered_devices: set[str] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Get configuration from entry with validation
            device_type = self.entry.data.get("device_type")
            chipset_ids = self.entry.data.get("chipset_ids")
            mode = self.entry.data.get("mode")
            project_id = self.entry.data.get("project_id")
            
            # Validate required fields
            if not device_type:
                raise UpdateFailed("Missing device_type in configuration")
            if not mode:
                raise UpdateFailed("Missing mode in configuration")
            if not project_id and not chipset_ids:
                raise UpdateFailed("Missing both project_id and chipset_ids in configuration")

            _LOGGER.debug("SmartSolar API Update - Interval: %s, Mode: %s", 
                        self.update_interval, mode)

            # Fetch metrics from API
            if project_id:
                # Use project ID for project mode
                data = await self.api.get_project_metrics(project_id)
            else:
                # Use existing logic for device mode or device IDs project mode
                if not chipset_ids:
                    raise UpdateFailed("No chipset_ids or project_id found in configuration")
                
                data = await self.api.get_metrics(
                    device_type=device_type,
                    chipset_ids=chipset_ids,
                    mode=mode,
                )

            # Log summary only — avoid logging full response with potentially sensitive data
            _LOGGER.debug(
                "API response: mode=%s, keys=%s, device_count=%s",
                data.get("_mode"), list(data.keys()),
                len(data.get("deviceLogs", [])),
            )
            
            # Track discovered devices for project mode
            if mode == "project" and "deviceLogs" in data:
                current_devices = {str(log.get("deviceGuid")) for log in data.get("deviceLogs", []) if log.get("deviceGuid")}
                new_devices = current_devices - self.discovered_devices
                if new_devices:
                    _LOGGER.info("New devices discovered: %s", list(new_devices))
                    self.discovered_devices.update(new_devices)

            # Add metadata to the data
            data["_mode"] = mode
            data["_device_type"] = device_type
            data["_chipset_ids"] = chipset_ids

            _LOGGER.debug("SmartSolar API Update Complete")
            return data

        except SmartSolarAPIError as err:
            _LOGGER.error("SmartSolar API error: %s", err)
            raise UpdateFailed(f"SmartSolar API error: {err}") from err
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Data processing error: %s", err, exc_info=True)
            raise UpdateFailed(f"Data processing error: {err}") from err
