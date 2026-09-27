"""Tests for diagnostics.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.smartsolar_mppt.const import DOMAIN
from custom_components.smartsolar_mppt.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _make_entry(entry_id: str = "entry-1"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.title = "SmartSolar MPPT (Project)"
    entry.version = 1
    entry.minor_version = 2
    entry.data = {
        "username": "vokupt",
        "password": "super-secret",
        "mode": "project",
        "project_id": "1072",
    }
    return entry


def _make_coordinator(*, mqtt=None, data=None):
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(seconds=5)
    coordinator.discovered_devices = {"547611", "14756976"}
    coordinator.last_update_success = True
    coordinator.mqtt_client = mqtt
    coordinator.mqtt_cached_device_count = 2
    coordinator.api.token = "abc"
    coordinator.api.token_expiry = datetime(2026, 10, 27, tzinfo=UTC)
    coordinator.data = data
    return coordinator


class TestDiagnosticsRedaction:
    """Diagnostics are downloadable, so secrets must never leak."""

    @pytest.mark.asyncio
    async def test_password_is_redacted(self):
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator()}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["entry"]["data"]["password"] == "***"
        assert result["entry"]["data"]["username"] == "vokupt"
        assert "super-secret" not in str(result)

    @pytest.mark.asyncio
    async def test_token_is_not_exposed(self):
        """Only presence/expiry of the API token is reported."""
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator()}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["api"]["has_token"] is True
        assert "abc" not in str(result)
        assert result["api"]["token_expiry"] == "2026-10-27T00:00:00+00:00"


class TestDiagnosticsContent:
    @pytest.mark.asyncio
    async def test_reports_coordinator_state(self):
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator()}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["coordinator"]["update_interval_seconds"] == 5.0
        assert result["coordinator"]["discovered_devices"] == ["14756976", "547611"]
        assert result["coordinator"]["last_update_success"] is True

    @pytest.mark.asyncio
    async def test_reports_mqtt_off_when_no_client(self):
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator(mqtt=None)}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["mqtt"]["enabled"] is False
        assert result["mqtt"]["connected"] is False

    @pytest.mark.asyncio
    async def test_reports_mqtt_on_when_client_present(self):
        entry = _make_entry()
        mqtt = MagicMock()
        mqtt.connected = True
        hass = MagicMock()
        hass.data = {DOMAIN: {entry.entry_id: _make_coordinator(mqtt=mqtt)}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["mqtt"]["enabled"] is True
        assert result["mqtt"]["connected"] is True

    @pytest.mark.asyncio
    async def test_summarises_api_response(self):
        entry = _make_entry()
        hass = MagicMock()
        coordinator = _make_coordinator(
            data={
                "_mode": "project",
                "_device_type": 2,
                "_chipset_ids": ["547611"],
                "synthesisStreams": [{"name": "pv_voltage", "value": 23.1}],
                "deviceLogs": [{"deviceGuid": "547611"}, {"deviceGuid": "14756976"}],
            }
        )
        hass.data = {DOMAIN: {entry.entry_id: coordinator}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["response"] == {
            "mode": "project",
            "device_type": 2,
            "chipset_ids": ["547611"],
            "has_synthesis_streams": True,
            "device_count": 2,
            "sensor_count": 1,
        }

    @pytest.mark.asyncio
    async def test_missing_coordinator_returns_error(self):
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {DOMAIN: {}}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result == {"error": "No coordinator found"}

    @pytest.mark.asyncio
    async def test_missing_domain_data_returns_error(self):
        """A domain removed from hass.data must not raise."""
        entry = _make_entry()
        hass = MagicMock()
        hass.data = {}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result == {"error": "No coordinator found"}
