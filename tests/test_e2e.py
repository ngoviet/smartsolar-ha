"""End-to-end tests for the SmartSolar MPPT integration.

These tests run the REAL integration entry points (``async_setup_entry`` /
``async_unload_entry`` / ``async_migrate_entry``) against a real
:class:`homeassistant.core.HomeAssistant` instance, using payloads recorded
from the live SmartSolar cloud API.

They complement the unit tests: instead of calling helper methods directly,
they assert on the entities, values and registry objects that a real config
entry actually produces.

``pytest-homeassistant-custom-component`` cannot be used here — it depends on
the POSIX-only ``fcntl`` module and fails to import on Windows — so a real
``HomeAssistant`` object is created and the handful of managers the
integration touches are attached manually.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.smartsolar_mppt import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.smartsolar_mppt.api import SmartSolarAPIError
from custom_components.smartsolar_mppt.const import DOMAIN, SENSOR_TYPES, STATS_SENSOR_TYPES
from custom_components.smartsolar_mppt.coordinator import SmartSolarDataUpdateCoordinator

# ── Real payloads recorded from api.smartsolar.io.vn (project 1072) ─────────
# Two MPPT Mạnh Quân chargers sharing one 24 V battery bus.
PROJECT_METRICS = {
    "command": "update_device_metrics",
    "deviceType": 2,
    "synthesisStreams": [
        {"name": "pv_voltage", "value": 23.13999939},
        {"name": "pv_current", "value": 0},
        {"name": "bat_voltage", "value": 26.6},
        {"name": "bat_current", "value": 0},
        {"name": "charge_power", "value": 0},
        {"name": "yield_today", "value": 0},
        {"name": "yield_total", "value": 1374.5169858},
        {"name": "temperature", "value": 33},
    ],
    # NOTE: the server lists 14756976 first — the integration must sort so the
    # PV1/PV2 labels stay pinned to a GUID.
    "deviceLogs": [
        {
            "deviceGuid": "14756976",
            "signalQuality": 80,
            "dataStreams": [
                {"name": "pv_voltage", "value": 23.13999939},
                {"name": "pv_current", "value": 0},
                {"name": "bat_voltage", "value": 26.44000053},
                {"name": "bat_current", "value": 0},
                {"name": "charge_power", "value": 0},
                {"name": "today_kwh", "value": 0},
                {"name": "total_kwh", "value": 986.4979858},
                {"name": "temperature", "value": 33},
                {"name": "status", "value": 2},
            ],
        },
        {
            "deviceGuid": "547611",
            "signalQuality": 60,
            "dataStreams": [
                {"name": "pv_voltage", "value": 5.26},
                {"name": "pv_current", "value": 0},
                {"name": "bat_voltage", "value": 26.6},
                {"name": "bat_current", "value": 0},
                {"name": "charge_power", "value": 0},
                {"name": "today_kwh", "value": 0},
                {"name": "total_kwh", "value": 388.019},
                {"name": "temperature", "value": 33},
                {"name": "status", "value": 2},
            ],
        },
    ],
}

DEVICE_STATUS = {
    "serverTime": 1790522088.6,
    "deviceGuid": "547611",
    "deviceType": 2,
    "isOnline": True,
    "lastMessage": {"dataStreams": [{"name": "pv_voltage", "value": 5.26}]},
    "mqttConnection": {
        "broker": "mqttx.smartsolar.io.vn",
        "port": 8084,
        "protocol": "wss",
        "username": "web_app",
        "password": "QWJjQDEzNTc5",  # base64 of "Abc@13579"
        "path": "/mqtt",
        "topic": "manhquan/device/mppt_charger/log/45a/547611",
    },
}


class FakeEntityPlatform:
    """Captures added entities, like HA's EntityComponent does."""

    def __init__(self) -> None:
        self.entities: list[Any] = []

    def add(self, entities: Any, update_before_add: bool = False) -> None:
        for entity in entities:
            self.entities.append(entity)
            # HA always assigns a platform; async_write_ha_state() is stubbed
            # because our fake hass has no entity-component bookkeeping.
            entity.async_write_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    def by_unique_id(self, unique_id: str) -> Any:
        for entity in self.entities:
            if entity.unique_id == unique_id:
                return entity
        raise AssertionError(f"{unique_id} not found. Present: {sorted(str(e.unique_id) for e in self.entities)}")


