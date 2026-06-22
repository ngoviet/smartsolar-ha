"""Tests for const.py."""

from __future__ import annotations

from custom_components.smartsolar_mppt.const import (
    API_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MODE_DEVICE,
    MODE_PROJECT,
    SENSOR_TYPES,
    STATUS_MAPPING,
    build_device_info,
    get_sensor_info,
)


class TestSensorTypes:
    """Tests for SENSOR_TYPES dict."""

    def test_all_ten_sensor_types_exist(self):
        """Verify all 10 sensor types are defined."""
        expected = {
            "pv_voltage", "pv_current", "bat_voltage", "bat_current",
            "charge_power", "today_kwh", "total_kwh", "temperature",
            "signal_quality", "status",
        }
        assert set(SENSOR_TYPES.keys()) == expected

    def test_each_sensor_has_required_fields(self):
        """Each sensor type must have name, icon."""
        for sensor_type, info in SENSOR_TYPES.items():
            assert "name" in info, f"{sensor_type} missing 'name'"
            assert "icon" in info, f"{sensor_type} missing 'icon'"

    def test_numeric_sensors_have_units(self):
        """All sensors except 'status' should have a unit."""
        for sensor_type, info in SENSOR_TYPES.items():
            if sensor_type != "status":
                assert info.get("unit") is not None, f"{sensor_type} should have a unit"

    def test_max_value_on_relevant_sensors(self):
        """Sensors that can overflow should have max_value."""
        sensors_with_max = {"pv_voltage", "pv_current", "bat_voltage", "bat_current",
                            "charge_power", "today_kwh", "total_kwh", "temperature"}
        for st in sensors_with_max:
            assert "max_value" in SENSOR_TYPES[st], f"{st} missing max_value"

    def test_status_has_no_max_value(self):
        """Status sensor should NOT have max_value (it's a string code)."""
        assert "max_value" not in SENSOR_TYPES["status"]


class TestStatusMapping:
    """Tests for STATUS_MAPPING."""

    def test_all_expected_status_codes(self):
        """Verify all 4 status codes are present."""
        assert 0 in STATUS_MAPPING
        assert 1 in STATUS_MAPPING
        assert 2 in STATUS_MAPPING
        assert 3 in STATUS_MAPPING

    def test_status_values_are_english(self):
        """Status strings should be in English."""
        assert STATUS_MAPPING[0] == "Online"
        assert STATUS_MAPPING[1] == "Charging"
        assert "Idle" in STATUS_MAPPING[2]
        assert STATUS_MAPPING[3] == "Fault"


class TestGetSensorInfo:
    """Tests for get_sensor_info()."""

    def test_returns_correct_dict_for_known_type(self):
        """Valid sensor type returns its info dict."""
        info = get_sensor_info("pv_voltage")
        assert info["name"] == "PV Voltage"
        assert info["unit"] == "V"
        assert info["icon"] == "mdi:lightning-bolt"

    def test_returns_empty_dict_for_unknown_type(self):
        """Unknown sensor type returns empty dict."""
        info = get_sensor_info("nonexistent_sensor")
        assert info == {}

    def test_returns_empty_dict_for_none(self):
        """None input returns empty dict."""
        info = get_sensor_info(None)
        assert info == {}


class TestBuildDeviceInfo:
    """Tests for build_device_info()."""

    def test_project_mode_with_project_id(self):
        """Project mode with project_id returns project-named device."""
        info = build_device_info("entry123", mode="project", project_id="1072")
        assert info["name"] == "SmartSolar MPPT Project 1072"
        assert ("smartsolar_mppt", "entry123") in info["identifiers"]
        assert info["manufacturer"] == "SmartSolar"
        assert info["model"] == "MPPT Controller"

    def test_project_mode_without_project_id(self):
        """Project mode without project_id returns generic name."""
        info = build_device_info("entry123", mode="project", project_id=None)
        assert info["name"] == "SmartSolar MPPT Project"

    def test_device_mode(self):
        """Device mode returns device-named info."""
        info = build_device_info("entry123", mode="device")
        assert info["name"] == "SmartSolar MPPT Device"

    def test_none_mode_defaults_to_device_name(self):
        """None mode defaults to device name."""
        info = build_device_info("entry123")
        assert info["name"] == "SmartSolar MPPT Device"


class TestConstants:
    """Tests for module-level constants."""

    def test_domain(self):
        assert DOMAIN == "smartsolar_mppt"

    def test_api_base_url(self):
        assert API_BASE_URL == "https://api.smartsolar.io.vn"

    def test_mode_constants(self):
        assert MODE_DEVICE == "device"
        assert MODE_PROJECT == "project"

    def test_default_update_interval(self):
        assert DEFAULT_UPDATE_INTERVAL.total_seconds() == 5

    def test_update_interval_bounds(self):
        assert MIN_UPDATE_INTERVAL == 1
        assert MAX_UPDATE_INTERVAL == 30
        assert MIN_UPDATE_INTERVAL < MAX_UPDATE_INTERVAL
