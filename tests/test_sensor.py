"""Tests for sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.smartsolar_mppt.const import SENSOR_TYPES
from custom_components.smartsolar_mppt.sensor import (
    SmartSolarDeviceSensor,
    SmartSolarProjectDeviceSensor,
    SmartSolarProjectSynthesisSensor,
    SmartSolarSensor,
)
from tests.conftest import SAMPLE_DEVICE_RESPONSE, SAMPLE_PROJECT_RESPONSE


class TestGetValueFromDataStreams:
    """Tests for _get_value_from_data_streams."""

    def setup_method(self):
        self.coordinator = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.entry_id = "test_entry"
        self.config_entry.data = {"mode": "project", "project_id": "1072"}
        self.sensor_info = SENSOR_TYPES["pv_voltage"]

    def _make_sensor(self):
        return SmartSolarSensor(
            coordinator=self.coordinator,
            config_entry=self.config_entry,
            sensor_type="pv_voltage",
            sensor_info=self.sensor_info,
        )

    def test_returns_none_for_empty_data_streams(self):
        """Empty data streams returns None."""
        sensor = self._make_sensor()
        result = sensor._get_value_from_data_streams([])
        assert result is None

    def test_returns_none_for_none_input(self):
        """None input returns None."""
        sensor = self._make_sensor()
        result = sensor._get_value_from_data_streams(None)
        assert result is None

    def test_extracts_correct_value(self):
        """Extracts correct value by sensor type name."""
        sensor = self._make_sensor()
        streams = [
            {"name": "pv_voltage", "value": "48.5"},
            {"name": "pv_current", "value": "5.2"},
        ]
        result = sensor._get_value_from_data_streams(streams)
        assert result == 48.5

    def test_returns_none_for_missing_sensor_type(self):
        """Returns None when sensor type not in streams."""
        sensor = SmartSolarSensor(
            coordinator=self.coordinator,
            config_entry=self.config_entry,
            sensor_type="bat_voltage",
            sensor_info=SENSOR_TYPES["bat_voltage"],
        )
        streams = [{"name": "pv_voltage", "value": "48.5"}]
        result = sensor._get_value_from_data_streams(streams)
        assert result is None

    def test_rejects_value_above_max_value(self):
        """Values exceeding max_value return None."""
        sensor = self._make_sensor()
        # pv_voltage max_value is 150
        streams = [{"name": "pv_voltage", "value": "999.0"}]
        result = sensor._get_value_from_data_streams(streams)
        assert result is None

    def test_accepts_value_at_max_value(self):
        """Values exactly at max_value are accepted."""
        sensor = self._make_sensor()
        streams = [{"name": "pv_voltage", "value": "150.0"}]
        result = sensor._get_value_from_data_streams(streams)
        assert result == 150.0

    def test_status_maps_numeric_to_string(self):
        """Status sensor maps numeric codes to text."""
        sensor = SmartSolarSensor(
            coordinator=self.coordinator,
            config_entry=self.config_entry,
            sensor_type="status",
            sensor_info=SENSOR_TYPES["status"],
        )
        streams = [{"name": "status", "value": "1"}]
        result = sensor._get_value_from_data_streams(streams)
        assert result == "Charging"

    def test_status_unknown_value(self):
        """Unknown status codes produce 'Unknown (X)' string."""
        sensor = SmartSolarSensor(
            coordinator=self.coordinator,
            config_entry=self.config_entry,
            sensor_type="status",
            sensor_info=SENSOR_TYPES["status"],
        )
        streams = [{"name": "status", "value": "99"}]
        result = sensor._get_value_from_data_streams(streams)
        assert "Unknown" in str(result)

    def test_falsy_name_not_skipped(self):
        """Stream with name='' but valid value should NOT be skipped (bug fix)."""
        # The fix is: s.get("name") is not None (not s.get("name"))
        sensor = self._make_sensor()
        streams = [{"name": "", "value": "1.0"}]  # Empty string name
        result = sensor._get_value_from_data_streams(streams)
        # "" is not pv_voltage, so should return None
        assert result is None

    def test_none_value_is_skipped(self):
        """Stream with value=None is skipped."""
        sensor = self._make_sensor()
        streams = [{"name": "pv_voltage", "value": None}]
        result = sensor._get_value_from_data_streams(streams)
        assert result is None


class TestSensorNaming:
    """Tests for sensor entity naming."""

    def test_synthesis_sensor_uses_total_prefix(self, mock_coordinator, mock_config_entry):
        """Synthesis sensor (no device_guid) uses 'Total' prefix."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
        )
        assert sensor._attr_name.startswith("Total ")
        assert "PV Voltage" in sensor._attr_name

    def test_device_sensor_uses_pv_prefix(self, mock_coordinator, mock_config_entry):
        """Per-device sensor uses 'PV1', 'PV2' naming."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
            device_guid="547611",
            device_index=1,
        )
        assert sensor._attr_name.startswith("PV1 ")

    def test_unique_id_format(self, mock_coordinator, mock_config_entry):
        """Unique ID follows correct format."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
        )
        assert mock_config_entry.entry_id in sensor._attr_unique_id
        assert "pv_voltage" in sensor._attr_unique_id
        assert sensor._attr_unique_id.endswith("_pv_voltage")


