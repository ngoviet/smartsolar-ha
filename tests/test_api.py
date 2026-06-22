"""Tests for api.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.smartsolar_mppt.api import (
    SmartSolarAPI,
    SmartSolarAPIError,
    SmartSolarAuthenticationError,
    SmartSolarConnectionError,
    SmartSolarNotFoundError,
)


class TestSmartSolarAPIError:
    """Tests for SmartSolarAPIError hierarchy."""

    def test_base_error(self):
        err = SmartSolarAPIError("test message", 500)
        assert err.message == "test message"
        assert err.status_code == 500
        assert str(err) == "test message"

    def test_auth_error(self):
        err = SmartSolarAuthenticationError("bad credentials", 401)
        assert err.status_code == 401
        assert isinstance(err, SmartSolarAPIError)

    def test_connection_error(self):
        err = SmartSolarConnectionError("timeout")
        assert isinstance(err, SmartSolarAPIError)

    def test_not_found_error(self):
        err = SmartSolarNotFoundError("not found", 404)
        assert err.status_code == 404


class TestSmartSolarAPI:
    """Tests for SmartSolarAPI client."""

    def test_init_stores_credentials(self):
        """Init stores username, password, and hass."""
        hass = MagicMock()
        api = SmartSolarAPI("user", "pass", hass)
        assert api._username == "user"
        assert api._password == "pass"
        assert api._session is None
        assert api._token is None
        assert api._token_expiry is None

    def test_token_property(self):
        """token property returns current token."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        assert api.token is None
        api._token = "abc123"
        assert api.token == "abc123"

    def test_token_expiry_property(self):
        """token_expiry property returns current expiry."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        assert api.token_expiry is None
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        api._token_expiry = dt
        assert api.token_expiry == dt

    @pytest.mark.asyncio
    async def test_get_session_creates_new(self):
        """_get_session creates new session when None."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        session = await api._get_session()
        assert session is not None
        assert isinstance(session, aiohttp.ClientSession)
        await api.close()

    @pytest.mark.asyncio
    async def test_get_session_reuses_existing(self):
        """_get_session reuses existing session."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        s1 = await api._get_session()
        s2 = await api._get_session()
        assert s1 is s2
        await api.close()

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_when_no_token(self):
        """refresh_token_if_needed calls login when no token."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.login = AsyncMock()
        await api.refresh_token_if_needed()
        api.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_when_token_valid(self):
        """refresh_token_if_needed does nothing when token is valid."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._token = "valid-token"
        api._token_expiry = datetime.now(timezone.utc) + timedelta(days=30)
        api.login = AsyncMock()
        await api.refresh_token_if_needed()
        api.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_when_expiring_soon(self):
        """refresh_token_if_needed calls login when token expires within 7 days."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._token = "valid-token"
        api._token_expiry = datetime.now(timezone.utc) + timedelta(days=3)
        api.login = AsyncMock()
        await api.refresh_token_if_needed()
        api.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_metrics_no_token(self):
        """get_metrics raises SmartSolarAPIError when no token."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.refresh_token_if_needed = AsyncMock()
        with pytest.raises(SmartSolarAPIError, match="No valid token"):
            await api.get_metrics(device_type=2, chipset_ids=["123"], mode="device")

    @pytest.mark.asyncio
    async def test_get_project_metrics_no_token(self):
        """get_project_metrics raises SmartSolarAPIError when no token."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.refresh_token_if_needed = AsyncMock()
        with pytest.raises(SmartSolarAPIError, match="No valid token"):
            await api.get_project_metrics("1072")

    @pytest.mark.asyncio
    async def test_close(self):
        """close closes session and sets to None."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        session = await api._get_session()
        await api.close()
        assert api._session is None
        assert session.closed

    @pytest.mark.asyncio
    async def test_close_when_already_closed(self):
        """close is safe to call when session is already None."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        await api.close()  # Should not raise
        assert api._session is None

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """test_connection returns True on successful login."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.login = AsyncMock()
        result = await api.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """test_connection returns False on login failure."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.login = AsyncMock(side_effect=SmartSolarAPIError("fail"))
        result = await api.test_connection()
        assert result is False
