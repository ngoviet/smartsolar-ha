"""Tests for the deploy/upload helper scripts.

``deploy_to_ha.py`` deletes files on the live host and overwrites the running
integration, so its bookkeeping deserves the same scrutiny as the integration
itself. Both scripts import ``paramiko`` at module level (a runtime-only
dependency, not part of the ``[test]`` extra), so a stub is installed when it is
not actually installed.
"""

from __future__ import annotations

import json
import sys
import types
import urllib.request
from pathlib import Path

import pytest

try:  # pragma: no cover - depends on the environment
    import paramiko  # noqa: F401
except ImportError:  # pragma: no cover - exercised when paramiko is absent
    sys.modules["paramiko"] = types.ModuleType("paramiko")

import deploy_to_ha  # noqa: E402
import upload_to_ha  # noqa: E402

CI_WORKFLOW = Path(".github") / "workflows" / "ci.yml"


class _FakeChannel:
    def __init__(self, status: int = 0) -> None:
        self._status = status

    def recv_exit_status(self) -> int:
        return self._status


class _FakeStream:
    def __init__(self, data: bytes = b"", status: int = 0) -> None:
        self._data = data
        self.channel = _FakeChannel(status)

    def read(self) -> bytes:
        return self._data


class _JsonResponse:
    """``urllib.request.urlopen`` result carrying a JSON body."""

    status = 200

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _JsonResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class FakeSSH:
    """Minimal ``paramiko.SSHClient`` stand-in that records every command."""

    def __init__(
        self,
        find_listing: str = "",
        tar_data: bytes = b"",
        tar_status: int = 0,
        legacy: str = "no",
    ) -> None:
        self.commands: list[str] = []
        self.find_listing = find_listing
        self.tar_data = tar_data
        self.tar_status = tar_status
        self.legacy = legacy

    def exec_command(self, cmd: str):
        self.commands.append(cmd)
        if cmd.startswith("sudo find"):
            return None, _FakeStream(self.find_listing.encode()), _FakeStream()
        if cmd.startswith("sudo tar"):
            return None, _FakeStream(self.tar_data, self.tar_status), _FakeStream()
        if cmd.startswith("test -d"):
            return None, _FakeStream(f"{self.legacy}\n".encode()), _FakeStream()
        return None, _FakeStream(), _FakeStream()


def _local_relative_paths() -> list[str]:
    return sorted(p.relative_to(deploy_to_ha.SRC_DIR).as_posix() for p in deploy_to_ha._local_file_list())


class TestLocalGateMatchesCi:
    """The docs promise the local gate is never weaker than CI.

    ``SOURCES`` here, the two ``ruff`` invocations in ``.github/workflows/ci.yml``
    and the command list in CLAUDE.md are three copies of the same thing; this
    pins the first two together.
    """

    @pytest.mark.parametrize("subcommand", ["check", "format --check"])
    def test_ci_runs_the_same_sources(self, subcommand):
        import shlex

        import yaml

        workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
        runs = [
            step["run"]
            for step in workflow["jobs"]["lint"]["steps"]
            if isinstance(step.get("run"), str) and f"ruff {subcommand}" in step["run"]
        ]

        assert runs, f"ci.yml no longer runs 'ruff {subcommand}'"
        assert shlex.split(runs[0]) == ["ruff", *subcommand.split(), *deploy_to_ha.SOURCES]


class TestPruneRemote:
    """Uploading only ever adds files, so leftovers must be pruned explicitly."""

    def test_removes_only_files_that_are_gone_locally(self):
        listing = "\n".join(
            [
                *_local_relative_paths(),
                "sensor_old.py",
                "translations/legacy.json",
                "__pycache__/sensor.cpython-314.pyc",
                "module.pyc",
            ]
        )
        ssh = FakeSSH(find_listing=listing)

        removed = deploy_to_ha.prune_remote(ssh)

        assert removed == 2
        rm_commands = [cmd for cmd in ssh.commands if cmd.startswith("sudo rm -f")]
        assert len(rm_commands) == 2
        assert any(cmd.endswith("sensor_old.py") for cmd in rm_commands)
        assert any(cmd.endswith("translations/legacy.json") for cmd in rm_commands)
        # Byte-code caches are not "stale source files".
        assert not any("__pycache__" in cmd for cmd in rm_commands)
        assert not any(cmd.endswith("module.pyc") for cmd in rm_commands)

    def test_no_op_when_the_host_matches_the_repository(self):
        ssh = FakeSSH(find_listing="\n".join(_local_relative_paths()))

        assert deploy_to_ha.prune_remote(ssh) == 0
        assert not [cmd for cmd in ssh.commands if cmd.startswith("sudo rm")]

    def test_empty_listing_is_tolerated(self):
        """``find`` prints nothing when the folder does not exist yet."""
        assert deploy_to_ha.prune_remote(FakeSSH(find_listing="")) == 0


