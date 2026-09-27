"""SmartSolar MPPT integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .api import SmartSolarAPI, SmartSolarAPIError
from .const import DOMAIN, build_device_info
from .coordinator import SmartSolarDataUpdateCoordinator
from .mqtt_client import SmartSolarMQTTClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]


async def async_setup(hass: HomeAssistant, _: dict[str, Any]) -> bool:
    """Set up the SmartSolar MPPT component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry to new version."""
    _LOGGER.debug(
        "Migrating config entry from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    if entry.version > 1:
        # Downgrading is not supported — refuse rather than corrupt the entry.
        _LOGGER.error(
            "Cannot migrate config entry from version %s.%s: newer than this integration supports",
            entry.version,
            entry.minor_version,
        )
        return False

    if entry.version == 1 and entry.minor_version < 2:
        # v1 → v1.2: ensure chipset_ids are strings, add missing keys
        new_data = dict(entry.data)
        chipset_ids = new_data.get("chipset_ids")
        if chipset_ids is not None:
            new_data["chipset_ids"] = [str(cid) for cid in chipset_ids]
        new_data.setdefault("update_interval", 5)

        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            minor_version=2,
        )
        _LOGGER.info("Migration to v1.2 complete")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartSolar MPPT from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    missing = [key for key in ("username", "password") if not entry.data.get(key)]
    if missing:
        _LOGGER.error(
            "Config entry %s is missing required keys: %s — cannot set up",
            entry.entry_id,
            ", ".join(missing),
        )
        return False

    # Initialize API client
    api = SmartSolarAPI(
        username=entry.data["username"],
        password=entry.data["password"],
        hass=hass,
    )

    # Get update interval from data (default to 5 seconds)
    # Note: update_interval is now controlled via Number entity
    update_interval = entry.data.get("update_interval", 5)  # Default 5 seconds

    # Initialize coordinator
    coordinator = SmartSolarDataUpdateCoordinator(
        hass=hass,
        api=api,
        entry=entry,
        update_interval=timedelta(seconds=update_interval),
    )

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Fetch initial data FIRST so sensor.py discovers per-device GUIDs from API.
    # Use async_refresh() instead of async_config_entry_first_refresh() to avoid
    # state check error on reload (HA 2025.x+).
    # A failed first refresh must NOT abort setup: the MQTT/HTTP paths recover
    # and the entities simply start as unavailable.
    try:
        await coordinator.async_refresh()
    except Exception as exc:  # noqa: BLE001 - setup must survive any API failure
        _LOGGER.warning("Initial SmartSolar refresh failed (%s) — continuing setup", exc)

    # Set up MQTT real-time data subscription (optional — degrades gracefully)
    mqtt_client = None
    chipset_ids = entry.data.get("chipset_ids", [])
    project_id = entry.data.get("project_id")
    mode = entry.data.get("mode", "device")

    # Determine device GUIDs for MQTT subscription
    mqtt_device_guids: list[str] = []
    if coordinator.data and "deviceLogs" in coordinator.data:
        mqtt_device_guids = coordinator.device_guids(coordinator.data)
    if not mqtt_device_guids and chipset_ids:
        mqtt_device_guids = [str(cid) for cid in chipset_ids]

    if mqtt_device_guids:
        try:
            # Extract MQTT credentials from API response
            mqtt_username: str | None = None
            mqtt_password: str | None = None  # base64-encoded

            if coordinator.data and "mqttConnection" in coordinator.data:
                # Device mode: /Device/Status response already has credentials
                mqtt_conn = coordinator.data["mqttConnection"]
                mqtt_username = mqtt_conn.get("username")
                mqtt_password = mqtt_conn.get("password")
                _LOGGER.debug("MQTT credentials from device API response for %s", mqtt_device_guids)
            else:
                # Project mode: fetch device status for first device to get credentials
                _LOGGER.debug("Fetching MQTT credentials from device API: %s", mqtt_device_guids[0])
                try:
                    device_status = await api.get_device_status(mqtt_device_guids[0])
                    if "mqttConnection" in device_status:
                        mqtt_conn = device_status["mqttConnection"]
                        mqtt_username = mqtt_conn.get("username")
                        mqtt_password = mqtt_conn.get("password")
                        _LOGGER.debug("MQTT credentials fetched from API")
                    else:
                        _LOGGER.warning("Device status response missing mqttConnection — MQTT disabled")
                except (SmartSolarAPIError, aiohttp.ClientError, TimeoutError) as exc:
                    _LOGGER.warning(
                        "Could not fetch MQTT credentials: %s — continuing without MQTT",
                        exc,
                    )

            if mqtt_username and mqtt_password:
                mqtt_client = SmartSolarMQTTClient(
                    device_guids=mqtt_device_guids,
                    on_data_callback=coordinator.async_process_mqtt_data,
                    username=mqtt_username,
                    password=mqtt_password,
                )
                coordinator.set_mqtt_client(mqtt_client)
                await mqtt_client.start()
                _LOGGER.info(
                    "MQTT real-time updates enabled for %d device(s)",
                    len(mqtt_device_guids),
                )
            else:
                _LOGGER.warning("No MQTT credentials available — MQTT real-time updates disabled")
                mqtt_client = None

        except Exception as exc:
            _LOGGER.warning(
                "MQTT setup failed (%s) — continuing with HTTP-only polling",
                exc,
            )
            mqtt_client = None

    # Store MQTT client reference for cleanup on unload
    if mqtt_client is not None:
        hass.data[f"{DOMAIN}_{entry.entry_id}_mqtt"] = mqtt_client

    # Set up platforms AFTER data is available (device GUIDs now in coordinator.data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create device registry entry
    device_registry = dr.async_get(hass)
    device_info = build_device_info(entry.entry_id, mode, project_id)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **device_info,
    )

    # Register services. Re-registering the same service name simply replaces
    # the handler, so a second config entry is harmless.
    async def async_refresh_token(service: ServiceCall) -> None:
        """Service to manually refresh API token."""
        entry_id = service.data["entry_id"]
        coordinator: SmartSolarDataUpdateCoordinator | None = hass.data[DOMAIN].get(entry_id)
        if coordinator is None:
            # Silently doing nothing used to look like a successful refresh.
            raise ServiceValidationError(f"Unknown SmartSolar HA config entry: {entry_id}")
        await coordinator.api.refresh_token_if_needed()
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "refresh_token",
        async_refresh_token,
        schema=vol.Schema(
            {
                # Required: without it the handler had no entry to act on and
                # every call was a silent no-op.
                vol.Required("entry_id"): str,
            }
        ),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop MQTT client if active
    mqtt_key = f"{DOMAIN}_{entry.entry_id}_mqtt"
    mqtt_client: SmartSolarMQTTClient | None = hass.data.pop(mqtt_key, None)
    if mqtt_client is not None:
        try:
            await mqtt_client.stop()
            _LOGGER.debug("MQTT client stopped for entry %s", entry.entry_id)
        except Exception as exc:
            _LOGGER.warning("Error stopping MQTT client: %s", exc)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: SmartSolarDataUpdateCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            try:
                await coordinator.api.close()
            except (aiohttp.ClientError, RuntimeError) as e:
                _LOGGER.warning("Error closing API session: %s", e)
            finally:
                # Stops the poll timer and cancels the midnight listener and
                # the MQTT notify throttle registered in the coordinator;
                # without this a reload leaks them.
                await coordinator.async_shutdown()
                hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
