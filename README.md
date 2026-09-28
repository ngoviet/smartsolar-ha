# SmartSolar MPPT — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-551%20passed-brightgreen)](https://github.com/ngoviet/smartsolar-ha)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar-ha&category=integration)

Home Assistant custom integration for **SmartSolar MPPT** solar charge controllers. Monitor PV voltage, charge current, daily/total energy, temperature, device status, and WiFi signal quality in real time via the SmartSolar Cloud API and MQTT.

---

## Features

- **MQTT real-time updates** — instant sensor data via SmartSolar MQTT broker (no polling delay)
- **WiFi signal monitoring** — track signal quality (0–100%) for each MPPT controller
- **Real-time monitoring** — PV voltage & current, battery voltage & current, charge power, temperature, status
- **Daily & total energy tracking** — kWh generated today and lifetime
- **Project mode** — aggregate multiple MPPT controllers into a single dashboard
- **Device mode** — monitor individual controllers
- **Adjustable polling** — configurable update interval from 1 to 30 seconds
- **Auto token refresh** — transparently refreshes API tokens before expiry
- **Auto MQTT credentials** — MQTT username/password discovered automatically from the API
- **Graceful degradation** — REST API polling continues if MQTT is unavailable
- **UI config flow** — step-by-step setup via Home Assistant's native interface
- **Reconfigure support** — edit credentials without removing and re-adding the integration
- **Vietnamese & English** — localized UI with translation file support

## Supported Devices

| Model | PV Voltage | Charge Current | Battery Voltage | Connectivity |
|-------|-----------|---------------|----------------|-------------|
| **40A WiFi** | 18–100V | 1–40A | 6–120V | WiFi + SmartSolar API |
| **45A WiFi** | 18–100V | 1–45A | 6–120V | WiFi + SmartSolar API |
| **60A WiFi** | 18–100V | 1–60A | 6–120V | WiFi + SmartSolar API |

Compatible with other SmartSolar devices using the same cloud API.

## Sensors

| Sensor | Unit | Description |
|--------|------|-------------|
| PV Voltage | V | Solar panel input voltage |
| PV Current | A | Solar panel input current |
| Battery Voltage | V | Battery/output voltage |
| Battery Current | A | Charge current to battery |
| Charge Power | W | Current charging power |
| Today Energy | kWh | Energy generated today |
| Total Energy | kWh | Lifetime energy generated |
| Temperature | °C | Controller temperature |
| Status | — | Operating status (Online / Charging / Idle / Fault) |
| WiFi Signal | % | WiFi signal quality (0–100%, via MQTT or REST) |
| Peak Power Today | W | Highest power output reached today |
| Avg Power Today | W | Average power output today |
| Production Hours Today | h | Hours of production today (above ~5 W) |

## Installation

### HACS (Recommended)

1. Add this repository to HACS: `https://github.com/ngoviet/smartsolar-ha`
2. Search for **"SmartSolar MPPT"** in HACS → Integrations
3. Click **Download**
4. Restart Home Assistant

### Manual

```bash
cd /config/custom_components
# the folder name must match the integration domain
git clone https://github.com/ngoviet/smartsolar-ha.git smartsolar_ha
# Restart Home Assistant
```