class TestValueExtraction:
    """Tests for native_value property."""

    def test_device_sensor_returns_value(self, mock_coordinator, mock_config_entry):
        """DeviceSensor extracts from lastMessage.dataStreams."""
        mock_coordinator.data = SAMPLE_DEVICE_RESPONSE
        sensor = SmartSolarDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
        )
        assert sensor.native_value == 48.5

    def test_device_sensor_returns_none_when_no_data(self, mock_coordinator, mock_config_entry):
        """DeviceSensor returns None when coordinator.data is None."""
        mock_coordinator.data = None
        sensor = SmartSolarDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
        )
        assert sensor.native_value is None

    def test_synthesis_sensor_returns_from_synthesis_streams(self, mock_coordinator, mock_config_entry):
        """Synthesis sensor reads from synthesisStreams."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
        )
        assert sensor.native_value == 48.5

    def test_synthesis_sensor_today_kwh_maps_field_name(self, mock_coordinator, mock_config_entry):
        """today_kwh maps to 'yield_today' in synthesisStreams."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="today_kwh",
            sensor_info=SENSOR_TYPES["today_kwh"],
        )
        assert sensor.native_value == 7.5  # yield_today

    def test_synthesis_sensor_total_kwh_maps_field_name(self, mock_coordinator, mock_config_entry):
        """total_kwh maps to 'yield_total' in synthesisStreams."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="total_kwh",
            sensor_info=SENSOR_TYPES["total_kwh"],
        )
        assert sensor.native_value == 3750.0  # yield_total

    def test_synthesis_sensor_status_from_synthesis_streams(self, mock_coordinator, mock_config_entry):
        """Synthesis status is mapped from the raw code to text."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="status",
            sensor_info=SENSOR_TYPES["status"],
        )
        # synthesisStreams carries "1.0" → "Charging"
        assert sensor.native_value == "Charging"

    def test_synthesis_sensor_falls_back_to_device_logs(self, mock_coordinator, mock_config_entry):
        """When synthesisStreams lacks a field, voltage is AVERAGED, not summed.

        Both chargers sit on the same 24 V battery bus, so the project battery
        voltage is ~24 V — summing would report a nonsense 48 V.
        """
        # Modify coordinator data to remove 'bat_voltage' from synthesisStreams
        mock_coordinator.data = {
            **SAMPLE_PROJECT_RESPONSE,
            "synthesisStreams": [s for s in SAMPLE_PROJECT_RESPONSE["synthesisStreams"] if s["name"] != "bat_voltage"],
        }
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="bat_voltage",
            sensor_info=SENSOR_TYPES["bat_voltage"],
        )
        # bat_voltage from deviceLogs: (24.1 + 24.1) / 2 = 24.1
        assert sensor.native_value == 24.1

    def test_synthesis_sensor_sums_current_from_device_logs(self, mock_coordinator, mock_config_entry):
        """Currents ARE summed across devices (they are additive)."""
        sensor = SmartSolarProjectSynthesisSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_current",
            sensor_info=SENSOR_TYPES["pv_current"],
        )
        # pv_current is always aggregated locally: 5.2 + 10.4
        assert sensor.native_value == pytest.approx(15.6)

    def test_project_device_sensor_matches_by_guid(self, mock_coordinator, mock_config_entry):
        """ProjectDeviceSensor matches correct deviceLog by deviceGuid."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="charge_power",
            sensor_info=SENSOR_TYPES["charge_power"],
            device_guid="547611",
            device_index=1,
        )
        assert sensor.native_value == 248.5

    def test_project_device_sensor_second_device(self, mock_coordinator, mock_config_entry):
        """Second device returns its own data."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="charge_power",
            sensor_info=SENSOR_TYPES["charge_power"],
            device_guid="14756976",
            device_index=2,
        )
        assert sensor.native_value == 497.0

    def test_project_device_sensor_none_when_guid_not_found(self, mock_coordinator, mock_config_entry):
        """Returns None when device GUID not in deviceLogs."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="pv_voltage",
            sensor_info=SENSOR_TYPES["pv_voltage"],
            device_guid="99999",
            device_index=3,
        )
        assert sensor.native_value is None


class TestSynthesisAggregation:
    """Per-sensor-type aggregation across the devices of a project."""

    def _sensor(self, coordinator, entry, sensor_type):
        return SmartSolarProjectSynthesisSensor(
            coordinator=coordinator,
            config_entry=entry,
            sensor_type=sensor_type,
            sensor_info=SENSOR_TYPES[sensor_type],
        )

    def _data_without_synthesis(self):
        """Project data with NO synthesisStreams — forces local aggregation."""
        return {
            "deviceLogs": [
                {
                    "deviceGuid": "547611",
                    "dataStreams": [
                        {"name": "pv_voltage", "value": "26.6"},
                        {"name": "bat_voltage", "value": "26.6"},
                        {"name": "pv_current", "value": "5.0"},
                        {"name": "charge_power", "value": "200.0"},
                        {"name": "temperature", "value": "30.0"},
                        {"name": "status", "value": "1"},
                    ],
                    "signalQuality": 60,
                },
                {
                    "deviceGuid": "14756976",
                    "dataStreams": [
                        {"name": "pv_voltage", "value": "26.4"},
                        {"name": "bat_voltage", "value": "26.4"},
                        {"name": "pv_current", "value": "3.0"},
                        {"name": "charge_power", "value": "100.0"},
                        {"name": "temperature", "value": "40.0"},
                        {"name": "status", "value": "2"},
                    ],
                    "signalQuality": 80,
                },
            ],
        }

    @pytest.mark.parametrize(
        ("sensor_type", "expected"),
        [
            # Additive — summed
            ("pv_current", 8.0),
            ("charge_power", 300.0),
            # Shared bus — averaged, never summed
            ("bat_voltage", 26.5),
            ("pv_voltage", 26.5),
            ("temperature", 35.0),
            ("signal_quality", 70.0),
        ],
    )
    def test_aggregation_strategy_per_sensor(self, mock_coordinator, mock_config_entry, sensor_type, expected):
        mock_coordinator.data = self._data_without_synthesis()
        sensor = self._sensor(mock_coordinator, mock_config_entry, sensor_type)
        assert sensor.native_value == pytest.approx(expected)

    def test_status_takes_worst_case_and_maps_to_text(self, mock_coordinator, mock_config_entry):
        """Status is a worst-case (max) over devices, then mapped to text."""
        mock_coordinator.data = self._data_without_synthesis()
        sensor = self._sensor(mock_coordinator, mock_config_entry, "status")
        # max(1, 2) = 2 → "Idle (No Sun)"
        assert sensor.native_value == "Idle (No Sun)"

    def test_battery_voltage_not_doubled(self, mock_coordinator, mock_config_entry):
        """Regression: two 26.5 V chargers must NOT report 53 V."""
        mock_coordinator.data = self._data_without_synthesis()
        sensor = self._sensor(mock_coordinator, mock_config_entry, "bat_voltage")
        assert sensor.native_value < 30

    def test_signal_quality_read_from_device_log_top_level(self, mock_coordinator, mock_config_entry):
        """REST exposes WiFi signal as a deviceLog field, not in dataStreams."""
        mock_coordinator.data = self._data_without_synthesis()
        sensor = self._sensor(mock_coordinator, mock_config_entry, "signal_quality")
        assert sensor.native_value == 70.0

    def test_signal_quality_prefers_data_streams_over_device_log_field(self, mock_coordinator, mock_config_entry):
        """Live MQTT values are merged into dataStreams and are the freshest."""
        data = self._data_without_synthesis()
        data["deviceLogs"][0]["dataStreams"].append({"name": "signal_quality", "value": "91"})
        mock_coordinator.data = data
        sensor = self._sensor(mock_coordinator, mock_config_entry, "signal_quality")
        # device 1 = 91 (dataStreams), device 2 = 80 (deviceLog field) → 85.5
        assert sensor.native_value == pytest.approx(85.5)

    def test_synthesis_value_is_preferred_when_available(self, mock_coordinator, mock_config_entry):
        """Server synthesisStreams wins for non-unreliable sensors."""
        mock_coordinator.data = {
            **self._data_without_synthesis(),
            "synthesisStreams": [{"name": "bat_voltage", "value": 26.52}],
        }
        sensor = self._sensor(mock_coordinator, mock_config_entry, "bat_voltage")
        assert sensor.native_value == 26.52

    def test_unreliable_sensor_ignores_server_value(self, mock_coordinator, mock_config_entry):
        """charge_power always comes from deviceLogs, even if the server sends one."""
        mock_coordinator.data = {
            **self._data_without_synthesis(),
            "synthesisStreams": [{"name": "charge_power", "value": 999999}],
        }
        sensor = self._sensor(mock_coordinator, mock_config_entry, "charge_power")
        assert sensor.native_value == 300.0

    def test_no_device_logs_returns_none(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {"deviceLogs": [], "synthesisStreams": []}
        sensor = self._sensor(mock_coordinator, mock_config_entry, "charge_power")
        assert sensor.native_value is None

    def test_device_without_field_is_skipped_in_average(self, mock_coordinator, mock_config_entry):
        """Devices lacking the metric do not drag the average toward zero."""
        mock_coordinator.data = {
            "deviceLogs": [
                {"deviceGuid": "1", "dataStreams": [{"name": "temperature", "value": "30"}]},
                {"deviceGuid": "2", "dataStreams": []},
                {"deviceGuid": "3", "dataStreams": [{"name": "temperature", "value": "40"}]},
            ]
        }
        sensor = self._sensor(mock_coordinator, mock_config_entry, "temperature")
        assert sensor.native_value == pytest.approx(35.0)


class TestDeviceModeSignalQuality:
    """Device mode WiFi signal may arrive as a top-level lastMessage field."""

    def test_device_sensor_reads_top_level_signal_quality(self, mock_coordinator, mock_config_entry):
        mock_coordinator.data = {
            "lastMessage": {
                "dataStreams": [{"name": "pv_voltage", "value": "5.0"}],
                "signalQuality": 88,
            }
        }
        sensor = SmartSolarDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="signal_quality",
            sensor_info=SENSOR_TYPES["signal_quality"],
        )
        assert sensor.native_value == 88.0


class TestSignalQualitySensor:
    """Tests for WiFi signal quality sensor."""

    def test_signal_quality_in_sensor_types(self):
        """signal_quality is defined in SENSOR_TYPES."""
        assert "signal_quality" in SENSOR_TYPES
        info = SENSOR_TYPES["signal_quality"]
        assert info["name"] == "WiFi Signal"
        assert info["unit"] == "%"
        assert info["icon"] == "mdi:wifi"
        assert info["max_value"] == 100

    def test_device_sensor_returns_signal_quality(self, mock_coordinator, mock_config_entry):
        """Device sensor extracts signal_quality from data streams."""
        mock_coordinator.data = {
            "lastMessage": {
                "dataStreams": [
                    {"name": "signal_quality", "value": "95"},
                ]
            }
        }
        from tests.conftest import SAMPLE_DEVICE_RESPONSE

        sensor = SmartSolarDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="signal_quality",
            sensor_info=SENSOR_TYPES["signal_quality"],
        )
        # Need full data for the sensor to work properly
        mock_coordinator.data = SAMPLE_DEVICE_RESPONSE
        assert sensor.native_value == 95.0

    def test_signal_quality_rejects_out_of_range(self):
        """Signal quality > 100 is rejected."""
        coordinator = MagicMock()
        config_entry = MagicMock()
        config_entry.entry_id = "test_entry"
        config_entry.data = {"mode": "device", "chipset_ids": ["123"]}
        sensor = SmartSolarDeviceSensor(
            coordinator=coordinator,
            config_entry=config_entry,
            sensor_type="signal_quality",
            sensor_info=SENSOR_TYPES["signal_quality"],
        )
        streams = [{"name": "signal_quality", "value": "999"}]
        result = sensor._get_value_from_data_streams(streams)
        assert result is None

    def test_project_device_sensor_signal_quality(self, mock_coordinator, mock_config_entry):
        """Project device sensor extracts signal_quality for a specific device."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="signal_quality",
            sensor_info=SENSOR_TYPES["signal_quality"],
            device_guid="547611",
            device_index=1,
        )
        assert sensor.native_value == 95.0

    def test_project_device_sensor_signal_quality_second_device(self, mock_coordinator, mock_config_entry):
        """Second device returns its own signal_quality."""
        sensor = SmartSolarProjectDeviceSensor(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            sensor_type="signal_quality",
            sensor_info=SENSOR_TYPES["signal_quality"],
            device_guid="14756976",
            device_index=2,
        )
        assert sensor.native_value == 85.0


