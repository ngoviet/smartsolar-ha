"""Sensor platform for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_STREAM_INDICES,
    DEVICE_TYPE_MANH_QUAN,
    DEVICE_TYPE_SUN_GTIL2,
    DOMAIN,
    MODE_DEVICE,
    MODE_PROJECT,
    SENSOR_TYPES,
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
    device_type = config_entry.data["device_type"]
    chipset_ids = config_entry.data["chipset_ids"]

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
        for device_guid in chipset_ids:
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


class SmartSolarSensor(CoordinatorEntity[SmartSolarDataUpdateCoordinator], SensorEntity):
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
        self._attr_native_unit_of_measurement = sensor_info["unit"]
        self._attr_icon = sensor_info["icon"]
        self._attr_device_class = sensor_info.get("device_class")
        self._attr_state_class = SensorStateClass(sensor_info.get("state_class", "measurement"))

        # Set device info
        device_type_name = "Sạc MPPT Mạnh Quân"  # Only support Mạnh Quân now
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

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    def _get_value_from_data_streams(self, data_streams: list[dict[str, Any]]) -> float | None:
        """Get value from data streams based on sensor type."""
        if not data_streams:
            return None

        # Find data stream by name instead of index
        for stream in data_streams:
            if stream.get("name") == self._sensor_type:
                try:
                    value = stream.get("value")
                    if value is None:
                        return None
                    return float(value)
                except (ValueError, TypeError):
                    return None
        
        return None


class SmartSolarDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for device mode."""

    @property
    def native_value(self) -> float | None:
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

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # For project mode synthesis, data is in synthesisStreams
        synthesis_streams = self.coordinator.data.get("synthesisStreams", [])
        
        return self._get_value_from_data_streams(synthesis_streams)


class SmartSolarProjectDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for individual device in project mode."""

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # For project mode individual device, find device in deviceLogs
        device_logs = self.coordinator.data.get("deviceLogs", [])
        
        _LOGGER.debug("Project device sensor %s - Looking for deviceGuid: %s", self._sensor_type, self._device_guid)
        _LOGGER.debug("Project device sensor %s - Available deviceLogs: %s", self._sensor_type, [log.get("deviceGuid") for log in device_logs])
        
        for device_log in device_logs:
            device_guid = device_log.get("deviceGuid")
            _LOGGER.debug("Project device sensor %s - Checking deviceGuid: %s (type: %s)", self._sensor_type, device_guid, type(device_guid))
            
            if device_guid == self._device_guid:
                data_streams = device_log.get("dataStreams", [])
                _LOGGER.debug("Project device sensor %s - Found matching device, dataStreams: %s", self._sensor_type, data_streams)
                return self._get_value_from_data_streams(data_streams)
        
        _LOGGER.warning("Project device sensor %s - No matching device found for GUID: %s", self._sensor_type, self._device_guid)
        return None

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._sensor_info['name']} ({self._device_guid[:8]}...)"