> Upgrading from v1.x? The folder and domain changed from `smartsolar_mppt` to
> `smartsolar_ha` — see the [v2.0.0 changelog](#v200--domain-rename--audit-fixes).

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"SmartSolar MPPT"**
3. Enter your SmartSolar account credentials
4. Choose mode:
   - **Device** — monitor a single controller by Chipset ID
   - **Project** — monitor via Project ID or multiple Device IDs
5. Enter the required IDs

### Update Interval

After setup, a **number entity** (`Update Frequency`) allows changing the polling interval from 1 to 30 seconds without editing configuration files.

## Architecture

```
        SmartSolar Cloud API (api.smartsolar.io.vn)
        |                               |
HTTP REST API              SmartSolar MQTT Broker
(POST /Auth/Login,         (mqttx.smartsolar.io.vn:8084)
 GET /Metric/*)                |
        |                  SmartSolarMQTTClient
        |                  (WebSocket Secure, WSS)
SmartSolarAPI                  |
(auth, token refresh,          |
 retry w/ backoff)             |
        |                       |
        +-------+---------------+
                |
SmartSolarDataUpdateCoordinator
(polling + real-time MQTT merge)
                |
      +-----+------+-----+
      |     |      |     |
   Sensor  Number  diag-  MQTT
   (×13)  (update nostic  client
           interval)
```

## Changelog

### v2.0.1 — audit release

No configuration change: this release only fixes behaviour, so an existing
`smartsolar_ha` entry keeps working.

**Correctness fixes:**

- **Live MQTT data is no longer hidden during a cloud outage.** When the HTTP
  poll failed, every entity reported `unavailable` even though real-time values
  were still arriving over MQTT (and being computed) — so those readings were
  discarded by Home Assistant and punched a hole in the recorder. A sensor is now
  available when either path can feed it. The `Update Frequency` control stays
  available too: it is a local setting, and it used to disappear exactly when you
  might want to slow the polling down.
- **Device mode publishes the right charger's data.** Device mode monitors one
  controller, but entering several Chipset IDs was accepted and then only the
  first was used — while the extra ID still passed the MQTT filter, and device
  mode merges every accepted device into a single stream set. The second
  charger's readings could therefore appear on the first charger's sensors. The
  config flow now refuses more than one ID in device mode (with a clear message),
  and an entry that already contains extras can no longer show wrong data.
- **Legacy metric names arriving inside MQTT `dataStreams` are no longer
  dropped.** Firmware that publishes `charging_power` / `yield_today` /
  `yield_total` inside `dataStreams` had all of those values filed under names no
  sensor reads; the field mapping is now applied there too.
- **Synthesis values are validated like every other reading.** The project
  "Total" sensors read the cloud's `synthesisStreams` without the guards the
  per-device path had, so NaN/Infinity could become a state (poisoning long-term
  statistics) and the per-sensor ceiling was skipped. A value that fails
  validation now falls back to the local per-device aggregation.
- **A malformed status code can no longer break an entity update.**
  `int(float("inf"))` raises `OverflowError`, which was not caught — one bad
  status stream turned into an error instead of an `Unknown (…)` state.
- **MQTT reconnects at a sane pace.** A broker that closed the subscription
  cleanly used to send the client straight back into connect with no delay, and
  cancelling the client during the reconnect wait left diagnostics reporting a
  live connection.
- **A failed setup cleans up after itself.** If a platform failed to load, the
  poll timer, midnight listener, HTTP session and MQTT task survived and Home
  Assistant's automatic setup retry added another poll timer each time.
- **Unloading is all-or-nothing.** Platforms are now unloaded before anything is
  torn down, so a refused unload no longer leaves an entry that is still loaded
  but with real-time updates and polling permanently stopped.
- **The `refresh_token` service is removed when the last entry is unloaded**, and
  it no longer lingers in the service registry.
- **The reauth and reconfigure dialogs are translated** (they previously rendered
  raw field keys), and both now reject blank or wrong credentials *before*
  writing them — reconfiguring with an empty password used to silently break a
  working entry.
- **Migration is safe for old entries**: a legacy scalar or comma-separated string
  `chipset_ids` used to abort the migration or turn `"547611,14756976"` into one
  entry per character.
- **A corrupt `update_interval` cannot create a polling storm** — the value is
  clamped to the same 1–30 s range the `Update Frequency` entity enforces.
- Also fixed: NaN/Infinity no longer reach the interval entity, a device removed
  from a project can no longer be resurrected from cached MQTT data, the deploy
  script prunes files that no longer exist in the repository, and `"deviceLogs":
  null` no longer crashes `verify_live.py`.

**Documentation corrections** (claims that were never true in this repository):

- `allow_multiple_instances` (listed as a v1.3.0 feature) is **not** a Home
  Assistant config-flow attribute. It was dead code and has been removed; multiple
  entries are allowed simply because the manifest does not set
  `single_config_entry`.
- The sensors inherit `RestoreEntity`, but they do **not** restore a stale value:
  a sensor shows `unknown` until the first successful poll (or MQTT message),
  because a restored reading could be arbitrarily old. Only the `Update Frequency`
  entity restores its own last value.

**Tooling:**

- **551 tests** (was 366). Every fix above has a regression test, and each of
  those tests was verified to fail before the fix.
- The declared tool versions can now actually run the gate: `ruff>=0.4` could not
  parse this repository's `pyproject.toml` at all, `mypy>=1.9` reported errors the
  pinned `mypy` accepts, and the pre-commit `ruff` pin (`v0.4.0`) failed on every
  commit.

### v2.0.0 — domain rename + audit fixes

> ⚠️ **Breaking change: the integration domain is now `smartsolar_ha`.**
> Home Assistant identifies an integration by its folder name, which must equal
> the `domain` in `manifest.json`, so this cannot be a drop-in update: an
> existing v1.x entry stops loading. To keep your entity IDs, dashboards and
> long-term statistics, migrate the stored entry in place — deleting and
> re-adding creates `_2`-suffixed entity IDs and orphans statistics — see the
> migration procedure in CLAUDE.md.

**Correctness fixes:**
- **A `"deviceLogs": null` response no longer kills the poll.** A `len()` call in a
  debug statement raised `UpdateFailed: object of type 'NoneType' has no len()`
  (debug arguments are evaluated even when debug logging is off), leaving every
  entity unavailable. `deviceLogs` is now normalized in one shared helper used by
  the coordinator, the sensors and diagnostics.
- **NaN/Infinity can no longer become a sensor state.** `json.loads` accepts the
  bare `NaN`/`Infinity` literals, and NaN slips through every `> max_value`
  comparison, so it used to reach Home Assistant and poison that sensor's
  long-term statistics. All non-finite values are rejected at the value layer.
- **A rejected API token recovers by itself.** On HTTP 401 the cached token is now
  discarded, so the next poll logs in again — previously the ~30-day token stayed
  "valid" and every later poll failed until Home Assistant was restarted.
- **Non-object API responses are classified.** A JSON list/HTML body used to
  escape as `AttributeError`, or as an unclassified `JSONDecodeError`.
- **HTTP 408/429 are retried** with the same backoff as a 5xx (`Retry-After`
  situations are transient; 4xx client errors still fail fast).
- **No more log flooding** while the cloud has no device logs: a per-sensor,
  per-poll `WARNING` became `DEBUG`.
- **MQTT `null` fields are dropped** instead of being written into `dataStreams`
  as the literal string `"None"`, which shadowed the real value.
- **`connected` no longer lies after shutdown** — stopping the MQTT client (or a
  message loop that ends) clears the flag that diagnostics report.
- **`refresh_token` now requires `entry_id`** (as `services.yaml` always
  documented). Without it the service silently did nothing; an unknown entry is
  now reported as a service validation error.
- Extra hardening: `verify_live.py` reports a `FAIL` line instead of crashing when
  a state is `unknown`, and the deploy gate lints the same files as CI.

**Tooling:**
- **366 tests** (was 261), including a regression test per fix above and a new
  `tests/test_helpers.py`.
- `requires-python`/classifiers now state the real floor (HA 2026.x needs
  **≥ 3.14.2**) and `ruff` targets `py314`; `deploy_to_ha.py` and CI lint the same
  file list.
- Removed the unused `custom_components/…/hacs.json`: HACS only reads the
  `hacs.json` at the repository root, and that copy contradicted it.

### v1.5.1 (2026-09-27) — audit release

**Correctness fixes:**
- **Project voltage/temperature no longer summed.** Both chargers share one 24 V
  bus; the aggregate used to report ~53 V for battery voltage. Each sensor type
  now has an explicit strategy: currents/power/energy sum, voltage/temperature/
  WiFi average, status takes the worst case.
- **Project status sensor always returned `unknown`** — status was mapped to text
  before cross-device aggregation. The numeric code is aggregated first, then mapped.
- **API retry/backoff actually runs now.** `_request_with_retry` existed but no
  request used it, so the documented 1s/2s retry never happened.
- **Token expiry parsing can no longer break refreshes.** A naive timestamp from
  the API used to raise `TypeError` when compared with an aware `utcnow()`.
- **MQTT data from other customers is rejected.** The SmartSolar broker is shared
  by every account; a foreign device GUID can no longer be injected into this
  config entry's data.
- **Malformed MQTT/deviceLog payloads can no longer crash a poll.**
- **Daily statistics sensors now report numbers.** They were registered but never
  updated on the previously deployed build.
- **`today_kwh` builds statistics again.** `state_class: measurement` with
  `device_class: energy` is rejected by Home Assistant, which logged a warning per
  entity and skipped the statistics; it is now `total_increasing`.
- **Stable PV1/PV2 labels.** Device order is sorted numerically by GUID, so
  entity IDs and dashboards no longer shuffle between restarts.
- **Clean unload.** The coordinator's poll timer and midnight listener are now
  actually stopped (`async_shutdown()` is a coroutine and was not awaited).
- **Per-device WiFi signal** reads the `signalQuality` field that REST reports
  outside `dataStreams`, while still preferring live MQTT values.

**Tooling:**
- **261 tests** (was 121), including `tests/test_e2e.py` which drives the real
  `async_setup_entry` / `async_unload_entry` against a real Home Assistant core.
- **mypy is a hard CI gate** — it previously ran as `mypy … || true`, hiding 29
  type errors.
- `deploy_to_ha.py` — gated deploy (lint + format + types + tests → backup →
  upload → restart → wait for the API).
- `verify_live.py` — asserts the deployed entities are correct on a live instance.

### v1.4.0 (2026-06-22)

**New Features:**
- **MQTT real-time updates** — instant sensor data via SmartSolar MQTT broker (WebSocket Secure). No polling delay for live metrics.
- **WiFi Signal Quality sensor** — monitor WiFi signal strength (0–100%) for each MPPT controller (available via MQTT).
- **Auto MQTT credential discovery** — username and password retrieved automatically from the SmartSolar REST API (`GET /Device/Status`).
- **Graceful degradation** — REST API polling continues normally if MQTT is unavailable or `aiomqtt` is not installed.

**Architecture:**
- New `mqtt_client.py` — async MQTT client with auto-reconnection, dual payload format support (dataStreams + flat dict), base64 password decoding.
- Coordinator extended with `async_process_mqtt_data()` — merges MQTT real-time data into API responses in-place.
- Support for two MQTT payload formats: standard `dataStreams` array and flat key-value dict (older firmware).

**Code Quality:**
- **121-unit test suite** (up from 93) covering `api.py`, `sensor.py`, `mqtt_client.py`, `number.py`, `config_flow.py`, `coordinator.py`, `const.py`
- 18 new MQTT tests: payload parsing, field mapping, credential handling, graceful degradation
- New `upload_to_ha.py` deployment script

### v1.3.0 (2026-06-22)

**Critical Fixes:**
- Fix `refresh_token` service crash — wrong method name causing `AttributeError`
- Fix reconfigure flow wiping config entries — now properly merges existing data
- Fix duplicate `"entity"` key breaking all sensor translations silently
- Fix hardcoded Vietnamese "Tổng" in sensor names → English "Total"

**New Features:**
- **Re-authentication flow** (`async_step_reauth`) — handle expired credentials without re-configuring
- **Config entry diagnostics** (`diagnostics.py`) — download detailed diagnostics from HA UI
- **Exponential backoff retry** — 3 attempts with 1s/2s backoff for network errors and 5xx server errors
- **Config migration** (`async_migrate_entry`) — seamless upgrade from v1.1/1.2 config entries

**Code Quality:**
- **93-unit test suite** covering `api.py`, `sensor.py`, `number.py`, `config_flow.py`, `coordinator.py`, `const.py`
- **`pyproject.toml`** with ruff linting and mypy type checking
- **`.pre-commit-config.yaml`** for automated code quality checks
- **GitHub Actions CI/CD** — Python 3.12 matrix, lint, format, tests with coverage
- **HACS validation** — automatic validation on push/PR

**Additional:**
- Vietnamese labels → English in UI (with `translations/vi.json` for Vietnamese users)
- `allow_multiple_instances` replaces deprecated `is_matching()`
- `RestoreEntity` on sensor base class preserves state across HA restarts
- Cached API client in config flow avoids creating new connections per step
- aiohttp `params=` for clean URL construction instead of manual string concatenation
- Log sanitization — summary only in debug logs, not full API response
- New files: `hacs.json`, `LICENSE`, `diagnostics.py`

### v1.2.2
- `max_value` validation to reject garbage sensor readings

### v1.2.1
- Fix config entry data loss on reconfigure
- Per-device sensor discovery from API response
- Orphaned entity cleanup on unload

### v1.2.0
- Bug fixes, performance optimization, HAOS future compatibility

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No sensor data | Verify credentials; check device is online in SmartSolar app |
| Integration won't load | Check HA logs; verify `aiohttp` is installed |
| API errors (502) | SmartSolar cloud may be temporarily down — retries automatically |
| Token expired | Auto-refresh 7 days before expiry; use `smartsolar_ha.refresh_token` service to force refresh |
| MQTT not connecting | Check that `aiomqtt>=2.0` is installed; verify network allows WSS on port 8084 |
| WiFi Signal shows "unknown" | Some older firmware doesn't include signalQuality field — normal degradation |
| MQTT "connection failed" warnings | Broker temporarily unreachable — auto-reconnects in 5s; REST polling continues |

## Services

| Service | Description |
|---------|-------------|
| `smartsolar_ha.refresh_token` | Manually refresh the API authentication token (requires `entry_id`) |

## Requirements

- Home Assistant **2026.9** or newer
- Python **3.14.2+** (required by Home Assistant 2026.x)
- `aiohttp >= 3.8.0`
- `aiomqtt >= 2.0` (optional but recommended — enables real-time MQTT updates)
- SmartSolar account (registered at [smartsolar.io.vn](https://smartsolar.io.vn))

## Contributing

Issues and pull requests are welcome.

- **Bug reports**: [Open an issue](https://github.com/ngoviet/smartsolar-ha/issues/new)
- **Feature requests**: [Open an issue](https://github.com/ngoviet/smartsolar-ha/issues/new)
- **Code**: [Create a pull request](https://github.com/ngoviet/smartsolar-ha/compare)

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Support

If this integration helps you monitor your solar energy, consider supporting its development:

**BSC / BNB Smart Chain (BEP20)**
```
0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa
```
Accepts: BTC, ETH, USDT, BNB, USDC, BUSD, CAKE

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-☕-yellow.svg)](https://www.buymeacoffee.com/ngoviet)

---

Made with ❤️ by [@ngoviet](https://github.com/ngoviet) — If you find this useful, give it a ⭐ on GitHub!
