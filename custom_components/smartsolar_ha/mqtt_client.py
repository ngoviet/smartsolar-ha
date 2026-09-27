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
from typing import TYPE_CHECKING, Any

from .const import (
    MQTT_BROKER,
    MQTT_FIELD_MAPPING,
    MQTT_PORT,
    MQTT_RECONNECT_DELAY,
    MQTT_TOPIC_PREFIX,
    MQTT_WS_PATH,
)

_LOGGER = logging.getLogger(__name__)

# aiomqtt is an optional dependency: the integration degrades to REST-only
# polling when it is missing. The fallback is bound through an explicitly
# annotated name so the module-level type is the same whether or not the
# package is installed (otherwise mypy reports an assignment error on one
# machine and an unused-ignore error on the other).
if TYPE_CHECKING:
    import aiomqtt
else:
    try:
        import aiomqtt
    except ImportError:  # pragma: no cover - exercised only without the extra
        aiomqtt = None

HAS_AIOMQTT = aiomqtt is not None

CallbackType = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

# Fields that describe the message itself rather than a measurement. They must
# never be turned into sensors. Hoisted out of the message handler: it used to
# rebuild this set for every payload, and a busy broker delivers ~2 messages per
# second per device.
BOOKKEEPING_FIELDS = frozenset({"command", "deviceGuid", "espId", "timeStamp", "firmwareVersion", "messagesCounter"})


class SmartSolarMQTTClient:
    """Async MQTT client for SmartSolar real-time device data.

    Connects to the SmartSolar platform MQTT broker and subscribes to
    per-device topics. Incoming data is normalized and forwarded via
    an async callback to the coordinator.
    """

    __slots__ = (
        "_device_guids",
        "_on_data",
        "_client",
        "_connected",
        "_running",
        "_task",
        "_username",
        "_password",
        "_websocket_path",
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
                "aiomqtt not installed — MQTT real-time updates disabled. Install with: pip install aiomqtt>=2.0"
            )
            return

        if not self._device_guids:
            _LOGGER.debug("No device GUIDs to subscribe to; MQTT not started")
            return

        self._running = True
        self._task = asyncio.create_task(self._message_loop())
        device_list = ", ".join(self._device_guids[:5])
        if len(self._device_guids) > 5:
            device_list += "..."
        _LOGGER.info(
            "MQTT client starting for %d device(s): %s",
            len(self._device_guids),
            device_list,
        )

    async def stop(self) -> None:
        """Stop MQTT client gracefully."""
        self._running = False
        # Clear the state here as well as on the way out of the loop:
        # diagnostics and the coordinator read `connected` immediately after
        # stop(), and a closed client must never be kept referenced. The loop's
        # `finally` covers the cancel path, but stop() can also be called when
        # no loop was ever started.
        self._connected = False
        self._client = None
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
        try:
            while self._running:
                try:
                    await self._connect_and_listen()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self._connected = False
                    if not self._running:
                        break
                    _LOGGER.warning(
                        "MQTT connection failed (%s), reconnecting in %ds...",
                        exc,
                        MQTT_RECONNECT_DELAY,
                    )
                else:
                    # The message stream ended without raising — the broker
                    # closed the subscription cleanly. Sleeping here too is what
                    # keeps that from becoming a tight reconnect loop that
                    # hammers the broker as fast as it can accept connections.
                    self._connected = False
                    if not self._running:
                        break
                    _LOGGER.warning(
                        "MQTT connection to %s closed, reconnecting in %ds...",
                        MQTT_BROKER,
                        MQTT_RECONNECT_DELAY,
                    )
                await asyncio.sleep(MQTT_RECONNECT_DELAY)
        finally:
            # Reached on cancel, on a clean end of the stream and on an
            # unexpected error alike; the broker connection is gone in every
            # case, so never keep reporting it as connected and never keep a
            # dead client reference. Cancellation during the reconnect sleep
            # used to skip this cleanup entirely.
            self._connected = False
            self._client = None

    async def _connect_and_listen(self) -> None:
        """Connect to broker, subscribe, and process messages."""
        # ssl.create_default_context() is blocking — run in thread executor.
        # get_running_loop(), not get_event_loop(): this is a coroutine, and
        # get_event_loop() is the legacy API that only happens to work inside a
        # running loop.
        tls_context = await asyncio.get_running_loop().run_in_executor(None, ssl.create_default_context)

        # Decode base64 password from API (handle non-base64 gracefully)
        mqtt_password: str | None = None
        if self._password:
            try:
                mqtt_password = base64.b64decode(self._password).decode("utf-8")
            except ValueError, UnicodeDecodeError:
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
            _LOGGER.info(
                "Connected to SmartSolar MQTT broker at %s:%d",
                MQTT_BROKER,
                MQTT_PORT,
            )

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
                    _LOGGER.warning("Error processing MQTT message: %s", exc, exc_info=True)

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
        except json.JSONDecodeError, UnicodeDecodeError:
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

        # Fields that describe the message itself rather than a measurement.
        # They must never be turned into sensors (see BOOKKEEPING_FIELDS).

        normalized: dict[str, Any] = {}
        data_streams = payload.get("dataStreams")
        if isinstance(data_streams, list) and data_streams:
            # Standard format — extract from dataStreams + pick up top-level extras
            for stream in data_streams:
                if not isinstance(stream, dict):
                    continue
                name = stream.get("name")
                value = stream.get("value")
                if value is None or not isinstance(name, str):
                    # A non-string name is not a measurement key: it cannot be
                    # matched against SENSOR_TYPES, and an unhashable one used to
                    # raise inside the dict assignment.
                    continue
                # Apply MQTT_FIELD_MAPPING here too. Firmware has been seen
                # publishing the legacy names (charging_power, yield_today,
                # yield_total) INSIDE dataStreams, and those fields were stored
                # under names no sensor reads — every value silently dropped.
                # The mapping is a no-op for the normal REST-named streams.
                normalized[MQTT_FIELD_MAPPING.get(name, name)] = value

            # Top-level fields NOT in dataStreams (e.g., signalQuality)
            if "signalQuality" in payload:
                mapped_key: str = MQTT_FIELD_MAPPING.get("signalQuality", "signalQuality")
                normalized[mapped_key] = payload["signalQuality"]

            _LOGGER.debug(
                "MQTT data for %s: %d fields (dataStreams format)",
                device_guid,
                len(normalized),
            )
        else:
            # Flat dict format — map every measurement key. An empty (or
            # non-list) dataStreams is treated as "not present" so the other
            # fields are not silently dropped.
            for key, value in payload.items():
                if key in BOOKKEEPING_FIELDS or key == "dataStreams":
                    continue
                mapped_field: str = MQTT_FIELD_MAPPING.get(key) or key
                normalized[mapped_field] = value

            _LOGGER.debug(
                "MQTT data for %s: %d fields (flat format)",
                device_guid,
                len(normalized),
            )

        # Forward to coordinator
        await self._on_data(device_guid, normalized)
