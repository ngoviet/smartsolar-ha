"""Config flow for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .api import SmartSolarAPI, SmartSolarAPIError
from .const import (
    CONF_CHIPSET_IDS,
    CONF_DEVICE_TYPE,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_PROJECT_ID,
    CONF_USERNAME,
    DEVICE_TYPE_MANH_QUAN,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CREDENTIALS,
    ERROR_UNKNOWN,
    MODE_DEVICE,
    MODE_PROJECT,
    PROJECT_MODE_BY_DEVICES,
    PROJECT_MODE_BY_ID,
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
        vol.Required("manh_quan_ids"): str,
    }
)

STEP_PROJECT_METHOD_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("project_method"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": PROJECT_MODE_BY_ID, "label": "Theo Project ID (khuyến nghị)"},
                    {"value": PROJECT_MODE_BY_DEVICES, "label": "Theo danh sách Device IDs"}
                ]
            )
        )
    }
)

STEP_PROJECT_ID_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROJECT_ID): str
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
        self._project_method: str | None = None
        self._project_id: str | None = None
        self._device_types: list[int] | None = None

    def is_matching(self, other_flow: "ConfigFlow") -> bool:
        """Check if this config entry matches the current flow."""
        return hasattr(other_flow, 'domain') and other_flow.domain == DOMAIN

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
                except (aiohttp.ClientError, ValueError, KeyError) as err:
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
                return await self.async_step_project_method()

        return self.async_show_form(
            step_id="mode",
            data_schema=STEP_MODE_DATA_SCHEMA,
        )

    async def async_step_project_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the project method selection step."""
        if user_input is not None:
            self._project_method = user_input["project_method"]
            if self._project_method == PROJECT_MODE_BY_ID:
                return await self.async_step_project_id()
            else:  # PROJECT_MODE_BY_DEVICES
                return await self.async_step_project_devices()

        return self.async_show_form(
            step_id="project_method",
            data_schema=STEP_PROJECT_METHOD_DATA_SCHEMA,
        )

    async def async_step_project_id(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the project ID input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            project_id = user_input.get(CONF_PROJECT_ID, "").strip()

            # Validate input
            if not project_id:
                errors["base"] = "project_id_required"
            else:
                # Test API call with project ID
                try:
                    assert self._username is not None
                    assert self._password is not None
                    api = SmartSolarAPI(
                        username=self._username,
                        password=self._password,
                        hass=self.hass,
                    )
                    await api.login()
                    await api.get_project_metrics(project_id)
                    await api.close()
                    
                    # Success - save configuration
                    self._project_id = project_id
                    self._device_type = DEVICE_TYPE_MANH_QUAN  # Default for project mode
                    return await self._create_entry()
                    
                except SmartSolarAPIError as err:
                    if err.status_code == 404:
                        errors["base"] = "project_not_found"
                    else:
                        errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="project_id",
            data_schema=STEP_PROJECT_ID_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_project_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the project devices configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            manh_quan_ids = user_input.get("manh_quan_ids", "").strip()

            # Initialize variables
            all_devices: list[str] = []
            device_types: list[int] = []
            
            # Validate input
            if not manh_quan_ids:
                errors["base"] = "manh_quan_ids_required"
            else:
                # Parse device IDs and auto-calculate count
                manh_ids = [str(id.strip()) for id in manh_quan_ids.split(",") if id.strip()]
                manh_quan_count = len(manh_ids)  # Auto-calculate count
                
                if manh_quan_count == 0:
                    errors["base"] = "manh_quan_ids_required"
                else:
                    # No maximum limit - users can add as many devices as needed
                    all_devices.extend(manh_ids)
                    device_types.extend([DEVICE_TYPE_MANH_QUAN] * manh_quan_count)

            if not errors and all_devices and device_types:
                self._chipset_ids = all_devices
                self._device_types = device_types
                
                # Test the configuration
                try:
                    assert self._username is not None
                    assert self._password is not None
                    assert self._mode is not None
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
                except (aiohttp.ClientError, ValueError, KeyError) as err:
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
                        assert self._username is not None
                        assert self._password is not None
                        assert self._device_type is not None
                        assert self._mode is not None
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
                    except (aiohttp.ClientError, ValueError, KeyError) as err:
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

    async def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Assert required values are not None
        assert self._username is not None
        assert self._password is not None
        assert self._mode is not None
        assert self._device_type is not None
        
        # Create unique ID for this configuration
        if self._project_id:
            unique_id = f"{self._username}_{self._mode}_{self._device_type}_{self._project_id}"
        else:
            assert self._chipset_ids is not None
            unique_id = f"{self._username}_{self._mode}_{self._device_type}_{'_'.join(self._chipset_ids)}"
        
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        
        # Prepare data
        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_MODE: self._mode,
            CONF_DEVICE_TYPE: self._device_type,
        }
        
        if self._project_id:
            data[CONF_PROJECT_ID] = self._project_id
        else:
            data[CONF_CHIPSET_IDS] = self._chipset_ids
        
        return self.async_create_entry(
            title=f"SmartSolar MPPT ({self._mode.title()})",
            data=data,
        )






class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class DeviceNotFound(HomeAssistantError):
    """Error to indicate device not found."""
