"""Deploy the SmartSolar MPPT integration to the live Home Assistant host.

Pipeline:
  1. ruff check + format --check + mypy + pytest        (refuse to ship red)
  2. archive the currently deployed files               (rollback safety)
  3. upload every file from custom_components/smartsolar_ha/
  4. drop __pycache__ inside the container
  5. restart Home Assistant, then wait for the API *and* for this integration's
     config entry to reach "loaded"

Usage:
    python deploy_to_ha.py            # full pipeline
    python deploy_to_ha.py --skip-checks
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import paramiko

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "custom_components" / "smartsolar_ha"
REMOTE_ROOT = "/homeassistant/custom_components"
REMOTE_DIR = f"{REMOTE_ROOT}/smartsolar_ha"
ARCHIVE_DIR = PROJECT_ROOT / "_local_archive" / "deployed"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

# Home Assistant resolves an integration from its folder name, so the folder is
# the domain: one source of truth for the readiness check below.
INTEGRATION_DOMAIN = SRC_DIR.name

# Home Assistant answers on the REST API before its integration platforms are
# added, so "the API replied" does not mean "the deployment is live". Both waits
# poll every HA_READY_INTERVAL s and may block up to HA_FETCH_TIMEOUT s on each
# fetch, so the worst case before they give up is
# HA_READY_ATTEMPTS * (HA_READY_INTERVAL + HA_FETCH_TIMEOUT) s.
HA_READY_INTERVAL = 5
HA_READY_ATTEMPTS = 60
HA_FETCH_TIMEOUT = 10
HA_READY_SECONDS = HA_READY_ATTEMPTS * (HA_READY_INTERVAL + HA_FETCH_TIMEOUT)

# A config entry is listed nearly as soon as the API answers. If this domain's
# entry is still missing after this many polls there is no entry for it at all
# (a fresh install, or a domain rename), which is reported instead of waited on.
HA_MISSING_ENTRY_ATTEMPTS = 3

HA_HOST = os.environ.get("HA_HOST", "192.168.10.15")
HA_USER = os.environ.get("HA_USER", "vokupt")
HA_URL = os.environ.get("HA_URL", f"http://{HA_HOST}:8123")

# Keep in sync with .github/workflows/ci.yml: the local gate used to lint only
# upload_to_ha.py, so the deploy script and verify_live.py were never checked
# before shipping even though CI checks the first one.
SOURCES = ["custom_components/", "tests/", "upload_to_ha.py", "deploy_to_ha.py", "verify_live.py"]


def load_env() -> dict[str, str]:
    """Read HA_PASS/HA_TOKEN from the repository .env or the process env."""
    env = dict(os.environ)
    for candidate in (PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def run_checks() -> None:
    """Run the full local gate; abort the deploy when anything is red."""
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    ruff = str(VENV_PYTHON.parent / "ruff.exe") if VENV_PYTHON.exists() else "ruff"

    checks = [
        ("ruff check", [ruff, "check", *SOURCES]),
        ("ruff format", [ruff, "format", "--check", *SOURCES]),
        ("mypy", [python, "-m", "mypy", "custom_components/"]),
        ("pytest", [python, "-m", "pytest", "tests/", "-q", "--no-header", "-p", "no:cacheprovider"]),
    ]
    for name, cmd in checks:
        print(f"  -> {name}")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout[-4000:])
            print(result.stderr[-4000:])
            raise SystemExit(f"ABORT: {name} failed (exit {result.returncode})")


def ssh_connect(env: dict[str, str]) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        HA_HOST,
        username=HA_USER,
        password=env["HA_PASS"],
        timeout=20,
    )
    return ssh


def run(ssh: paramiko.SSHClient, cmd: str) -> str:
    _stdin, stdout, stderr = ssh.exec_command(cmd)
    status = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if status != 0:
        raise RuntimeError(f"command failed [{status}]: {cmd}\n{err.strip()}")
    return out


def archive_remote(ssh: paramiko.SSHClient) -> Path | None:
    """Download the currently deployed integration as a tarball.

    Returns the archive path, or None when there was nothing to archive (for
    example a first-time install, where the remote folder does not exist yet).
    The tar exit status used to be discarded, so a failed archive was reported
    as "archived 0 bytes" and the deploy continued without a rollback point.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = ARCHIVE_DIR / f"smartsolar_ha_{stamp}.tar.gz"

    _stdin, stdout, stderr = ssh.exec_command(f"sudo tar -C {REMOTE_ROOT} -czf - smartsolar_ha")
    data = stdout.read()
    status = stdout.channel.recv_exit_status()
    if status != 0 or not data:
        print(f"  WARNING: nothing archived (tar exit {status}); no rollback point for this deploy")
        err = stderr.read().decode(errors="replace").strip()
        if err:
            print(f"  {err}")
        return None

    target.write_bytes(data)
    print(f"  archived {len(data)} bytes -> {target.name}")
    return target


