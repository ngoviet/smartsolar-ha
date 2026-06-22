"""Tests for coordinator.py."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.smartsolar_mppt.api import SmartSolarAPIError
from custom_components.smartsolar_mppt.coordinator import SmartSolarDataUpdateCoordinator
from tests.conftest import SAMPLE_DEVICE_RESPONSE, SAMPLE_PROJECT_RESPONSE


class TestCoordinatorInitialization:
    """Tests for coordinator init."""

    def test_default_update_interval(self, mock_hass, mock_api, mock_config_entry):
        """When update_interval is None, uses DEFAULT_UPDATE_INTERVAL."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        assert coordinator.update_interval == timedelta(seconds=5)

    def test_custom_update_interval(self, mock_hass, mock_api, mock_config_entry):
        """Custom update_interval is respected."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
            update_interval=timedelta(seconds=10),
        )
        assert coordinator.update_interval == timedelta(seconds=10)

    def test_discovered_devices_empty_on_init(self, mock_hass, mock_api, mock_config_entry):
        """New coordinator has empty discovered_devices set."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        assert coordinator.discovered_devices == set()

    def test_always_update_is_false(self, mock_hass, mock_api, mock_config_entry):
        """Coordinator should have always_update=False."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        assert coordinator.always_update is False


class TestAsyncUpdateData:
    """Tests for _async_update_data()."""

    @pytest.mark.asyncio
    async def test_device_mode_fetches_metrics(self, mock_hass, mock_api, mock_config_entry_device):
        """Device mode calls api.get_metrics and returns data."""
        mock_config_entry_device.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry_device,
        )
        result = await coordinator._async_update_data()
        mock_api.get_metrics.assert_called_once_with(
            device_type=2, chipset_ids=["547611"], mode="device",
        )
        assert result == SAMPLE_DEVICE_RESPONSE

    @pytest.mark.asyncio
    async def test_project_mode_fetches_project_metrics(self, mock_hass, mock_api, mock_config_entry):
        """Project mode with project_id calls api.get_project_metrics."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        result = await coordinator._async_update_data()
        mock_api.get_project_metrics.assert_called_once_with("1072")
        assert result == SAMPLE_PROJECT_RESPONSE

    @pytest.mark.asyncio
    async def test_missing_device_type_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """Missing device_type raises UpdateFailed."""
        mock_config_entry.data = {"mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="Missing device_type"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_missing_mode_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """Missing mode raises UpdateFailed."""
        mock_config_entry.data = {"device_type": 2, "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="Missing mode"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_api_error_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """SmartSolarAPIError is wrapped as UpdateFailed."""
        mock_api.get_metrics = AsyncMock(side_effect=SmartSolarAPIError("API error"))
        mock_config_entry.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="SmartSolar API error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_metadata_added_to_response(self, mock_hass, mock_api, mock_config_entry_device):
        """_async_update_data adds _mode, _device_type, _chipset_ids metadata."""
        mock_config_entry_device.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry_device,
        )
        result = await coordinator._async_update_data()
        assert result["_mode"] == "device"
        assert result["_device_type"] == 2
        assert result["_chipset_ids"] == ["547611"]

    @pytest.mark.asyncio
    async def test_device_discovery_tracks_new_guids(self, mock_hass, mock_api, mock_config_entry):
        """New device GUIDs are tracked in discovered_devices."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass, api=mock_api, entry=mock_config_entry,
        )
        await coordinator._async_update_data()
        assert "547611" in coordinator.discovered_devices
        assert "14756976" in coordinator.discovered_devices
