"""Tests for verify_live.py — the live-instance verifier's payload handling.

The verifier talks to the cloud and to Home Assistant over plain urllib, so it
had no test coverage at all. Its payload handling still has to be as defensive as
the integration's: it asks the SAME cloud API for the same field, and the cloud
has been observed answering ``"deviceLogs": null``.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

import verify_live

_ENV = {"SMARTSOLAR_USER": "user", "SMARTSOLAR_PASS": "pass"}


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for what ``urllib.request.urlopen`` yields."""

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _urlopen_serving(payloads: list[object]):
    """Build a urlopen replacement that serves ``payloads`` in order."""
    pending = iter(payloads)

    def fake_urlopen(_request: object, timeout: int | None = None) -> _FakeResponse:
        del timeout
        return _FakeResponse(json.dumps(next(pending)).encode())

    return fake_urlopen


def _patch_urlopen(payloads: list[object]):
    return patch.object(verify_live.urllib.request, "urlopen", _urlopen_serving(payloads))


class TestAsFloat:
    """Entity states are strings; 'unknown' is a normal value, not a crash."""

    @pytest.mark.parametrize("value", ["unknown", "unavailable", "", None, "12.5x", "24,1"])
    def test_non_numeric_states_return_none(self, value):
        assert verify_live.as_float(value) is None

    @pytest.mark.parametrize(("value", "expected"), [("24.1", 24.1), (24, 24.0), ("-3.5", -3.5)])
    def test_numeric_states_are_parsed(self, value, expected):
        assert verify_live.as_float(value) == expected


class TestLiveSignalQuality:
    """The cloud signal map must degrade to "unknown map" on any odd payload."""

    def test_missing_credentials_skip_without_calling_the_cloud(self):
        with patch.object(
            verify_live.urllib.request,
            "urlopen",
            side_effect=AssertionError("the cloud must not be contacted without credentials"),
        ):
            assert verify_live.live_signal_quality({}) == {}

    @pytest.mark.parametrize("device_logs", [None, 5, "oops", {}, True])
    def test_non_list_device_logs_reports_no_map_instead_of_crashing(self, device_logs):
        """``"deviceLogs": null`` used to raise TypeError and abort the run.

        The verifier crashed with a traceback where the integration itself
        already treats the same payload as "no device logs".
        """
        with _patch_urlopen([{"token": "t"}, {"deviceLogs": device_logs}]):
            assert verify_live.live_signal_quality(_ENV) == {}

    def test_missing_device_logs_key_reports_no_map(self):
        with _patch_urlopen([{"token": "t"}, {"synthesisStreams": []}]):
            assert verify_live.live_signal_quality(_ENV) == {}

    def test_reported_signals_are_keyed_by_string_guid(self):
        with _patch_urlopen(
            [
                {"token": "t"},
                {
                    "deviceLogs": [
                        {"deviceGuid": 547611, "signalQuality": 95},
                        {"deviceGuid": "14756976", "signalQuality": None},
                        {"deviceGuid": "999", "signalQuality": 80},
                    ]
                },
            ]
        ):
            assert verify_live.live_signal_quality(_ENV) == {"547611": 95, "999": 80}

    def test_non_mapping_entries_are_skipped(self):
        with _patch_urlopen(
            [
                {"token": "t"},
                {
                    "deviceLogs": [
                        "oops",
                        5,
                        None,
                        {"deviceGuid": "547611", "signalQuality": 95},
                        {"signalQuality": 50},
                    ]
                },
            ]
        ):
            assert verify_live.live_signal_quality(_ENV) == {"547611": 95}

    def test_network_failure_reports_no_map(self):
        with patch.object(
            verify_live.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("cloud down"),
        ):
            assert verify_live.live_signal_quality(_ENV) == {}

    def test_login_without_token_reports_no_map(self):
        with _patch_urlopen([{}]):
            assert verify_live.live_signal_quality(_ENV) == {}

    def test_invalid_json_reports_no_map(self):
        with patch.object(
            verify_live.urllib.request,
            "urlopen",
            side_effect=ValueError("not json"),
        ):
            assert verify_live.live_signal_quality(_ENV) == {}


class TestMainGuards:
    """The verifier must report, not traceback, when it cannot run."""

    def test_missing_token_reports_a_message_and_exit_code_2(self, capsys):
        with patch.object(verify_live, "load_env", return_value={}):
            assert verify_live.main() == 2

        assert "HA_TOKEN is not set" in capsys.readouterr().out

    def test_unreachable_instance_reports_exit_code_2(self, capsys):
        with (
            patch.object(verify_live, "load_env", return_value={"HA_TOKEN": "t"}),
            patch.object(verify_live.urllib.request, "urlopen", side_effect=urllib.error.URLError("no route")),
        ):
            assert verify_live.main() == 2

        assert "Could not read states" in capsys.readouterr().out


