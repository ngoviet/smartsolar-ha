"""Tests for MQTT client and coordinator MQTT integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smartsolar_mppt.const import MQTT_FIELD_MAPPING
from custom_components.smartsolar_mppt.mqtt_client import (
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


class TestCoordinatorMQTTIntegration:
    """Tests for coordinator MQTT data processing."""

    @pytest.mark.asyncio
    async def test_async_process_mqtt_data_stores_in_cache(self, mock_coordinator):
        """MQTT data is stored in _mqtt_data cache."""
        await mock_coordinator.async_process_mqtt_data(
            "547611", {"pv_voltage": 50.0}
        )
        assert "547611" in mock_coordinator._mqtt_data
        assert mock_coordinator._mqtt_data["547611"]["pv_voltage"] == 50.0

    @pytest.mark.asyncio
    async def test_async_process_mqtt_data_updates_coordinator_data(self, mock_coordinator):
        """MQTT data patches coordinator.data in-place."""
        from tests.conftest import SAMPLE_PROJECT_RESPONSE

        mock_coordinator.data = SAMPLE_PROJECT_RESPONSE.copy()
        await mock_coordinator.async_process_mqtt_data(
            "547611", {"pv_voltage": 99.9}
        )
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
