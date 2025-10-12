"""Sensor platform for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_DEVICE,
    MODE_PROJECT,
    SENSOR_TYPES,
    STATUS_MAPPING,
)
from .coordinator import SmartSolarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SmartSolar MPPT sensor based on a config entry."""
    coordinator: SmartSolarDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    mode = config_entry.data["mode"]
    chipset_ids = config_entry.data.get("chipset_ids")

    entities: list[SmartSolarSensor] = []

    if mode == MODE_DEVICE:
        # Device mode: create sensors for single device
        for sensor_type, sensor_info in SENSOR_TYPES.items():
            entities.append(
                SmartSolarDeviceSensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    sensor_type=sensor_type,
                    sensor_info=sensor_info,
                    device_guid=chipset_ids[0] if chipset_ids else "unknown",
                )
            )
    elif mode == MODE_PROJECT:
        # Project mode: create synthesis sensors + individual device sensors
        # Synthesis sensors (overall project data)
        for sensor_type, sensor_info in SENSOR_TYPES.items():
            entities.append(
                SmartSolarProjectSynthesisSensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    sensor_type=sensor_type,
                    sensor_info=sensor_info,
                )
            )

        # Individual device sensors
        # Get device GUIDs from coordinator data (works for both Project ID and Device IDs mode)
        device_guids = []
        
        # Try to get device GUIDs from coordinator data first
        if coordinator.data and "deviceLogs" in coordinator.data:
            device_guids = [str(log.get("deviceGuid")) for log in coordinator.data.get("deviceLogs", []) if log.get("deviceGuid")]
        
        # Fallback to chipset_ids from config if no data available yet
        if not device_guids and chipset_ids:
            device_guids = chipset_ids
        
        # Create individual device sensors for each discovered device
        for device_guid in device_guids:
            for sensor_type, sensor_info in SENSOR_TYPES.items():
                entities.append(
                    SmartSolarProjectDeviceSensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        sensor_type=sensor_type,
                        sensor_info=sensor_info,
                        device_guid=device_guid,
                    )
                )

    async_add_entities(entities)


class SmartSolarSensor(CoordinatorEntity, SensorEntity):  # type: ignore[misc]
    """Base class for SmartSolar sensors."""

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_info: dict[str, Any],
        device_guid: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._sensor_type = sensor_type
        self._sensor_info = sensor_info
        self._device_guid = device_guid

        # Set unique ID
        if device_guid:
            self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}_{device_guid}"
        else:
            self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"

        # Set basic attributes
        self._attr_name = sensor_info["name"]
        self._attr_native_unit_of_measurement = sensor_info.get("unit")
        self._attr_icon = sensor_info["icon"]
        self._attr_device_class = sensor_info.get("device_class")
        
        # Set state_class only if it's not None
        state_class = sensor_info.get("state_class")
        if state_class is not None:
            self._attr_state_class = SensorStateClass(state_class)
        else:
            self._attr_state_class = None

        # Set device info
        mode_name = "Device" if config_entry.data["mode"] == MODE_DEVICE else "Project"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"SmartSolar MPPT {mode_name}",
            "manufacturer": "SmartSolar",
            "model": "MPPT Controller",
            "sw_version": "1.0.0",
            "hw_version": "MPPT",
            "configuration_url": "https://smartsolar.io.vn/",
        }


    def _get_value_from_data_streams(self, data_streams: list[dict[str, Any]]) -> float | str | None:
        """Get value from data streams based on sensor type - optimized version."""
        if not data_streams:
            return None

        # Use dict for O(1) lookup instead of list iteration
        stream_dict = {s["name"]: s["value"] for s in data_streams if s.get("name") and s.get("value") is not None}
        value = stream_dict.get(self._sensor_type)
        
        if value is None:
            return None
        
        # Handle status mapping
        if self._sensor_type == "status":
            try:
                return STATUS_MAPPING.get(int(value), f"Unknown ({value})")
            except (ValueError, TypeError):
                return f"Unknown ({value})"
        
        # Convert to float for numeric sensors
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


class SmartSolarDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for device mode."""

    @cached_property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available")
            return None

        # For device mode, data is in lastMessage.dataStreams
        last_message = self.coordinator.data.get("lastMessage", {})
        data_streams = last_message.get("dataStreams", [])
        
        _LOGGER.debug("Device sensor %s - lastMessage: %s", self._sensor_type, last_message)
        _LOGGER.debug("Device sensor %s - dataStreams: %s", self._sensor_type, data_streams)
        
        return self._get_value_from_data_streams(data_streams)


class SmartSolarProjectSynthesisSensor(SmartSolarSensor):
    """SmartSolar sensor for project synthesis mode."""

    @cached_property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # For project mode synthesis, get data directly from synthesisStreams
        synthesis_streams = self.coordinator.data.get("synthesisStreams", [])
        
        if not synthesis_streams:
            _LOGGER.debug("Project synthesis sensor %s - No synthesisStreams available", self._sensor_type)
            return None
        
        # Map sensor types to API field names
        api_field_mapping = {
            "today_kwh": "yield_today",
            "total_kwh": "yield_total"
        }
        
        # Use mapped field name or original sensor type
        field_name = api_field_mapping.get(self._sensor_type, self._sensor_type)
        
        # Find the synthesis stream with matching name
        for stream in synthesis_streams:
            if stream.get("name") == field_name:
                try:
                    value = stream.get("value")
                    if value is None:
                        return None
                    return float(value)
                except (ValueError, TypeError):
                    return None
        
        # For status, calculate average from deviceLogs since it's not in synthesisStreams
        if self._sensor_type == "status":
            device_logs = self.coordinator.data.get("deviceLogs", [])
            if not device_logs:
                _LOGGER.debug("Project synthesis sensor %s - No deviceLogs available for status calculation", self._sensor_type)
                return None
            
            total_status = 0.0
            count = 0
            
            for device_log in device_logs:
                data_streams = device_log.get("dataStreams", [])
                device_status = self._get_value_from_data_streams(data_streams)
                
                if device_status is not None:
                    # For status calculation, we need the raw numeric value, not the mapped string
                    # Find the raw status value from data streams
                    raw_status = None
                    for stream in data_streams:
                        if stream.get("name") == "status":
                            try:
                                raw_status = float(stream.get("value", 0))
                                break
                            except (ValueError, TypeError):
                                raw_status = 0
                    
                    if raw_status is not None:
                        total_status += raw_status
                        count += 1
            
            if count == 0:
                _LOGGER.debug("Project synthesis sensor %s - No valid status data from any device", self._sensor_type)
                return None
            
            # Return average status
            avg_status = total_status / count
            # Map status number to text
            return STATUS_MAPPING.get(int(avg_status), f"Unknown ({avg_status})")
        
        _LOGGER.debug("Project synthesis sensor %s - Field '%s' not found in synthesisStreams", self._sensor_type, field_name)
        return None


class SmartSolarProjectDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for individual device in project mode."""

    @cached_property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # For project mode individual device, find device in deviceLogs
        device_logs = self.coordinator.data.get("deviceLogs", [])
        
        _LOGGER.debug("Project device sensor %s - Looking for deviceGuid: '%s' (type: %s)", self._sensor_type, self._device_guid, type(self._device_guid))
        _LOGGER.debug("Project device sensor %s - Available deviceLogs: %s", self._sensor_type, [log.get("deviceGuid") for log in device_logs])
        
        for device_log in device_logs:
            device_guid = device_log.get("deviceGuid")
            _LOGGER.debug("Project device sensor %s - Checking deviceGuid: '%s' (type: %s)", self._sensor_type, device_guid, type(device_guid))
            
            if str(device_guid) == str(self._device_guid):
                data_streams = device_log.get("dataStreams", [])
                _LOGGER.debug("Project device sensor %s - Found matching device, dataStreams: %s", self._sensor_type, data_streams)
                return self._get_value_from_data_streams(data_streams)
        
        _LOGGER.warning("Project device sensor %s - No matching device found for GUID: %s", self._sensor_type, self._device_guid)
        return None

    @cached_property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self._sensor_info and self._device_guid:
            return f"{self._sensor_info['name']} ({self._device_guid[:8]}...)"
        elif self._device_guid:
            return f"Unknown ({self._device_guid[:8]}...)"
        else:
            return "Unknown Device"

