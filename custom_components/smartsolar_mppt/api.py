"""SmartSolar API client."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    API_LOGIN_ENDPOINT,
    API_METRICS_ENDPOINT,
    TOKEN_REFRESH_DAYS_BEFORE_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)


class SmartSolarAPIError(Exception):
    """Exception raised for SmartSolar API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize SmartSolar API error."""
        super().__init__(message)
        self.status_code = status_code


class SmartSolarAPI:
    """SmartSolar API client."""

    def __init__(
        self,
        username: str,
        password: str,
        hass: HomeAssistant,
    ) -> None:
        """Initialize SmartSolar API client."""
        self._username = username
        self._password = password
        self._hass = hass
        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self) -> None:
        """Close the API session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._session.close())
            except (RuntimeError, asyncio.CancelledError):
                pass

    async def login(self) -> dict[str, Any]:
        """Login to SmartSolar API and get token."""
        session = await self._get_session()
        
        login_data = {
            "username": self._username,
            "password": self._password,
        }

        try:
            async with session.post(
                API_LOGIN_ENDPOINT,
                json=login_data,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._token = data.get("token")
                    
                    # Parse token expiry safely
                    expiration_str = data.get("expiration", "")
                    if expiration_str:
                        try:
                            # Handle different datetime formats
                            if expiration_str.endswith("Z"):
                                expiration_str = expiration_str.replace("Z", "+00:00")
                            self._token_expiry = datetime.fromisoformat(expiration_str)
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning("Could not parse token expiry: %s, using default 30 days", e)
                            self._token_expiry = dt_util.utcnow() + timedelta(days=30)
                    else:
                        # Default to 30 days if no expiry provided
                        self._token_expiry = dt_util.utcnow() + timedelta(days=30)
                    
                    _LOGGER.debug("Successfully logged in to SmartSolar API")
                    return data
                else:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Login failed with status %s: %s", 
                        response.status, 
                        error_text
                    )
                    raise SmartSolarAPIError(
                        f"Login failed: {error_text}", 
                        response.status
                    )
        except aiohttp.ClientError as err:
            _LOGGER.error("Login request failed: %s", err)
            raise SmartSolarAPIError(f"Login request failed: {err}") from err

    async def refresh_token_if_needed(self) -> None:
        """Refresh token if it's close to expiry."""
        if not self._token or not self._token_expiry:
            _LOGGER.debug("No token available, logging in")
            await self.login()
            return

        # Check if token expires within the refresh threshold
        refresh_threshold = dt_util.utcnow() + timedelta(
            days=TOKEN_REFRESH_DAYS_BEFORE_EXPIRY
        )
        
        if self._token_expiry <= refresh_threshold:
            _LOGGER.info("Token expires soon, refreshing...")
            await self.login()
        else:
            _LOGGER.debug("Token is still valid")

    async def get_metrics(
        self, 
        device_type: int, 
        chipset_ids: list[str],
        mode: str = "device"
    ) -> dict[str, Any]:
        """Get metrics from SmartSolar API."""
        await self.refresh_token_if_needed()

        if not self._token:
            raise SmartSolarAPIError("No valid token available")

        session = await self._get_session()
        
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            if mode == "device":
                # For device mode, use Device/Status endpoint
                device_guid = chipset_ids[0]
                url = f"{API_BASE_URL}/Device/Status?deviceGuid={device_guid}"
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Device API response: %s", data)
                        return data
                    else:
                        error_text = await response.text()
                        _LOGGER.error("Device API failed with status %s: %s", response.status, error_text)
                        raise SmartSolarAPIError(f"Device API failed: {error_text}", response.status)
            else:
                # For project mode, use Metric/SynthesisMetrics endpoint
                params = {"deviceType": device_type}
                # Add multiple deviceGuids parameters (deviceGuids=547611&deviceGuids=14756976)
                for chipset_id in chipset_ids:
                    params["deviceGuids"] = chipset_id

                _LOGGER.warning("Project mode API call - URL: %s, params: %s", API_METRICS_ENDPOINT, params)
                async with session.get(
                    API_METRICS_ENDPOINT,
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Normalize deviceGuid to string for consistent matching
                        if "deviceLogs" in data:
                            for device_log in data["deviceLogs"]:
                                if "deviceGuid" in device_log:
                                    device_log["deviceGuid"] = str(device_log["deviceGuid"])
                        
                        _LOGGER.debug("Successfully fetched metrics from SmartSolar API")
                        return data
                    elif response.status == 404:
                        error_text = await response.text()
                        _LOGGER.error("Device not found (404): %s", error_text)
                        raise SmartSolarAPIError(
                            "Device not found. Please check your ChipsetId(s).", 
                            404
                        )
                    else:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Get metrics failed with status %s: %s", 
                            response.status, 
                            error_text
                        )
                        raise SmartSolarAPIError(
                            f"Get metrics failed: {error_text}", 
                            response.status
                        )
        except aiohttp.ClientError as err:
            _LOGGER.error("Get metrics request failed: %s", err)
            raise SmartSolarAPIError(f"Get metrics request failed: {err}") from err

    async def test_connection(self) -> bool:
        """Test API connection by attempting login."""
        try:
            await self.login()
            return True
        except SmartSolarAPIError:
            return False

    @property
    def token(self) -> str | None:
        """Get current token."""
        return self._token

    @property
    def token_expiry(self) -> datetime | None:
        """Get token expiry time."""
        return self._token_expiry
