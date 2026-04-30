# SmartSolar MPPT Home Assistant Integration

Home Assistant custom integration for SmartSolar MPPT solar charge controllers. Fetches real-time metrics via HTTP API from `api.smartsolar.io.vn`.

## Project Structure

```
custom_components/smartsolar_mppt/
├── __init__.py          # Integration entry point, setup/unload, service registration
├── manifest.json        # v1.1.6, domain=smartsolar_mppt, config_flow=true
├── const.py             # Constants, sensor definitions, API endpoints
├── config_flow.py       # Multi-step config flow: auth → mode → device/project
├── api.py               # HTTP API client: login, get_metrics, get_project_metrics
├── coordinator.py       # DataUpdateCoordinator: fetches API data every N seconds
├── sensor.py            # Sensor entities (device, project synthesis, project device)
├── number.py            # Number entity for dynamic update interval control
├── services.yaml        # Service definitions
├── strings.json         # UI strings
├── translations/        # en.json, vi.json
└── hacs.json            # HACS configuration
```

## Architecture & Data Flow

### API (`api.smartsolar.io.vn`)

1. **Auth**: `POST /Auth/Login?Key=Content-Type` with `{username, password}` → token + expiry
2. **Token refresh**: Auto-refresh when within 7 days of expiry
3. **Device mode**: `GET /Device/Status?deviceGuid={guid}` → `{lastMessage: {dataStreams: [...]}}`
4. **Project mode (by ID)**: `GET /Metric/ProjectMetrics?projectId={id}` → `{synthesisStreams, deviceLogs}`
5. **Project mode (by devices)**: `GET /Metric/SynthesisMetrics?deviceType={type}&deviceGuids={id1}&deviceGuids={id2}` → same structure

### Data Flow

```
Config Entry (username, password, mode, chipset_ids/project_id)
    ↓
SmartSolarAPI (login → token → periodic refresh)
    ↓
SmartSolarDataUpdateCoordinator (polling every N seconds, default 5s)
    ↓
Sensor Entities (CoordinatorEntity, read from coordinator.data)
```

### Sensor Types

9 sensor types per device: `pv_voltage`, `pv_current`, `bat_voltage`, `bat_current`, `charge_power`, `today_kwh`, `total_kwh`, `temperature`, `status`

### Three Sensor Classes

| Class | Mode | Data Source |
|-------|------|-------------|
| `SmartSolarDeviceSensor` | Device | `data.lastMessage.dataStreams` |
| `SmartSolarProjectSynthesisSensor` | Project | `data.synthesisStreams` (fallback: sum from deviceLogs) |
| `SmartSolarProjectDeviceSensor` | Project | `data.deviceLogs[deviceGuid].dataStreams` |

## Current Issues (v1.1.6)

### On HA (192.168.10.15)
- Config entry exists: **SmartSolar MPPT (Project)**, state: loaded
- Only **2 entities**: `number.smartsolar_mppt_project_update_frequency` + HACS update entity
- **No sensor entities** — despite loaded config entry

### Known Issues

1. **Sensor init crashes if `mode`/`project_id`/`chipset_ids` not in local scope** — `sensor.py:117` references `mode`, `project_id`, `chipset_ids` from local variables but these are defined inside `async_setup_entry`, not in the class `__init__`. This causes `NameError` at entity creation.

2. **`lru_cache` on `get_sensor_info` never evicts** — `const.py:134`: `@lru_cache(maxsize=None)` with infinite cache, but the function is trivial (dict lookup). Cache overhead > lookup overhead.

3. **`async_get_translations` called on every coordinator refresh** — `coordinator.py:74`: Translation fetch inside `_async_update_data` if chipset_ids is empty. This is expensive and unnecessary for an error path.

4. **Device info duplicated** — `sensor.py:184-192` and `number.py:92-100` and `__init__.py:78-86` all construct identical DeviceInfo objects. Should be a shared helper.

5. **No `always_update=False`** — Coordinator notifies all entities every 5 seconds even if data unchanged.

6. **`__del__` with event loop access** — `api.py:76-89`: `__del__` method tries to access the event loop, which may already be closed. HA discourages `__del__` in integrations.

7. **No `__slots__`** — Sensor classes and coordinator don't use `__slots__`, wasting memory.

8. **Lazy import in `async_set_native_value`** — `number.py:112`: `from datetime import timedelta` inside method (already imported at module level in `const.py`).

9. **No `async_step_reconfigure`** — Missing HA 2024.3+ reconfigure flow.

10. **No `RestoreEntity`** — Number entity loses state on restart.

11. **`FlowResult` instead of `ConfigFlowResult`** — `config_flow.py:13`: Uses deprecated `FlowResult` from `data_entry_flow` instead of `ConfigFlowResult` from `config_entries`.

12. **Hardcoded Vietnamese status strings** — `const.py:127-131`: Status mapping uses Vietnamese text that won't work for non-Vietnamese users.

13. **No error recovery** — API errors in coordinator raise `UpdateFailed` but no retry logic.

## Development Guidelines

### HA Connection
- URL: `http://192.168.10.15:8123`
- SSH: `vokupt@192.168.10.15` / `qweszxc12`
- Long-lived token available

### Code Style Targets
- Python 3.12+, Home Assistant 2024.1+
- Dependencies: aiohttp
- Use `__slots__` for memory efficiency
- Use `CoordinatorEntity` for all entities
- `always_update=False` with value-change check
- Shared helpers in `common.py` or `const.py`

### Key Naming Conventions
- Entity ID: `sensor.smartsolar_mppt_{prefix}_{type}` (e.g., `sensor.smartsolar_mppt_p_123_pv_voltage`)
- Unique ID: `{entry_id}_{prefix}_{sensor_type}`
- Config keys: `username`, `password`, `mode`, `device_type`, `chipset_ids`, `project_id`
