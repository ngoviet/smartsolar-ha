"""Tests for number.py."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smartsolar_mppt.const import MAX_UPDATE_INTERVAL, MIN_UPDATE_INTERVAL
from custom_components.smartsolar_mppt.number import UpdateIntervalNumber


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

    def test_default_name(self):
        """Default name before translations load."""
        entity = self._make_number()
        assert entity._attr_name == "Update Frequency"

    def test_default_unit(self):
        """Default unit before translations load."""
        entity = self._make_number()
        assert entity._attr_native_unit_of_measurement == "seconds"

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
    async def test_set_native_value_truncates_floats(self):
        """Float values are truncated to int (step=1)."""
        entity = self._make_number()
        await entity.async_set_native_value(10.7)
        assert self.coordinator.update_interval == timedelta(seconds=10)
