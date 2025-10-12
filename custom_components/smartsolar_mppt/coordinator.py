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

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Get configuration from entry
            device_type = self.entry.data["device_type"]
            chipset_ids = self.entry.data["chipset_ids"]
            mode = self.entry.data["mode"]

            _LOGGER.debug("Fetching metrics - device_type: %s, chipset_ids: %s, mode: %s", 
                         device_type, chipset_ids, mode)

            # Fetch metrics from API
            data = await self.api.get_metrics(
                device_type=device_type,
                chipset_ids=chipset_ids,
                mode=mode,
            )

            _LOGGER.debug("API response data: %s", data)

            # Add metadata to the data
            data["_mode"] = mode
            data["_device_type"] = device_type
            data["_chipset_ids"] = chipset_ids

            return data

        except SmartSolarAPIError as err:
            _LOGGER.error("SmartSolar API error: %s", err)
            raise UpdateFailed(f"SmartSolar API error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err, exc_info=True)
            raise UpdateFailed(f"Unexpected error: {err}") from err
