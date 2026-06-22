"""Data update coordinator for SmartSolar MPPT."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartSolarAPI, SmartSolarAPIError
from .const import DEFAULT_UPDATE_INTERVAL, MODE_DEVICE

_LOGGER = logging.getLogger(__name__)


class SmartSolarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the SmartSolar API.

    Supports optional MQTT real-time data: when MQTT data is available
    for a device, it is merged into the HTTP response so sensors see
    live values between polling intervals.
    """

    __slots__ = ("api", "entry", "discovered_devices", "_mqtt_data", "_mqtt_client")

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
        self._mqtt_data: dict[str, dict[str, Any]] = {}
        self._mqtt_client: Any = None  # SmartSolarMQTTClient set by __init__.py

    def set_mqtt_client(self, mqtt_client: Any) -> None:
        """Set the MQTT client reference for real-time data merging."""
        self._mqtt_client = mqtt_client

    async def async_process_mqtt_data(
        self, device_guid: str, data: dict[str, Any]
    ) -> None:
        """Process incoming MQTT data for a device.

        Stores the normalized data and triggers an entity update so
        sensors reflect real-time values without waiting for the next
        HTTP poll.
        """
        self._mqtt_data[device_guid] = data

        # If coordinator.data exists, patch it in-place and notify entities
        if self.data is not None:
            self._merge_mqtt_into_data(self.data, device_guid, data)
            self.async_set_updated_data(self.data)

    def _mqtt_to_data_stream(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert flat MQTT data dict to dataStreams list format."""
        return [
            {"name": key, "value": str(value)}
            for key, value in data.items()
        ]

    def _merge_mqtt_into_data(
        self,
        api_data: dict[str, Any],
        device_guid: str,
        mqtt_data: dict[str, Any],
    ) -> None:
        """Merge MQTT data into API response data in-place."""
        mqtt_streams = self._mqtt_to_data_stream(mqtt_data)

        mode = api_data.get("_mode", self.entry.data.get("mode"))

        if mode == MODE_DEVICE:
            # Device mode: update lastMessage.dataStreams
            last_msg = api_data.setdefault("lastMessage", {})
            existing = last_msg.get("dataStreams", [])
            merged = self._merge_streams(existing, mqtt_streams)
            last_msg["dataStreams"] = merged
        else:
            # Project mode: update deviceLogs for the matching device
            device_logs = api_data.get("deviceLogs", [])
            found = False
            for device_log in device_logs:
                if str(device_log.get("deviceGuid")) == str(device_guid):
                    existing = device_log.get("dataStreams", [])
                    device_log["dataStreams"] = self._merge_streams(
                        existing, mqtt_streams
                    )
                    found = True
                    break

            if not found:
                # New device — add a deviceLog entry from MQTT data
                api_data.setdefault("deviceLogs", []).append({
                    "deviceGuid": device_guid,
                    "dataStreams": mqtt_streams,
                })
                _LOGGER.info(
                    "MQTT discovered new device %s not yet in API response",
                    device_guid,
                )

    @staticmethod
    def _merge_streams(
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge incoming dataStreams into existing, overwriting by name."""
        merged = {s["name"]: s for s in existing}
        for stream in incoming:
            merged[stream["name"]] = stream
        return list(merged.values())

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

            # Merge any MQTT real-time data into the HTTP response
            if self._mqtt_data:
                for guid, mqtt_data in self._mqtt_data.items():
                    self._merge_mqtt_into_data(data, guid, mqtt_data)

            _LOGGER.debug("SmartSolar API Update Complete")
            return data

        except SmartSolarAPIError as err:
            _LOGGER.error("SmartSolar API error: %s", err)
            raise UpdateFailed(f"SmartSolar API error: {err}") from err
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Data processing error: %s", err, exc_info=True)
            raise UpdateFailed(f"Data processing error: {err}") from err
