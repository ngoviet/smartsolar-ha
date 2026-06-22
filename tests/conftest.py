"""Test fixtures for SmartSolar MPPT integration tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_frame_helper():
    """Patch Home Assistant frame helper to allow creating coordinators in tests."""
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        yield

# Sample API responses
SAMPLE_DEVICE_RESPONSE = {
    "lastMessage": {
        "dataStreams": [
            {"name": "pv_voltage", "value": "48.5"},
            {"name": "pv_current", "value": "5.2"},
            {"name": "bat_voltage", "value": "24.1"},
            {"name": "bat_current", "value": "10.3"},
            {"name": "charge_power", "value": "248.5"},
            {"name": "today_kwh", "value": "2.5"},
            {"name": "total_kwh", "value": "1250.0"},
            {"name": "temperature", "value": "35.0"},
            {"name": "signal_quality", "value": "95"},
            {"name": "status", "value": "1"},
        ]
    }
}

SAMPLE_PROJECT_RESPONSE = {
    "synthesisStreams": [
        {"name": "pv_voltage", "value": "48.5"},
        {"name": "pv_current", "value": "15.6"},
        {"name": "bat_voltage", "value": "24.1"},
        {"name": "bat_current", "value": "30.9"},
        {"name": "charge_power", "value": "745.5"},
        {"name": "yield_today", "value": "7.5"},
        {"name": "yield_total", "value": "3750.0"},
        {"name": "temperature", "value": "35.0"},
        {"name": "signal_quality", "value": "90.0"},
        {"name": "status", "value": "1.0"},
    ],
    "deviceLogs": [
        {
            "deviceGuid": "547611",
            "dataStreams": [
                {"name": "pv_voltage", "value": "48.5"},
                {"name": "pv_current", "value": "5.2"},
                {"name": "bat_voltage", "value": "24.1"},
                {"name": "bat_current", "value": "10.3"},
                {"name": "charge_power", "value": "248.5"},
                {"name": "today_kwh", "value": "2.5"},
                {"name": "total_kwh", "value": "1250.0"},
                {"name": "temperature", "value": "35.0"},
                {"name": "signal_quality", "value": "95"},
                {"name": "status", "value": "1"},
            ]
        },
        {
            "deviceGuid": "14756976",
            "dataStreams": [
                {"name": "pv_voltage", "value": "48.5"},
                {"name": "pv_current", "value": "10.4"},
                {"name": "bat_voltage", "value": "24.1"},
                {"name": "bat_current", "value": "20.6"},
                {"name": "charge_power", "value": "497.0"},
                {"name": "today_kwh", "value": "5.0"},
                {"name": "total_kwh", "value": "2500.0"},
                {"name": "temperature", "value": "35.0"},
                {"name": "signal_quality", "value": "85"},
                {"name": "status", "value": "1"},
            ]
        }
    ],
    "_mode": "project",
    "_device_type": 2,
    "_chipset_ids": ["547611", "14756976"],
}

# Sample MQTT payload as received from the broker
SAMPLE_MQTT_PAYLOAD = {
    "pv_voltage": 50.1,
    "pv_current": 5.8,
    "bat_voltage": 24.5,
    "bat_current": 11.0,
    "charging_power": 269.5,
    "yield_today": 3.2,
    "yield_total": 1260.0,
    "temperature": 36.0,
    "signal_quality": 100,
    "status": 1,
}

# Expected normalized data after MQTT_FIELD_MAPPING
EXPECTED_MQTT_NORMALIZED = {
    "pv_voltage": 50.1,
    "pv_current": 5.8,
    "bat_voltage": 24.5,
    "bat_current": 11.0,
    "charge_power": 269.5,
    "today_kwh": 3.2,
    "total_kwh": 1260.0,
    "temperature": 36.0,
    "signal_quality": 100,
    "status": 1,
}


@pytest.fixture
def sample_device_response():
    """Return a sample device mode API response."""
    return SAMPLE_DEVICE_RESPONSE.copy()


@pytest.fixture
def sample_project_response():
    """Return a sample project mode API response."""
    return SAMPLE_PROJECT_RESPONSE.copy()


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.services = MagicMock()
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock ConfigEntry for project mode."""
    entry = MagicMock()
    entry.entry_id = "test_entry_12345"
    entry.domain = "smartsolar_mppt"
    entry.title = "SmartSolar MPPT (Project)"
    entry.version = 1
    entry.minor_version = 1
    entry.data = {
        "username": "test_user",
        "password": "test_pass",
        "mode": "project",
        "device_type": 2,
        "project_id": "1072",
        "chipset_ids": ["547611", "14756976"],
    }
    return entry


@pytest.fixture
def mock_config_entry_device():
    """Create a mock ConfigEntry for device mode."""
    entry = MagicMock()
    entry.entry_id = "test_entry_device"
    entry.domain = "smartsolar_mppt"
    entry.title = "SmartSolar MPPT (Device)"
    entry.version = 1
    entry.minor_version = 1
    entry.data = {
        "username": "test_user",
        "password": "test_pass",
        "mode": "device",
        "device_type": 2,
        "chipset_ids": ["547611"],
    }
    return entry


@pytest.fixture
def mock_api():
    """Create a mock SmartSolarAPI."""
    api = MagicMock()
    api.token = "test_token"
    api.token_expiry = None
    api.login = AsyncMock(return_value={"token": "test_token", "expiration": ""})
    api.refresh_token_if_needed = AsyncMock()
    api.get_metrics = AsyncMock(return_value=SAMPLE_DEVICE_RESPONSE)
    api.get_project_metrics = AsyncMock(return_value=SAMPLE_PROJECT_RESPONSE)
    api.test_connection = AsyncMock(return_value=True)
    api.close = AsyncMock()
    return api


@pytest.fixture
def mock_coordinator(mock_hass, mock_api, mock_config_entry):
    """Create a mock SmartSolarDataUpdateCoordinator."""
    from custom_components.smartsolar_mppt.coordinator import SmartSolarDataUpdateCoordinator

    coordinator = SmartSolarDataUpdateCoordinator(
        hass=mock_hass,
        api=mock_api,
        entry=mock_config_entry,
        update_interval=timedelta(seconds=5),
    )
    # Manually set data to avoid needing async_update
    coordinator.data = SAMPLE_PROJECT_RESPONSE.copy()
    return coordinator
