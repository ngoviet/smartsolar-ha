# SmartSolar MPPT Home Assistant Integration

> **System info**: [../System_info/CLAUDE.md](../System_info/CLAUDE.md) — HA at 192.168.10.15, network, credentials
> **Code search**: `semble search "query" .` — intent-based, ~98% fewer tokens than grep

Home Assistant custom integration for SmartSolar MPPT solar charge controllers. Fetches real-time metrics via HTTP API from `api.smartsolar.io.vn`. **Current version: v1.3.0**.

## Project Structure

```
custom_components/smartsolar_mppt/
├── __init__.py          # Integration entry point, setup/unload, service registration, async_migrate_entry
├── manifest.json        # v1.3.0, domain=smartsolar_mppt, config_flow=true
├── const.py             # Constants, SENSOR_TYPES, retry config, build_device_info helper
├── config_flow.py       # Multi-step config flow: auth → mode → device/project, reauth, reconfigure
├── api.py               # HTTP API client: login, token refresh, retry with exponential backoff
├── coordinator.py       # DataUpdateCoordinator: fetches API data every N seconds
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
tests/
├── conftest.py          # Shared fixtures: mock HA, API responses, coordinator
├── test_api.py          # 18 tests: API client, error hierarchy
├── test_sensor.py       # 93 tests: value extraction, naming, naming patterns
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
4. **Device mode**: `GET /Device/Status?deviceGuid={guid}` → `{lastMessage: {dataStreams: [...]}}`
5. **Project mode (by ID)**: `GET /Metric/ProjectMetrics?projectId={id}` → `{synthesisStreams, deviceLogs}`
6. **Project mode (by devices)**: `GET /Metric/SynthesisMetrics?deviceType={type}&deviceGuids={id1}&deviceGuids={id2}` → same structure

### Data Flow

```
Config Entry (username, password, mode, chipset_ids/project_id)
    ↓
SmartSolarAPI (login → token → periodic refresh, retry with backoff)
    ↓
SmartSolarDataUpdateCoordinator (polling every N seconds, default 5s)
    ↓
Sensor Entities (CoordinatorEntity + RestoreEntity, read from coordinator.data)
```

### Sensor Types

9 sensor types per device: `pv_voltage`, `pv_current`, `bat_voltage`, `bat_current`, `charge_power`, `today_kwh`, `total_kwh`, `temperature`, `status`

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
- SSH: `vokupt@192.168.10.15` / `qweszxc12`
- Long-lived token available

### Code Style Targets
- Python 3.12+, Home Assistant 2024.1+
- Dependencies: aiohttp >= 3.8.0
- Use `__slots__` for memory efficiency
- Use `CoordinatorEntity` with `RestoreEntity` for all entities
- `always_update=False` with value-change check
- Shared helpers in `const.py`

### Key Naming Conventions
- Entity ID: `sensor.smartsolar_mppt_{prefix}_{type}` (e.g., `sensor.smartsolar_mppt_p_123_pv_voltage`)
- Unique ID: `{entry_id}_{prefix}_{sensor_type}`
- Config keys: `username`, `password`, `mode`, `device_type`, `chipset_ids`, `project_id`