def warn_if_legacy_folder_present(ssh: paramiko.SSHClient) -> None:
    """Warn when the pre-2.0.0 ``smartsolar_mppt`` folder is still deployed.

    v2.0.0 renamed the domain to ``smartsolar_ha``. Home Assistant resolves an
    integration by folder name, so a leftover ``smartsolar_mppt`` folder is not
    just dead weight: its stored config entry can no longer be loaded and logs
    an error on every start.
    """
    legacy = f"{REMOTE_ROOT}/smartsolar_mppt"
    _stdin, stdout, _stderr = ssh.exec_command(f"test -d {legacy} && echo yes || echo no")
    present = stdout.read().decode(errors="replace").strip()
    stdout.channel.recv_exit_status()
    if present == "yes":
        print(
            f"  WARNING: legacy folder {legacy} still exists on the host.\n"
            "           Delete it and remove the stale 'smartsolar_mppt' config entry\n"
            "           in Home Assistant, or it will log an error on every restart."
        )


def _local_file_list() -> list[Path]:
    """Return every file of the integration that should exist on the host."""
    return sorted(p for p in SRC_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def upload_tree(ssh: paramiko.SSHClient) -> int:
    """Upload every file, base64 encoded, via sudo tee."""
    files = _local_file_list()
    for local in files:
        rel = local.relative_to(SRC_DIR).as_posix()
        remote = f"{REMOTE_DIR}/{rel}"
        payload = base64.b64encode(local.read_bytes()).decode()
        remote_dir = remote.rsplit("/", 1)[0]
        run(ssh, f"sudo mkdir -p {remote_dir}")
        # Chunk so no single shell command gets unwieldy.
        chunks = [payload[i : i + 51200] for i in range(0, len(payload), 51200)]
        for index, chunk in enumerate(chunks):
            op = "tee" if index == 0 else "tee -a"
            run(ssh, f"echo '{chunk}' | sudo {op} {remote}.b64 > /dev/null")
        run(ssh, f"sudo sh -c 'base64 -d {remote}.b64 > {remote} && rm {remote}.b64'")
        print(f"  ok {rel}")
    return len(files)


def _remote_file_listing(ssh: paramiko.SSHClient) -> list[str]:
    """List the integration's files on the host, relative to ``REMOTE_DIR``.

    Home Assistant OS ships BusyBox's ``find``, which does **not** support
    ``-printf``; the original command failed there, its ``|| true`` swallowed the
    error, and an empty listing meant "nothing is stale" — so pruning silently
    did nothing at all on a real host. The absolute paths BusyBox prints are
    trimmed here instead, and the command is deliberately not wrapped in
    ``|| true``: a listing that cannot be read must fail the deploy rather than
    pretend the host matches the repository.
    """
    listing = run(ssh, f"sudo find {REMOTE_DIR} -type f")
    prefix = f"{REMOTE_DIR}/"
    entries = [line.strip() for line in listing.splitlines() if line.strip()]
    return [entry[len(prefix) :] if entry.startswith(prefix) else entry for entry in entries]


def prune_remote(ssh: paramiko.SSHClient) -> int:
    """Delete files on the host that no longer exist locally.

    Uploading only ever adds files, so a module deleted or renamed in the repo
    stayed on the host forever. That is not merely untidy: a leftover module
    keeps being importable (a stale ``example_configuration.yaml`` or
    ``.gitignore`` is harmless, a stale ``.py`` is not). Only files inside this
    integration's own folder are considered, so nothing outside
    ``custom_components/smartsolar_ha`` can be touched.
    """
    wanted = {p.relative_to(SRC_DIR).as_posix() for p in _local_file_list()}
    listing = _remote_file_listing(ssh)
    if not listing:
        raise RuntimeError(
            f"the host listing of {REMOTE_DIR} came back empty although {len(wanted)} files "
            "were just uploaded; refusing to report a clean prune without a readable listing"
        )
    stale = [
        rel for rel in listing if rel not in wanted and not rel.endswith(".pyc") and "__pycache__" not in rel.split("/")
    ]
    for rel in stale:
        run(ssh, f"sudo rm -f {REMOTE_DIR}/{rel}")
        print(f"  removed stale {rel}")
    return len(stale)


def _fetch_json(url: str, token: str) -> object:
    """GET a JSON document from the Home Assistant REST API."""
    import json
    import urllib.request

    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=HA_FETCH_TIMEOUT) as response:
        if response.status != 200:
            return None
        return json.loads(response.read())


