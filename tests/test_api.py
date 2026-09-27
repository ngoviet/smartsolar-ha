"""Tests for api.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.smartsolar_ha.api import (
    SmartSolarAPI,
    SmartSolarAPIError,
    SmartSolarAuthenticationError,
    SmartSolarConnectionError,
    SmartSolarNotFoundError,
    _parse_expiration,
)
from custom_components.smartsolar_ha.const import RETRY_MAX_ATTEMPTS


class _FakeResponse:
    """Stand-in for aiohttp.ClientResponse used inside _request_with_retry."""

    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    async def read(self) -> bytes:
        return self._body

    async def json(self) -> Any:
        return json.loads(self._body.decode())

    async def text(self) -> str:
        return self._body.decode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeSession:
    """Returns queued responses; exceptions may be queued too."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.requests = 0

    def request(self, _method: str, _url: str, **_kwargs: Any) -> Any:
        self.requests += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        status, payload = result
        return _FakeResponse(status, payload)

    def post(self, _url: str, **_kwargs: Any) -> Any:
        """Stand-in for session.post() used by login()."""
        return self.request("POST", _url)


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
        dt = datetime(2026, 1, 1, tzinfo=UTC)
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
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)
        api.login = AsyncMock()
        await api.refresh_token_if_needed()
        api.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_when_expiring_soon(self):
        """refresh_token_if_needed calls login when token expires within 7 days."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._token = "valid-token"
        api._token_expiry = datetime.now(UTC) + timedelta(days=3)
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

    @pytest.mark.asyncio
    async def test_test_connection_propagates_auth_error(self):
        """test_connection re-raises SmartSolarAuthenticationError for a 401."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api.login = AsyncMock(side_effect=SmartSolarAuthenticationError("bad", 401))
        with pytest.raises(SmartSolarAuthenticationError):
            await api.test_connection()

    @pytest.mark.asyncio
    async def test_no_token_when_login_returns_no_token(self):
        """A 200 login without a token is an error, not a silent success."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=_FakeSession([(200, {})]))
        with pytest.raises(SmartSolarAPIError, match="no token"):
            await api.login()


class TestParseExpiration:
    """Tests for the token-expiry parser.

    Mixing naive and tz-aware datetimes raises TypeError, so a naive value from
    the API used to break ``refresh_token_if_needed`` completely.
    """

    def test_z_suffix_is_utc_aware(self):
        parsed = _parse_expiration("2026-10-27T15:14:48Z")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_offset_is_preserved(self):
        parsed = _parse_expiration("2026-10-27T15:14:48+07:00")
        assert parsed is not None
        assert parsed.utcoffset() == timedelta(hours=7)

    def test_naive_string_is_assumed_utc(self):
        parsed = _parse_expiration("2026-10-27T15:14:48")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    @pytest.mark.parametrize("value", [None, "", "not-a-date", 12345, {}])
    def test_invalid_values_return_none(self, value):
        assert _parse_expiration(value) is None

    @pytest.mark.asyncio
    async def test_naive_expiry_does_not_break_refresh(self):
        """A naive expiry must still compare against an aware utcnow()."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._token = "t"
        api._token_expiry = _parse_expiration("2026-10-27T15:14:48")
        api.login = AsyncMock()
        await api.refresh_token_if_needed()  # must not raise TypeError
        assert api.login.await_count in (0, 1)


