"""Tests for config_flow.py handlers.

The config flow is driven through its real async step methods. ``ConfigFlow``
cannot be constructed normally outside Home Assistant's flow manager, so the
instance is created with ``object.__new__`` and the attributes the steps use
(``hass``, ``context``, the ``_async_show_form``/``_async_create_entry``
helpers) are supplied by hand.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.smartsolar_ha.api import (
    SmartSolarAPIError,
    SmartSolarAuthenticationError,
)
from custom_components.smartsolar_ha.config_flow import SmartSolarConfigFlow

STEP_RESULT = {"type": "form", "step_id": "test", "errors": {}}


def make_entry(data):
    """A config entry stand-in whose ``data`` mutation we can observe."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = dict(data)
    return entry


def make_flow(*, api=None):
    """Build a SmartSolarConfigFlow instance with stubbed HA plumbing."""
    flow = object.__new__(SmartSolarConfigFlow)
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = None
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.context = {"entry_id": "entry-1"}
    flow._async_show_form = lambda **kwargs: {"type": "form", **kwargs}  # type: ignore[method-assign]
    flow._async_create_entry = lambda **kwargs: {"type": "create_entry", **kwargs}  # type: ignore[method-assign]
    flow._async_abort = lambda **kwargs: {"type": "abort", **kwargs}  # type: ignore[method-assign]
    flow.async_set_unique_id = AsyncMock()  # type: ignore[method-assign]
    flow._abort_if_unique_id_configured = MagicMock()  # type: ignore[method-assign]
    flow._get_api = MagicMock(return_value=api)  # type: ignore[method-assign]
    flow._close_api = AsyncMock()  # type: ignore[method-assign]
    flow._username = None
    flow._password = None
    flow._mode = None
    flow._device_type = None
    flow._chipset_ids = None
    flow._project_method = None
    flow._project_id = None
    flow._api = None
    flow._api_username = None
    flow._api_password = None
    return flow


class _FakeAPIContext:
    """Replace SmartSolarAPI inside config_flow for one test."""

    def __init__(self, **methods):
        self._methods = methods
        self._original = None
        self.instance = MagicMock()

    def __enter__(self):
        from custom_components.smartsolar_ha import config_flow

        for name, value in self._methods.items():
            setattr(self.instance, name, value)
        self.instance.close = AsyncMock()
        self._original = config_flow.SmartSolarAPI
        config_flow.SmartSolarAPI = MagicMock(return_value=self.instance)  # type: ignore[assignment]
        return self.instance

    def __exit__(self, *exc):
        from custom_components.smartsolar_ha import config_flow

        config_flow.SmartSolarAPI = self._original  # type: ignore[assignment]
        return False


