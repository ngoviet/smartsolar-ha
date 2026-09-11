# SmartSolar MPPT Home Assistant Integration

> **System info**: [../System_info/CLAUDE.md](../System_info/CLAUDE.md) — HA at 192.168.10.15, network, credentials
> **Code search**: `semble search "query" .` — intent-based, ~98% fewer tokens than grep

Home Assistant custom integration for SmartSolar MPPT solar charge controllers. Fetches real-time metrics via HTTP API from `api.smartsolar.io.vn` and MQTT WebSocket Secure from `mqttx.smartsolar.io.vn:8084`. **Current version: v1.4.0**.

## Project Structure

```
custom_components/smartsolar_mppt/
├── __init__.py          # Integration entry point, setup/unload, service registration, async_migrate_entry
├── manifest.json        # v1.4.0, domain=smartsolar_mppt, config_flow=true
├── const.py             # Constants, SENSOR_TYPES, MQTT config, build_device_info helper
├── config_flow.py       # Multi-step config flow: auth → mode → device/project, reauth, reconfigure
├── api.py               # HTTP API client: login, token refresh, retry, get_device_status for MQTT creds
├── mqtt_client.py       # MQTT client: WSS connect, subscribe, payload parsing, auto-reconnect
├── coordinator.py       # DataUpdateCoordinator: polls API + merges MQTT real-time data
├── sensor.py            # Sensor entities (device, project synthesis, project device) + RestoreEntity
├── number.py            # Number entity for dynamic update interval control
├── diagnostics.py       # Config entry diagnostics (HA 2024.2+)
├── services.yaml        # Service definitions
├── strings.json         # UI strings (English)
├── translations/        # en.json, vi.json
└── hacs.json            # HACS configuration
```

Root-level files:
```
hacs.json                # HACS metadata (content_in_root=false, min HA 2024.1.0)
pyproject.toml           # Python project config: ruff, mypy, pytest
.pre-commit-config.yaml  # Pre-commit hooks: ruff, yaml/json checks
LICENSE                  # MIT License
upload_to_ha.py          # Deployment script: paramiko SSH + base64 + sudo tee to HA container
tests/
├── conftest.py          # Shared fixtures: mock HA, API responses, coordinator
├── test_api.py          # 18 tests: API client, error hierarchy
├── test_sensor.py       # 93 tests: value extraction, naming, naming patterns
├── test_mqtt.py         # 18 tests: MQTT payload parsing, field mapping, credential handling
├── test_number.py       # 13 tests: interval get/set, bounds
├── test_config_flow.py  # 7 tests: reconfigure merge, unique IDs, abort reasons
└── test_coordinator.py  # Coordinator data fetching
.github/workflows/
├── ci.yml               # Python 3.12 matrix: ruff check, pytest with coverage
├── hacs-validation.yml   # HACS validation on push/PR
└── release.yml          # Auto GitHub release on tag push
```

## Architecture & Data Flow

### API (`api.smartsolar.io.vn`)

1. **Auth**: `POST /Auth/Login?Key=Content-Type` with `{username, password}` → token + expiry
2. **Token refresh**: Auto-refresh when within 7 days of expiry
3. **Retry logic**: Exponential backoff (1s, 2s, 4s) for network errors and 5xx responses (max 3 attempts)
4. **Device mode**: `GET /Device/Status?deviceGuid={guid}` → `{lastMessage: {dataStreams: [...]}, mqttConnection: {username, password}}`
5. **Project mode (by ID)**: `GET /Metric/ProjectMetrics?projectId={id}` → `{synthesisStreams, deviceLogs}`
6. **Project mode (by devices)**: `GET /Metric/SynthesisMetrics?deviceType={type}&deviceGuids={id1}&deviceGuids={id2}` → same structure
7. **MQTT Device Status**: `GET /Device/Status?deviceGuid={guid}` (used in project mode to extract mqttConnection credentials)

### MQTT (`mqttx.smartsolar.io.vn:8084`)

1. **Transport**: WebSocket Secure (WSS) at path `/mqtt`
2. **Credentials**: Auto-discovered from REST API `mqttConnection` field — username `web_app`, password base64-encoded
3. **Topics**: `manhquan/device/mppt_charger/log/+/<deviceGuid>` (single-level `+` wildcard for model)
4. **Payload format A** (standard): `{dataStreams: [{name, value}, ...], signalQuality, command, deviceGuid, firmwareVersion, messagesCounter}`
5. **Payload format B** (older firmware): Flat dict with keys like `charging_power`, `yield_today`, etc.
6. **Restart-less upgrades**: Only 1 topic must be re-subscribed after HA restart.
7. **Reconnection**: Auto-reconnect every 5s on disconnect; graceful degradation to REST polling

### Data Flow

```
Config Entry (username, password, mode, chipset_ids/project_id)
    ↓
    ├── SmartSolarAPI ──────────────────────────────────────────────┐
    │   (login → token → periodic refresh, retry w/ backoff)        │
    │   POST /Auth/Login, GET /Metric/*, GET /Device/Status         │
    ↓                                                                │
    ├── SmartSolarMQTTClient ───────────────────────────────────────┤
    │   (WSS connect → subscribe topics → parse payloads)           │
    │   mqttx.smartsolar.io.vn:8084/mqtt                           │
    │   Auto-discovers mqttConnection from API response             │
    ↓                                                                │
SmartSolarDataUpdateCoordinator                                     │
    (polling every N seconds + real-time MQTT merge)                │
    async_process_mqtt_data() → _merge_mqtt_into_data()             │
    async_set_updated_data() → triggers entity updates              │
    ↓
Sensor Entities (CoordinatorEntity + RestoreEntity, ×10 types)
Number Entity (Update Frequency, 1-30s)
```

