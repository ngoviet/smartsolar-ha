"""Small shared helpers for the SmartSolar MPPT integration.

Kept dependency-free so both the API/coordinator layer and the entity
platforms can use them without import cycles.
"""

from __future__ import annotations

import math
from typing import Any


def coerce_float(value: Any) -> float | None:
    """Return ``value`` as float, or None when it is missing/not numeric.

    Rejects booleans: ``float(True) == 1.0`` would silently turn a flag into a
    measurement.

    Also rejects non-finite results. ``json.loads`` accepts the non-standard
    ``NaN`` / ``Infinity`` / ``-Infinity`` literals, so a device or the cloud
    API can put them into a payload; a NaN state then poisons Home Assistant's
    long-term statistics for that sensor (every derived value stays NaN).
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except ValueError, TypeError:
        return None
    return result if math.isfinite(result) else None


def as_list(value: Any) -> list[Any]:
    """Return ``value`` when it really is a list, otherwise an empty list.

    Cloud responses are third-party JSON: a field the integration iterates has
    to be checked before use, because ``for x in 5`` raises ``TypeError`` and
    would take down the whole poll/entity update.
    """
    return value if isinstance(value, list) else []


def device_logs(data: Any) -> list[Any]:
    """Return ``data["deviceLogs"]`` as a list, whatever the API actually sent.

    The response is third-party JSON: the field has been observed absent,
    ``null``, and (in defensive tests) a scalar. Every consumer must treat a
    non-list as "no device logs" instead of raising — a bare
    ``len(data.get("deviceLogs", []))`` inside a debug statement used to fail an
    entire poll cycle with ``UpdateFailed: object of type 'NoneType' has no
    len()`` whenever the server answered ``"deviceLogs": null``.
    """
    if not isinstance(data, dict):
        return []
    return as_list(data.get("deviceLogs"))


def stream_dict(data_streams: Any) -> dict[str, Any]:
    """Build a ``{name: value}`` view of a ``dataStreams`` list.

    Malformed entries are skipped: these lists come straight from a
    third-party cloud API and from MQTT payloads, and one bad element must not
    be able to break a poll cycle.
    """
    if not isinstance(data_streams, list):
        return {}
    return {
        stream["name"]: stream.get("value")
        for stream in data_streams
        if isinstance(stream, dict) and stream.get("name") is not None and stream.get("value") is not None
    }


def guid_sort_key(guid: str) -> tuple[int, int | str]:
    """Sort device GUIDs numerically when possible, alphabetically otherwise.

    The PV1/PV2 entity names — and therefore the entity_ids and every
    dashboard reference — are derived from device order. The server does not
    guarantee the order of ``deviceLogs``, so the labels would otherwise
    shuffle between restarts.
    """
    try:
        return (0, int(guid))
    except TypeError, ValueError:
        return (1, guid)
