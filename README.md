# SmartSolar MPPT — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.1%2B-41BDF5)](https://www.home-assistant.io)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar-ha&category=integration)

Home Assistant custom integration for **SmartSolar MPPT** solar charge controllers. Monitor PV voltage, charge current, daily/total energy, temperature, and device status in real time via the SmartSolar Cloud API.

---

## Features

- **Real-time monitoring** — PV voltage & current, battery voltage & current, charge power, temperature, status
- **Daily & total energy tracking** — kWh generated today and lifetime
- **Project mode** — aggregate multiple MPPT controllers into a single dashboard
- **Device mode** — monitor individual controllers
- **Adjustable polling** — configurable update interval from 1 to 30 seconds
- **Auto token refresh** — transparently refreshes API tokens before expiry
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
        |
SmartSolarAPI (auth, token refresh, metrics)
        |
SmartSolarDataUpdateCoordinator (polling)
        |
  +-----+------+
  |             |
Sensor (×9)   Number (update interval)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No sensor data | Verify credentials; check device is online in SmartSolar app |
| Integration won't load | Check HA logs; verify `aiohttp` is installed |
| API errors (502) | SmartSolar cloud may be temporarily down — retries automatically |
| Token expired | Auto-refresh 7 days before expiry; use `smartsolar_mppt.refresh_token` service to force refresh |

## Services

| Service | Description |
|---------|-------------|
| `smartsolar_mppt.refresh_token` | Manually refresh the API authentication token |

## Requirements

- Home Assistant **2023.1** or newer
- Python **3.11+**
- `aiohttp >= 3.8.0`
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