class FakeConfigEntries:
    """Drives the real platform setup/unload functions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.platforms: dict[str, FakeEntityPlatform] = {}
        self.reloaded: list[str] = []

    async def async_forward_entry_setups(self, entry: Any, platforms: list[Any]) -> bool:
        import custom_components.smartsolar_mppt.number as number_mod
        import custom_components.smartsolar_mppt.sensor as sensor_mod

        setup = {
            "sensor": sensor_mod.async_setup_entry,
            "number": number_mod.async_setup_entry,
        }
        for platform in platforms:
            name = getattr(platform, "value", str(platform))
            fake = FakeEntityPlatform()
            self.platforms[name] = fake
            await setup[name](self.hass, entry, fake.add)
        return True

    async def async_unload_platforms(self, entry: Any, platforms: list[Any]) -> bool:
        for platform in platforms:
            name = getattr(platform, "value", str(platform))
            self.platforms.pop(name, None)
        return True

    async def async_reload(self, entry_id: str) -> None:
        self.reloaded.append(entry_id)

    def async_update_entry(self, entry: Any, **kwargs: Any) -> None:
        # ConfigEntry blocks direct assignment of these attributes
        # (UPDATE_ENTRY_CONFIG_ENTRY_ATTRS); bypass it like Home Assistant does.
        for key in ("data", "version", "minor_version", "options", "title"):
            if key in kwargs:
                object.__setattr__(entry, key, kwargs[key])


class FakeDeviceRegistry:
    """Captures device registration."""

    def __init__(self) -> None:
        self.devices: list[dict[str, Any]] = []

    def async_get_or_create(self, **kwargs: Any) -> Any:
        self.devices.append(kwargs)
        return kwargs


class FakeServices:
    def __init__(self) -> None:
        self.registered: dict[tuple[str, str], Any] = {}

    def async_register(self, domain: str, service: str, func: Any, schema: Any = None) -> None:
        self.registered[(domain, service)] = func

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self.registered


@asynccontextmanager
async def running_hass():
    """Yield a started real HomeAssistant wired with the managers we need."""
    import tempfile

    hass = HomeAssistant(tempfile.mkdtemp(prefix="ha-smartsolar-e2e-"))
    await hass.async_start()
    frame.async_setup(hass)

    config_entries = FakeConfigEntries(hass)
    device_registry = FakeDeviceRegistry()
    services = FakeServices()
    hass.config_entries = config_entries  # type: ignore[assignment]
    hass.services = services  # type: ignore[assignment]

    import custom_components.smartsolar_mppt as integration

    integration.dr = MagicMock()  # type: ignore[assignment]
    integration.dr.async_get.return_value = device_registry

    try:
        yield hass, config_entries, device_registry, services
    finally:
        await hass.async_stop()


def make_entry(**overrides: Any) -> ConfigEntry:
    """Build a realistic project-mode config entry."""
    data = {
        "username": "vokupt",
        "password": "secret",
        "mode": "project",
        "device_type": 2,
        "project_id": "1072",
        "chipset_ids": [],
        "update_interval": 5,
    }
    data.update(overrides)
    return ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="SmartSolar MPPT (Project)",
        data=data,
        source=SOURCE_USER,
        entry_id="01K7DZBBS75AS1WBR48FVXVQZ1",
        unique_id="vokupt_project_2_1072",
        discovery_keys={},
        subentries_data=None,
        options={},
    )


async def setup_with_mocked_api(hass, entry, *, metrics=None, status=None, fail_first=False):
    """Run async_setup_entry with a stubbed API client, return the coordinator."""
    import custom_components.smartsolar_mppt as integration

    metrics = metrics if metrics is not None else deepcopy(PROJECT_METRICS)
    status = status if status is not None else deepcopy(DEVICE_STATUS)

    class FakeAPI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.token = "test-token"
            self.token_expiry = None
            self.calls = 0
            self.closed = False

        async def get_project_metrics(self, project_id: str) -> dict[str, Any]:
            self.calls += 1
            if fail_first and self.calls == 1:
                raise SmartSolarAPIError("boom", 500)
            return deepcopy(metrics)

        async def get_metrics(self, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            return deepcopy(metrics)

        async def get_device_status(self, device_guid: str) -> dict[str, Any]:
            return deepcopy(status)

        async def refresh_token_if_needed(self) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

    original = integration.SmartSolarAPI
    integration.SmartSolarAPI = FakeAPI  # type: ignore[assignment]
    try:
        assert await integration.async_setup_entry(hass, entry)
    finally:
        integration.SmartSolarAPI = original  # type: ignore[assignment]

    return hass.data[DOMAIN][entry.entry_id]


class TestProjectModeSetup:
    """End-to-end: a project config entry produces the expected entities."""

    @pytest.mark.asyncio
    async def test_setup_creates_synthesis_and_per_device_sensors(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            sensors = config_entries.platforms["sensor"].entities
            # 10 sensor types + 3 stats, for the project total and 2 devices
            expected_sensor_count = len(SENSOR_TYPES) * 3 + len(STATS_SENSOR_TYPES) * 2
            assert len(sensors) == expected_sensor_count

            unique_ids = {str(e.unique_id) for e in sensors}
            assert f"{entry.entry_id}_p_1072_pv_voltage" in unique_ids
            assert f"{entry.entry_id}_pd_547611_pv_voltage" in unique_ids
            assert f"{entry.entry_id}_pd_14756976_pv_voltage" in unique_ids
            assert coordinator is hass.data[DOMAIN][entry.entry_id]

    @pytest.mark.asyncio
    async def test_pv1_is_lowest_guid_even_when_server_lists_it_second(self):
        """PV1/PV2 labels are pinned to the sorted GUID order."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            platform = config_entries.platforms["sensor"]
            pv1 = platform.by_unique_id(f"{entry.entry_id}_pd_547611_pv_voltage")
            pv2 = platform.by_unique_id(f"{entry.entry_id}_pd_14756976_pv_voltage")

            assert pv1._attr_name == "PV1 PV Voltage"
            assert pv2._attr_name == "PV2 PV Voltage"
            assert pv1.native_value == pytest.approx(5.26)
            assert pv2.native_value == pytest.approx(23.13999939)

    @pytest.mark.asyncio
    async def test_total_battery_voltage_is_not_summed(self):
        """Two chargers on one 24 V bus must not report ~53 V."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            sensor = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_p_1072_bat_voltage")
            value = sensor.native_value
            assert 20 < value < 30, f"battery voltage looks summed: {value}"

    @pytest.mark.asyncio
    async def test_total_energy_matches_synthesis_stream(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            sensor = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_p_1072_total_kwh")
            assert sensor.native_value == pytest.approx(1374.5169858)

    @pytest.mark.asyncio
    async def test_per_device_wifi_signal_uses_device_log_field(self):
        """REST reports WiFi signal as a deviceLog field, not a dataStream."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            platform = config_entries.platforms["sensor"]
            assert platform.by_unique_id(f"{entry.entry_id}_pd_547611_signal_quality").native_value == 60.0
            assert platform.by_unique_id(f"{entry.entry_id}_pd_14756976_signal_quality").native_value == 80.0

    @pytest.mark.asyncio
    async def test_stats_sensors_report_numbers_not_unavailable(self):
        """Regression: the daily-stats sensors used to exist but never update."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            platform = config_entries.platforms["sensor"]
            for sensor_type in STATS_SENSOR_TYPES:
                sensor = platform.by_unique_id(f"{entry.entry_id}_pd_547611_{sensor_type}")
                assert sensor.native_value is not None
                assert isinstance(sensor.native_value, (int, float))
                assert sensor.available is True

    @pytest.mark.asyncio
    async def test_status_sensor_is_text(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            platform = config_entries.platforms["sensor"]
            assert platform.by_unique_id(f"{entry.entry_id}_pd_547611_status").native_value == "Idle (No Sun)"

    @pytest.mark.asyncio
    async def test_number_entity_created_for_entry(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            numbers = config_entries.platforms["number"].entities
            assert len(numbers) == 1
            assert numbers[0].unique_id == f"{entry.entry_id}_update_interval"
            assert numbers[0].native_value == 5.0
            assert numbers[0]._attr_native_min_value == 1
            assert numbers[0]._attr_native_max_value == 30

    @pytest.mark.asyncio
    async def test_device_is_registered_in_device_registry(self):
        async with running_hass() as (hass, _ce, devices, _services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)

            assert devices.devices, "no device registered"
            device = devices.devices[0]
            assert device["identifiers"] == {(DOMAIN, entry.entry_id)}
            assert device["name"] == "SmartSolar MPPT Project 1072"
            assert device["config_entry_id"] == entry.entry_id

    @pytest.mark.asyncio
    async def test_refresh_token_service_is_registered(self):
        async with running_hass() as (hass, _ce, _devices, services):
            entry = make_entry()
            await setup_with_mocked_api(hass, entry)
            assert services.has_service(DOMAIN, "refresh_token")

    @pytest.mark.asyncio
    async def test_unload_releases_coordinator_and_api(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            assert await async_unload_entry(hass, entry)

            assert entry.entry_id not in hass.data[DOMAIN]
            assert coordinator.api.closed is True
            assert config_entries.platforms == {}


class TestUnloadTeardown:
    """Unloading must cancel the coordinator's midnight and MQTT listeners."""

    @pytest.mark.asyncio
    async def test_unload_cancels_listeners_and_is_idempotent(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            assert coordinator._daily_tracker_unsub is not None

            coordinator._schedule_mqtt_notify()
            assert coordinator._mqtt_notify_unsub is not None

            assert await async_unload_entry(hass, entry)
            assert coordinator._daily_tracker_unsub is None
            assert coordinator._mqtt_notify_unsub is None

            assert await async_unload_entry(hass, entry) is True


class TestDeviceModeSetup:
    """End-to-end: a device-mode entry produces one set of sensors."""

    @pytest.mark.asyncio
    async def test_device_mode_sensor_count_and_values(self):
        device_response = {
            "isOnline": True,
            "lastMessage": {"dataStreams": list(PROJECT_METRICS["deviceLogs"][1]["dataStreams"])},
            "mqttConnection": deepcopy(DEVICE_STATUS["mqttConnection"]),
        }
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry(
                mode="device",
                chipset_ids=["547611"],
                project_id=None,
            )
            await setup_with_mocked_api(hass, entry, metrics=device_response)

            sensors = config_entries.platforms["sensor"].entities
            # 10 sensor types + 3 stats for the single charger
            assert len(sensors) == len(SENSOR_TYPES) + len(STATS_SENSOR_TYPES)
            unique_ids = {str(e.unique_id) for e in sensors}
            assert f"{entry.entry_id}_d_547611_pv_voltage" in unique_ids

            platform = config_entries.platforms["sensor"]
            assert platform.by_unique_id(f"{entry.entry_id}_d_547611_pv_voltage").native_value == pytest.approx(5.26)


class TestDegradedStartup:
    """The integration must survive a failing cloud API."""

    @pytest.mark.asyncio
    async def test_setup_succeeds_when_first_poll_fails(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry, fail_first=True)

            assert coordinator.last_update_success is False
            # Synthesis sensors still exist; per-device ones fall back to the
            # configured chipset_ids (empty here) so only the total is created.
            sensors = config_entries.platforms["sensor"].entities
            assert any(str(e.unique_id).endswith("_p_1072_pv_voltage") for e in sensors)

    @pytest.mark.asyncio
    async def test_setup_refuses_entry_without_credentials(self):
        async with running_hass() as (hass, _ce, _devices, _services):
            entry = make_entry(username="", password="")
            assert await async_setup_entry(hass, entry) is False

    @pytest.mark.asyncio
    async def test_coordinator_setup_does_not_use_contextvar(self):
        """The coordinator must pass config_entry explicitly (HA 2026 guard)."""
        async with running_hass() as (hass, _ce, _devices, _services):
            entry = make_entry()
            api = MagicMock()
            api.token = "t"
            coordinator = SmartSolarDataUpdateCoordinator(hass=hass, api=api, entry=entry)
            assert coordinator.config_entry is entry
            assert coordinator.update_interval == timedelta(seconds=5)


class TestMigration:
    """async_migrate_entry must be idempotent and refuse newer versions."""

    @pytest.mark.asyncio
    async def test_v1_1_is_migrated_to_1_2(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry(minor_version=2)
            # Simulate an old entry that still holds numeric chipset ids.
            config_entries.async_update_entry(
                entry, version=1, minor_version=1, data={**dict(entry.data), "chipset_ids": [547611, 14756976]}
            )

            assert await async_migrate_entry(hass, entry) is True
            assert entry.minor_version == 2
            assert entry.data["chipset_ids"] == ["547611", "14756976"]

    @pytest.mark.asyncio
    async def test_already_current_entry_is_untouched(self):
        async with running_hass() as (hass, _ce, _devices, _services):
            entry = make_entry()
            before = dict(entry.data)

            assert await async_migrate_entry(hass, entry) is True
            assert entry.minor_version == 2
            assert dict(entry.data) == before

    @pytest.mark.asyncio
    async def test_future_version_is_refused(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            config_entries.async_update_entry(entry, version=99)

            assert await async_migrate_entry(hass, entry) is False


class TestMqttLiveUpdates:
    """Live MQTT data must reach the entity values without a restart."""

    @pytest.mark.asyncio
    async def test_mqtt_update_changes_sensor_value(self):
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            platform = config_entries.platforms["sensor"]
            sensor = platform.by_unique_id(f"{entry.entry_id}_pd_547611_charge_power")
            assert sensor.native_value == pytest.approx(0.0)

            await coordinator.async_process_mqtt_data(
                "547611",
                {"charge_power": 348.25, "signal_quality": 91},
            )

            assert sensor.native_value == pytest.approx(348.25)
            assert platform.by_unique_id(f"{entry.entry_id}_pd_547611_signal_quality").native_value == 91.0

    @pytest.mark.asyncio
    async def test_foreign_mqtt_device_is_ignored(self):
        """The broker is shared with every SmartSolar customer."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            await coordinator.async_process_mqtt_data("99999999", {"pv_voltage": 99.9})

            guids = {str(log["deviceGuid"]) for log in coordinator.data["deviceLogs"]}
            assert guids == {"547611", "14756976"}

    @pytest.mark.asyncio
    async def test_garbage_mqtt_value_is_rejected_by_sensor(self):
        """Firmware overflow sentinels must not reach the entity state."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            sensor = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_pd_547611_pv_current")
            await coordinator.async_process_mqtt_data("547611", {"pv_current": 2147483.647})

            assert sensor.native_value is None

    @pytest.mark.asyncio
    async def test_legacy_firmware_device_keeps_rest_wifi_signal(self):
        """A device that never publishes signalQuality must not read 'unknown'.

        The 40A charger publishes the OLDER ``updateDeviceLog`` message, which
        carries no signalQuality field at all, so none of its MQTT messages put
        a WiFi value into dataStreams. The REST deviceLog field is then the only
        source and must be used as the fallback.
        """
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            metrics = deepcopy(PROJECT_METRICS)
            # The REST payload DOES carry signalQuality for this device.
            for log in metrics["deviceLogs"]:
                if log["deviceGuid"] == "14756976":
                    log["signalQuality"] = 80
            coordinator = await setup_with_mocked_api(hass, entry, metrics=metrics)

            # Exactly what the broker sends for 14756976: no signalQuality.
            await coordinator.async_process_mqtt_data(
                "14756976",
                {
                    "pv_voltage": 23.1,
                    "bat_voltage": 26.44,
                    "charge_power": 0.0,
                    "today_kwh": 0.0,
                    "total_kwh": 986.5,
                    "temperature": 33.0,
                    "status": 2,
                },
            )

            wifi = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_pd_14756976_signal_quality")
            assert wifi.native_value == 80.0  # from the REST deviceLog field

            # ...while the total WiFi signal still aggregates both devices.
            total_wifi = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_p_1072_signal_quality")
            assert total_wifi.native_value == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_device_without_signal_quality_reports_unknown(self):
        """When the cloud returns null the truthful state is 'unknown'.

        The live 40A charger is exactly this case: /Metric/ProjectMetrics
        returns signalQuality=null for it, so no value exists to publish.
        """
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            metrics = deepcopy(PROJECT_METRICS)
            for log in metrics["deviceLogs"]:
                if log["deviceGuid"] == "14756976":
                    log.pop("signalQuality", None)
            await setup_with_mocked_api(hass, entry, metrics=metrics)

            wifi = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_pd_14756976_signal_quality")
            assert wifi.native_value is None

            # The 60A charger still reports its value.
            pv1_wifi = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_pd_547611_signal_quality")
            assert pv1_wifi.native_value == 60.0

    @pytest.mark.asyncio
    async def test_live_mqtt_wifi_beats_stale_rest_value(self):
        """When MQTT does publish signalQuality it must win over REST."""
        async with running_hass() as (hass, config_entries, _devices, _services):
            entry = make_entry()
            coordinator = await setup_with_mocked_api(hass, entry)

            await coordinator.async_process_mqtt_data("547611", {"signal_quality": 91})

            wifi = config_entries.platforms["sensor"].by_unique_id(f"{entry.entry_id}_pd_547611_signal_quality")
            assert wifi.native_value == 91.0
