"""Tests for coordinator.py."""

from __future__ import annotations

from datetime import datetime, timedelta
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
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        assert coordinator.update_interval == timedelta(seconds=5)

    def test_custom_update_interval(self, mock_hass, mock_api, mock_config_entry):
        """Custom update_interval is respected."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
            update_interval=timedelta(seconds=10),
        )
        assert coordinator.update_interval == timedelta(seconds=10)

    def test_discovered_devices_empty_on_init(self, mock_hass, mock_api, mock_config_entry):
        """New coordinator has empty discovered_devices set."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        assert coordinator.discovered_devices == set()

    def test_always_update_is_false(self, mock_hass, mock_api, mock_config_entry):
        """Coordinator should have always_update=False."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        assert coordinator.always_update is False


class TestAsyncUpdateData:
    """Tests for _async_update_data()."""

    @pytest.mark.asyncio
    async def test_device_mode_fetches_metrics(self, mock_hass, mock_api, mock_config_entry_device):
        """Device mode calls api.get_metrics and returns data."""
        mock_config_entry_device.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry_device,
        )
        result = await coordinator._async_update_data()
        mock_api.get_metrics.assert_called_once_with(
            device_type=2,
            chipset_ids=["547611"],
            mode="device",
        )
        assert result == SAMPLE_DEVICE_RESPONSE

    @pytest.mark.asyncio
    async def test_project_mode_fetches_project_metrics(self, mock_hass, mock_api, mock_config_entry):
        """Project mode with project_id calls api.get_project_metrics."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        result = await coordinator._async_update_data()
        mock_api.get_project_metrics.assert_called_once_with("1072")
        assert result == SAMPLE_PROJECT_RESPONSE

    @pytest.mark.asyncio
    async def test_missing_device_type_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """Missing device_type raises UpdateFailed."""
        mock_config_entry.data = {"mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="Missing device_type"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_missing_mode_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """Missing mode raises UpdateFailed."""
        mock_config_entry.data = {"device_type": 2, "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="Missing mode"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_api_error_raises_update_failed(self, mock_hass, mock_api, mock_config_entry):
        """SmartSolarAPIError is wrapped as UpdateFailed."""
        mock_api.get_metrics = AsyncMock(side_effect=SmartSolarAPIError("API error"))
        mock_config_entry.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        with pytest.raises(UpdateFailed, match="SmartSolar API error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_metadata_added_to_response(self, mock_hass, mock_api, mock_config_entry_device):
        """_async_update_data adds _mode, _device_type, _chipset_ids metadata."""
        mock_config_entry_device.data = {"device_type": 2, "mode": "device", "chipset_ids": ["547611"]}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry_device,
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
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        await coordinator._async_update_data()
        assert "547611" in coordinator.discovered_devices
        assert "14756976" in coordinator.discovered_devices


class TestDeviceGuidOrdering:
    """PV1/PV2 labels are derived from device order, so it must be stable."""

    def test_guids_are_sorted_numerically(self):
        """Order does not depend on the order the server returns deviceLogs."""
        logs = [
            {"deviceGuid": "14756976"},
            {"deviceGuid": "547611"},
        ]
        assert SmartSolarDataUpdateCoordinator.device_guids({"deviceLogs": logs}) == [
            "547611",
            "14756976",
        ]

    def test_guids_sorted_same_regardless_of_input_order(self):
        a = [{"deviceGuid": "999"}, {"deviceGuid": "100"}]
        b = [{"deviceGuid": "100"}, {"deviceGuid": "999"}]
        assert SmartSolarDataUpdateCoordinator.device_guids(
            {"deviceLogs": a}
        ) == SmartSolarDataUpdateCoordinator.device_guids({"deviceLogs": b})

    def test_non_numeric_guids_fall_back_to_string_sort(self):
        logs = [{"deviceGuid": "b"}, {"deviceGuid": "a"}, {"deviceGuid": "10"}]
        assert SmartSolarDataUpdateCoordinator.device_guids({"deviceLogs": logs}) == [
            "10",
            "a",
            "b",
        ]

    def test_malformed_entries_are_ignored(self):
        logs = [{"deviceGuid": "1"}, {"no_guid": True}, "junk", None, {"deviceGuid": ""}]
        assert SmartSolarDataUpdateCoordinator.device_guids({"deviceLogs": logs}) == ["1"]

    def test_missing_device_logs_returns_empty(self):
        assert SmartSolarDataUpdateCoordinator.device_guids({}) == []
        assert SmartSolarDataUpdateCoordinator.device_guids({"deviceLogs": None}) == []


class TestMqttRobustness:
    """MQTT payloads come from third-party firmware and must never break a poll."""

    @pytest.mark.asyncio
    async def test_foreign_device_is_not_merged(self, mock_hass, mock_api, mock_config_entry):
        """A GUID outside this entry must not be injected into deviceLogs."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator.data = {
            "_mode": "project",
            "deviceLogs": [{"deviceGuid": "547611", "dataStreams": []}],
        }
        coordinator.discovered_devices = {"547611"}

        await coordinator.async_process_mqtt_data("999999", {"pv_voltage": 12.0})

        assert len(coordinator.data["deviceLogs"]) == 1
        guids = [str(log["deviceGuid"]) for log in coordinator.data["deviceLogs"]]
        assert guids == ["547611"]

    @pytest.mark.asyncio
    async def test_tracked_device_is_merged(self, mock_hass, mock_api, mock_config_entry):
        """A GUID from this entry is merged into its deviceLog."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator.data = {
            "_mode": "project",
            "deviceLogs": [{"deviceGuid": "547611", "dataStreams": [{"name": "pv_voltage", "value": "5.0"}]}],
        }
        coordinator.discovered_devices = {"547611"}

        await coordinator.async_process_mqtt_data("547611", {"pv_voltage": 12.0})

        streams = {s["name"]: s["value"] for s in coordinator.data["deviceLogs"][0]["dataStreams"]}
        assert streams["pv_voltage"] == "12.0"

    @pytest.mark.asyncio
    async def test_chipset_device_tracked_before_first_poll(self, mock_hass, mock_api, mock_config_entry_device):
        """Device mode tracks its chipset id even before discovery runs."""
        mock_config_entry_device.data = {
            "device_type": 2,
            "mode": "device",
            "chipset_ids": ["547611"],
        }
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry_device,
        )
        coordinator.data = {"_mode": "device", "lastMessage": {"dataStreams": []}}

        await coordinator.async_process_mqtt_data("547611", {"pv_voltage": 7.5})

        streams = {s["name"]: s["value"] for s in coordinator.data["lastMessage"]["dataStreams"]}
        assert streams["pv_voltage"] == "7.5"

    def test_merge_streams_skips_malformed_entries(self, mock_hass, mock_api, mock_config_entry):
        """Streams without a name, or that are not dicts, are skipped."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        existing = [
            {"name": "pv_voltage", "value": "5.0"},
            "junk",
            {"value": "no-name"},
            None,
        ]
        incoming = [{"name": "pv_current", "value": "1.0"}, {"no_name": True}]

        merged = coordinator._merge_streams(existing, incoming)
        names = {s["name"] for s in merged}
        assert names == {"pv_voltage", "pv_current"}

    @pytest.mark.asyncio
    async def test_merge_does_not_raise_on_malformed_device_logs(self, mock_hass, mock_api, mock_config_entry):
        """Malformed deviceLogs entries do not break the merge."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator.data = {"_mode": "project", "deviceLogs": ["junk", None]}
        coordinator.discovered_devices = {"547611"}

        await coordinator.async_process_mqtt_data("547611", {"pv_voltage": 1.0})

        assert coordinator.data["deviceLogs"][0] == "junk"

    def test_merge_streams_accepts_none_arguments(self, mock_hass, mock_api, mock_config_entry):
        """Explicit null dataStreams from the API must not abort a poll."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        assert coordinator._merge_streams(None, None) == []
        merged = coordinator._merge_streams(None, [{"name": "pv_voltage", "value": "12.0"}])
        assert {s["name"] for s in merged} == {"pv_voltage"}

    @pytest.mark.asyncio
    async def test_null_data_streams_does_not_abort_poll(self, mock_hass, mock_api, mock_config_entry):
        """A deviceLog with ``dataStreams: null`` still accepts MQTT data."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator.data = {
            "_mode": "project",
            "deviceLogs": [{"deviceGuid": "547611", "dataStreams": None}],
        }
        coordinator.discovered_devices = {"547611"}

        await coordinator.async_process_mqtt_data("547611", {"pv_voltage": 12.0})

        streams = {s["name"]: s["value"] for s in coordinator.data["deviceLogs"][0]["dataStreams"]}
        assert streams["pv_voltage"] == "12.0"

    @pytest.mark.asyncio
    async def test_foreign_device_keeps_caches_clean(self, mock_hass, mock_api, mock_config_entry):
        """A foreign GUID must not populate the MQTT cache or daily-stats map."""
        mock_config_entry.data = {"device_type": 2, "mode": "project", "project_id": "1072"}
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator.data = {
            "_mode": "project",
            "deviceLogs": [{"deviceGuid": "547611", "dataStreams": []}],
        }
        coordinator.discovered_devices = {"547611"}

        await coordinator.async_process_mqtt_data("999999", {"pv_voltage": 12.0, "charge_power": 100.0})

        assert "999999" not in coordinator._mqtt_data
        assert "999999" not in coordinator._daily_stats
        assert coordinator.mqtt_cached_device_count == 0


class TestDailyStats:
    """Tests for the daily peak/average/production-hour tracking."""

    def test_ignores_garbage_charge_power(self, mock_hass, mock_api, mock_config_entry):
        """Firmware overflow sentinels must not poison the statistics."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator._update_daily_stats("547611", 2147483.647)
        coordinator._update_daily_stats("547611", -5)

        stats = coordinator.get_daily_stats("547611")
        assert stats["peak_power"] == 0.0
        assert stats["avg_power"] == 0.0

    def test_tracks_peak_and_average(self, mock_hass, mock_api, mock_config_entry):
        """Peak is the max, average is the mean of accepted readings."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        for value in (100.0, 300.0, 200.0):
            coordinator._update_daily_stats("547611", value)

        stats = coordinator.get_daily_stats("547611")
        assert stats["peak_power"] == 300.0
        assert stats["avg_power"] == 200.0

    def test_production_hours_counts_distinct_minutes(self, mock_hass, mock_api, mock_config_entry):
        """Production hours counts unique minutes above the 5 W threshold."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        base = datetime(2026, 9, 27, 10, 0)
        coordinator._update_daily_stats("547611", 100.0, base)
        coordinator._update_daily_stats("547611", 120.0, base)  # same minute
        coordinator._update_daily_stats("547611", 120.0, base.replace(minute=1))
        coordinator._update_daily_stats("547611", 1.0, base.replace(minute=2))  # below threshold

        stats = coordinator.get_daily_stats("547611")
        assert stats["production_hours"] == pytest.approx(2 / 60, abs=0.01)

    def test_midnight_reset_clears_stats(self, mock_hass, mock_api, mock_config_entry):
        """The midnight listener wipes the per-day state."""
        coordinator = SmartSolarDataUpdateCoordinator(
            hass=mock_hass,
            api=mock_api,
            entry=mock_config_entry,
        )
        coordinator._update_daily_stats("547611", 250.0)
        coordinator._reset_daily_stats(datetime(2026, 9, 28))
        assert coordinator.get_daily_stats("547611")["peak_power"] == 0.0
