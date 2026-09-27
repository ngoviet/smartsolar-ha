"""Tests for MQTT client and coordinator MQTT integration."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smartsolar_ha.const import MQTT_FIELD_MAPPING
from custom_components.smartsolar_ha.mqtt_client import (
    HAS_AIOMQTT,
    SmartSolarMQTTClient,
)


class TestMQTTFieldMapping:
    """Tests for MQTT → REST field name mapping."""

    def test_charging_power_maps_to_charge_power(self):
        """MQTT 'charging_power' → REST 'charge_power'."""
        assert MQTT_FIELD_MAPPING["charging_power"] == "charge_power"

    def test_yield_today_maps_to_today_kwh(self):
        """MQTT 'yield_today' → REST 'today_kwh'."""
        assert MQTT_FIELD_MAPPING["yield_today"] == "today_kwh"

    def test_yield_total_maps_to_total_kwh(self):
        """MQTT 'yield_total' → REST 'total_kwh'."""
        assert MQTT_FIELD_MAPPING["yield_total"] == "total_kwh"

    def test_normalize_mqtt_fields(self):
        """Full normalization maps all known fields correctly."""
        from tests.conftest import EXPECTED_MQTT_NORMALIZED, SAMPLE_MQTT_PAYLOAD

        normalized = {}
        for key, value in SAMPLE_MQTT_PAYLOAD.items():
            mapped_key = MQTT_FIELD_MAPPING.get(key, key)
            normalized[mapped_key] = value

        assert normalized == EXPECTED_MQTT_NORMALIZED
        assert normalized["charge_power"] == 269.5  # was 'charging_power'
        assert normalized["today_kwh"] == 3.2  # was 'yield_today'
        assert normalized["total_kwh"] == 1260.0  # was 'yield_total'
        assert normalized["signal_quality"] == 100  # unchanged

    def test_unknown_fields_passthrough(self):
        """Unknown MQTT fields pass through unchanged."""
        result = {}
        payload = {"unknown_field": 42, "pv_voltage": 48.5}
        for key, value in payload.items():
            mapped_key = MQTT_FIELD_MAPPING.get(key, key)
            result[mapped_key] = value
        assert result["unknown_field"] == 42
        assert result["pv_voltage"] == 48.5


class TestMQTTClientInit:
    """Tests for SmartSolarMQTTClient initialization."""

    def test_client_creates_with_device_guids(self):
        """Client stores device GUIDs and callback."""
        callback = AsyncMock()
        client = SmartSolarMQTTClient(
            device_guids=["000372", "547611"],
            on_data_callback=callback,
        )
        assert client._device_guids == ["000372", "547611"]
        assert client._on_data is callback
        assert client.connected is False
        assert not client.is_running()

    def test_client_topic_generation(self):
        """Topic uses wildcard for device model."""
        client = SmartSolarMQTTClient(
            device_guids=["000372"],
            on_data_callback=AsyncMock(),
        )
        topic = client._make_topic("000372")
        assert topic == "manhquan/device/mppt_charger/log/+/000372"
        assert "000372" in topic

    @pytest.mark.asyncio
    async def test_start_without_aiomqtt_does_nothing(self):
        """When aiomqtt is not installed, start() does nothing."""
        if HAS_AIOMQTT:
            pytest.skip("aiomqtt is installed — skipping fallback test")
        client = SmartSolarMQTTClient(
            device_guids=["000372"],
            on_data_callback=AsyncMock(),
        )
        await client.start()
        assert not client.is_running()

    @pytest.mark.asyncio
    async def test_start_with_empty_guids_does_nothing(self):
        """Empty device list skips MQTT start."""
        client = SmartSolarMQTTClient(
            device_guids=[],
            on_data_callback=AsyncMock(),
        )
        await client.start()
        assert not client.is_running()

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_safe(self):
        """Stopping a client that was never started is safe."""
        client = SmartSolarMQTTClient(
            device_guids=["000372"],
            on_data_callback=AsyncMock(),
        )
        await client.stop()  # Should not raise
        assert not client.is_running()

    def test_available_property(self):
        """available reflects whether aiomqtt is installed."""
        client = SmartSolarMQTTClient(
            device_guids=[],
            on_data_callback=AsyncMock(),
        )
        assert client.available == HAS_AIOMQTT


class TestMQTTMessageParsing:
    """Tests for MQTT message handling."""

    def _make_client(self):
        """Create client with mock callback."""
        return SmartSolarMQTTClient(
            device_guids=["000372", "547611"],
            on_data_callback=AsyncMock(),
        )

    def _make_mock_message(self, topic: str, payload: dict):
        """Create a mock aiomqtt Message."""
        import json

        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode("utf-8")
        return msg

    @pytest.mark.asyncio
    async def test_handle_valid_message(self):
        """Valid JSON message is parsed and forwarded."""
        client = self._make_client()
        from tests.conftest import SAMPLE_MQTT_PAYLOAD

        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/000372",
            SAMPLE_MQTT_PAYLOAD,
        )

        await client._handle_message(msg)

        # Callback should be called with device_guid + normalized data
        client._on_data.assert_called_once()
        call_args = client._on_data.call_args
        assert call_args[0][0] == "000372"  # device_guid from topic
        normalized = call_args[0][1]
        assert normalized["charge_power"] == 269.5  # was 'charging_power'
        assert normalized["today_kwh"] == 3.2  # was 'yield_today'

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self):
        """Invalid JSON is silently skipped."""
        client = self._make_client()
        msg = MagicMock()
        msg.topic = "manhquan/device/mppt_charger/log/45a/000372"
        msg.payload = b"not json"

        await client._handle_message(msg)
        client._on_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_non_dict_payload(self):
        """Non-dict payload (e.g., array or string) is skipped."""
        import json

        client = self._make_client()
        msg = MagicMock()
        msg.topic = "manhquan/device/mppt_charger/log/45a/000372"
        msg.payload = json.dumps([1, 2, 3]).encode("utf-8")

        await client._handle_message(msg)
        client._on_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_topic_without_trailing_slash(self):
        """Topic without trailing slash still extracts GUID correctly."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {"pv_voltage": 50.0},
        )

        await client._handle_message(msg)
        client._on_data.assert_called_once()
        assert client._on_data.call_args[0][0] == "547611"

    @pytest.mark.asyncio
    async def test_trailing_slash_on_topic_is_tolerated(self):
        """A trailing slash must not produce an empty GUID."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611/",
            {"pv_voltage": 50.0},
        )

        await client._handle_message(msg)
        assert client._on_data.call_args[0][0] == "547611"

    @pytest.mark.asyncio
    async def test_data_streams_format_extracts_signal_quality(self):
        """The live payload carries signalQuality at the TOP level.

        It is not one of the dataStreams, so it has to be picked up separately
        or the WiFi sensor stays unknown forever.
        """
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {
                "command": "update_device_metrics",
                "deviceGuid": "547611",
                "signalQuality": 56,
                "messagesCounter": 1064144,
                "dataStreams": [
                    {"name": "pv_voltage", "value": 4.24},
                    {"name": "bat_voltage", "value": 26.26},
                    {"name": "charge_power", "value": 0},
                ],
            },
        )

        await client._handle_message(msg)

        normalized = client._on_data.call_args[0][1]
        assert normalized["signal_quality"] == 56
        assert normalized["pv_voltage"] == 4.24
        assert normalized["bat_voltage"] == 26.26

    @pytest.mark.asyncio
    async def test_data_streams_format_ignores_bookkeeping_fields(self):
        """command/deviceGuid/messagesCounter are not sensors."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {
                "command": "updateDeviceLog",
                "deviceGuid": "547611",
                "messagesCounter": 12,
                "dataStreams": [{"name": "temperature", "value": 29}],
            },
        )

        await client._handle_message(msg)

        assert client._on_data.call_args[0][1] == {"temperature": 29}

    @pytest.mark.asyncio
    async def test_update_device_log_format_is_parsed(self):
        """Older firmware sends updateDeviceLog with unit/stream fields."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/3272656",
            {
                "command": "updateDeviceLog",
                "deviceGuid": "3272656",
                "dataStreams": [
                    {"stream": 0, "name": "pv_voltage", "value": 4.760000229, "unit": "Volt"},
                    {"stream": 5, "name": "today_kwh", "value": 1.190999985, "unit": "kWh"},
                    {"stream": 8, "name": "status", "value": 2, "unit": "None"},
                ],
            },
        )

        await client._handle_message(msg)

        normalized = client._on_data.call_args[0][1]
        assert normalized["pv_voltage"] == pytest.approx(4.760000229)
        assert normalized["today_kwh"] == pytest.approx(1.190999985)
        assert normalized["status"] == 2

    @pytest.mark.asyncio
    async def test_data_stream_entries_without_name_are_skipped(self):
        """A malformed stream element must not abort the whole payload."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {
                "dataStreams": [
                    {"name": "pv_voltage", "value": 5.0},
                    {"stream": 1, "value": 1.0},  # missing name
                    {"name": "bat_voltage", "value": None},
                    "junk",
                ]
            },
        )

        await client._handle_message(msg)

        assert client._on_data.call_args[0][1] == {"pv_voltage": 5.0}

    @pytest.mark.asyncio
    async def test_numeric_guid_in_topic_is_forwarded_as_string(self):
        """GUIDs are matched as strings everywhere."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/000372",
            {"pv_voltage": 1.0},
        )

        await client._handle_message(msg)
        guid = client._on_data.call_args[0][0]
        assert isinstance(guid, str)
        assert guid == "000372"

    @pytest.mark.asyncio
    async def test_flat_format_maps_all_known_fields(self):
        """Older firmware sends a flat dict without dataStreams."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {"charging_power": 300.0, "yield_today": 1.5, "yield_total": 42.0},
        )

        await client._handle_message(msg)

        assert client._on_data.call_args[0][1] == {
            "charge_power": 300.0,
            "today_kwh": 1.5,
            "total_kwh": 42.0,
        }

    @pytest.mark.asyncio
    async def test_empty_data_streams_list_falls_back_to_flat_format(self):
        """A payload with an empty dataStreams must still be processed."""
        client = self._make_client()
        msg = self._make_mock_message(
            "manhquan/device/mppt_charger/log/45a/547611",
            {"dataStreams": [], "charging_power": 10.0},
        )

        await client._handle_message(msg)

        assert client._on_data.call_args[0][1]["charge_power"] == 10.0