class TestRequestRetry:
    """Tests for _request_with_retry and its use by the public methods."""

    @pytest.mark.asyncio
    async def test_retries_on_server_error_then_succeeds(self):
        """5xx responses are retried with backoff until one succeeds."""
        session = _FakeSession([(503, {"e": 1}), (502, {"e": 2}), (200, {"ok": True})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        with patch("custom_components.smartsolar_ha.api.asyncio.sleep", new=AsyncMock()) as sleep:
            response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 200
        assert await response.json() == {"ok": True}
        assert session.requests == 3
        assert sleep.await_count == 2  # one wait between each of the 3 attempts

    @pytest.mark.asyncio
    async def test_gives_up_after_max_attempts(self):
        """Persistent 5xx raises SmartSolarAPIError with the server status."""
        session = _FakeSession([(500, {}), (500, {}), (500, {})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        with (
            patch("custom_components.smartsolar_ha.api.asyncio.sleep", new=AsyncMock()),
            pytest.raises(SmartSolarAPIError) as err,
        ):
            await api._request_with_retry("GET", "https://example.invalid/x")

        assert err.value.status_code == 500
        assert session.requests == RETRY_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self):
        """Network errors are retried."""
        session = _FakeSession([aiohttp.ClientConnectionError("boom"), (200, {"ok": True})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        with patch("custom_components.smartsolar_ha.api.asyncio.sleep", new=AsyncMock()):
            response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 200
        assert session.requests == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_404(self):
        """404 is returned immediately so callers can fail fast."""
        session = _FakeSession([(404, {"error": "nope"})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 404
        assert session.requests == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_401(self):
        """401 is returned immediately."""
        session = _FakeSession([(401, {})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 401
        assert session.requests == 1

    @pytest.mark.asyncio
    async def test_project_404_raises_not_found(self):
        """get_project_metrics turns a 404 into SmartSolarNotFoundError."""
        session = _FakeSession([(404, {"error": "missing"})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)
        api._token = "t"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        with pytest.raises(SmartSolarNotFoundError) as err:
            await api.get_project_metrics("9999")
        assert err.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_metrics_without_chipset_ids_raises(self):
        """Empty chipset_ids fails before touching the network."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        with pytest.raises(SmartSolarAPIError, match="chipset_ids"):
            await api.get_metrics(device_type=2, chipset_ids=[], mode="device")

    @pytest.mark.asyncio
    async def test_get_metrics_normalizes_device_guid_to_str(self):
        """deviceGuid values are coerced to str for stable matching."""
        session = _FakeSession([(200, {"deviceLogs": [{"deviceGuid": 547611}]})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)
        api._token = "t"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        data = await api.get_metrics(device_type=2, chipset_ids=["547611"], mode="project")
        assert data["deviceLogs"][0]["deviceGuid"] == "547611"


class _RawBodySession:
    """Session whose responses carry a literal (possibly non-JSON) body."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.requests = 0

    def _response(self) -> Any:
        session = self
        session.requests += 1

        class _Resp:
            def __init__(self) -> None:
                self.status = session.status

            async def read(self) -> bytes:
                return session._body

            async def text(self) -> str:
                return session._body.decode(errors="replace")

            async def json(self) -> Any:
                return json.loads(session._body.decode())

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *exc: Any) -> bool:
                return False

        return _Resp()

    def post(self, *_args: Any, **_kwargs: Any) -> Any:
        return self._response()

    def request(self, *_args: Any, **_kwargs: Any) -> Any:
        return self._response()


class TestNonObjectResponses:
    """A payload that is not a JSON object must be an API error.

    ``ClientResponse.json()`` is typed ``Any``; a bare list used to escape as
    ``AttributeError: 'list' object has no attribute 'get'`` from inside a
    caller, and no handler classified it.
    """

    @pytest.mark.asyncio
    async def test_login_with_list_body_raises_api_error(self):
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=_RawBodySession(200, b'["a", "b"]'))

        with pytest.raises(SmartSolarAPIError, match="expected a JSON object"):
            await api.login()

    @pytest.mark.asyncio
    async def test_login_with_invalid_json_raises_api_error(self):
        """A JSON content type with an HTML body used to raise JSONDecodeError."""
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=_RawBodySession(200, b"<html>bad gateway</html>"))

        with pytest.raises(SmartSolarAPIError, match="not valid JSON"):
            await api.login()

    @pytest.mark.asyncio
    async def test_get_metrics_with_list_body_raises_api_error(self):
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=_RawBodySession(200, b"[1, 2, 3]"))
        api._token = "t"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        with pytest.raises(SmartSolarAPIError, match="expected a JSON object"):
            await api.get_metrics(device_type=2, chipset_ids=["547611"], mode="project")

    @pytest.mark.asyncio
    async def test_get_project_metrics_with_invalid_json_raises_api_error(self):
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=_RawBodySession(200, b"not json at all"))
        api._token = "t"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        with pytest.raises(SmartSolarAPIError, match="not valid JSON"):
            await api.get_project_metrics("1072")


class TestTokenInvalidationOn401:
    """A token the server rejects must be dropped, not cached forever.

    Tokens live ~30 days, so ``refresh_token_if_needed()`` would keep the stale
    token and every later poll failed with 401 until Home Assistant restarted.
    """

    @pytest.mark.asyncio
    async def test_401_clears_the_cached_token(self):
        session = _FakeSession([(401, {"error": "revoked"})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)
        api._token = "stale-token"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        with pytest.raises(SmartSolarAuthenticationError):
            await api.get_project_metrics("1072")

        assert api.token is None
        assert api.token_expiry is None

    @pytest.mark.asyncio
    async def test_next_call_authenticates_again(self):
        """The dropped token makes the following call log in and succeed."""
        session = _FakeSession(
            [
                (401, {"error": "revoked"}),
                (200, {"token": "fresh-token", "expiration": "2027-01-01T00:00:00Z"}),
                (200, {"synthesisStreams": [], "deviceLogs": []}),
            ]
        )
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)
        api._token = "stale-token"
        api._token_expiry = datetime.now(UTC) + timedelta(days=30)

        with pytest.raises(SmartSolarAuthenticationError):
            await api.get_project_metrics("1072")

        data = await api.get_project_metrics("1072")

        assert api.token == "fresh-token"
        assert data == {"synthesisStreams": [], "deviceLogs": []}
        assert session.requests == 3  # 401, login POST, retried GET


class TestRetryableStatuses:
    """408/429 mean "come back later", so they are retried like a 5xx."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [408, 429])
    async def test_rate_limit_and_timeout_are_retried(self, status):
        session = _FakeSession([(status, {"error": "slow down"}), (200, {"ok": True})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        with patch("custom_components.smartsolar_ha.api.asyncio.sleep", new=AsyncMock()) as sleep:
            response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 200
        assert session.requests == 2
        assert sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_client_error_is_not_retried(self):
        """400 is a permanent failure — retrying it just adds latency."""
        session = _FakeSession([(400, {"error": "bad request"})])
        api = SmartSolarAPI("user", "pass", MagicMock())
        api._get_session = AsyncMock(return_value=session)

        response = await api._request_with_retry("GET", "https://example.invalid/x")

        assert response.status == 400
        assert session.requests == 1
