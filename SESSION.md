# SmartSolar MPPT — Home Assistant Integration

## Bắt đầu từ đây trong session mới

Đọc file này trước, sau đó đọc `CLAUDE.md` để hiểu kiến trúc chi tiết.

---

## Trạng thái hiện tại (2026-04-30, cập nhật cuối)

### v1.2.1 — Đã fix xong, đang chạy ổn định

- **Version:** v1.2.1 (đã deploy lên HA, commit db5211e)
- **HA config entry:** `01K7DZBBS75AS1WBR48FVXVQZ1` — Project mode, project_id=1072, 2 thiết bị
- **29 entities hoạt động:** 9 synthesis + 18 per-device (2 device x 9) + 1 number + 1 update
- **GitHub:** https://github.com/ngoviet/smartsolar-ha (cần push v1.2.1)
- **CLAUDE.md:** Đã có

### Bug đã fix trong session này
1. **Thiếu per-device sensors** — `async_forward_entry_setups` gọi trước khi có data → sensor.py không thấy device GUIDs → không tạo được sensor riêng cho từng thiết bị. Fix: dùng `async_refresh()` trước platform setup
2. **Config entry mất field** — `mode`, `device_type`, `project_id`, `chipset_ids` biến mất khỏi config entry data → coordinator báo "Missing device_type". Fix: restore thủ công các field vào config entry
3. **`_device_discovery_callbacks` AttributeError** — đã xóa khỏi `__slots__` nhưng code vẫn reference → crash. Fix: xóa dead code
4. **29 entity rác** — entity registry còn entity từ các lần cài cũ. Fix: script Python clean entity_registry

---

## Đã fix trong v1.2.0 (so với bản gốc v1.1.6)

| Vấn đề | Fix |
|--------|-----|
| `NameError` — biến `mode`/`project_id`/`chipset_ids` dùng trước khi khai báo | Đưa khai báo biến lên trước debug log |
| `assert` statements trong production code (config_flow.py) | Thay bằng `if ... is None: raise ValueError(...)` |
| `FlowResult` deprecated (config_flow.py) | Thay bằng `ConfigFlowResult` |
| API session leak — `test_connection()` không gọi `close()` | Thêm `finally: await self.close()` |
| `__del__` method unsafe trong api.py | Đã xóa |
| Private API access trong number.py (`_unsub_refresh`, `_schedule_refresh`) | Dùng public API `update_interval` |
| `@cached_property` name override không cần thiết | Đã xóa, dùng `_attr_name` |
| `_device_discovery_callbacks` dead code | Đã xóa toàn bộ |
| `DATA_STREAM_INDICES`, `CONF_UPDATE_INTERVAL` unused constants | Đã xóa |
| Debug log noise (~650 logs/min) | Giảm xuống 0 trong hot path |
| Thiếu `__slots__` | Đã thêm vào coordinator, sensors, number |
| Thiếu `MINOR_VERSION` | `MINOR_VERSION = 1` |
| `STATUS_MAPPING` hardcoded tiếng Việt | Đổi sang English keys |
| `DeviceInfo` trùng lặp 3 nơi | `build_device_info()` shared helper trong const.py |
| `from datetime import timedelta` import lười trong number.py | Đưa lên module top |

---

## Kiến trúc

```
SmartSolar Cloud API (api.smartsolar.io.vn)
        |
SmartSolarAPI (auth, token refresh, metrics)
        |
SmartSolarDataUpdateCoordinator (polling 5s mặc định)
        |
  +-----+------+
  |             |
Sensor (x9)   Number (update interval)
```

### Sensors (9 loại)
PV Voltage (V), PV Current (A), Battery Voltage (V), Battery Current (A), Charge Power (W), Today Energy (kWh), Total Energy (kWh), Temperature (°C), Status

### Integration modes
- **Device mode:** Monitor 1 controller bằng Chipset ID
- **Project mode:** Tổng hợp nhiều controller qua Project ID hoặc danh sách Device IDs

---

## Kết nối HA

- **URL:** http://192.168.10.15:8123
- **SSH:** `vokupt@192.168.10.15` / password: `qweszxc12`
- **HA Token:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0YWM5MWI2N2I2OTM0Y2ZhOGQ4OGY4YzIzYmViNGQ5NSIsImlhdCI6MTc3NzQ2NDk3MSwiZXhwIjoyMDkyODI0OTcxfQ.qWN6mb2BHMb6ypJR-pYFY1MhDVGGBziGL7Vgvm-JfO8`
- **HA chạy trong Docker:** `sudo docker exec homeassistant ...`
- **Config path:** `/config` (mount từ host)
- **Restart HA:** `curl -X POST -H "Authorization: Bearer <token>" http://192.168.10.15:8123/api/services/homeassistant/restart`

### Deploy code lên HA

```python
import paramiko, base64

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.10.15', username='vokupt', password='qweszxc12')

with open('file.py', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
client.exec_command(f'echo "{b64}" > /tmp/file.b64')

script = f'import base64; open("/config/custom_components/smartsolar_mppt/file.py","w").write(base64.b64decode(open("/tmp/file.b64").read()).decode())'
b64_script = base64.b64encode(script.encode()).decode()
client.exec_command(f'echo "{b64_script}" > /tmp/decode.b64 && base64 -d /tmp/decode.b64 > /tmp/decode.py && sudo /usr/bin/python3 /tmp/decode.py')

client.exec_command('sudo docker restart homeassistant')
```

---

## Cấu trúc thư mục

```
D:/Code/SmartSolar/
├── SESSION.md                # File này
├── CLAUDE.md                 # Kiến trúc chi tiết
├── README.md                 # README chuyên nghiệp (English)
├── custom_components/
│   └── smartsolar_mppt/
│       ├── __init__.py       # Setup/unload, platform forward, service register
│       ├── manifest.json     # v1.2.0
│       ├── const.py          # Constants, SENSOR_TYPES, STATUS_MAPPING, build_device_info
│       ├── config_flow.py    # UI config flow (device/project mode)
│       ├── api.py            # SmartSolar Cloud API client
│       ├── coordinator.py    # DataUpdateCoordinator
│       ├── sensor.py         # Sensor entities (Device/Project/Synthesis)
│       ├── number.py         # UpdateInterval number entity
│       ├── services.yaml     # Service definitions
│       └── translations/     # en.json, vi.json
└── assets/                   # logo.png, icon.png
```

---

## Git

- **Repo:** https://github.com/ngoviet/smartsolar-ha
- **Local:** `D:/Code/SmartSolar` (clone từ upstream)
- **Branch:** `main`
- **Commit cuối:** `0a169b3` — docs: Professional README rewrite
- **Release:** v1.2.0
- **User:** ngoviet
