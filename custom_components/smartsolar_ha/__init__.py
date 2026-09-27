"""SmartSolar MPPT integration for Home Assistant."""

from __future__ import annotations

import contextlib
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
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    build_device_info,
)
from .coordinator import SmartSolarDataUpdateCoordinator
from .helpers import coerce_float
from .mqtt_client import SmartSolarMQTTClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

# How many devices to probe for the shared MQTT credentials before giving up.
# The credentials are per-server, so the first device that answers is enough;
# the cap only stops a large project from making one API call per device.
MQTT_CREDENTIAL_ATTEMPTS = 3


def _resolve_update_interval(raw: Any) -> int:
    """Return a usable update interval in whole seconds.

    The config entry is plain JSON on disk and the Number entity is not its only
    writer, so this value cannot be trusted. A zero or negative interval used to
    reach ``DataUpdateCoordinator.update_interval`` unchanged, and
    ``_schedule_refresh`` then schedules the next poll *in the past* — a tight
    loop against the cloud API. Out-of-range and non-numeric values are clamped
    to the same 1-30 s range the Number entity enforces.
    """
    seconds = coerce_float(raw)
    if seconds is None:
        return int(DEFAULT_UPDATE_INTERVAL.total_seconds())
    return int(min(max(seconds, MIN_UPDATE_INTERVAL), MAX_UPDATE_INTERVAL))


def _normalize_chipset_ids(raw: Any) -> list[str]:
    """Return legacy ``chipset_ids`` as a list of strings.

    Migration has to cope with whatever an old entry stored. Iterating the raw
    value raised ``TypeError`` for a scalar (the migration then failed and left
    the entry stuck on the old version), and a comma-separated *string* was
    iterated per character — turning "547611,14756976" into
    ``["5", "4", "7", ...]`` and corrupting the entry.
    """
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(cid) for cid in raw if cid is not None and str(cid).strip()]
    return []


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
        # Always store a LIST. Downstream code iterates this field (and indexes
        # it), so leaving a scalar or the comma-separated string form in place
        # raised TypeError inside async_setup_entry or the coordinator instead of
        # producing a usable entry.
        new_data["chipset_ids"] = _normalize_chipset_ids(new_data.get("chipset_ids"))
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

    # `mode` is indexed directly by the sensor platform, so a missing one used to
    # raise KeyError from inside a platform — after the coordinator (with its poll
    # timer and midnight listener) had already been created and stored.
    missing = [key for key in ("username", "password", "mode") if not entry.data.get(key)]
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
    update_interval = _resolve_update_interval(entry.data.get("update_interval", 5))

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

            if coordinator.data and isinstance(coordinator.data.get("mqttConnection"), dict):
                # Device mode: /Device/Status response already has credentials
                mqtt_conn = coordinator.data["mqttConnection"]
                mqtt_username = mqtt_conn.get("username")
                mqtt_password = mqtt_conn.get("password")
                _LOGGER.debug("MQTT credentials from device API response for %s", mqtt_device_guids)
            else:
                # Project mode: the credentials come from /Device/Status. These
                # are per-SERVER credentials, so the first device that reports
                # them is enough — but only querying mqtt_device_guids[0] meant a
                # single offline device (or one whose payload omits
                # `mqttConnection`) silently disabled real-time updates for the
                # whole project.
                for candidate in mqtt_device_guids[:MQTT_CREDENTIAL_ATTEMPTS]:
                    try:
                        device_status = await api.get_device_status(candidate)
                    except (SmartSolarAPIError, aiohttp.ClientError, TimeoutError) as exc:
                        _LOGGER.debug("Could not read device status for %s: %s", candidate, exc)
                        continue

                    # Third-party JSON: `mqttConnection` has been observed
                    # missing and null. Calling .get() on a non-mapping used to
                    # raise AttributeError, which the outer handler reported as a
                    # generic "MQTT setup failed".
                    mqtt_conn = device_status.get("mqttConnection")
                    if isinstance(mqtt_conn, dict) and mqtt_conn.get("username") and mqtt_conn.get("password"):
                        mqtt_username = mqtt_conn.get("username")
                        mqtt_password = mqtt_conn.get("password")
                        _LOGGER.debug("MQTT credentials fetched from device API (%s)", candidate)
                        break

                    _LOGGER.debug("Device status for %s has no mqttConnection; trying the next device", candidate)

                if not (mqtt_username and mqtt_password):
                    _LOGGER.warning("No device reported MQTT credentials — MQTT real-time updates disabled")

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
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # A failing platform must not leak everything already created here: the
        # coordinator's poll timer and midnight listener, the aiohttp session and
        # the MQTT task. Home Assistant does NOT call async_unload_entry for an
        # entry whose setup failed — it retries setup instead, and each retry
        # would add another poll timer hammering the cloud API.
        _LOGGER.exception("Failed to set up the SmartSolar HA platforms for %s — rolling back", entry.entry_id)
        # Home Assistant gathers the platform setups and does not roll back the
        # ones that already succeeded, so unload them here: otherwise a retried
        # setup would add the same entities (and unique_ids) a second time.
        with contextlib.suppress(Exception):
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        await _async_teardown(hass, entry, coordinator, mqtt_client)
        return False

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


async def _async_teardown(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: SmartSolarDataUpdateCoordinator | None,
    mqtt_client: SmartSolarMQTTClient | None,
) -> None:
    """Release everything ``async_setup_entry`` created for one entry.

    Shared by the unload path and by the rollback taken when platform setup
    fails, so there is exactly one place that knows what has to be released.
    """
    if mqtt_client is not None:
        try:
            await mqtt_client.stop()
            _LOGGER.debug("MQTT client stopped for entry %s", entry.entry_id)
        except Exception as exc:
            _LOGGER.warning("Error stopping MQTT client: %s", exc)
    hass.data.pop(f"{DOMAIN}_{entry.entry_id}_mqtt", None)

    if coordinator is not None:
        try:
            await coordinator.api.close()
        except (aiohttp.ClientError, RuntimeError) as e:
            _LOGGER.warning("Error closing API session: %s", e)
        finally:
            # Stops the poll timer and cancels the midnight listener and the
            # MQTT notify throttle registered in the coordinator; without this a
            # reload (or a retried setup) leaks them.
            await coordinator.async_shutdown()

    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the platforms FIRST. Tearing the MQTT client and the coordinator
    # down before the result is known left a half-dead entry behind when a
    # platform refused to unload: still loaded, but with real-time updates and
    # polling permanently stopped and nothing left to stop them again.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator: SmartSolarDataUpdateCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)
    mqtt_client: SmartSolarMQTTClient | None = hass.data.get(f"{DOMAIN}_{entry.entry_id}_mqtt")
    await _async_teardown(hass, entry, coordinator, mqtt_client)

    # Home Assistant does NOT remove services that a config entry registered (it
    # only calls the optional async_remove_entry hook), so the refresh_token
    # service would linger after the last entry is unloaded and every call to it
    # would fail with ServiceValidationError. Other entries keep it alive.
    if not [other for other in hass.config_entries.async_entries(DOMAIN) if other.entry_id != entry.entry_id]:
        hass.services.async_remove(DOMAIN, "refresh_token")

    return True
