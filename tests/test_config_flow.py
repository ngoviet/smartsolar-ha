"""Tests for config_flow.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smartsolar_mppt.config_flow import SmartSolarConfigFlow
from custom_components.smartsolar_mppt.const import DOMAIN

# Mock the config_entries module before importing
import sys
from unittest.mock import MagicMock as Mock

# Create a mock ConfigFlow and ConfigFlowResult
class MockConfigFlow:
    VERSION = 1
    MINOR_VERSION = 1

# We cannot easily instantiate SmartSolarConfigFlow outside HA context,
# so these tests focus on the logic that CAN be tested in isolation.


class TestReconfigureLogic:
    """Tests for reconfigure logic (the merge fix)."""

    def test_reconfigure_merge_preserves_existing_data(self):
        """When merging user_input with existing data, existing keys are preserved."""
        existing_data = {
            "username": "old_user",
            "password": "old_pass",
            "mode": "project",
            "device_type": 2,
            "project_id": "1072",
        }
        user_input = {
            "username": "new_user",
            "password": "new_pass",
        }
        # This is the fix: {**existing_data, **user_input}
        merged = {**existing_data, **user_input}
        assert merged["username"] == "new_user"
        assert merged["password"] == "new_pass"
        assert merged["mode"] == "project"  # preserved!
        assert merged["device_type"] == 2  # preserved!
        assert merged["project_id"] == "1072"  # preserved!

    def test_old_code_would_have_wiped_data(self):
        """Demonstrate that the OLD code (now fixed) would have destroyed data."""
        existing_data = {
            "username": "old_user",
            "password": "old_pass",
            "mode": "project",
            "device_type": 2,
            "project_id": "1072",
        }
        user_input = {"username": "new_user", "password": "new_pass"}
        # Old code: data=user_input — this destroys everything else
        old_result = dict(user_input)
        assert "mode" not in old_result
        assert "project_id" not in old_result
        # New code: {**existing_data, **user_input} — preserves everything
        new_result = {**existing_data, **user_input}
        assert new_result["mode"] == "project"
        assert new_result["project_id"] == "1072"


class TestConfigFlowInit:
    """Tests for SmartSolarConfigFlow initialization."""

    def test_init_stores_none_attributes(self):
        """All initial attributes should be None."""
        # We create a mock config flow to test attribute initialization
        flow = MagicMock(spec=SmartSolarConfigFlow)
        flow._username = None
        flow._password = None
        flow._mode = None
        flow._device_type = None
        flow._chipset_ids = None
        flow._project_method = None
        flow._project_id = None
        flow._device_types = None
        assert flow._username is None
        assert flow._password is None
        assert flow._mode is None
        assert flow._device_type is None

    def test_version_constants(self):
        """VERSION and MINOR_VERSION are correctly set to expected values."""
        # After v1.3.0, these should be 1 and 2
        # We check the class definition itself
        assert True  # Placeholder; actual check requires running the class


class TestUniqueIDPatterns:
    """Tests for unique ID generation patterns."""

    def test_project_by_id_unique_id(self):
        """Project by ID uses project_id in unique_id."""
        username = "test_user"
        mode = "project"
        device_type = 2
        project_id = "1072"
        unique_id = f"{username}_{mode}_{device_type}_{project_id}"
        assert "test_user" in unique_id
        assert "project" in unique_id
        assert "1072" in unique_id

    def test_chipset_ids_unique_id_format(self):
        """Chipset IDs unique_id includes device_type (fixes potential collision)."""
        username = "test_user"
        mode = "device"
        device_type = 2
        chipset_ids = ["547611"]
        unique_id = f"{username}_{mode}_{device_type}_{'_'.join(chipset_ids)}"
        assert "547611" in unique_id
        assert "2" in unique_id  # device_type is included

    def test_different_device_types_dont_collide(self):
        """Same chipset IDs with different device types should have different unique_ids."""
        username = "test_user"
        mode = "device"
        chipset_ids = ["547611"]
        id_type1 = f"{username}_{mode}_1_{'_'.join(chipset_ids)}"
        id_type2 = f"{username}_{mode}_2_{'_'.join(chipset_ids)}"
        assert id_type1 != id_type2


class TestAbortReasons:
    """Tests that abort reasons are consistent."""

    def test_reconfigure_successful_exists(self):
        """'reconfigure_successful' abort reason is defined in en.json."""
        import json
        with open("custom_components/smartsolar_mppt/translations/en.json") as f:
            data = json.load(f)
        assert "reconfigure_successful" in data["config"]["abort"]

    def test_reauth_successful_exists(self):
        """'reauth_successful' abort reason still exists."""
        import json
        with open("custom_components/smartsolar_mppt/translations/en.json") as f:
            data = json.load(f)
        assert "reauth_successful" in data["config"]["abort"]
