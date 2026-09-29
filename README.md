# SmartSolar MPPT — Home Assistant Integration

[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar_ha.svg)](https://github.com/ngoviet/smartsolar_ha/releases)
[![CI](https://github.com/ngoviet/smartsolar_ha/actions/workflows/ci.yml/badge.svg)](https://github.com/ngoviet/smartsolar_ha/actions/workflows/ci.yml)
[![HACS Validation](https://github.com/ngoviet/smartsolar_ha/actions/workflows/hacs-validation.yml/badge.svg)](https://github.com/ngoviet/smartsolar_ha/actions/workflows/hacs-validation.yml)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5)](https://www.home-assistant.io)
[![Python](https://img.shields.io/badge/python-3.14.2%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar_ha&category=integration)

Custom integration for **SmartSolar MPPT** solar charge controllers. It reads
live metrics from the SmartSolar cloud API and from the SmartSolar MQTT broker,
exposes them as Home Assistant sensors, and keeps the values flowing from
whichever source is available.

- **Current version:** v2.0.3 — verified live against **HA 2026.9.4** (2026-09-28)
- **Test suite:** 567 passed, 1 skipped (ruff, format, mypy and pytest are hard gates in CI)

---

## Features

| | |
|---|---|
| **Real-time via MQTT** | Live values arrive over WebSocket Secure; sensors update without waiting for the next poll |
| **REST polling as the base** | The cloud API fills in what MQTT does not carry, such as the project-level totals |
| **Survives either outage** | If the poll fails, entities fed by MQTT stay available — and the other way round |
| **Daily statistics** | Peak power, average power and production hours for today, per device and aggregated |
| **Project or device mode** | Aggregate several controllers into one dashboard, or monitor a single one |
| **Devices and entity naming pinned** | `PV1`/`PV2` follow the numerically sorted device GUIDs, so entity IDs do not shuffle between restarts |
| **Adjustable polling** | `Update Frequency` number entity, 1–30 s, no YAML editing |
| **Self-healing auth** | Tokens refresh before expiry, and a server-rejected token is discarded so the next poll logs in again |
| **MQTT credentials discovered automatically** | Read from the cloud API; nothing to configure by hand |
| **UI config flow** | Setup, re-authentication and reconfiguration all in the Home Assistant UI (English + Vietnamese) |
| **Diagnostics download** | One click in the UI, with password and token redacted |

## Supported devices

| Model | PV voltage | Charge current | Battery voltage | Connectivity |
|-------|-----------|----------------|-----------------|--------------|
| 40A WiFi | 18–100 V | 1–40 A | 6–120 V | WiFi + SmartSolar cloud + MQTT |
| 45A WiFi | 18–100 V | 1–45 A | 6–120 V | WiFi + SmartSolar cloud + MQTT |
| 60A WiFi | 18–100 V | 1–60 A | 6–120 V | WiFi + SmartSolar cloud + MQTT |

Other SmartSolar controllers that publish to the same cloud API and broker work
too — the integration does not hard-code model names.

## Installation

### HACS (recommended)

This repository is **not** in HACS's default list, so add it as a *custom*
repository:

1. HACS → **Integrations** → ⋮ (top right) → **Custom repositories**
2. Repository: `https://github.com/ngoviet/smartsolar_ha`, category **Integration**
3. Search for **SmartSolar MPPT** in HACS and click **Download**
4. Restart Home Assistant

The button above opens the same dialog on your own instance.

### Manual

```bash
cd /config/custom_components
# the folder name must equal the integration domain
git clone https://github.com/ngoviet/smartsolar_ha.git smartsolar_ha
# then restart Home Assistant
```

> **Upgrading from v1.x?** The folder and domain changed from `smartsolar_mppt`
> to `smartsolar_ha` in v2.0.0. Home Assistant resolves an integration by its
> folder name, so an old entry cannot load under the new name. Migrate the stored
> entry instead of deleting it — see
> [Migration from v1.x](#migration-from-v1x).

## Configuration

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **SmartSolar MPPT**
3. Enter your SmartSolar account username and password
4. Choose the mode:
   - **Device** — one controller, identified by its **Chipset ID**
   - **Project** — every controller of a project, by **Project ID**, or by a list
     of **Device IDs**
5. Enter the IDs and submit

Credentials are validated before the entry is created, and the same validation
runs for re-authentication and reconfiguration — a blank or wrong password is
rejected instead of being written and breaking a working entry.

### Config entry keys

| Key | Meaning |
|-----|---------|
| `username`, `password` | SmartSolar account credentials (password is redacted in diagnostics) |
| `mode` | `device` or `project` |
| `device_type` | Device type used by the project-by-devices API call |
| `chipset_ids` | Device mode: exactly one Chipset ID. Project by devices: the monitored GUIDs. Project by ID: empty, filled from the API response |
| `project_id` | Project mode by ID only |
| `update_interval` | Poll interval in seconds, 1–30 (clamped on load, editable later from the number entity) |

### Update interval

The `Update Frequency` number entity changes the poll interval between 1 and 30
seconds. It is stored in the config entry, so it survives restarts, and it stays
available during a cloud outage — it is a local setting, and slowing the polling
down is exactly what you may want then.

## Entities

### Sensors (13 per device)

| Sensor | Unit | Source |
|--------|------|--------|
| PV Voltage | V | MQTT + REST |
| PV Current | A | MQTT + REST |
| Battery Voltage | V | MQTT + REST |
| Battery Current | A | MQTT + REST |
| Charge Power | W | MQTT + REST |
| Today Energy | kWh | MQTT + REST (`total_increasing`, resets at midnight) |
| Total Energy | kWh | MQTT + REST (`total_increasing`) |
| Temperature | °C | MQTT + REST |
| Status | — | MQTT + REST, mapped from the numeric code (Online / Charging / Idle (No Sun) / Fault) |
| WiFi Signal | % | MQTT, or the REST `signalQuality` field |
| Peak Power Today | W | Computed by the coordinator from today's samples |
| Avg Power Today | W | Mean of today's samples (not time-weighted — see limitations) |
| Production Hours Today | h | Hours today above ~5 W |

In project mode you get a set per device (`…pv1…`, `…pv2…`) plus the project
totals; in device mode you get one set.

Entity IDs are derived by Home Assistant from the device name, so they look like
`sensor.<device_slug>_pv1_pv_voltage`. Unique IDs are
`{entry_id}_{prefix}_{sensor_type}`, which is why migrating an entry in place
(instead of deleting and re-adding it) keeps every entity ID and all long-term
statistics intact.

### Cross-device aggregation

When a project total is computed from the individual controllers — which happens
whenever the cloud's own `synthesisStreams` is missing or stale — each sensor
type has an explicit strategy:

| Strategy | Sensors | Why |
|----------|---------|-----|
| **sum** | PV current, battery current, charge power, today/total energy | These add up across controllers |
| **average** | PV voltage, battery voltage, temperature, WiFi signal | Both chargers sit on the same 24 V bus, so summing would report ~53 V |
| **max** | Status | The worst state wins |

Charge power, currents and signal quality always aggregate locally, because the
cloud's synthesis values for them are frequently absent.

### Number

| Entity | Range | Notes |
|--------|-------|-------|
| Update Frequency | 1–30 s | Restores its own value after a restart; always available |

## How it works

```
        SmartSolar cloud (api.smartsolar.io.vn)      SmartSolar broker
        POST /Auth/Login, GET /Metric/*,             mqttx.smartsolar.io.vn:8084
        GET /Device/Status                                  │ WSS /mqtt
                 │                                          │
        SmartSolarAPI                                SmartSolarMQTTClient
        (auth, token refresh,                        (subscribe per device,
         retry with backoff)                          parse payloads, reconnect)
                 └────────────────┬─────────────────────────┘
                                  ▼
                 SmartSolarDataUpdateCoordinator
                 (poll + merge MQTT into the polled data,
                  daily statistics, 1 Hz listener notification cap)
                                  │
                 sensors (×13 per device) · Update Frequency · diagnostics
```

**REST API**

- `POST /Auth/Login` returns a token with an expiry; it is refreshed before
  expiry, and a `401` discards the cached token so the next call logs in again.
- Transient failures (network errors, 5xx, 408, 429) are retried with
  exponential backoff — with `RETRY_MAX_ATTEMPTS = 3` the waits are 1 s then 2 s.
  Other 4xx responses fail fast.
- Device mode reads `GET /Device/Status?deviceGuid=…`; project mode reads
  `GET /Metric/ProjectMetrics?projectId=…` or
  `GET /Metric/SynthesisMetrics?deviceType=…&deviceGuids=…`.

**MQTT**

- WebSocket Secure on port 8084, credentials discovered from the API response.
- Three payload shapes are understood: the current `update_device_metrics`
  format (`signalQuality` at the top level), the older `updateDeviceLog` format
  (no signal quality — that device's WiFi sensor stays `unknown`), and the legacy
  flat dictionary whose keys are mapped through `MQTT_FIELD_MAPPING`.
- The broker is shared by every SmartSolar customer, so only the per-device
  topics of this config entry are subscribed and any other device GUID is
  rejected in the callback.
- A dropped connection reconnects after 5 s; REST polling continues meanwhile.

## Services

| Service | Fields | Description |
|---------|--------|-------------|
| `smartsolar_ha.refresh_token` | `entry_id` (required) | Force an immediate token refresh for one config entry |

## Known limitations and deliberate behaviour

These are choices, not bugs — each is covered by tests:

- **A device that first appears after setup gets no entities.** The MQTT
  subscription set and the entity set are fixed at setup time. Per-device
  sensors are labelled `PV1`, `PV2`, … from the numerically sorted GUIDs, so
  inserting a device with a lower GUID would renumber existing entity IDs and
  break dashboards. Restart Home Assistant after adding a controller.
- **`Avg Power Today` is a sample mean**, not a time-weighted average: MQTT
  publishes at roughly 2 Hz and each poll adds one more sample.
- **`WiFi Signal` stays `unknown` for some firmware.** The 40A unit in the
  reference installation never reports `signalQuality` (the API returns `null`
  and its MQTT payloads use the older format without the field).
- **Sensors do not restore stale values** after a restart. They inherit
  `RestoreEntity`, but a sensor shows `unknown` until the first poll or MQTT
  message, because a restored reading could be arbitrarily old. Only `Update
  Frequency` restores its own value.
- **Diagnostics include the account username** (and redact password and token),
  so that a diagnostics dump can be traced to an account.

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| No sensor data | Credentials are valid and the device is online in the SmartSolar app; check the integration's INFO logs |
| Integration does not load | `manifest.json` requires `aiohttp` and `aiomqtt`; check the Home Assistant log for the loader error |
| Cloud errors (502/503/timeouts) | The SmartSolar cloud is temporarily unavailable — polls retry with backoff, and MQTT-fed sensors keep updating |
| Token problems | Tokens refresh automatically; the `smartsolar_ha.refresh_token` service forces a refresh for one entry |
| MQTT never connects | Outbound WSS to `mqttx.smartsolar.io.vn:8084` must be allowed; the integration keeps polling over REST regardless |
| Entities `unavailable` during a cloud outage | Should not happen any more: a sensor is available when the poll **or** live MQTT data can feed it |
| WiFi Signal `unknown` | Normal for firmware that does not publish `signalQuality` (see limitations) |
| Device added to the project but not visible | Restart Home Assistant: entity sets are fixed at setup time |

## Development

```bash
py -3.14 -m venv .venv                       # Home Assistant 2026.x needs Python >= 3.14.2
.venv/Scripts/python -m pip install -e ".[test,dev,deploy]"

.venv/Scripts/python -m pytest tests/ --cov=custom_components/
.venv/Scripts/ruff check custom_components/ tests/ upload_to_ha.py deploy_to_ha.py verify_live.py
.venv/Scripts/ruff format --check custom_components/ tests/ upload_to_ha.py deploy_to_ha.py verify_live.py
.venv/Scripts/python -m mypy custom_components/
```

The `[test]` extra pins `homeassistant==2026.9.4` — the version the integration
is verified against and the version the reference installation runs. The
`[deploy]` extra (`paramiko`) is only needed by the SSH helper scripts.

### The same gate runs locally and in CI

`deploy_to_ha.py` and `.github/workflows/ci.yml` lint the same file list, and
CI additionally runs the full suite with coverage plus HACS validation.

### Deploying to a live instance

```bash
.venv/Scripts/python deploy_to_ha.py               # gated deploy: lint + types + tests → backup → upload → restart → wait
.venv/Scripts/python deploy_to_ha.py --skip-checks # emergency re-push
.venv/Scripts/python verify_live.py                # assert the deployed entities are correct
```

`deploy_to_ha.py` archives what is currently deployed to `_local_archive/deployed/`,
prunes files that no longer exist in the repository, and then waits for two
things: the REST API to answer, **and** this integration's config entry to report
`loaded`. It refuses the deploy when the entry is stuck in
`setup_retry`/`setup_error`, and it does not mistake an unreadable listing for an
absent entry.

`verify_live.py` can be chained straight after it: because Home Assistant writes
entity states asynchronously after the entry loads, the verifier waits (bounded,
12 × 5 s) until every entity it asserts on exists before judging values.

### Project layout

```
custom_components/smartsolar_ha/
├── __init__.py        Setup/unload, service registration, entry migration
├── manifest.json      Domain, version, requirements
├── const.py           Sensor metadata, aggregation rules, MQTT and log config
├── helpers.py         Pure helpers (coerce_float, as_list, device_logs, …)
├── config_flow.py     Auth → mode → device/project, reauth, reconfigure
├── api.py             REST client: login, token refresh, retry/backoff
├── mqtt_client.py     MQTT client: WSS connect, payload parsing, reconnect
├── coordinator.py     Polling + MQTT merge + daily statistics
├── sensor.py          Sensor entities (device, project synthesis, project device, stats)
├── number.py          Update Frequency entity
├── diagnostics.py     Config entry diagnostics (secrets redacted)
├── brand/             Local icon/logo served by Home Assistant
└── translations/      en.json, vi.json
tests/                 Unit, script and end-to-end tests (567 passed, 1 skipped)
```

`CLAUDE.md` documents the architecture decisions and every audit fix in detail;
`KNOWLEDGE.md` is the Vietnamese deep-dive on the cloud API and the MQTT broker.

## Migration from v1.x

v2.0.0 renamed the integration and its domain from `smartsolar_mppt` to
`smartsolar_ha`, because Home Assistant requires the integration folder to equal
`manifest["domain"]` and a domain may contain only lowercase letters and
underscores. (The GitHub repository name is unrelated — Home Assistant never
reads it.)

An existing entry cannot load under the new domain. Two options:

- **Migrate the entry in place (recommended).** Rewrite the domain in
  `core.config_entries`, `core.entity_registry` and `core.device_registry` while
  Home Assistant is stopped. The `entry_id` stays the same, so every unique ID,
  entity ID, dashboard and long-term statistic survives. The exact procedure is
  in `CLAUDE.md` → "Deploying to HA".
- **Delete and re-add.** Simpler, but it creates a new `entry_id`, so entity IDs
  gain `_2` suffixes, dashboards need updating and long-term statistics are
  orphaned.

## Requirements

- Home Assistant **2026.9** or newer (`hacs.json` declares `2026.9.0`)
- Python **3.14.2+** (required by Home Assistant 2026.x)
- `aiohttp >= 3.8.0` and `aiomqtt >= 2.0` — declared in the manifest, installed
  by Home Assistant. If `aiomqtt` cannot be imported, the integration still works
  through REST polling.
- A SmartSolar account registered at [smartsolar.io.vn](https://smartsolar.io.vn)

## Contributing

Issues and pull requests are welcome.

- **Bug reports**: [open an issue](https://github.com/ngoviet/smartsolar_ha/issues/new)
- **Feature requests**: [open an issue](https://github.com/ngoviet/smartsolar_ha/issues/new)
- **Code**: [create a pull request](https://github.com/ngoviet/smartsolar_ha/compare)

Please run the local gate above before opening a pull request; CI runs the same
checks and adds HACS validation.

## License

MIT — see [LICENSE](LICENSE).

---

## Support

If this integration helps you monitor your solar energy, consider supporting its
development:

**BSC / BNB Smart Chain (BEP20)**
```
0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa
```
Accepts: BTC, ETH, USDT, BNB, USDC, BUSD, CAKE

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-☕-yellow.svg)](https://buymeacoffee.com/ngoviet)

---

Made with ❤️ by [@ngoviet](https://github.com/ngoviet) — if you find it useful, give it a ⭐ on GitHub!