class TestArchiveRemote:
    """A failed archive must not be reported as a successful rollback point."""

    def test_warns_and_writes_nothing_when_tar_fails(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(deploy_to_ha, "ARCHIVE_DIR", tmp_path)

        assert deploy_to_ha.archive_remote(FakeSSH(tar_status=1)) is None

        assert "WARNING" in capsys.readouterr().out
        assert list(tmp_path.iterdir()) == []

    def test_warns_when_tar_returns_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(deploy_to_ha, "ARCHIVE_DIR", tmp_path)

        assert deploy_to_ha.archive_remote(FakeSSH(tar_data=b"")) is None

        assert "nothing archived" in capsys.readouterr().out

    def test_writes_the_tarball_on_success(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(deploy_to_ha, "ARCHIVE_DIR", tmp_path)
        payload = b"\x1f\x8b\x08payload"

        target = deploy_to_ha.archive_remote(FakeSSH(tar_data=payload))

        assert target is not None
        assert target.parent == tmp_path
        assert target.read_bytes() == payload
        assert f"archived {len(payload)} bytes" in capsys.readouterr().out


class TestLegacyFolderWarning:
    def test_warns_when_the_old_domain_folder_is_deployed(self, capsys):
        deploy_to_ha.warn_if_legacy_folder_present(FakeSSH(legacy="yes"))

        out = capsys.readouterr().out
        assert "smartsolar_mppt" in out
        assert "config entry" in out

    def test_silent_when_absent(self, capsys):
        deploy_to_ha.warn_if_legacy_folder_present(FakeSSH(legacy="no"))

        assert capsys.readouterr().out == ""


class TestRestartWaitsOnConfiguredUrl:
    """The wait used to poll a hardcoded host:8123, ignoring HA_URL."""

    def test_polls_ha_url(self, monkeypatch):
        monkeypatch.setattr(deploy_to_ha, "HA_URL", "http://ha.example:9999")
        monkeypatch.setattr(deploy_to_ha.time, "sleep", lambda _seconds: None)
        seen: list[str] = []

        def fake_urlopen(request, timeout=None):  # noqa: ARG001
            seen.append(request.full_url)
            if request.full_url.endswith("/api/config"):
                return _JsonResponse({"version": "2026.9.4"})
            return _JsonResponse([{"domain": "smartsolar_ha", "state": "loaded"}])

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert seen == [
            "http://ha.example:9999/api/config",
            "http://ha.example:9999/api/config/config_entries/entry",
        ]

    def test_skips_the_wait_without_a_token(self, monkeypatch):
        monkeypatch.setattr(deploy_to_ha, "HA_URL", "http://ha.example:9999")

        def explode(*_args, **_kwargs):
            raise AssertionError("must not poll without a token")

        monkeypatch.setattr(urllib.request, "urlopen", explode)

        deploy_to_ha.restart_ha(FakeSSH(), {})  # must not raise


class TestRestartWaitsForTheIntegrationToLoad:
    """The API answers before the platforms are added.

    A verification run chained right after a restart therefore saw zero
    entities: the deploy reported success while the integration was still
    loading. The wait now also requires this domain's entry to be ``loaded``.
    """

    @staticmethod
    def _serve(monkeypatch, entry_payloads):
        """Answer /api/config with a version and the entry listing in sequence."""
        calls: list[str] = []
        remaining = list(entry_payloads)

        def fake_urlopen(request, timeout=None):  # noqa: ARG001
            calls.append(request.full_url)
            if request.full_url.endswith("/api/config"):
                return _JsonResponse({"version": "2026.9.4"})
            return _JsonResponse(remaining.pop(0) if remaining else None)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(deploy_to_ha, "HA_URL", "http://ha.example:9999")
        monkeypatch.setattr(deploy_to_ha.time, "sleep", lambda _seconds: None)
        return calls

    def test_returns_immediately_once_the_entry_is_loaded(self, monkeypatch, capsys):
        calls = self._serve(monkeypatch, [[{"domain": "smartsolar_ha", "state": "loaded"}]])

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert len(calls) == 2, "a loaded entry must not be polled again"
        assert "smartsolar_ha is loaded" in capsys.readouterr().out

    def test_keeps_waiting_while_the_entry_is_retrying(self, monkeypatch):
        calls = self._serve(
            monkeypatch,
            [
                [{"domain": "smartsolar_ha", "state": "setup_retry"}],
                [{"domain": "smartsolar_ha", "state": "not_loaded"}],
                [{"domain": "smartsolar_ha", "state": "loaded"}],
            ],
        )

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        # 1 version probe + 3 entry probes.
        assert len(calls) == 4

    def test_another_domains_loaded_entry_does_not_satisfy_the_wait(self, monkeypatch):
        calls = self._serve(
            monkeypatch,
            [
                [{"domain": "other_integration", "state": "loaded"}],
                [{"domain": "smartsolar_ha", "state": "loaded"}],
            ],
        )

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert len(calls) == 3

    def test_reports_an_entry_that_never_loads(self, monkeypatch):
        monkeypatch.setattr(deploy_to_ha, "HA_READY_ATTEMPTS", 3)
        self._serve(monkeypatch, [[{"domain": "smartsolar_ha", "state": "setup_error"}]] * 5)

        with pytest.raises(RuntimeError, match="setup_error"):
            deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

    def test_reports_a_missing_entry_instead_of_waiting_for_it(self, monkeypatch, capsys):
        calls = self._serve(monkeypatch, [[]])

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert len(calls) == 1 + deploy_to_ha.HA_MISSING_ENTRY_ATTEMPTS
        assert "no smartsolar_ha config entry found" in capsys.readouterr().out

    def test_tolerates_a_malformed_entry_listing(self, monkeypatch, capsys):
        calls = self._serve(monkeypatch, [{"unexpected": "mapping"}])

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert len(calls) == 1 + deploy_to_ha.HA_MISSING_ENTRY_ATTEMPTS
        assert "no smartsolar_ha config entry found" in capsys.readouterr().out


class TestUploadScript:
    def test_reports_a_missing_password_instead_of_raising(self, monkeypatch, capsys):
        """It used to die with ``KeyError: 'HA_PASS'`` before printing anything."""
        monkeypatch.delenv("HA_PASS", raising=False)

        assert upload_to_ha.main() == 2
        assert "HA_PASS is not set" in capsys.readouterr().out
