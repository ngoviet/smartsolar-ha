"""Tests for helpers.py — the shared, dependency-free value coercions.

These helpers are the first line of defence against a third-party payload
(cloud API or MQTT) reaching an entity: everything here is pure, so the tests
are plain synchronous assertions.
"""

from __future__ import annotations

import pytest

from custom_components.smartsolar_ha.helpers import (
    as_list,
    coerce_float,
    device_logs,
    guid_sort_key,
    stream_dict,
)


class TestCoerceFloat:
    """coerce_float turns payload values into measurements or None."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, 1.0),
            (1.5, 1.5),
            ("48.5", 48.5),
            (" 48.5 ", 48.5),
            (0, 0.0),
            ("0", 0.0),
            (-5.2, -5.2),  # battery current is negative while discharging
            (1e6, 1e6),
        ],
    )
    def test_numeric_values_are_converted(self, value, expected):
        assert coerce_float(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "abc",
            "",
            "12v",
            {},
            [],
            object(),
        ],
    )
    def test_non_numeric_values_return_none(self, value):
        assert coerce_float(value) is None

    @pytest.mark.parametrize("value", [True, False])
    def test_booleans_are_rejected(self, value):
        """float(True) == 1.0 would turn a flag into a measurement."""
        assert coerce_float(value) is None

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_floats_are_rejected(self, value):
        """A NaN state poisons Home Assistant's long-term statistics."""
        assert coerce_float(value) is None

    @pytest.mark.parametrize("value", ["nan", "NaN", "Infinity", "-inf", "1e999"])
    def test_non_finite_strings_are_rejected(self, value):
        """json.loads accepts bare NaN/Infinity, and '1e999' overflows to inf."""
        assert coerce_float(value) is None


class TestAsList:
    """as_list guards every fields that gets iterated."""

    def test_list_is_returned_unchanged(self):
        value = [1, 2]
        assert as_list(value) is value

    @pytest.mark.parametrize("value", [None, 5, "abc", {"a": 1}, (), object()])
    def test_non_lists_become_empty(self, value):
        assert as_list(value) == []


class TestDeviceLogs:
    """device_logs is the defensive accessor for response["deviceLogs"]."""

    def test_returns_the_list(self):
        logs = [{"deviceGuid": "547611"}]
        assert device_logs({"deviceLogs": logs}) == logs

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"deviceLogs": None},  # observed from the live API
            {"deviceLogs": 7},
            {"deviceLogs": "oops"},
            {"deviceLogs": {"547611": {}}},
            None,
            [],
            "not-a-dict",
        ],
    )
    def test_malformed_payloads_return_empty_list(self, payload):
        """A scalar here used to raise TypeError and fail the whole poll."""
        assert device_logs(payload) == []


class TestStreamDict:
    """stream_dict builds the {name: value} view used by every sensor."""

    def test_builds_name_value_map(self):
        streams = [
            {"name": "pv_voltage", "value": "48.5"},
            {"name": "charge_power", "value": "248.5"},
        ]
        assert stream_dict(streams) == {"pv_voltage": "48.5", "charge_power": "248.5"}

    def test_keeps_falsy_but_present_values(self):
        """0 % WiFi is a real reading, not a missing one."""
        streams = [{"name": "signal_quality", "value": 0}, {"name": "bat_current", "value": 0.0}]
        assert stream_dict(streams) == {"signal_quality": 0, "bat_current": 0.0}

    def test_skips_malformed_entries(self):
        streams = [
            {"name": "pv_voltage", "value": 48.5},
            {"value": "no name"},
            {"name": None, "value": 1},
            {"name": "missing_value"},
            "not-a-dict",
            None,
            5,
        ]
        assert stream_dict(streams) == {"pv_voltage": 48.5}

    @pytest.mark.parametrize("value", [None, "text", 5, {"name": "x"}])
    def test_non_list_input_returns_empty_map(self, value):
        assert stream_dict(value) == {}


class TestGuidSortKey:
    """GUID order decides the PV1/PV2 labels, so it must be stable."""

    def test_numeric_guids_sort_by_value(self):
        guids = ["14756976", "547611", "10", "9"]
        assert sorted(guids, key=guid_sort_key) == ["9", "10", "547611", "14756976"]

    def test_non_numeric_guids_sort_after_numbers(self):
        guids = ["b", "547611", "a"]
        assert sorted(guids, key=guid_sort_key) == ["547611", "a", "b"]

    def test_mixed_types_do_not_raise(self):
        """The API has returned deviceGuid as both int and str."""
        guids = ["547611", "abc", "12"]
        assert sorted(guids, key=guid_sort_key) == ["12", "547611", "abc"]