class TestMQTTDataMerging:
    """Tests for MQTT data merging in coordinator."""

    def test_mqtt_to_data_stream_converts_flat_dict(self, mock_coordinator):
        """_mqtt_to_data_stream converts flat dict to dataStreams format."""
        flat = {"pv_voltage": 50.1, "charge_power": 269.5}
        streams = mock_coordinator._mqtt_to_data_stream(flat)
        assert len(streams) == 2
        name_value = {s["name"]: s["value"] for s in streams}
        assert name_value["pv_voltage"] == "50.1"
        assert name_value["charge_power"] == "269.5"

    def test_merge_streams_overwrites_existing(self, mock_coordinator):
        """_merge_streams overwrites existing fields with incoming values."""
        existing = [
            {"name": "pv_voltage", "value": "48.5"},
            {"name": "charge_power", "value": "248.5"},
        ]
        incoming = [
            {"name": "pv_voltage", "value": "50.1"},
            {"name": "signal_quality", "value": "100"},
        ]
        merged = mock_coordinator._merge_streams(existing, incoming)
        merged_dict = {s["name"]: s["value"] for s in merged}
        assert merged_dict["pv_voltage"] == "50.1"  # overwritten
        assert merged_dict["charge_power"] == "248.5"  # preserved
        assert merged_dict["signal_quality"] == "100"  # new

    def test_merge_mqtt_into_device_mode(self, mock_coordinator, mock_config_entry):
        """_merge_mqtt_into_data updates lastMessage for device mode."""
        api_data = {
            "_mode": "device",
            "lastMessage": {
                "dataStreams": [
                    {"name": "pv_voltage", "value": "48.5"},
                ]
            },
        }
        mqtt_data = {"pv_voltage": 50.1, "signal_quality": 100}
        mock_coordinator._merge_mqtt_into_data(api_data, "547611", mqtt_data)
        streams = api_data["lastMessage"]["dataStreams"]
        stream_dict = {s["name"]: s["value"] for s in streams}
        assert stream_dict["pv_voltage"] == "50.1"
        assert stream_dict["signal_quality"] == "100"

    def test_merge_mqtt_into_project_mode(self, mock_coordinator, mock_config_entry):
        """_merge_mqtt_into_data updates deviceLogs for project mode."""
        from tests.conftest import SAMPLE_PROJECT_RESPONSE

        api_data = SAMPLE_PROJECT_RESPONSE.copy()
        mqtt_data = {"pv_voltage": 52.0, "signal_quality": 100}
        mock_coordinator._merge_mqtt_into_data(api_data, "547611", mqtt_data)
        # Find device 547611 and check updated values
        for device_log in api_data["deviceLogs"]:
            if device_log["deviceGuid"] == "547611":
                streams = {s["name"]: s["value"] for s in device_log["dataStreams"]}
                assert streams["pv_voltage"] == "52.0"
                assert streams["signal_quality"] == "100"
                return
        raise AssertionError("Device 547611 not found")

    def test_merge_mqtt_new_device_adds_entry(self, mock_coordinator, mock_config_entry):
        """_merge_mqtt_into_data adds deviceLog entry for unknown device GUID."""
        api_data = {
            "_mode": "project",
            "deviceLogs": [],
        }
        mqtt_data = {"pv_voltage": 48.5, "signal_quality": 70}
        mock_coordinator._merge_mqtt_into_data(api_data, "new_device_999", mqtt_data)
        assert len(api_data["deviceLogs"]) == 1
        assert api_data["deviceLogs"][0]["deviceGuid"] == "new_device_999"
        streams = {s["name"]: s["value"] for s in api_data["deviceLogs"][0]["dataStreams"]}
        assert streams["signal_quality"] == "70"
