"""MQTT client for SmartSolar MPPT real-time data subscription.

Connects to the SmartSolar MQTT broker (mqttx.smartsolar.io.vn:8084) via
WebSocket Secure (WSS) and subscribes to per-device MQTT topics for
real-time metric updates. Falls back gracefully if aiomqtt is unavailable.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import ssl
from collections.abc import Callable, Coroutine
from typing import Any

from .const import (
    MQTT_BROKER,
    MQTT_FIELD_MAPPING,
    MQTT_PORT,
    MQTT_RECONNECT_DELAY,
    MQTT_TOPIC_PREFIX,
    MQTT_WS_PATH,
)

_LOGGER = logging.getLogger(__name__)

try:
    import aiomqtt

    HAS_AIOMQTT = True
except ImportError:
    HAS_AIOMQTT = False
    aiomqtt = None  # type: ignore[assignment]

CallbackType = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class SmartSolarMQTTClient:
    """Async MQTT client for SmartSolar real-time device data.

    Connects to the SmartSolar platform MQTT broker and subscribes to
    per-device topics. Incoming data is normalized and forwarded via
    an async callback to the coordinator.
    """

    __slots__ = (
        "_device_guids", "_on_data", "_client", "_connected",
        "_running", "_task", "_username", "_password", "_websocket_path",
    )

    def __init__(
        self,
        device_guids: list[str],
        on_data_callback: CallbackType,
        username: str | None = None,
        password: str | None = None,
        websocket_path: str = MQTT_WS_PATH,
    ) -> None:
        """Initialize MQTT client.

        Args:
            device_guids: List of device GUIDs to subscribe to.
            on_data_callback: Async callback(device_guid, normalized_data).
            username: MQTT broker username (from API mqttConnection).
            password: MQTT broker password, base64-encoded (from API mqttConnection).
            websocket_path: WebSocket path (default /mqtt).
        """
        self._device_guids = device_guids
        self._on_data = on_data_callback
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._username = username
        self._password = password  # base64-encoded from API
        self._websocket_path = websocket_path

    @property
    def connected(self) -> bool:
        """Return whether MQTT is currently connected."""
        return self._connected

    @property
    def available(self) -> bool:
        """Return whether aiomqtt is installed and usable."""
        return HAS_AIOMQTT

    def _make_topic(self, device_guid: str) -> str:
        """Build MQTT topic for a device GUID.

        Uses single-level wildcard (+) to match any device model
        (40a, 45a, 60a, etc.) in the topic path.
        """
        return f"{MQTT_TOPIC_PREFIX}/+/{device_guid}"

    async def start(self) -> None:
        """Start MQTT connection in background."""
        if not HAS_AIOMQTT:
            _LOGGER.warning(
                "aiomqtt not installed — MQTT real-time updates disabled. "
                "Install with: pip install aiomqtt>=2.0"
            )
            return

        if not self._device_guids:
            _LOGGER.debug("No device GUIDs to subscribe to; MQTT not started")
            return

        self._running = True
        self._task = asyncio.create_task(self._message_loop())
        _LOGGER.info(
            "MQTT client starting for %d device(s): %s",
            len(self._device_guids),
            ", ".join(self._device_guids[:5])
            + ("..." if len(self._device_guids) > 5 else ""),
        )

    async def stop(self) -> None:
        """Stop MQTT client gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        _LOGGER.debug("MQTT client stopped")

    def is_running(self) -> bool:
        """Check if the MQTT message loop is active."""
        return self._running and self._task is not None and not self._task.done()

    async def _message_loop(self) -> None:
        """Main MQTT message loop with automatic reconnection."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._connected = False
                if self._running:
                    _LOGGER.warning(
                        "MQTT connection failed (%s), reconnecting in %ds...",
                        exc, MQTT_RECONNECT_DELAY,
                    )
                    await asyncio.sleep(MQTT_RECONNECT_DELAY)

    async def _connect_and_listen(self) -> None:
        """Connect to broker, subscribe, and process messages."""
        # ssl.create_default_context() is blocking — run in thread executor
        tls_context = await asyncio.get_event_loop().run_in_executor(
            None, ssl.create_default_context
        )

        # Decode base64 password from API (handle non-base64 gracefully)
        mqtt_password: str | None = None
        if self._password:
            try:
                mqtt_password = base64.b64decode(self._password).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                _LOGGER.warning("MQTT password is not valid base64, using as-is")
                mqtt_password = self._password

        async with aiomqtt.Client(
            hostname=MQTT_BROKER,
            port=MQTT_PORT,
            transport="websockets",
            websocket_path=self._websocket_path,
            tls_context=tls_context,
            username=self._username,
            password=mqtt_password,
            keepalive=60,
        ) as client:
            self._client = client
            self._connected = True
            _LOGGER.info("Connected to SmartSolar MQTT broker at %s:%d",
                          MQTT_BROKER, MQTT_PORT)

            # Subscribe to all device topics
            for guid in self._device_guids:
                topic = self._make_topic(guid)
                await client.subscribe(topic)
                _LOGGER.debug("Subscribed: %s", topic)

            # Process messages
            async for message in client.messages:
                try:
                    await self._handle_message(message)
                except Exception as exc:
                    _LOGGER.warning(
                        "Error processing MQTT message: %s", exc, exc_info=True
                    )

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        """Parse and normalize an incoming MQTT message.

        The MQTT payload uses the same ``lastMessage`` structure as the REST API:
        a ``dataStreams`` array of {name, value} objects plus a few top-level
        fields (``signalQuality``, ``command``, ``deviceGuid``, etc.).

        Two formats are supported:
        1. Standard format with ``dataStreams`` array — extract streams directly.
        2. Flat dict (some devices or older firmware) — map field names via
           ``MQTT_FIELD_MAPPING``.
        """
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _LOGGER.debug(
                "Invalid JSON on topic %s: %s",
                message.topic,
                message.payload[:200],
            )
            return

        if not isinstance(payload, dict):
            _LOGGER.debug("MQTT payload is not a dict on topic %s", message.topic)
            return

        # Extract device GUID from topic (last segment)
        topic_str = str(message.topic)
        topic_parts = topic_str.rstrip("/").split("/")
        if len(topic_parts) < 2:
            _LOGGER.debug("Unexpected topic format: %s", topic_str)
            return
        device_guid = topic_parts[-1]

        normalized: dict[str, Any] = {}

        if "dataStreams" in payload and isinstance(payload["dataStreams"], list):
            # Standard format — extract from dataStreams + pick up top-level extras
            for stream in payload["dataStreams"]:
                if not isinstance(stream, dict):
                    continue
                name = stream.get("name")
                value = stream.get("value")
                if name is not None and value is not None:
                    normalized[name] = value

            # Top-level fields NOT in dataStreams (e.g., signalQuality)
            top_level_fields = ("signalQuality",)
            for key in top_level_fields:
                if key in payload:
                    mapped_key = MQTT_FIELD_MAPPING.get(key, key)
                    normalized[mapped_key] = payload[key]

            _LOGGER.debug(
                "MQTT data for %s: %d fields (dataStreams format)",
                device_guid, len(normalized),
            )
        else:
            # Flat dict format — map all keys through MQTT_FIELD_MAPPING
            for key, value in payload.items():
                mapped_key = MQTT_FIELD_MAPPING.get(key, key)
                normalized[mapped_key] = value

            _LOGGER.debug(
                "MQTT data for %s: %d fields (flat format)",
                device_guid, len(normalized),
            )

        # Forward to coordinator
        await self._on_data(device_guid, normalized)
