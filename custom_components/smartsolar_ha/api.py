"""SmartSolar API client."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    API_DEVICE_STATUS_ENDPOINT,
    API_LOGIN_ENDPOINT,
    API_METRICS_ENDPOINT,
    API_PROJECT_METRICS_ENDPOINT,
    RETRY_BACKOFF_FACTOR,
    RETRY_MAX_ATTEMPTS,
    TOKEN_REFRESH_DAYS_BEFORE_EXPIRY,
)
from .helpers import device_logs

_LOGGER = logging.getLogger(__name__)

# Token lifetime used when the API does not report an expiry.
DEFAULT_TOKEN_LIFETIME = timedelta(days=30)

# Statuses below 500 that are still worth retrying: the server is asking the
# client to come back later rather than reporting a permanent failure.
RETRYABLE_STATUSES = frozenset({408, 429})


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


class _BufferedResponse:
    """A fully-read HTTP response.

    ``_request_with_retry()`` uses ``async with session.request(...)`` so the
    connection is released before a possible retry; reading the body inside the
    block means callers can no longer use ``aiohttp.ClientResponse`` helpers.
    This thin wrapper restores the small surface the client needs.
    """

    __slots__ = ("status", "_body")

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        """Return the raw body."""
        return self._body

    async def text(self) -> str:
        """Return the decoded body."""
        return self._body.decode("utf-8", errors="replace")

    async def json(self) -> Any:
        """Return the body decoded as JSON."""
        return json.loads(self._body.decode("utf-8"))


async def _json_object(response: Any, context: str) -> dict[str, Any]:
    """Decode a response body that is expected to be a JSON object.

    ``ClientResponse.json()`` is typed ``Any``: an unexpected or truncated
    payload (a bare list, a plain string, invalid JSON) used to escape this
    module as ``AttributeError: 'list' object has no attribute 'get'`` from
    deep inside a caller, which no handler classified. Normalize every such
    case into :class:`SmartSolarAPIError` instead.

    ``aiohttp.ClientError`` (wrong content type, dropped connection) is left to
    propagate so callers keep classifying it as a connection failure.
    """
    try:
        payload = await response.json()
    except ValueError as err:  # json.JSONDecodeError
        raise SmartSolarAPIError(f"{context}: response body is not valid JSON: {err}") from err
    if not isinstance(payload, dict):
        raise SmartSolarAPIError(f"{context}: expected a JSON object, got {type(payload).__name__}")
    return payload


def _parse_expiration(expiration_str: Any) -> datetime | None:
    """Parse the API ``expiration`` field into a timezone-aware datetime.

    The API returns an ISO-8601 string (usually with a ``Z`` suffix). If the
    payload has no timezone we assume UTC: mixing naive and aware datetimes in
    ``refresh_token_if_needed()`` raises ``TypeError`` and would stop token
    refreshes entirely.
    """
    if not expiration_str or not isinstance(expiration_str, str):
        return None
    value = expiration_str.strip()
    if value.endswith(("Z", "z")):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError, TypeError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


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
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
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
                    payload = await _json_object(response, "Login")
                    self._token = payload.get("token")
                    if not self._token:
                        raise SmartSolarAPIError("Login succeeded but no token was returned")

                    # Parse token expiry safely
                    self._token_expiry = _parse_expiration(payload.get("expiration"))
                    if self._token_expiry is None:
                        _LOGGER.warning(
                            "Could not parse token expiry (%r), assuming %s days",
                            payload.get("expiration"),
                            DEFAULT_TOKEN_LIFETIME.days,
                        )
                        self._token_expiry = dt_util.utcnow() + DEFAULT_TOKEN_LIFETIME

                    _LOGGER.debug("Successfully logged in to SmartSolar API")
                    return payload

                error_text = await response.text()
                if response.status >= 500 or response.status in RETRYABLE_STATUSES:
                    # DEBUG: the coordinator owns the user-visible outage report.
                    _LOGGER.debug("Login failed with status %s: %s", response.status, error_text)
                else:
                    _LOGGER.error("Login failed with status %s: %s", response.status, error_text)
                if response.status == 401:
                    raise SmartSolarAuthenticationError(f"Invalid credentials: {error_text}", response.status)
                raise SmartSolarAPIError(f"Login failed: {error_text}", response.status)
        except (TimeoutError, aiohttp.ClientError) as err:
            # DEBUG: the coordinator owns the user-visible outage report.
            _LOGGER.debug("Login request failed: %s", err)
            raise SmartSolarConnectionError(f"Login request failed: {err}") from err

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> _BufferedResponse:
        """Make an HTTP request with exponential backoff retry.

        Retries transient failures only: aiohttp/timeout errors, 5xx server
        responses, and the two "try again later" statuses (408 request timeout,
        429 rate limited). Auth failures (401) and not-found (404) are returned
        to the caller immediately so error handling stays fast.

        The returned response is **already read and released** — this method
        always buffers the body so a retry cannot reuse a consumed response.
        """
        last_exception: Exception | None = None
        for attempt in range(RETRY_MAX_ATTEMPTS):
            try:
                session = await self._get_session()
                async with session.request(method, url, **kwargs) as response:
                    # Fail fast on auth/not-found and on any other non-retryable
                    # status; retry 5xx plus 408/429.
                    if response.status < 500 and response.status not in RETRYABLE_STATUSES:
                        # Read the body while the connection is still open.
                        return _BufferedResponse(response.status, await response.read())
                    last_exception = SmartSolarAPIError(
                        f"Server error {response.status}",
                        response.status,
                    )
            except (TimeoutError, aiohttp.ClientError) as err:
                last_exception = err

            if attempt < RETRY_MAX_ATTEMPTS - 1:
                delay = RETRY_BACKOFF_FACTOR**attempt
                # DEBUG, not WARNING: the coordinator reports the outage once
                # (see _async_update_data). At WARNING this wrote two lines per
                # poll for as long as the cloud stayed down — a full day of an
                # outage produced tens of thousands of identical warnings.
                _LOGGER.debug(
                    "Request attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    RETRY_MAX_ATTEMPTS,
                    last_exception,
                    delay,
                )
                await asyncio.sleep(delay)

        if isinstance(last_exception, SmartSolarAPIError):
            raise last_exception
        raise SmartSolarConnectionError(
            f"Request failed after {RETRY_MAX_ATTEMPTS} attempts: {last_exception}"
        ) from last_exception

    async def _authed_get(self, url: str, params: Any) -> dict[str, Any]:
        """GET a JSON document with the current token, retrying transient errors.

        Returns the decoded JSON body. Raises the appropriate
        :class:`SmartSolarAPIError` subclass for API-level failures.
        """
        await self.refresh_token_if_needed()

        if not self._token:
            raise SmartSolarAPIError("No valid token available")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        _LOGGER.debug("API GET %s params=%s", url, params)

        response = await self._request_with_retry("GET", url, headers=headers, params=params)

        if response.status == 200:
            return await _json_object(response, f"GET {url}")
        if response.status == 404:
            raise SmartSolarNotFoundError(f"Not found: {url}", 404)
        if response.status == 401:
            # The server rejected the token: drop it so the next call logs in
            # again. ``refresh_token_if_needed()`` only re-authenticates when
            # the cached expiry is near, and the API hands out ~30-day tokens —
            # keeping the stale one meant every later poll failed with 401 until
            # Home Assistant was restarted.
            _LOGGER.warning("API rejected the cached token for %s — will log in again", url)
            self._token = None
            self._token_expiry = None
            raise SmartSolarAuthenticationError("Token rejected by API (401)", 401)

        error_text = await response.text()
        raise SmartSolarAPIError(
            f"Request to {url} failed with status {response.status}: {error_text}",
            response.status,
        )

    @staticmethod
    def _normalize_device_guids(data: dict[str, Any]) -> dict[str, Any]:
        """Normalize deviceLogs[].deviceGuid to str for consistent matching.

        ``deviceLogs`` is third-party JSON and has been observed absent, ``null``
        and (defensively) a scalar. Iterating the raw field raised ``TypeError``
        for the scalar case and failed the whole poll, so the shared
        ``helpers.device_logs()`` guard is used here as well as in the
        coordinator, the sensors and diagnostics.
        """
        for device_log in device_logs(data):
            if isinstance(device_log, dict) and device_log.get("deviceGuid") is not None:
                device_log["deviceGuid"] = str(device_log["deviceGuid"])
        return data

    async def refresh_token_if_needed(self) -> None:
        """Refresh token if it's close to expiry."""
        if not self._token or not self._token_expiry:
            _LOGGER.debug("No token available, logging in")
            await self.login()
            return

        # Check if token expires within the refresh threshold
        refresh_threshold = dt_util.utcnow() + timedelta(days=TOKEN_REFRESH_DAYS_BEFORE_EXPIRY)

        if self._token_expiry <= refresh_threshold:
            _LOGGER.debug("Token expires soon, refreshing...")
            await self.login()
        else:
            _LOGGER.debug("Token is still valid")

    async def get_project_metrics(self, project_id: str) -> dict[str, Any]:
        """Get metrics by Project ID."""
        data = await self._authed_get(
            API_PROJECT_METRICS_ENDPOINT,
            {"projectId": project_id},
        )
        _LOGGER.debug("Successfully fetched project metrics from SmartSolar API")
        return self._normalize_device_guids(data)

    async def get_metrics(
        self,
        device_type: int,
        chipset_ids: list[str],
        mode: str = "device",
    ) -> dict[str, Any]:
        """Get metrics from SmartSolar API."""
        if not chipset_ids:
            raise SmartSolarAPIError("No chipset_ids provided")

        if mode == "device":
            # For device mode, use Device/Status endpoint with params
            data = await self._authed_get(
                API_DEVICE_STATUS_ENDPOINT,
                {"deviceGuid": chipset_ids[0]},
            )
            _LOGGER.debug("Device API response received successfully")
            return self._normalize_device_guids(data)

        # For project mode, use Metric/SynthesisMetrics endpoint
        # aiohttp params= handles multiple deviceGuids values correctly
        params: list[tuple[str, str]] = [("deviceType", str(device_type))]
        params.extend(("deviceGuids", chipset_id) for chipset_id in chipset_ids)

        data = await self._authed_get(API_METRICS_ENDPOINT, params)
        _LOGGER.debug("Successfully fetched metrics from SmartSolar API")
        return self._normalize_device_guids(data)

    async def get_device_status(self, device_guid: str) -> dict[str, Any]:
        """Get device status including MQTT connection credentials.

        Calls GET /Device/Status?deviceGuid={guid} and returns the full
        response, which includes the ``mqttConnection`` object containing
        MQTT broker, username, password (base64), and topic.
        """
        data = await self._authed_get(
            API_DEVICE_STATUS_ENDPOINT,
            {"deviceGuid": device_guid},
        )
        _LOGGER.debug(
            "Device status for %s: online=%s, has_mqtt=%s",
            device_guid,
            data.get("isOnline"),
            "mqttConnection" in data,
        )
        return data

    async def test_connection(self) -> bool:
        """Test API connection by attempting login."""
        try:
            await self.login()
            return True
        except SmartSolarAuthenticationError:
            raise
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
