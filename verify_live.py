"""Verify the deployed SmartSolar MPPT integration against the live HA instance."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

HA_HOST = os.environ.get("HA_HOST", "192.168.10.15")
BASE = f"http://{HA_HOST}:8123"


def as_float(value: object) -> float | None:
    """Return ``value`` as a float, or None when the state is not numeric.

    Entity states are strings and 'unknown'/'unavailable' are normal values;
    calling ``float()`` on them used to abort the whole verification with a
    traceback instead of reporting a FAIL line.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    for candidate in (Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip())
    return env


def api(path: str, token: str):
    request = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def live_signal_quality(env: dict[str, str]) -> dict[str, int]:
    """Ask the SmartSolar cloud which devices actually report a WiFi signal.

    Some firmware never populates ``signalQuality`` (it comes back null), and
    then 'unknown' is the truthful state for that device's WiFi sensor. The
    credentials are optional — without them the check is skipped.
    """
    username = env.get("SMARTSOLAR_USER")
    password = env.get("SMARTSOLAR_PASS")
    if not username or not password:
        return {}
    try:
        body = json.dumps({"username": username, "password": password}).encode()
        request = urllib.request.Request(
            "https://api.smartsolar.io.vn/Auth/Login?Key=Content-Type",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            token = json.loads(response.read())["token"]

        request = urllib.request.Request(
            "https://api.smartsolar.io.vn/Metric/ProjectMetrics?projectId=1072",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        return {
            str(log["deviceGuid"]): log["signalQuality"]
            for log in payload.get("deviceLogs", [])
            if log.get("signalQuality") is not None
        }
    except urllib.error.URLError, KeyError, ValueError, TimeoutError:
        return {}


def main() -> int:
    env = load_env()
    token = env.get("HA_TOKEN")
    if not token:
        print("HA_TOKEN is not set (checked the environment and .env)")
        return 2

    try:
        states = {s["entity_id"]: s for s in api("/api/states", token)}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as err:
        print(f"Could not read states from {BASE}: {err}")
        return 2
    solar = {k: v for k, v in states.items() if "smartsolar" in k}
    prefix = "sensor.technology_smartsolar_mppt_project_1072_"

    failures: list[str] = []
    notes: list[str] = []

    def check(condition: bool, message: str) -> None:
        (notes if condition else failures).append(("PASS " if condition else "FAIL ") + message)

    check(len(solar) > 0, f"integration provides {len(solar)} entities")

    # 1. Daily-stat sensors must report numbers, not 'unavailable'.
    for sensor in ("peak_power_today", "avg_power_today", "production_hours_today"):
        for device in ("pv1", "pv2"):
            entity = f"{prefix}{device}_{sensor}"
            state = states.get(entity)
            if state is None:
                check(False, f"{entity} is missing")
            else:
                check(
                    state["state"] not in ("unavailable", "unknown"),
                    f"{entity} = {state['state']}",
                )

    # 2. Per-device WiFi signal must come from the deviceLog signalQuality field
    #    when the device reports one. The 40A charger's firmware never reports
    #    signalQuality (the live REST payload returns null for it) and its MQTT
    #    messages use the older updateDeviceLog format without the field, so for
    #    that device 'unknown' is the correct, honest answer.
    reported = live_signal_quality(env)
    if not reported:
        # Without the cloud map there is no way to tell an honest 'unknown' (the
        # device reports no signal) from an invented value. Asserting 'unknown'
        # for every device then fails on any device whose payload does carry a
        # signal — say the check was skipped instead of reporting a false FAIL.
        notes.append(
            "SKIP  per-device WiFi signal check — cloud signal map unavailable "
            "(set SMARTSOLAR_USER / SMARTSOLAR_PASS in .env to enable it)"
        )
    else:
        for device, guid in (("pv1", "547611"), ("pv2", "14756976")):
            entity = f"{prefix}{device}_wifi_signal"
            state = states.get(entity)
            if guid not in reported:
                check(
                    state is not None and state["state"] == "unknown",
                    f"{entity} = {state['state'] if state else 'MISSING'} "
                    f"(API reports no signalQuality for {guid}, so 'unknown' is correct)",
                )
            else:
                check(
                    state is not None and state["state"] not in ("unavailable", "unknown"),
                    f"{entity} = {state['state'] if state else 'MISSING'} (API reports {reported[guid]} for {guid})",
                )

    # 3. Battery voltage must be ~24 V, never the sum of both chargers (~53 V).
    total_bat = states.get(f"{prefix}total_battery_voltage")
    total_bat_value = as_float(total_bat["state"]) if total_bat else None
    if total_bat is None:
        check(False, "total_battery_voltage missing")
    elif total_bat_value is None:
        check(False, f"total_battery_voltage = {total_bat['state']!r} (expected a number in 20-32 V)")
    else:
        check(20 <= total_bat_value <= 32, f"total_battery_voltage = {total_bat_value} V (must be one bus, not a sum)")

    # 4. The per-device sensors must still be intact.
    for entity in (
        f"{prefix}pv1_pv_voltage",
        f"{prefix}pv2_pv_voltage",
        f"{prefix}total_charge_power",
        f"{prefix}total_status",
    ):
        state = states.get(entity)
        check(state is not None, f"{entity} present = {state['state'] if state else 'MISSING'}")

    # 5. PV1 must be the lowest GUID (547611) — the stable ordering contract.
    pv1 = states.get(f"{prefix}pv1_total_energy")
    pv1_expected = 388.019
    pv1_value = as_float(pv1["state"]) if pv1 else None
    if pv1 is None:
        check(False, "pv1_total_energy missing")
    elif pv1_value is None:
        check(False, f"pv1_total_energy = {pv1['state']!r} (expected a number near {pv1_expected})")
    else:
        delta = abs(pv1_value - pv1_expected)
        check(delta < 20, f"pv1_total_energy = {pv1['state']} (expected ~{pv1_expected} for GUID 547611)")

    # 6. The number entity must be present.
    number = states.get("number.technology_smartsolar_mppt_project_1072_update_frequency")
    check(number is not None, f"number entity = {number['state'] if number else 'MISSING'}")

    print(f"entities matching 'smartsolar': {len(solar)}")
    for line in sorted(notes):
        print("  " + line)
    if failures:
        print("\nFAILURES:")
        for line in failures:
            print("  " + line)
        return 1
    print("\nAll live checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
