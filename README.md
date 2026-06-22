# SmartSolar MPPT — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-121%20passed-brightgreen)](https://github.com/ngoviet/smartsolar-ha)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org)

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
| WiFi Signal | % | WiFi signal quality (0–100%, MQTT only) |

## Installation

### HACS (Recommended)

1. Add this repository to HACS: `https://github.com/ngoviet/smartsolar-ha`
2. Search for **"SmartSolar MPPT"** in HACS → Integrations
3. Click **Download**
4. Restart Home Assistant

### Manual

```bash
cd /config/custom_components
git clone https://github.com/ngoviet/smartsolar-ha.git smartsolar_mppt
# Restart Home Assistant
```

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
   (×10)  (update nostic  client
           interval)
```

## Changelog

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
- **Exponential backoff retry** — 3 attempts with 1s/2s/4s backoff for network errors and 5xx server errors
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
| Token expired | Auto-refresh 7 days before expiry; use `smartsolar_mppt.refresh_token` service to force refresh |
| MQTT not connecting | Check that `aiomqtt>=2.0` is installed; verify network allows WSS on port 8084 |
| WiFi Signal shows "unknown" | Some older firmware doesn't include signalQuality field — normal degradation |
| MQTT "connection failed" warnings | Broker temporarily unreachable — auto-reconnects in 5s; REST polling continues |

## Services

| Service | Description |
|---------|-------------|
| `smartsolar_mppt.refresh_token` | Manually refresh the API authentication token |

## Requirements

- Home Assistant **2024.1** or newer
- Python **3.12+**
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
