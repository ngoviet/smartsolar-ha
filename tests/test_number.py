"""Tests for number.py."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smartsolar_ha.const import (
    DEFAULT_UPDATE_INTERVAL,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from custom_components.smartsolar_ha.number import UpdateIntervalNumber


class TestUpdateIntervalNumber:
    """Tests for UpdateIntervalNumber entity."""

    def setup_method(self):
        self.coordinator = MagicMock()
        self.coordinator.update_interval = timedelta(seconds=5)
        self.coordinator.async_refresh = AsyncMock()
        self.entry = MagicMock()
        self.entry.entry_id = "test_entry_123"
        self.entry.data = {"mode": "project", "project_id": "1072"}
        self.hass = MagicMock()
        self.hass.config.language = "en"
        self.hass.config_entries = MagicMock()

    def _make_number(self):
        entity = UpdateIntervalNumber(
            coordinator=self.coordinator,
            entry=self.entry,
        )
        entity.hass = self.hass
        entity.async_write_ha_state = MagicMock()  # Avoid NoEntitySpecifiedError
        return entity

    def test_unique_id_format(self):
        """Unique ID is entry_id + '_update_interval'."""
        entity = self._make_number()
        assert entity._attr_unique_id == "test_entry_123_update_interval"

    def test_native_value_returns_coordinator_interval(self):
        """native_value returns coordinator.update_interval in seconds."""
        entity = self._make_number()
        assert entity.native_value == 5.0

    def test_native_value_defaults_to_5_when_no_interval(self):
        """native_value defaults to 5.0 when no update_interval on coordinator."""
        self.coordinator.update_interval = None
        entity = self._make_number()
        assert entity.native_value == 5.0

    def test_native_min_max_values(self):
        """Number entity has correct min/max bounds."""
        entity = self._make_number()
        assert entity._attr_native_min_value == MIN_UPDATE_INTERVAL  # 1
        assert entity._attr_native_max_value == MAX_UPDATE_INTERVAL  # 30

    def test_native_step_is_1(self):
        """Step size is 1 second."""
        entity = self._make_number()
        assert entity._attr_native_step == 1

    def test_mode_is_box(self):
        """Number mode is BOX (user types a value)."""
        from homeassistant.components.number import NumberMode

        entity = self._make_number()
        assert entity._attr_mode == NumberMode.BOX

    def test_default_name_key(self):
        """Entity name comes from the HA translation key, not a hardcoded string."""
        entity = self._make_number()
        assert entity._attr_translation_key == "update_frequency"
        assert entity._attr_has_entity_name is True

    def test_default_unit(self):
        """Unit is the HA-conventional seconds symbol."""
        entity = self._make_number()
        assert entity._attr_native_unit_of_measurement == "s"

    def test_icon(self):
        """Icon is timer-cog."""
        entity = self._make_number()
        assert entity._attr_icon == "mdi:timer-cog"

    @pytest.mark.asyncio
    async def test_set_native_value_updates_coordinator(self):
        """async_set_native_value updates coordinator.update_interval."""
        entity = self._make_number()
        await entity.async_set_native_value(10.0)
        assert self.coordinator.update_interval == timedelta(seconds=10)

    @pytest.mark.asyncio
    async def test_set_native_value_updates_config_entry(self):
        """async_set_native_value stores value in config entry data."""
        entity = self._make_number()
        await entity.async_set_native_value(15.0)
        self.hass.config_entries.async_update_entry.assert_called_once()
        call_args = self.hass.config_entries.async_update_entry.call_args
        assert call_args[1]["data"]["update_interval"] == 15

    @pytest.mark.asyncio
    async def test_set_native_value_triggers_refresh(self):
        """async_set_native_value triggers coordinator refresh."""
        entity = self._make_number()
        await entity.async_set_native_value(3.0)
        self.coordinator.async_refresh.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("value", "expected"), [(10.7, 11), (10.4, 10), (1.6, 2), (29.5, 30)])
    async def test_set_native_value_rounds_floats(self, value, expected):
        """Fractional values are rounded, not truncated.

        Home Assistant's number.set_value service coerces to float and checks
        min/max but does NOT enforce native_step, so a fractional value really
        arrives. ``int(10.7) == 10`` used to change the requested interval
        silently.
        """
        entity = self._make_number()
        await entity.async_set_native_value(value)
        assert self.coordinator.update_interval == timedelta(seconds=expected)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    async def test_non_finite_value_does_not_raise(self, value):
        """NaN passes HA's min/max check (every NaN comparison is False).

        ``round()``/``int()`` on NaN raises ValueError and on Infinity raises
        OverflowError, so without the coerce_float guard this escaped
        ``async_set_native_value`` entirely.
        """
        entity = self._make_number()
        await entity.async_set_native_value(value)
        assert self.coordinator.update_interval == timedelta(seconds=5)
        self.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [0.0, -1.0, 31.0, 1000.0])
    async def test_out_of_range_value_is_rejected(self, value):
        """Values outside 1..30 never reach the coordinator or the config entry."""
        entity = self._make_number()
        await entity.async_set_native_value(value)
        assert self.coordinator.update_interval == timedelta(seconds=5)
        self.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_defaults_to_default_interval_when_none(self):
        """native_value falls back to DEFAULT_UPDATE_INTERVAL."""
        self.coordinator.update_interval = None
        entity = self._make_number()
        assert entity.native_value == DEFAULT_UPDATE_INTERVAL.total_seconds()

    def test_restore_entity_in_mro(self):
        """The number entity must be a RestoreEntity so state survives restarts."""
        from homeassistant.helpers.restore_state import RestoreEntity

        assert issubclass(UpdateIntervalNumber, RestoreEntity)

    @pytest.mark.asyncio
    async def test_restores_last_interval_on_add(self):
        """A restored state re-applies the interval to the coordinator."""
        self.coordinator.update_interval = timedelta(seconds=5)
        entity = self._make_number()
        last_state = MagicMock()
        last_state.state = "25"
        entity.async_get_last_state = AsyncMock(return_value=last_state)

        await entity.async_added_to_hass()

        assert self.coordinator.update_interval == timedelta(seconds=25)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("restored", ["unavailable", "unknown", "0", "99", "abc", ""])
    async def test_ignores_unusable_restored_state(self, restored):
        """Junk or out-of-range restored state leaves the interval alone."""
        self.coordinator.update_interval = timedelta(seconds=5)
        entity = self._make_number()
        last_state = MagicMock()
        last_state.state = restored
        entity.async_get_last_state = AsyncMock(return_value=last_state)

        await entity.async_added_to_hass()

        assert self.coordinator.update_interval == timedelta(seconds=5)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("restored", ["inf", "-inf", "nan", "Infinity"])
    async def test_non_finite_restored_state_does_not_raise(self, restored):
        """``int(float("inf"))`` raises OverflowError, which was not caught.

        The old handler only covered ``ValueError``/``TypeError``, so a
        non-finite restored state aborted the entity being added.
        """
        self.coordinator.update_interval = timedelta(seconds=5)
        entity = self._make_number()
        last_state = MagicMock()
        last_state.state = restored
        entity.async_get_last_state = AsyncMock(return_value=last_state)

        await entity.async_added_to_hass()

        assert self.coordinator.update_interval == timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_no_restored_state_is_safe(self):
        """First-ever start has no previous state."""
        entity = self._make_number()
        entity.async_get_last_state = AsyncMock(return_value=None)

        await entity.async_added_to_hass()

        assert self.coordinator.update_interval == timedelta(seconds=5)

    def test_mro_is_consistent(self):
        """A valid MRO means the class definition is not contradictory."""
        assert UpdateIntervalNumber.__mro__
