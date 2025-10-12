"""SmartSolar MPPT integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .api import SmartSolarAPI
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .coordinator import SmartSolarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]


async def async_setup(hass: HomeAssistant, _: dict[str, Any]) -> bool:
    """Set up the SmartSolar MPPT component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartSolar MPPT from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize API client
    api = SmartSolarAPI(
        username=entry.data["username"],
        password=entry.data["password"],
        hass=hass,
    )

    # Get update interval from data (default to 5 seconds)
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, 5)

    # Initialize coordinator
    coordinator = SmartSolarDataUpdateCoordinator(
        hass=hass,
        api=api,
        entry=entry,
        update_interval=timedelta(seconds=update_interval),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create device registry entry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"SmartSolar MPPT {entry.data.get('mode', 'Device').title()}",
        manufacturer="SmartSolar",
        model="MPPT Controller",
        sw_version="1.0.0",
        hw_version="MPPT",
        configuration_url="https://smartsolar.io.vn/",
    )

    # Register services
    async def async_refresh_token(service: ServiceCall) -> None:
        """Service to manually refresh API token."""
        coordinator = hass.data[DOMAIN].get(service.data.get("entry_id"))
        if coordinator:
            await coordinator.api.refresh_token()
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "refresh_token",
        async_refresh_token,
        schema=vol.Schema({
            "entry_id": str,
        }),
    )

    return True




async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: SmartSolarDataUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            try:
                await coordinator.api.close()
            except (aiohttp.ClientError, RuntimeError) as e:
                _LOGGER.warning("Error closing API session: %s", e)
            finally:
                hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
