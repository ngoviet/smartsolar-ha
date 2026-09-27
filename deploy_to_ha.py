"""Deploy the SmartSolar MPPT integration to the live Home Assistant host.

Pipeline:
  1. ruff check + format --check + mypy + pytest        (refuse to ship red)
  2. archive the currently deployed files               (rollback safety)
  3. upload every file from custom_components/smartsolar_ha/
  4. drop __pycache__ inside the container
  5. restart Home Assistant and wait for the API to answer

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


def prune_remote(ssh: paramiko.SSHClient) -> int:
    """Delete files on the host that no longer exist locally.

    Uploading only ever adds files, so a module deleted or renamed in the repo
    stayed on the host forever. That is not merely untidy: a leftover module
    keeps being importable (and a leftover ``.py`` next to a renamed one
    shadows nothing but still ships stale code into the running integration).
    Only files inside this integration's own folder are considered, so nothing
    outside ``custom_components/smartsolar_ha`` can be touched.
    """
    wanted = {p.relative_to(SRC_DIR).as_posix() for p in _local_file_list()}
    listing = run(ssh, f"sudo find {REMOTE_DIR} -type f -printf '%P\\n' 2>/dev/null || true")
    stale = [
        rel
        for rel in (line.strip() for line in listing.splitlines())
        if rel and rel not in wanted and not rel.endswith(".pyc") and "__pycache__" not in rel.split("/")
    ]
    for rel in stale:
        run(ssh, f"sudo rm -f {REMOTE_DIR}/{rel}")
        print(f"  removed stale {rel}")
    return len(stale)


def restart_ha(ssh: paramiko.SSHClient, env: dict[str, str]) -> None:
    """Restart the container and wait until the REST API answers again."""
    run(ssh, f"sudo rm -rf {REMOTE_DIR}/__pycache__")
    print("  __pycache__ removed")
    run(ssh, "sudo docker restart homeassistant > /dev/null 2>&1 || true")
    print("  restart issued")

    token = env.get("HA_TOKEN")
    if not token:
        return

    import json
    import urllib.error
    import urllib.request

    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(5)
        try:
            request = urllib.request.Request(
                # HA_URL, not a hardcoded host: the deployment target is
                # configurable (HA_HOST / HA_URL) and the wait used to ignore it.
                f"{HA_URL}/api/config",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == 200:
                    info = json.loads(response.read())
                    print(f"  HA is back: {info.get('version')}")
                    return
        except urllib.error.URLError, TimeoutError, ConnectionError, OSError:
            continue
    raise RuntimeError("HA did not come back within 300s")


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
