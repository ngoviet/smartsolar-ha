"""Diagnostics support for SmartSolar MPPT."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Credential-ish keys that must never leave the instance.
_REDACTED_KEYS = frozenset({"password", "token", "mqtt_password"})


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with secrets replaced by a placeholder."""
    return {key: "***" if key in _REDACTED_KEYS else value for key, value in data.items()}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not coordinator:
        return {"error": "No coordinator found"}

    mqtt_client = coordinator.mqtt_client
    data: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": _redact(dict(entry.data)),
        },
        "coordinator": {
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "discovered_devices": sorted(coordinator.discovered_devices),
            "last_update_success": coordinator.last_update_success,
        },
        "api": {
            "has_token": bool(coordinator.api.token),
            "token_expiry": (coordinator.api.token_expiry.isoformat() if coordinator.api.token_expiry else None),
        },
        "mqtt": {
            "enabled": mqtt_client is not None,
            "connected": bool(mqtt_client.connected) if mqtt_client else False,
            "cached_devices": coordinator.mqtt_cached_device_count,
        },
    }

    if coordinator.data:
        api_data = coordinator.data
        data["response"] = {
            "mode": api_data.get("_mode"),
            "device_type": api_data.get("_device_type"),
            "chipset_ids": api_data.get("_chipset_ids"),
            "has_synthesis_streams": "synthesisStreams" in api_data,
            "device_count": len(api_data.get("deviceLogs", []) or []),
            "sensor_count": len(api_data.get("synthesisStreams", []) or []),
        }

    return data
