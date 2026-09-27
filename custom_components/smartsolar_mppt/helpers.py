"""Small shared helpers for the SmartSolar MPPT integration.

Kept dependency-free so both the API/coordinator layer and the entity
platforms can use them without import cycles.
"""

from __future__ import annotations

from typing import Any


def coerce_float(value: Any) -> float | None:
    """Return ``value`` as float, or None when it is missing/not numeric.

    Rejects booleans: ``float(True) == 1.0`` would silently turn a flag into a
    measurement.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


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
    except (TypeError, ValueError):
        return (1, guid)