def _state(entity_id: str, state: str) -> dict[str, str]:
    return {"entity_id": entity_id, "state": state}


def _complete_state_machine() -> list[dict[str, str]]:
    """A settled instance: every entity the verifier reads carries a real value."""
    states = [_state(entity, "1.0") for entity in verify_live.expected_entities()]
    values = {
        f"{verify_live.PREFIX}total_battery_voltage": "27.53",
        f"{verify_live.PREFIX}pv1_total_energy": "389.364",
        f"{verify_live.PREFIX}total_status": "Online",
        f"{verify_live.PREFIX}pv2_wifi_signal": "unknown",
        verify_live.NUMBER_ENTITY: "5.0",
    }
    return [dict(entry, state=values.get(entry["entity_id"], entry["state"])) for entry in states]


def _serving_states(payloads: list[list[dict[str, str]]], seen: list[str]):
    """Serve ``/api/states`` from ``payloads`` in order, repeating the last one."""
    remaining = list(payloads)

    def fake_urlopen(request: object, timeout: int | None = None) -> _FakeResponse:
        del timeout
        seen.append(request.full_url)  # type: ignore[attr-defined]
        payload = remaining.pop(0) if len(remaining) > 1 else (remaining[0] if remaining else [])
        return _FakeResponse(json.dumps(payload).encode())

    return fake_urlopen


class TestSettlingStateMachine:
    """HA writes entity states asynchronously after a restart.

    A verification chained straight to a deploy used to read a half-filled state
    machine and report every missing entity as a failure, even though the
    integration was loaded and those entities appeared seconds later.
    """

    @staticmethod
    def _run(monkeypatch, payloads):
        seen: list[str] = []
        monkeypatch.setattr(verify_live.urllib.request, "urlopen", _serving_states(payloads, seen))
        monkeypatch.setattr(verify_live, "load_env", lambda: {"HA_TOKEN": "t"})
        monkeypatch.setattr(verify_live.time, "sleep", lambda _seconds: None)
        return seen

    def test_waits_for_the_expected_entities_and_then_passes(self, monkeypatch, capsys):
        partial = [entry for entry in _complete_state_machine() if not entry["entity_id"].endswith("total_status")]
        seen = self._run(monkeypatch, [partial, _complete_state_machine()])

        assert verify_live.main() == 0

        out = capsys.readouterr().out
        assert "waiting for 1 entity/entities to appear" in out
        assert "All live checks passed." in out
        assert len(seen) == 2, "it must read the states again after the wait"

    def test_does_not_wait_when_everything_is_already_there(self, monkeypatch, capsys):
        seen = self._run(monkeypatch, [_complete_state_machine()])

        assert verify_live.main() == 0

        out = capsys.readouterr().out
        assert "waiting for" not in out
        assert len(seen) == 1

    def test_reports_the_entities_that_never_appear(self, monkeypatch, capsys):
        monkeypatch.setattr(verify_live, "SETTLE_ATTEMPTS", 3)
        partial = [entry for entry in _complete_state_machine() if not entry["entity_id"].endswith("peak_power_today")]
        seen = self._run(monkeypatch, [partial])

        assert verify_live.main() == 1

        out = capsys.readouterr().out
        assert "gave up after 3 polls; still missing:" in out
        assert f"FAIL {verify_live.PREFIX}pv1_peak_power_today is missing" in out
        assert len(seen) == 3, "the wait is bounded by SETTLE_ATTEMPTS"

    def test_a_settling_instance_that_never_settles_still_reports(self, monkeypatch, capsys):
        """An empty state machine is a FAIL, not a crash or a silent pass."""
        monkeypatch.setattr(verify_live, "SETTLE_ATTEMPTS", 2)
        seen = self._run(monkeypatch, [[]])

        assert verify_live.main() == 1

        out = capsys.readouterr().out
        assert "integration provides 0 entities" in out
        assert len(seen) == 2


class TestExpectedEntities:
    """The wait list must cover every entity the checks read, or it proves nothing."""

    def test_covers_every_asserted_entity(self):
        expected = verify_live.expected_entities()

        assert len(expected) == len(set(expected))
        for name in (
            f"{verify_live.PREFIX}pv1_peak_power_today",
            f"{verify_live.PREFIX}pv2_production_hours_today",
            f"{verify_live.PREFIX}pv1_wifi_signal",
            f"{verify_live.PREFIX}total_battery_voltage",
            f"{verify_live.PREFIX}total_status",
            f"{verify_live.PREFIX}pv1_total_energy",
            verify_live.NUMBER_ENTITY,
        ):
            assert name in expected
