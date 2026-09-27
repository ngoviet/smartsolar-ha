"""Tests for the deploy/upload helper scripts.

``deploy_to_ha.py`` deletes files on the live host and overwrites the running
integration, so its bookkeeping deserves the same scrutiny as the integration
itself. Both scripts import ``paramiko`` at module level (a runtime-only
dependency, not part of the ``[test]`` extra), so a stub is installed when it is
not actually installed.
"""

from __future__ import annotations

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
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        expected = f"run: ruff {subcommand} "
        line = next((line for line in workflow.splitlines() if line.strip().startswith(expected)), None)

        assert line is not None, f"ci.yml no longer runs 'ruff {subcommand}'"
        assert line.strip().removeprefix("run:").split() == ["ruff", *subcommand.split(), *deploy_to_ha.SOURCES]


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

        class _Response:
            status = 200

            def read(self) -> bytes:
                return b'{"version": "2026.9.3"}'

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *_exc: object) -> bool:
                return False

        def fake_urlopen(request, timeout=None):  # noqa: ARG001
            seen.append(request.full_url)
            return _Response()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        deploy_to_ha.restart_ha(FakeSSH(), {"HA_TOKEN": "token"})

        assert seen == ["http://ha.example:9999/api/config"]

    def test_skips_the_wait_without_a_token(self, monkeypatch):
        monkeypatch.setattr(deploy_to_ha, "HA_URL", "http://ha.example:9999")

        def explode(*_args, **_kwargs):
            raise AssertionError("must not poll without a token")

        monkeypatch.setattr(urllib.request, "urlopen", explode)

        deploy_to_ha.restart_ha(FakeSSH(), {})  # must not raise


class TestUploadScript:
    def test_reports_a_missing_password_instead_of_raising(self, monkeypatch, capsys):
        """It used to die with ``KeyError: 'HA_PASS'`` before printing anything."""
        monkeypatch.delenv("HA_PASS", raising=False)

        assert upload_to_ha.main() == 2
        assert "HA_PASS is not set" in capsys.readouterr().out