class TestCoordinatorMQTTIntegration:
    """Tests for coordinator MQTT data processing."""

    @pytest.mark.asyncio
    async def test_async_process_mqtt_data_stores_in_cache(self, mock_coordinator):
        """MQTT data is stored in _mqtt_data cache."""
        await mock_coordinator.async_process_mqtt_data("547611", {"pv_voltage": 50.0})
        assert "547611" in mock_coordinator._mqtt_data
        assert mock_coordinator._mqtt_data["547611"]["pv_voltage"] == 50.0

    @pytest.mark.asyncio
    async def test_async_process_mqtt_data_updates_coordinator_data(self, mock_coordinator):
        """MQTT data patches coordinator.data in-place."""
        from tests.conftest import SAMPLE_PROJECT_RESPONSE

        # deepcopy, not copy(): the merge rewrites nested deviceLogs entries,
        # which a shallow copy would share with the module-level constant.
        mock_coordinator.data = deepcopy(SAMPLE_PROJECT_RESPONSE)
        await mock_coordinator.async_process_mqtt_data("547611", {"pv_voltage": 99.9})
        # Check that device 547611 was updated in coordinator.data
        for log in mock_coordinator.data["deviceLogs"]:
            if log["deviceGuid"] == "547611":
                streams = {s["name"]: s["value"] for s in log["dataStreams"]}
                assert streams["pv_voltage"] == "99.9"
                return
        raise AssertionError("Device not found in coordinator.data")

    @pytest.mark.asyncio
    async def test_set_mqtt_client(self, mock_coordinator):
        """set_mqtt_client stores reference."""
        mock_client = MagicMock()
        mock_coordinator.set_mqtt_client(mock_client)
        assert mock_coordinator._mqtt_client is mock_client


