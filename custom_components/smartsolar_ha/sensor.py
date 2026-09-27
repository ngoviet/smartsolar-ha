"""Sensor platform for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_DEVICE,
    MODE_PROJECT,
    SENSOR_LOGGER,
    SENSOR_TYPES,
    STATS_SENSOR_TYPES,
    STATUS_MAPPING,
    SYNTHESIS_FIELD_MAPPING,
    UNRELIABLE_SYNTHESIS_SENSORS,
    build_device_info,
    get_aggregation,
)
from .coordinator import SmartSolarDataUpdateCoordinator
from .helpers import as_list, coerce_float, device_logs, stream_dict

_LOGGER = logging.getLogger(SENSOR_LOGGER)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SmartSolar MPPT sensor based on a config entry."""
    coordinator: SmartSolarDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    mode = config_entry.data["mode"]
    chipset_ids = config_entry.data.get("chipset_ids")

    entities: list[SmartSolarSensor] = []

    if mode == MODE_DEVICE:
        # Device mode: create sensors for single device
        device_guid = chipset_ids[0] if chipset_ids else "unknown"
        for sensor_type, sensor_info in SENSOR_TYPES.items():
            entities.append(
                SmartSolarDeviceSensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    sensor_type=sensor_type,
                    sensor_info=sensor_info,
                    device_guid=device_guid,
                )
            )
        # Stats sensors (daily peak, avg, production hours)
        for sensor_type, sensor_info in STATS_SENSOR_TYPES.items():
            entities.append(
                SmartSolarStatsSensor(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    sensor_type=sensor_type,
                    sensor_info=sensor_info,
                    device_guid=device_guid,
                )
            )
    elif mode == MODE_PROJECT:
        # Project mode: create synthesis sensors + individual device sensors
        # Synthesis sensors (overall project data) — labeled "Tổng"
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
        device_guids: list[str] = []

        # Try to get device GUIDs from coordinator data first. The order is
        # sorted (see SmartSolarDataUpdateCoordinator.device_guids) so the
        # PV1/PV2 labels and the resulting entity_ids do not shuffle between
        # restarts.
        if coordinator.data and "deviceLogs" in coordinator.data:
            device_guids = coordinator.device_guids(coordinator.data)

        # Fallback to chipset_ids from config if no data available yet
        if not device_guids and chipset_ids:
            device_guids = [str(cid) for cid in chipset_ids]

        # Create individual device sensors for each discovered device (labeled PV1, PV2, ...)
        for idx, device_guid in enumerate(device_guids):
            for sensor_type, sensor_info in SENSOR_TYPES.items():
                entities.append(
                    SmartSolarProjectDeviceSensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        sensor_type=sensor_type,
                        sensor_info=sensor_info,
                        device_guid=device_guid,
                        device_index=idx + 1,  # 1-based: PV1, PV2, ...
                    )
                )
            # Stats sensors for each device in project mode
            for sensor_type, sensor_info in STATS_SENSOR_TYPES.items():
                entities.append(
                    SmartSolarStatsSensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        sensor_type=sensor_type,
                        sensor_info=sensor_info,
                        device_guid=device_guid,
                        device_index=idx + 1,
                    )
                )

    async_add_entities(entities)


class SmartSolarSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base class for SmartSolar sensors."""

    # Narrow the coordinator type: CoordinatorEntity only knows the generic
    # DataUpdateCoordinator, but our subclasses call the SmartSolar-specific
    # get_daily_stats()/device_guids() helpers.
    coordinator: SmartSolarDataUpdateCoordinator

    __slots__ = (
        "_config_entry",
        "_sensor_type",
        "_sensor_info",
        "_device_guid",
        "_attr_unique_id",
        "_attr_name",
        "_attr_native_unit_of_measurement",
        "_attr_icon",
        "_attr_device_class",
        "_attr_state_class",
        "_attr_device_info",
    )

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_info: dict[str, Any],
        device_guid: str | None = None,
        device_index: int | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._sensor_type = sensor_type
        self._sensor_info = sensor_info
        self._device_guid = device_guid

        mode = config_entry.data.get("mode")
        project_id = config_entry.data.get("project_id")
        chipset_ids = config_entry.data.get("chipset_ids")

        _LOGGER.debug(
            "Creating sensor - Type: %s, Mode: %s, Project ID: %s, Chipset IDs: %s, Device GUID: %s",
            sensor_type,
            mode,
            project_id,
            chipset_ids,
            device_guid,
        )

        if mode == MODE_DEVICE:
            # Device mode: d_{device_id}
            prefix = f"d_{device_guid if device_guid else 'unknown'}"
        elif mode == MODE_PROJECT:
            if device_guid:
                # Individual device in project mode
                prefix = f"pd_{device_guid}" if project_id else f"md_{device_guid}"
            else:
                # Synthesis sensor in project mode
                prefix = f"p_{project_id}" if project_id else f"m_{chipset_ids[0] if chipset_ids else 'unknown'}"
        else:
            prefix = "unknown"

        self._attr_unique_id = f"{config_entry.entry_id}_{prefix}_{sensor_type}"

        # Debug: Log generated unique_id
        _LOGGER.debug(
            "Generated unique_id: %s (prefix: %s, sensor_type: %s)", self._attr_unique_id, prefix, sensor_type
        )

        # Set basic attributes (name without prefix)
        base_name = sensor_info["name"]

        if device_guid and device_index:
            # Per-device sensor in project mode: "PV1 Voltage", "PV2 Current", etc.
            self._attr_name = f"PV{device_index} {base_name}"
        elif device_guid:
            # Device mode or unknown index: fallback to GUID suffix
            self._attr_name = f"{base_name} ({device_guid})"
        else:
            # Synthesis sensor: add "Tổng" for clarity
            self._attr_name = f"Total {base_name}"

        self._attr_native_unit_of_measurement = sensor_info.get("unit")
        self._attr_icon = sensor_info["icon"]
        self._attr_device_class = sensor_info.get("device_class")

        # Set state_class only if it's not None
        state_class = sensor_info.get("state_class")
        if state_class is not None:
            self._attr_state_class = SensorStateClass(state_class)
        else:
            self._attr_state_class = None

        self._attr_device_info = build_device_info(config_entry.entry_id, mode, project_id)

    def _get_value_from_data_streams(self, data_streams: list[dict[str, Any]] | None) -> float | str | None:
        """Get value from data streams based on sensor type - optimized version."""
        if not data_streams:
            return None

        return self._convert_stream_value(stream_dict(data_streams).get(self._sensor_type))

    def _convert_stream_value(self, value: Any) -> float | str | None:
        """Convert a raw stream value into the sensor's native value."""
        if value is None:
            return None

        # Handle status mapping
        if self._sensor_type == "status":
            try:
                return STATUS_MAPPING.get(int(float(value)), f"Unknown ({value})")
            except ValueError, TypeError:
                return f"Unknown ({value})"

        # Convert to float for numeric sensors
        try:
            num_value = float(value)
        except ValueError, TypeError:
            return None

        # NaN slips through every ``>``/``<`` comparison below, so it has to be
        # rejected explicitly: json.loads accepts the bare NaN/Infinity literals
        # that appear in some MQTT payloads, and a NaN state poisons Home
        # Assistant's long-term statistics for the sensor.
        if not math.isfinite(num_value):
            _LOGGER.debug(
                "Sensor %s value %r is not finite — treating as invalid",
                self._sensor_type,
                num_value,
            )
            return None

        # Validate against max_value to reject garbage/overflow readings
        max_val = self._sensor_info.get("max_value")
        if max_val is not None and num_value > max_val:
            _LOGGER.debug(
                "Sensor %s value %.1f exceeds max %.0f — treating as invalid",
                self._sensor_type,
                num_value,
                max_val,
            )
            return None

        return num_value

    def _device_log_value(self, device_log: Any, *, raw_status: bool = False) -> float | str | None:
        """Extract this sensor's value from one deviceLog entry.

        Two locations are consulted, in this order:
          1. ``dataStreams`` — live MQTT values are merged in here, so this is
             the freshest source whenever the device publishes them.
          2. the deviceLog's top-level ``signalQuality`` — the REST
             ``/Metric/*`` response reports WiFi signal there, NOT inside
             ``dataStreams``. Some firmware only ever sends the older
             ``updateDeviceLog`` message, which carries no signalQuality at all,
             so for those devices this REST value is the only one that exists.

        ``raw_status`` returns the numeric status code untouched, which is what
        cross-device aggregation needs (aggregating already-mapped text would
        always fail).
        """
        if not isinstance(device_log, dict):
            return None

        if raw_status and self._sensor_type == "status":
            return coerce_float(stream_dict(device_log.get("dataStreams")).get("status"))

        data_streams = device_log.get("dataStreams")
        value = self._get_value_from_data_streams(data_streams if isinstance(data_streams, list) else None)
        if value is None and self._sensor_type == "signal_quality":
            value = self._convert_stream_value(device_log.get("signalQuality"))
        return value


class SmartSolarDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for device mode."""

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available")
            return None

        # For device mode, data is in lastMessage.dataStreams
        last_message = self.coordinator.data.get("lastMessage") or {}
        return self._device_log_value(last_message)


class SmartSolarProjectSynthesisSensor(SmartSolarSensor):
    """SmartSolar sensor for project synthesis mode."""

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor.

        For most sensors the server's ``synthesisStreams`` value is used, and
        individual ``deviceLogs`` are the fallback. Sensors listed in
        ``UNRELIABLE_SYNTHESIS_SENSORS`` (charge_power, currents, WiFi signal)
        are ALWAYS aggregated from ``deviceLogs`` because the server value is
        frequently stale or absent.

        Aggregation is per sensor type (see ``const.AGGREGATION``): currents,
        power and energy are summed, while voltage / temperature / signal
        quality are averaged. The devices of a project share one battery bus,
        so summing voltages would report 53 V for a 24 V system.
        """
        if not self.coordinator.data:
            return None

        # ── Always aggregate locally ──
        if self._sensor_type in UNRELIABLE_SYNTHESIS_SENSORS:
            return self._calculate_from_device_logs()

        # ── Prefer the server-side synthesis value ──
        synthesis_streams = as_list(self.coordinator.data.get("synthesisStreams"))
        if synthesis_streams:
            field_name = SYNTHESIS_FIELD_MAPPING.get(self._sensor_type, self._sensor_type)
            for stream in synthesis_streams:
                if not isinstance(stream, dict) or stream.get("name") != field_name:
                    continue
                value = stream.get("value")
                if value is None:
                    break
                try:
                    num_value = float(value)
                except ValueError, TypeError:
                    break
                return self._apply_status_mapping(num_value)

        return self._calculate_from_device_logs()

    def _apply_status_mapping(self, num_value: float) -> float | str:
        """Map a status code to text; pass other numeric values through."""
        if self._sensor_type == "status":
            return STATUS_MAPPING.get(int(num_value), f"Unknown ({num_value})")
        return num_value

    def _calculate_from_device_logs(self) -> float | str | None:
        """Aggregate the value from the individual device logs."""
        device_log_entries = device_logs(self.coordinator.data)
        if not device_log_entries:
            _LOGGER.debug(
                "Synthesis sensor %s - no deviceLogs available for aggregation",
                self._sensor_type,
            )
            return None

        values: list[float] = []
        for device_log in device_log_entries:
            value = self._device_log_value(device_log, raw_status=True)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))

        if not values:
            return None

        return self._aggregate(values)

    def _aggregate(self, values: list[float]) -> float | str:
        """Combine per-device values according to the sensor's strategy.

        Only "sum", "average" and "max" are reachable; ``const.AGGREGATION``
        maps every sensor type to one of those three.
        """
        strategy = get_aggregation(self._sensor_type)

        if strategy == "sum":
            return sum(values)

        result = max(values) if strategy == "max" else sum(values) / len(values)

        if self._sensor_type == "status":
            return self._apply_status_mapping(result)
        return result


class SmartSolarProjectDeviceSensor(SmartSolarSensor):
    """SmartSolar sensor for individual device in project mode."""

    def __init__(
        self,
        coordinator: SmartSolarDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_info: dict[str, Any],
        device_guid: str,
        device_index: int,
    ) -> None:
        """Initialize individual device sensor with index for friendly naming."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            sensor_type=sensor_type,
            sensor_info=sensor_info,
            device_guid=device_guid,
            device_index=device_index,
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        device_log_entries = device_logs(self.coordinator.data)
        if not device_log_entries:
            # Debug, not warning: this fires for every sensor of the entry on
            # every poll (and once per second per MQTT message), which used to
            # flood the log while the first refresh was still failing.
            _LOGGER.debug("No deviceLogs in coordinator data, keys: %s", list(self.coordinator.data.keys()))
            return None

        for device_log in device_log_entries:
            if not isinstance(device_log, dict):
                continue
            if str(device_log.get("deviceGuid")) == str(self._device_guid):
                return self._device_log_value(device_log)

        _LOGGER.debug(
            "Device GUID %s not found in deviceLogs. Available GUIDs: %s",
            self._device_guid,
            [str(log.get("deviceGuid")) for log in device_log_entries if isinstance(log, dict)],
        )
        return None


class SmartSolarStatsSensor(SmartSolarSensor):
    """Sensor for daily statistics computed by the coordinator.

    Reads from coordinator.get_daily_stats() which tracks peak power,
    average power, and production hours per device. These statistics
    are NOT stored by the SmartSolar server long-term.
    """

    @property
    def native_value(self) -> float | None:
        """Return the stats value from coordinator daily tracking."""
        if self._device_guid is None:
            return None

        stats: dict[str, float] = self.coordinator.get_daily_stats(self._device_guid)

        # Map sensor_type → stat key returned by get_daily_stats()
        stat_key_map = {
            "peak_power_today": "peak_power",
            "avg_power_today": "avg_power",
            "production_hours_today": "production_hours",
        }
        key = stat_key_map.get(self._sensor_type)
        if key is None:
            return None

        return stats.get(key, 0.0)