def _entry_status(payload: object) -> tuple[bool, str]:
    """Report whether this integration is listed, and in which state.

    A *valid* listing distinguishes the two cases that matter: Home Assistant
    keeps listing an entry it failed to load (``setup_retry`` / ``setup_error``),
    so "listed but not loaded" is not the same as "no entry for this domain".
    A payload that is not a list is neither: it is an unreadable answer.
    """
    if not isinstance(payload, list):
        return False, ""
    for entry in payload:
        if isinstance(entry, dict) and entry.get("domain") == INTEGRATION_DOMAIN:
            state = entry.get("state")
            return True, state if isinstance(state, str) else ""
    return False, ""


def _wait_for_api(token: str) -> None:
    """Wait until the REST API answers, then report the version it runs."""
    import json
    import urllib.error

    for _attempt in range(HA_READY_ATTEMPTS):
        time.sleep(HA_READY_INTERVAL)
        try:
            info = _fetch_json(f"{HA_URL}/api/config", token)
        except urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError:
            continue
        if isinstance(info, dict):
            print(f"  HA is back: {info.get('version')}")
            return
    raise RuntimeError(f"HA did not come back within {HA_READY_SECONDS}s")


def _wait_for_integration(token: str) -> None:
    """Wait until this integration's config entry reports ``loaded``.

    The REST API answers while the integration platforms are still being added,
    so "the API replied" is not "the deployment is live": a verification run
    chained right after the restart used to find zero entities.

    Three outcomes are kept apart on purpose. A listing that was *read* and does
    not mention this domain is reported and the deploy continues (a fresh
    install, or a renamed domain, has nothing to verify). A listing that was read
    but shows another state keeps waiting and then fails, because that is the
    new code not loading. A listing that could **not** be read (HTTP error,
    timeout, non-list body) is neither absence nor failure yet — treating it as
    absence used to report a clean success without ever seeing ``loaded``.
    """
    import json
    import urllib.error

    state = ""
    read_listing = False
    seen_domain = False
    missing = 0
    for _attempt in range(HA_READY_ATTEMPTS):
        try:
            payload = _fetch_json(f"{HA_URL}/api/config/config_entries/entry", token)
        except urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError:
            payload = None

        if not isinstance(payload, list):
            # An unreadable answer is neither absence nor failure yet, and it
            # must not count towards the "no entry" threshold.
            time.sleep(HA_READY_INTERVAL)
            continue

        read_listing = True
        listed_now, state_now = _entry_status(payload)
        if listed_now:
            seen_domain = True
            missing = 0
            if state_now:
                state = state_now
            if state_now == "loaded":
                print(f"  {INTEGRATION_DOMAIN} is loaded")
                return
        else:
            # A listing that was read and does not mention this domain.
            missing += 1
            if missing >= HA_MISSING_ENTRY_ATTEMPTS:
                print(f"  no {INTEGRATION_DOMAIN} config entry found; nothing to verify")
                return
        time.sleep(HA_READY_INTERVAL)

    if not read_listing:
        raise RuntimeError(
            f"could not read the {INTEGRATION_DOMAIN} config-entry listing from "
            f"{HA_URL}/api/config/config_entries/entry within {HA_READY_SECONDS}s"
        )
    if not seen_domain:
        raise RuntimeError(
            f"the {INTEGRATION_DOMAIN} config entry never reached 'loaded' within "
            f"{HA_READY_SECONDS}s; the readable config-entry "
            f"listings did not contain the domain"
        )
    raise RuntimeError(f"the {INTEGRATION_DOMAIN} config entry stayed '{state or 'unknown'}' for {HA_READY_SECONDS}s")


def restart_ha(ssh: paramiko.SSHClient, env: dict[str, str]) -> None:
    """Restart the container, then wait until the integration is really loaded."""
    run(ssh, f"sudo rm -rf {REMOTE_DIR}/__pycache__")
    print("  __pycache__ removed")
    run(ssh, "sudo docker restart homeassistant > /dev/null 2>&1 || true")
    print("  restart issued")

    token = env.get("HA_TOKEN")
    if not token:
        return

    _wait_for_api(token)
    _wait_for_integration(token)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-checks", action="store_true")
    args = parser.parse_args()

    env = load_env()
    if "HA_PASS" not in env:
        print("HA_PASS is not set (checked environment and .env)")
        return 2

    if not args.skip_checks:
        print("Local gate:")
        run_checks()
        print("  all checks passed")

    print(f"Connecting to {HA_USER}@{HA_HOST}...")
    ssh = ssh_connect(env)
    try:
        print("Checking deployed state:")
        warn_if_legacy_folder_present(ssh)

        print("Archiving deployed version:")
        archive_remote(ssh)

        print("Uploading:")
        count = upload_tree(ssh)

        print("Removing files that no longer exist locally:")
        stale = prune_remote(ssh)
        if not stale:
            print("  none")

        print("Restarting Home Assistant:")
        restart_ha(ssh, env)
    finally:
        ssh.close()

    print(f"\nDeployed {count} files to {REMOTE_DIR} ({stale} stale file(s) removed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
