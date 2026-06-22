"""Diagnostics support for SmartSolar MPPT."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if not coordinator:
        return {"error": "No coordinator found"}

    data: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": {k: "***" if k == "password" else v for k, v in entry.data.items()},
        },
        "coordinator": {
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "discovered_devices": list(coordinator.discovered_devices),
            "last_update_success": coordinator.last_update_success,
        },
        "api": {
            "has_token": bool(coordinator.api.token),
            "token_expiry": coordinator.api.token_expiry.isoformat()
            if coordinator.api.token_expiry
            else None,
        },
    }

    if coordinator.data:
        api_data = coordinator.data
        data["response"] = {
            "mode": api_data.get("_mode"),
            "device_type": api_data.get("_device_type"),
            "chipset_ids": api_data.get("_chipset_ids"),
            "has_synthesis_streams": "synthesisStreams" in api_data,
            "device_count": len(api_data.get("deviceLogs", [])),
            "sensor_count": len(api_data.get("synthesisStreams", [])),
        }

    return data