### Sensor Types

10 sensor types per device: `pv_voltage`, `pv_current`, `bat_voltage`, `bat_current`, `charge_power`, `today_kwh`, `total_kwh`, `temperature`, `signal_quality` (WiFi % via MQTT), `status`

### Three Sensor Classes

| Class | Mode | Data Source |
|-------|------|-------------|
| `SmartSolarDeviceSensor` | Device | `data.lastMessage.dataStreams` |
| `SmartSolarProjectSynthesisSensor` | Project | `data.synthesisStreams` (fallback: sum from deviceLogs) |
| `SmartSolarProjectDeviceSensor` | Project | `data.deviceLogs[deviceGuid].dataStreams` |

## v1.3.0 Status — All Issues Resolved

All 13 known issues from v1.1.6 have been fixed:

| # | Issue | Status |
|---|-------|--------|
| 1 | Sensor init crashes with NameError | ✅ Fixed — mode/project_id/chipset_ids scoped correctly |
| 2 | `lru_cache` on trivial `get_sensor_info` | ✅ Removed |
| 3 | `async_get_translations` on every refresh | ✅ Removed from hot path |
| 4 | Duplicated DeviceInfo construction | ✅ Shared `build_device_info()` in const.py |
| 5 | No `always_update=False` | ✅ Value-change checks on all sensors |
| 6 | `__del__` with event loop access | ✅ Removed; proper `async_unload_entry` cleanup |
| 7 | No `__slots__` | ✅ Added to sensor/coordinator classes |
| 8 | Lazy import in `async_set_native_value` | ✅ Cleaned up |
| 9 | No `async_step_reconfigure` | ✅ Added (HA 2024.3+) |
| 10 | No `RestoreEntity` | ✅ Added to sensor & number entities |
| 11 | `FlowResult` instead of `ConfigFlowResult` | ✅ Updated |
| 12 | Vietnamese status strings | ✅ English with vi.json translations |
| 13 | No error recovery | ✅ Retry with exponential backoff |

### New in v1.3.0

- **`async_step_reauth`** — credential refresh without full reconfigure
- **`diagnostics.py`** — downloadable diagnostics from HA UI
- **`async_migrate_entry`** — automatic migration from v1.1 → v1.2 config entries
- **`allow_multiple_instances`** — supports multiple accounts/configs
- **93 tests** across 6 test files — all passing
- **CI/CD** — GitHub Actions with ruff, pytest, HACS validation

### New in v1.4.0

- **MQTT real-time updates** — `SmartSolarMQTTClient` in `mqtt_client.py` subscribes to per-device topics via WSS
- **MQTT credential auto-discovery** — `Device.get_device_status()` fetches `mqttConnection` from REST API, decodes base64 password
- **Dual payload formats** — Standard `dataStreams` array and flat key-value dict for older firmware
- **In-place data merge** — `coordinator.async_process_mqtt_data()` merges MQTT data into `coordinator.data` without replacing the dict reference
- **`signal_quality` sensor** — 10th sensor type, top-level field in MQTT payload (not in `dataStreams`), mapped via `MQTT_FIELD_MAPPING`
- **Graceful degradation** — MQTT failure logs WARNING, REST polling continues; older devices without `signalQuality` show "unknown"
- **`upload_to_ha.py`** — paramiko SSH deployment script with base64 encoding + sudo tee
- **121 tests** across 7 test files (18 new MQTT tests) — all passing

## Development Guidelines

### Running Tests

```bash
cd d:/Code/SmartSolar
pip install -e ".[dev]"
pytest tests/ --cov=custom_components/
ruff check custom_components/
```

### HA Connection
- URL: `http://192.168.10.15:8123`
- SSH: `vokupt@192.168.10.15` — password via `HA_PASS` env var (never commit)
- Long-lived token: create via HA Profile → Security → Long-lived access tokens; export as `HA_TOKEN`

### Code Style Targets
- Python 3.12+, Home Assistant 2024.1+
- Dependencies: aiohttp >= 3.8.0, aiomqtt >= 2.0 (optional but recommended)
- Use `__slots__` for memory efficiency
- Use `CoordinatorEntity` with `RestoreEntity` for all entities
- `always_update=False` with value-change check
- Shared helpers in `const.py`

### Key Naming Conventions
- Entity ID: `sensor.smartsolar_mppt_{prefix}_{type}` (e.g., `sensor.smartsolar_mppt_p_123_pv_voltage`)
- Unique ID: `{entry_id}_{prefix}_{sensor_type}`
- Config keys: `username`, `password`, `mode`, `device_type`, `chipset_ids`, `project_id`

### Deploying to HA

```bash
cd d:/Code/SmartSolar
python upload_to_ha.py              # Uploads custom_components/smartsolar_mppt/ to HA container
ssh vokupt@192.168.10.15 -p 22     # Then: docker restart homeassistant && sleep 35
```

The script uses paramiko SSH + base64 encoding + `sudo tee` to write files into the Docker container at `/homeassistant/custom_components/smartsolar_mppt/`. Requires HA Docker container to be running.