class TestUserStep:
    """Credential validation and error mapping."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("username", "password", "expected"),
        [
            ("", "pw", "username_required"),
            ("   ", "pw", "username_required"),
            ("user", "", "password_required"),
            ("user", "   ", "password_required"),
        ],
    )
    async def test_blank_fields_are_rejected(self, username, password, expected):
        flow = make_flow(api=MagicMock())
        result = await flow.async_step_user({"username": username, "password": password})
        assert result["errors"]["base"] == expected

    @pytest.mark.asyncio
    async def test_valid_credentials_advance_to_mode(self):
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=True)
        flow = make_flow(api=api)
        flow.async_step_mode = AsyncMock(return_value=STEP_RESULT)  # type: ignore[method-assign]

        result = await flow.async_step_user({"username": "u", "password": "p"})

        assert result is STEP_RESULT
        # test_connection() closes the session, so the cached client is dropped
        assert flow._api is None

    @pytest.mark.asyncio
    async def test_unreachable_api_reports_cannot_connect(self):
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=False)
        flow = make_flow(api=api)
        result = await flow.async_step_user({"username": "u", "password": "p"})
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_401_reports_invalid_credentials(self):
        api = MagicMock()
        api.test_connection = AsyncMock(side_effect=SmartSolarAuthenticationError("bad", 401))
        flow = make_flow(api=api)
        result = await flow.async_step_user({"username": "u", "password": "p"})
        assert result["errors"]["base"] == "invalid_credentials"

    @pytest.mark.asyncio
    async def test_500_reports_cannot_connect(self):
        api = MagicMock()
        api.test_connection = AsyncMock(side_effect=SmartSolarAPIError("boom", 500))
        flow = make_flow(api=api)
        result = await flow.async_step_user({"username": "u", "password": "p"})
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_failing_user_step_closes_api_session(self):
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=False)
        api.close = AsyncMock()
        flow = make_flow(api=api)
        flow._api = api
        flow._close_api = SmartSolarConfigFlow._close_api.__get__(flow)  # type: ignore[method-assign]

        result = await flow.async_step_user({"username": "u", "password": "p"})

        assert result["errors"]["base"] == "cannot_connect"
        api.close.assert_awaited()
        assert flow._api is None

    def test_get_api_rebuilds_when_credentials_change(self):
        flow = make_flow(api=None)
        flow._get_api = SmartSolarConfigFlow._get_api.__get__(flow)  # type: ignore[method-assign]
        flow._username = "user"
        flow._password = "pw1"

        first = flow._get_api()
        flow._password = "pw2"
        second = flow._get_api()

        assert second is not first
        assert second._password == "pw2"

    def test_get_api_without_credentials_raises(self):
        """Building the API client before credentials exist is a bug."""
        flow = make_flow(api=None)
        flow._get_api = SmartSolarConfigFlow._get_api.__get__(flow)  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="Missing credentials"):
            flow._get_api()


class TestModeStep:
    @pytest.mark.asyncio
    async def test_device_mode_goes_to_chipset_step(self):
        flow = make_flow()
        flow.async_step_chipset_ids = AsyncMock(return_value=STEP_RESULT)  # type: ignore[method-assign]
        result = await flow.async_step_mode({"mode": "device"})
        assert result is STEP_RESULT
        assert flow._mode == "device"
        assert flow._device_type == 2  # DEVICE_TYPE_MANH_QUAN

    @pytest.mark.asyncio
    async def test_project_mode_goes_to_method_step(self):
        flow = make_flow()
        flow.async_step_project_method = AsyncMock(return_value=STEP_RESULT)  # type: ignore[method-assign]
        result = await flow.async_step_mode({"mode": "project"})
        assert result is STEP_RESULT
        assert flow._mode == "project"


class TestProjectIdStep:
    @pytest.mark.asyncio
    async def test_empty_project_id_is_rejected(self):
        flow = make_flow(api=MagicMock())
        result = await flow.async_step_project_id({"project_id": "  "})
        assert result["errors"]["base"] == "project_id_required"

    @pytest.mark.asyncio
    async def test_successful_lookup_creates_entry(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_id({"project_id": "1072"})

        assert result["type"] == "create_entry"
        assert result["data"]["project_id"] == "1072"
        assert result["data"]["update_interval"] == 5
        flow._close_api.assert_awaited()

    @pytest.mark.asyncio
    async def test_404_reports_project_not_found(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(side_effect=SmartSolarAPIError("nope", 404))
        flow = make_flow(api=api)
        result = await flow.async_step_project_id({"project_id": "9999"})
        assert result["errors"]["base"] == "project_not_found"

    @pytest.mark.asyncio
    async def test_500_reports_cannot_connect(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(side_effect=SmartSolarAPIError("boom", 500))
        flow = make_flow(api=api)
        result = await flow.async_step_project_id({"project_id": "1072"})
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_failing_step_closes_api_session(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(side_effect=SmartSolarAPIError("nope", 404))
        api.close = AsyncMock()
        flow = make_flow(api=api)
        flow._api = api
        flow._close_api = SmartSolarConfigFlow._close_api.__get__(flow)  # type: ignore[method-assign]
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_id({"project_id": "9999"})

        assert result["errors"]["base"] == "project_not_found"
        api.close.assert_awaited()
        assert flow._api is None


class TestChipsetIdsStep:
    @pytest.mark.asyncio
    async def test_empty_chipset_id_is_rejected(self):
        flow = make_flow(api=MagicMock())
        flow._mode = "device"
        result = await flow.async_step_chipset_ids({"chipset_ids": "  "})
        assert result["errors"]["base"] == "chipset_ids_required"

    @pytest.mark.asyncio
    async def test_only_separators_is_rejected(self):
        flow = make_flow(api=MagicMock())
        flow._mode = "device"
        result = await flow.async_step_chipset_ids({"chipset_ids": " , , "})
        assert result["errors"]["base"] == "chipset_ids_invalid"

    @pytest.mark.asyncio
    async def test_successful_device_entry(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "device"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": " 547611 "})

        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611"]
        assert result["data"]["mode"] == "device"

    @pytest.mark.asyncio
    async def test_device_not_found_is_reported(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(side_effect=SmartSolarAPIError("nope", 404))
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "device"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": "999"})
        assert result["errors"]["base"] == "device_not_found"

    @pytest.mark.asyncio
    async def test_duplicate_entry_abort_releases_client(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        api.close = AsyncMock()
        flow = make_flow(api=api)
        flow._api = api
        flow._close_api = SmartSolarConfigFlow._close_api.__get__(flow)  # type: ignore[method-assign]
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "device"
        flow._device_type = 2
        flow._abort_if_unique_id_configured = MagicMock(side_effect=AbortFlow("already_configured"))

        with pytest.raises(AbortFlow):
            await flow.async_step_chipset_ids({"chipset_ids": "547611"})

        api.close.assert_awaited()
        assert flow._api is None


class TestProjectDevicesStep:
    @pytest.mark.asyncio
    async def test_empty_list_is_rejected(self):
        flow = make_flow(api=MagicMock())
        flow._mode = "project"
        result = await flow.async_step_project_devices({"manh_quan_ids": ""})
        assert result["errors"]["base"] == "manh_quan_ids_required"

    @pytest.mark.asyncio
    async def test_successful_multi_device_entry(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_devices({"manh_quan_ids": "547611,14756976"})

        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611", "14756976"]
        assert result["data"]["device_type"] == 2

    @pytest.mark.asyncio
    async def test_entry_data_matches_the_documented_contract(self):
        """Entry data carries exactly the documented keys — no dead extras.

        ``device_types`` was written here but read nowhere: it duplicated
        ``device_type`` and made the project-by-devices entry shape differ from
        every other flow's.
        """
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_devices({"manh_quan_ids": "547611"})

        assert set(result["data"]) == {
            "username",
            "password",
            "mode",
            "device_type",
            "chipset_ids",
            "update_interval",
        }

    @pytest.mark.asyncio
    async def test_missing_credentials_reports_unknown(self):
        flow = make_flow(api=MagicMock())
        flow._mode = None
        result = await flow.async_step_project_devices({"manh_quan_ids": "547611"})
        assert result["errors"]["base"] == "unknown"


class TestDeviceModeSingleId:
    """Device mode reads one charger, so it must refuse a list.

    The extra ids used to be accepted and then ignored — and because device mode
    merges every *accepted* device into one ``lastMessage.dataStreams``, the
    second charger's readings ended up on the first charger's sensors.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["547611,14756976", "547611, 14756976", "a,b,c"])
    async def test_multiple_ids_are_rejected(self, value):
        flow = make_flow(api=MagicMock())
        flow._mode = "device"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": value})

        assert result["errors"]["base"] == "single_chipset_id_required"

    @pytest.mark.asyncio
    async def test_multiple_ids_never_reach_the_api(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._mode = "device"
        flow._device_type = 2

        await flow.async_step_chipset_ids({"chipset_ids": "547611,14756976"})

        api.get_metrics.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_single_id_still_creates_the_entry(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "device"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": "547611"})

        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611"]

    @pytest.mark.asyncio
    async def test_project_mode_still_accepts_a_list(self):
        """The single-id rule applies to device mode only."""
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": "547611,14756976"})

        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611", "14756976"]

    def test_error_key_is_translated(self):
        assert "single_chipset_id_required" in _load_translation_section("error")


class TestReconfigureAndReauth:
    @pytest.mark.asyncio
    async def test_reconfigure_preserves_existing_keys(self):
        entry_data = {
            "username": "old",
            "password": "old",
            "mode": "project",
            "device_type": 2,
            "project_id": "1072",
        }
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=True)
        flow = make_flow(api=api)
        entry = make_entry(entry_data)
        flow.hass.config_entries.async_get_entry.return_value = entry
        # Emulate HomeAssistant.config_entries.async_update_entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        result = await flow.async_step_reconfigure({"username": "new", "password": "new"})

        assert result["reason"] == "reconfigure_successful"
        assert entry.data["username"] == "new"
        assert entry.data["mode"] == "project"
        assert entry.data["project_id"] == "1072"
        flow.hass.config_entries.async_reload.assert_awaited_once_with("entry-1")
        # test_connection() closes the session, so the cached client is dropped
        flow._close_api.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("username", "password", "expected"),
        [
            ("", "pw", "username_required"),
            ("   ", "pw", "username_required"),
            ("user", "", "password_required"),
            ("user", "   ", "password_required"),
        ],
    )
    async def test_reconfigure_rejects_blank_credentials(self, username, password, expected):
        """A blank field used to be written into the entry.

        ``async_setup_entry`` then refused to load it (its required-key check),
        so reconfiguring with an empty password silently broke a working
        integration on the next reload.
        """
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=True)
        flow = make_flow(api=api)
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        result = await flow.async_step_reconfigure({"username": username, "password": password})

        assert result["errors"]["base"] == expected
        assert entry.data["username"] == "old"
        assert entry.data["password"] == "old"
        flow.hass.config_entries.async_reload.assert_not_awaited()
        api.test_connection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconfigure_rejects_credentials_the_api_refuses(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        api = MagicMock()
        api.test_connection = AsyncMock(return_value=False)
        flow = make_flow(api=api)
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        result = await flow.async_step_reconfigure({"username": "new", "password": "new"})

        assert result["errors"]["base"] == "cannot_connect"
        assert entry.data["password"] == "old"
        flow.hass.config_entries.async_reload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconfigure_reports_invalid_credentials(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        api = MagicMock()
        api.test_connection = AsyncMock(side_effect=SmartSolarAuthenticationError("bad", 401))
        flow = make_flow(api=api)
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        result = await flow.async_step_reconfigure({"username": "new", "password": "bad"})

        assert result["errors"]["base"] == "invalid_credentials"
        assert entry.data["password"] == "old"
        flow.hass.config_entries.async_reload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconfigure_shows_the_form_without_input(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry

        result = await flow.async_step_reconfigure(None)

        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    @pytest.mark.asyncio
    async def test_reconfigure_unknown_entry_aborts(self):
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = None
        result = await flow.async_step_reconfigure({"username": "u", "password": "p"})
        assert result["reason"] == "unknown_entry"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("username", "password", "expected"),
        [
            ("", "pw", "username_required"),
            ("   ", "pw", "username_required"),
            ("user", "", "password_required"),
            ("user", "   ", "password_required"),
        ],
    )
    async def test_reauth_rejects_blank_fields(self, username, password, expected):
        """Blanks used to be sent to the API, which answered 'invalid_credentials'.

        With the API down the same submission reported 'cannot_connect' instead,
        hiding the real problem behind a connectivity error.
        """
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry

        with _FakeAPIContext(test_connection=AsyncMock(return_value=True)) as api:
            result = await flow.async_step_reauth({"username": username, "password": password})

        assert result["errors"]["base"] == expected
        api.test_connection.assert_not_awaited()
        flow.hass.config_entries.async_reload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reauth_still_accepts_valid_credentials(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        with _FakeAPIContext(test_connection=AsyncMock(return_value=True)):
            result = await flow.async_step_reauth({"username": " new ", "password": "pw"})

        assert result["reason"] == "reauth_successful"

    @pytest.mark.asyncio
    async def test_reauth_unknown_entry_aborts(self):
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = None
        result = await flow.async_step_reauth({"username": "u", "password": "p"})
        assert result["reason"] == "unknown_entry"

    @pytest.mark.asyncio
    async def test_reauth_success_updates_entry(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        with _FakeAPIContext(test_connection=AsyncMock(return_value=True)):
            result = await flow.async_step_reauth({"username": "new", "password": "new"})

        assert result["reason"] == "reauth_successful"
        assert entry.data["username"] == "new"
        assert entry.data["mode"] == "project"
        flow.hass.config_entries.async_reload.assert_awaited_once_with("entry-1")

    @pytest.mark.asyncio
    async def test_reauth_failure_reports_error_and_keeps_entry(self):
        entry = MagicMock()
        entry.entry_id = "entry-1"
        entry.data = {"username": "old", "password": "old"}
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry

        with _FakeAPIContext(test_connection=AsyncMock(side_effect=SmartSolarAuthenticationError("bad", 401))):
            result = await flow.async_step_reauth({"username": "u", "password": "p"})

        assert result["errors"]["base"] == "invalid_credentials"
        flow.hass.config_entries.async_reload.assert_not_awaited()


def _load_translation_file(relative_path: str) -> dict:
    """Load one translation file shipped inside the integration directory."""
    import json

    with open(f"custom_components/smartsolar_ha/{relative_path}", encoding="utf-8") as f:
        return json.load(f)


def _load_translation_section(section: str) -> dict[str, str]:
    return _load_translation_file("translations/en.json")["config"][section]


class TestUniqueIdGeneration:
    """The unique_id passed to async_set_unique_id must reflect the entry."""

    @pytest.mark.asyncio
    async def test_project_id_step_unique_id_and_data(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_id({"project_id": "1072"})

        flow.async_set_unique_id.assert_awaited_once_with("vokupt_project_2_1072")
        assert result["type"] == "create_entry"
        assert result["data"]["project_id"] == "1072"
        assert result["data"]["username"] == "vokupt"

    @pytest.mark.asyncio
    async def test_project_by_id_unique_id_includes_device_type(self):
        flow = make_flow()
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"
        flow._device_type = 2
        flow._project_id = "1072"

        result = await flow._create_entry()

        flow.async_set_unique_id.assert_awaited_once_with("vokupt_project_2_1072")
        assert result["type"] == "create_entry"
        assert result["data"]["project_id"] == "1072"
        assert result["data"]["username"] == "vokupt"

    @pytest.mark.asyncio
    async def test_device_chipset_ids_unique_id_includes_device_type(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "device"
        flow._device_type = 2

        result = await flow.async_step_chipset_ids({"chipset_ids": "547611"})

        flow.async_set_unique_id.assert_awaited_once_with("vokupt_device_2_547611")
        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611"]
        assert result["data"]["device_type"] == 2

    @pytest.mark.asyncio
    async def test_project_devices_unique_id_joins_device_ids(self):
        api = MagicMock()
        api.get_metrics = AsyncMock(return_value={})
        flow = make_flow(api=api)
        flow._username = "vokupt"
        flow._password = "pw"
        flow._mode = "project"

        result = await flow.async_step_project_devices({"manh_quan_ids": "547611,14756976"})

        flow.async_set_unique_id.assert_awaited_once_with("vokupt_project_547611_14756976")
        assert result["type"] == "create_entry"
        assert result["data"]["chipset_ids"] == ["547611", "14756976"]

    @pytest.mark.asyncio
    async def test_different_device_types_do_not_collide(self):
        flow1 = make_flow()
        flow1._username = "vokupt"
        flow1._password = "pw"
        flow1._mode = "device"
        flow1._device_type = 1
        flow1._chipset_ids = ["547611"]
        await flow1._create_entry()

        flow2 = make_flow()
        flow2._username = "vokupt"
        flow2._password = "pw"
        flow2._mode = "device"
        flow2._device_type = 2
        flow2._chipset_ids = ["547611"]
        await flow2._create_entry()

        flow1.async_set_unique_id.assert_awaited_once_with("vokupt_device_1_547611")
        flow2.async_set_unique_id.assert_awaited_once_with("vokupt_device_2_547611")


class TestTranslationKeys:
    """Every error/abort key the flow emits must resolve in en.json."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("user_input", "expected"),
        [
            ({"username": "", "password": "pw"}, "username_required"),
            ({"username": "u", "password": "  "}, "password_required"),
        ],
    )
    async def test_emitted_login_error_key_resolves(self, user_input, expected):
        flow = make_flow(api=MagicMock())
        result = await flow.async_step_user(user_input)
        assert result["errors"]["base"] == expected
        assert expected in _load_translation_section("error")

    @pytest.mark.asyncio
    async def test_emitted_project_error_key_resolves(self):
        api = MagicMock()
        api.login = AsyncMock()
        api.get_project_metrics = AsyncMock(side_effect=SmartSolarAPIError("nope", 404))
        flow = make_flow(api=api)

        result = await flow.async_step_project_id({"project_id": "9999"})

        assert result["errors"]["base"] == "project_not_found"
        assert "project_not_found" in _load_translation_section("error")

    @pytest.mark.asyncio
    async def test_emitted_reauth_abort_key_resolves(self):
        entry = make_entry({"username": "old", "password": "old", "mode": "project"})
        flow = make_flow()
        flow.hass.config_entries.async_get_entry.return_value = entry
        flow.hass.config_entries.async_update_entry = lambda e, **kw: setattr(e, "data", kw["data"])

        with _FakeAPIContext(test_connection=AsyncMock(return_value=True)):
            result = await flow.async_step_reauth({"username": "new", "password": "new"})

        assert result["reason"] == "reauth_successful"
        assert "reauth_successful" in _load_translation_section("abort")

    def test_unknown_entry_abort_key_resolves(self):
        """``async_abort(reason="unknown_entry")`` needs a translation too.

        Without one the UI shows the raw reason string. Both reauth and
        reconfigure emit it when the entry disappeared mid-flow.
        """
        assert "unknown_entry" in _load_translation_section("abort")


class TestCredentialStepTranslations:
    """The reauth/reconfigure dialogs must be translated, in every language.

    ``async_show_form(step_id="reauth")`` with no matching translation renders
    the form with raw field keys and no title, which is what shipped before.
    """

    @pytest.mark.parametrize(
        "relative_path",
        ["strings.json", "translations/en.json", "translations/vi.json"],
    )
    @pytest.mark.parametrize("step_id", ["reauth", "reconfigure"])
    def test_credential_step_is_translated(self, relative_path, step_id):
        config = _load_translation_file(relative_path)["config"]

        assert step_id in config["step"], f"{step_id} missing from {relative_path}"
        step = config["step"][step_id]
        assert step.get("title"), f"{step_id} has no title in {relative_path}"
        assert set(step["data"]) == {"username", "password"}

    @pytest.mark.parametrize(
        "relative_path",
        ["strings.json", "translations/en.json", "translations/vi.json"],
    )
    def test_unknown_entry_abort_is_translated(self, relative_path):
        assert "unknown_entry" in _load_translation_file(relative_path)["config"]["abort"]

    @pytest.mark.parametrize("relative_path", ["strings.json", "translations/en.json", "translations/vi.json"])
    def test_every_step_the_flow_shows_is_declared(self, relative_path):
        """Every ``step_id`` used by the flow has a section, so none renders raw."""
        shown = {
            "user",
            "mode",
            "chipset_ids",
            "project_method",
            "project_id",
            "project_devices",
            "reauth",
            "reconfigure",
        }
        assert shown <= set(_load_translation_file(relative_path)["config"]["step"])
