"""SmartSolar API client."""

from __future__ import annotations

import asyncio
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
    RETRY_BACKOFF_FACTOR,
    RETRY_MAX_ATTEMPTS,
    TOKEN_REFRESH_DAYS_BEFORE_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)


class SmartSolarAPIError(Exception):
    """Exception raised for SmartSolar API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize SmartSolar API error."""
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class SmartSolarAuthenticationError(SmartSolarAPIError):
    """Authentication failed."""


class SmartSolarConnectionError(SmartSolarAPIError):
    """Connection error."""


class SmartSolarNotFoundError(SmartSolarAPIError):
    """Resource not found."""


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
                    if response.status == 401:
                        raise SmartSolarAuthenticationError(
                            f"Invalid credentials: {error_text}",
                            response.status
                        )
                    else:
                        raise SmartSolarAPIError(
                            f"Login failed: {error_text}",
                            response.status
                        )
        except aiohttp.ClientError as err:
            _LOGGER.error("Login request failed: %s", err)
            raise SmartSolarConnectionError(f"Login request failed: {err}") from err

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Make an HTTP request with exponential backoff retry.

        Only retries on transient errors (ClientError, TimeoutError).
        Does NOT retry on auth errors (401) or not-found (404).
        """
        last_exception: Exception | None = None
        for attempt in range(RETRY_MAX_ATTEMPTS):
            try:
                session = await self._get_session()
                response = await session.request(method, url, **kwargs)
                # Don't retry auth failures or not-found — fail fast
                if response.status in (401, 404):
                    return response
                if response.status < 500:
                    return response
                # Server error (5xx) — retry
                last_exception = SmartSolarAPIError(
                    f"Server error {response.status}", response.status
                )
            except (TimeoutError, aiohttp.ClientError) as err:
                last_exception = err

            if attempt < RETRY_MAX_ATTEMPTS - 1:
                delay = RETRY_BACKOFF_FACTOR ** attempt
                _LOGGER.warning(
                    "Request attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1, RETRY_MAX_ATTEMPTS, last_exception, delay,
                )
                await asyncio.sleep(delay)

        if isinstance(last_exception, SmartSolarAPIError):
            raise last_exception
        raise SmartSolarConnectionError(
            f"Request failed after {RETRY_MAX_ATTEMPTS} attempts: {last_exception}"
        ) from last_exception

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

    async def get_project_metrics(self, project_id: str) -> dict[str, Any]:
        """Get metrics by Project ID."""
        await self.refresh_token_if_needed()

        if not self._token:
            raise SmartSolarAPIError("No valid token available")

        session = await self._get_session()

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            url = f"{API_BASE_URL}/Metric/ProjectMetrics"
            params = {"projectId": project_id}
            _LOGGER.debug("Project metrics API call - URL: %s, projectId: %s", url, project_id)

            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Normalize deviceGuid to string for consistent matching
                    if "deviceLogs" in data:
                        for device_log in data["deviceLogs"]:
                            if "deviceGuid" in device_log:
                                device_log["deviceGuid"] = str(device_log["deviceGuid"])

                    _LOGGER.debug("Successfully fetched project metrics from SmartSolar API")
                    return data
                elif response.status == 404:
                    error_text = await response.text()
                    _LOGGER.error("Project not found (404): %s", error_text)
                    raise SmartSolarNotFoundError(
                        "Project not found. Please check your Project ID.",
                        404
                    )
                else:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Get project metrics failed with status %s: %s",
                        response.status,
                        error_text
                    )
                    raise SmartSolarAPIError(
                        f"Get project metrics failed: {error_text}",
                        response.status
                    )
        except aiohttp.ClientError as err:
            _LOGGER.error("Get project metrics request failed: %s", err)
            raise SmartSolarConnectionError(f"Get project metrics request failed: {err}") from err

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
                # For device mode, use Device/Status endpoint with params
                device_guid = chipset_ids[0]
                url = f"{API_BASE_URL}/Device/Status"
                params = {"deviceGuid": device_guid}
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Device API response received successfully")
                        return data
                    else:
                        error_text = await response.text()
                        _LOGGER.error("Device API failed with status %s: %s", response.status, error_text)
                        raise SmartSolarAPIError(f"Device API failed: {error_text}", response.status)
            else:
                # For project mode, use Metric/SynthesisMetrics endpoint
                # aiohttp params= handles multiple deviceGuids values correctly
                params: list[tuple[str, str]] = [("deviceType", str(device_type))]
                for chipset_id in chipset_ids:
                    params.append(("deviceGuids", chipset_id))

                _LOGGER.debug("Project mode API call - URL: %s, params: %s",
                              API_METRICS_ENDPOINT, params)

                async with session.get(
                    API_METRICS_ENDPOINT,
                    headers=headers,
                    params=params,
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

    async def get_device_status(self, device_guid: str) -> dict[str, Any]:
        """Get device status including MQTT connection credentials.

        Calls GET /Device/Status?deviceGuid={guid} and returns the full
        response, which includes the ``mqttConnection`` object containing
        MQTT broker, username, password (base64), and topic.
        """
        await self.refresh_token_if_needed()

        if not self._token:
            raise SmartSolarAPIError("No valid token available")

        session = await self._get_session()

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            url = f"{API_BASE_URL}/Device/Status"
            params = {"deviceGuid": device_guid}
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(
                        "Device status for %s: online=%s, has_mqtt=%s",
                        device_guid, data.get("isOnline"),
                        "mqttConnection" in data,
                    )
                    return data
                else:
                    error_text = await response.text()
                    raise SmartSolarAPIError(
                        f"Device status failed: {error_text}",
                        response.status,
                    )
        except aiohttp.ClientError as err:
            raise SmartSolarConnectionError(
                f"Device status request failed: {err}"
            ) from err

    async def test_connection(self) -> bool:
        """Test API connection by attempting login."""
        try:
            await self.login()
            return True
        except SmartSolarAPIError:
            return False
        finally:
            await self.close()

    @property
    def token(self) -> str | None:
        """Get current token."""
        return self._token

    @property
    def token_expiry(self) -> datetime | None:
        """Get token expiry time."""
        return self._token_expiry