class TestConnectionState:
    """`connected` must reflect reality after the loop ends or stop() runs.

    It used to stay True after a cancelled/ended message loop, so diagnostics
    reported a live MQTT connection that no longer existed.
    """

    def _make_client(self):
        return SmartSolarMQTTClient(
            device_guids=["547611"],
            on_data_callback=AsyncMock(),
            username="web_app",
            password="cGFzcw==",
        )

    @pytest.mark.asyncio
    async def test_stop_clears_connected(self):
        client = self._make_client()
        client._connected = True
        client._running = True

        await client.stop()

        assert client.connected is False
        assert client.is_running() is False

    @pytest.mark.asyncio
    async def test_message_loop_clears_state_on_exit(self):
        """On exit the broker connection is gone, whatever ended the loop."""
        client = self._make_client()
        client._running = True

        async def fake_connect_and_listen(inner_self) -> None:
            inner_self._connected = True
            inner_self._running = False  # ask the loop to exit

        # Patched on the class: the client uses __slots__, so the bound method
        # cannot be replaced on the instance.
        with patch.object(SmartSolarMQTTClient, "_connect_and_listen", fake_connect_and_listen):
            await client._message_loop()

        assert client.connected is False
        assert client._client is None

    @pytest.mark.asyncio
    async def test_message_loop_clears_state_after_failure(self):
        """A failing connection attempt must not leave connected=True."""
        client = self._make_client()
        client._running = True

        async def failing_connect(inner_self) -> None:
            inner_self._connected = True
            inner_self._running = False
            raise OSError("broker unreachable")

        with (
            patch.object(SmartSolarMQTTClient, "_connect_and_listen", failing_connect),
            patch("custom_components.smartsolar_ha.mqtt_client.asyncio.sleep", new=AsyncMock()),
        ):
            await client._message_loop()

        assert client.connected is False
