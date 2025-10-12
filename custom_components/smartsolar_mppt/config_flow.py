"""Config flow for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .api import SmartSolarAPI, SmartSolarAPIError
from .const import (
    CONF_CHIPSET_IDS,
    CONF_DEVICE_TYPE,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    DEFAULT_UPDATE_INTERVAL,
    DEVICE_TYPE_MANH_QUAN,
    DEVICE_TYPE_SUN_GTIL2,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CREDENTIALS,
    ERROR_UNKNOWN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MODE_DEVICE,
    MODE_PROJECT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_MODE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In([MODE_DEVICE, MODE_PROJECT]),
    }
)


STEP_CHIPSET_IDS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHIPSET_IDS): str,
    }
)

STEP_PROJECT_DEVICES_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("manh_quan_count"): str,
        vol.Required("manh_quan_ids"): str,
    }
)

# Options schema removed - TextSelector doesn't support min/max
# Using vol.Schema directly in async_step_init instead


class SmartSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SmartSolar MPPT."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._username: str | None = None
        self._password: str | None = None
        self._mode: str | None = None
        self._device_type: int | None = None
        self._chipset_ids: list[str] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            # Validate required fields
            if not self._username or not self._username.strip():
                errors["base"] = "username_required"
            elif not self._password or not self._password.strip():
                errors["base"] = "password_required"
            else:
                try:
                    # Test the connection
                    api = SmartSolarAPI(
                        username=self._username,
                        password=self._password,
                        hass=self.hass,
                    )
                    
                    if await api.test_connection():
                        return await self.async_step_mode()
                    else:
                        errors["base"] = ERROR_CANNOT_CONNECT
                except SmartSolarAPIError as err:
                    if err.status_code == 401:
                        errors["base"] = ERROR_INVALID_CREDENTIALS
                    else:
                        errors["base"] = ERROR_CANNOT_CONNECT
                    _LOGGER.error("API error during login: %s", err)
                except Exception as err:
                    _LOGGER.error("Unexpected error during login: %s", err)
                    errors["base"] = ERROR_UNKNOWN

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the mode selection step."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            if self._mode == MODE_DEVICE:
                self._device_type = DEVICE_TYPE_MANH_QUAN  # Default to Sạc MPPT Mạnh Quân
                return await self.async_step_chipset_ids()
            else:  # MODE_PROJECT
                return await self.async_step_project_devices()

        return self.async_show_form(
            step_id="mode",
            data_schema=STEP_MODE_DATA_SCHEMA,
            description_placeholders={
                "device_info": "• device: Xem dữ liệu từ một thiết bị đơn lẻ\n• project: Tổng hợp dữ liệu từ nhiều thiết bị trong một nơi"
            }
        )


    async def async_step_project_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the project devices configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            manh_quan_count_str = user_input.get("manh_quan_count", "").strip()
            manh_quan_ids = user_input.get("manh_quan_ids", "").strip()

            # Validate input
            if not manh_quan_count_str:
                errors["base"] = "manh_quan_count_required"
            elif not manh_quan_ids:
                errors["base"] = "manh_quan_ids_required"
            else:
                try:
                    manh_quan_count = int(manh_quan_count_str)
                    if manh_quan_count < 1 or manh_quan_count > 10:
                        errors["base"] = "manh_quan_count_invalid"
                except ValueError:
                    errors["base"] = "manh_quan_count_invalid"
                
                if not errors:
                    # Parse device IDs
                    all_devices = []
                    device_types = []
                    
                    manh_ids = [str(id.strip()) for id in manh_quan_ids.split(",") if id.strip()]
                    if len(manh_ids) != manh_quan_count:
                        errors["base"] = "manh_quan_count_mismatch"
                    else:
                        all_devices.extend(manh_ids)
                        device_types.extend([DEVICE_TYPE_MANH_QUAN] * manh_quan_count)

                if not errors and all_devices and device_types:
                    self._chipset_ids = all_devices
                    self._device_types = device_types
                    
                    # Test the configuration
                    try:
                        api = SmartSolarAPI(
                            username=self._username,
                            password=self._password,
                            hass=self.hass,
                        )
                        
                        # Test with first device
                        await api.get_metrics(
                            device_type=device_types[0],
                            chipset_ids=[all_devices[0]],
                            mode=self._mode,
                        )
                        
                        # Create unique ID for this configuration
                        unique_id = f"{self._username}_{self._mode}_{'_'.join(all_devices)}"
                        
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()
                        
                        return self.async_create_entry(
                            title=f"SmartSolar MPPT ({self._mode.title()})",
                            data={
                                CONF_USERNAME: self._username,
                                CONF_PASSWORD: self._password,
                                CONF_MODE: self._mode,
                                CONF_DEVICE_TYPE: device_types[0],  # Primary device type
                                CONF_CHIPSET_IDS: self._chipset_ids,
                                "device_types": self._device_types,  # All device types
                            },
                        )
                        
                    except SmartSolarAPIError as err:
                        if err.status_code == 404:
                            errors["base"] = "device_not_found"
                        else:
                            errors["base"] = ERROR_CANNOT_CONNECT
                        _LOGGER.error("API error during test: %s", err)
                    except Exception as err:
                        _LOGGER.error("Unexpected error during test: %s", err)
                        errors["base"] = ERROR_UNKNOWN

        return self.async_show_form(
            step_id="project_devices",
            data_schema=STEP_PROJECT_DEVICES_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_chipset_ids(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the chipset IDs input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            chipset_ids_str = user_input[CONF_CHIPSET_IDS].strip()
            
            if not chipset_ids_str:
                errors["base"] = "chipset_ids_required"
            else:
                # Parse chipset IDs (comma-separated)
                chipset_ids = [id.strip() for id in chipset_ids_str.split(",") if id.strip()]
                
                if not chipset_ids:
                    errors["base"] = "chipset_ids_invalid"
                else:
                    self._chipset_ids = chipset_ids
                    
                    # Test the configuration
                    try:
                        api = SmartSolarAPI(
                            username=self._username,
                            password=self._password,
                            hass=self.hass,
                        )
                        
                        # Test with the first chipset ID
                        await api.get_metrics(
                            device_type=self._device_type,
                            chipset_ids=chipset_ids,
                            mode=self._mode,
                        )
                        
                        # Create unique ID for this configuration
                        unique_id = f"{self._username}_{self._mode}_{self._device_type}_{'_'.join(chipset_ids)}"
                        
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()
                        
                        return self.async_create_entry(
                            title=f"SmartSolar MPPT ({self._mode.title()})",
                            data={
                                CONF_USERNAME: self._username,
                                CONF_PASSWORD: self._password,
                                CONF_MODE: self._mode,
                                CONF_DEVICE_TYPE: self._device_type,
                                CONF_CHIPSET_IDS: self._chipset_ids,
                            },
                        )
                        
                    except SmartSolarAPIError as err:
                        if err.status_code == 404:
                            errors["base"] = "device_not_found"
                        else:
                            errors["base"] = ERROR_CANNOT_CONNECT
                        _LOGGER.error("API error during test: %s", err)
                    except Exception as err:
                        _LOGGER.error("Unexpected error during test: %s", err)
                        errors["base"] = ERROR_UNKNOWN

        # Build help text based on mode
        help_text = ""
        if self._mode == MODE_DEVICE:
            help_text = "Nhập ChipsetId của thiết bị (chỉ một ID)."
        elif self._mode == MODE_PROJECT:
            help_text = "Nhập các ChipsetId của thiết bị, phân cách bằng dấu phẩy (ví dụ: ID1, ID2, ID3)."

        return self.async_show_form(
            step_id="chipset_ids",
            data_schema=STEP_CHIPSET_IDS_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"help_text": help_text},
        )






class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class DeviceNotFound(HomeAssistantError):
    """Error to indicate device not found."""
