# SmartSolar MPPT — Home Assistant Integration

## Bắt đầu từ đây trong session mới

Đọc file này trước, sau đó đọc `CLAUDE.md` để hiểu kiến trúc chi tiết.

---

## Trạng thái hiện tại (2026-04-30, cuối session)

### v1.2.1 — Đã deploy lên HA, đang chạy ổn định, 29 entities

- **Version:** v1.2.1 (commit `869ddd2`, chưa push GitHub)
- **HA config entry:** `01K7DZBBS75AS1WBR48FVXVQZ1` — Project mode, project_id=1072
- **2 thiết bị MPPT:** GUID `14756976` và `547611`
- **29 entities hoạt động với dữ liệu thật:**
  - 9 "Tổng" (synthesis — project aggregate)
  - 9 "PV1" (device 547611) 
  - 9 "PV2" (device 14756976)
  - 1 number (Update Frequency)
  - 1 update (HACS)

### Entity mapping hiện tại

| Label | GUID | PV Voltage | Power | Total Energy | Vai trò |
|-------|------|-----------|-------|-------------|---------|
| **Tổng** | — | ~70V | ~218W | 899.2 kWh | Aggregate cả 2 thiết bị |
| **PV1** | 547611 | ~44.5V | ~1.7W | 223.9 kWh | Thiết bị phụ (thấp) |
| **PV2** | 14756976 | ~70V | ~216.7W | 675.4 kWh | Thiết bị chính (cao) |

> **Lưu ý:** PV1/PV2 được đánh số tự động theo thứ tự GUID từ API. 
> PV1 = 547611 (thấp), PV2 = 14756976 (cao). Nếu muốn đổi PV1↔PV2, cần sort device GUIDs trước khi gán index.

---

## Nhật ký công việc — Session 2026-04-30

### Bug 1: Thiếu per-device sensors trong Project mode

**Phát hiện:** Entity registry có 27 entities, nhưng chỉ 11 active. Thiếu toàn bộ 18 sensor cho 2 thiết bị riêng lẻ.

**Root cause:** Trong `__init__.py`, `async_forward_entry_setups` (platform setup) được gọi TRƯỚC `async_config_entry_first_refresh`. Khi sensor.py chạy `async_setup_entry`, coordinator.data còn rỗng → `deviceLogs` không có → `device_guids = []` → không tạo được `SmartSolarProjectDeviceSensor` cho từng thiết bị.

```python
# Thứ tự SAI (v1.2.0):
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)  # sensor.py chạy, data rỗng
await coordinator.async_config_entry_first_refresh()                      # data mới có

# Thứ tự ĐÚNG (v1.2.1):
await coordinator.async_refresh()                                         # data có trước
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)   # sensor.py thấy deviceLogs
```

**Khó khăn gặp phải:** `async_config_entry_first_refresh()` bị HA 2026.4.4 từ chối khi state = LOADED (chỉ chấp nhận SETUP_IN_PROGRESS). Phải chuyển sang dùng `async_refresh()` — method này không check state.

**Kết quả:** 29 entities (9 tổng + 18 per-device + 1 number + 1 update), tất cả có dữ liệu thật.

---

### Bug 2: Config entry mất field — "Missing device_type in configuration"

**Phát hiện:** HA log báo `Missing device_type in configuration`. Sensor platform không load được.

**Root cause:** Config entry data CHỈ CÒN `username` và `password`. Các field `mode`, `device_type`, `project_id`, `chipset_ids` đã biến mất. Không rõ nguyên nhân gốc — có thể do migration từ version cũ, hoặc do `async_update_entry` trong number.py ghi đè data.

**Cách fix:** Script Python sửa trực tiếp file `/config/.storage/core.config_entries`:
```python
e["data"]["mode"] = "project"
e["data"]["device_type"] = 2           # DEVICE_TYPE_MANH_QUAN
e["data"]["project_id"] = "1072"
e["data"]["chipset_ids"] = []
```
Suy luận từ `unique_id` = `vokupt_project_2_1072` → mode=project, project_id=1072.

**Kết quả:** Config entry hoạt động trở lại, coordinator fetch được data.

---

### Bug 3: AttributeError `_device_discovery_callbacks`

**Phát hiện:** HA log báo `'SmartSolarDataUpdateCoordinator' object has no attribute '_device_discovery_callbacks'`.

**Root cause:** Trong v1.2.0, `_device_discovery_callbacks` đã bị xóa khỏi `__slots__` và `__init__` (vì là dead code), nhưng code trong `_async_update_data` (dòng 91-95) vẫn reference đến nó.

**Fix:** Xóa đoạn code gọi callback trong `_async_update_data`:
```python
# ĐÃ XÓA:
for callback in self._device_discovery_callbacks:
    try:
        callback(list(new_devices))
    except ...:
        ...
```

**Kết quả:** Coordinator chạy không còn crash.

---

### Bug 4: 29 entity rác trong registry

**Phát hiện:** Entity registry có 29 entities đã mồ côi từ các lần cài đặt cũ:
- 9 entities dạng `sensor.pv_voltage` (không prefix, từ Device mode cũ)
- 9 entities dạng `sensor.pv_voltage_14756976` (Device mode cũ với GUID)
- 9 entities dạng `sensor.pv_voltage_547611` (Device mode cũ với GUID)
- `update.smartsolar_mppt_update`, `switch.smartsolar_mppt_pre_release`

**Cách fix:** Script Python lọc entity_registry, giữ lại entities có `smartsolar_mppt_project` trong unique_id (thuộc về config entry hiện tại), xóa phần còn lại.

**Kết quả:** Entity registry sạch, 2903 entities (giảm 29).

---

### Bug 5: Entity naming — GUID khó phân biệt

**Vấn đề:** Entity name dùng GUID như `PV Voltage (14756976)` và `PV Voltage (547611)`. Người dùng không biết GUID nào tương ứng với thiết bị vật lý nào.

**Fix:** Thêm `device_index` parameter vào `SmartSolarSensor.__init__`. Trong project mode, device được đánh số theo thứ tự xuất hiện trong `deviceLogs`:
- Index 1 → name `PV1 Voltage`, `PV1 Current`, ...
- Index 2 → name `PV2 Voltage`, `PV2 Current`, ...
- Synthesis → name `Tổng PV Voltage`, `Tổng PV Current`, ...

**Mapping hiện tại:** PV1 = GUID 547611, PV2 = GUID 14756976. Thứ tự phụ thuộc vào thứ tự GUID trong API response. Nếu muốn cố định PV1 là thiết bị chính (công suất cao), cần sort device GUIDs khi tạo index.

---

## Các điểm cần lưu ý khi làm tiếp

### Vấn đề chưa giải quyết
1. **PV1/PV2 mapping chưa ổn định** — thứ tự phụ thuộc vào API response, có thể thay đổi giữa các lần restart. Nên cho phép người dùng chọn GUID → PV1/PV2 mapping trong config flow HOẶC sort GUIDs theo thứ tự cố định.
2. **Chưa push v1.2.1 lên GitHub** — commit `869ddd2` mới chỉ local.
3. **Chưa có async_migrate_entry** — nếu sau này tăng VERSION, config entry cũ sẽ không migrate được.

### Deployment pipeline đã dùng (ghi nhớ để tái sử dụng)
1. Đọc file local → base64 encode
2. SSH paramiko → `echo "{b64}" > /tmp/file.b64`
3. Host python3 decode base64 → write ra `/config/custom_components/smartsolar_mppt/`
4. `sudo rm -rf __pycache__` + `sudo docker restart homeassistant`

### Cảnh báo quan trọng
- **Không dùng `grep -v` để xóa dòng khỏi JSON** — sẽ làm hỏng cấu trúc như đã gặp với NPC project. Luôn dùng Python `json.load()` → sửa → `json.dump()`.
- **Kiểm tra cả `entities` và `deleted_entities`** trong entity_registry.
- **File trong `/config/.storage/` phải có owner `root:root`.**
- **Không dùng `async_config_entry_first_refresh` trên HA 2025.x+** khi config entry đã LOADED — dùng `async_refresh()` thay thế.
- **Print UTF-8 từ Windows sang console** gây lỗi cp1252. Luôn ghi output ra file rồi dùng `Read` tool.

---

## Đã fix trong v1.2.0 (session trước)

| Vấn đề | Fix |
|--------|-----|
| `NameError` — biến `mode`/`project_id`/`chipset_ids` dùng trước khi khai báo | Đưa khai báo biến lên trước debug log |
| `assert` statements trong production code (config_flow.py) | Thay bằng `if ... is None: raise ValueError(...)` |
| `FlowResult` deprecated (config_flow.py) | Thay bằng `ConfigFlowResult` |
| API session leak — `test_connection()` không gọi `close()` | Thêm `finally: await self.close()` |
| `__del__` method unsafe trong api.py | Đã xóa |
| Private API access trong number.py (`_unsub_refresh`, `_schedule_refresh`) | Dùng public API `update_interval` |
| `@cached_property` name override không cần thiết | Đã xóa, dùng `_attr_name` |
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
- **Project mode:** Tổng hợp nhiều controller qua Project ID hoặc danh sách Device IDs. Tạo 9 synthesis sensors + 9 sensors cho mỗi device.

---

## Kết nối HA

- **URL:** http://192.168.10.15:8123
- **SSH:** `vokupt@192.168.10.15` / password: `qweszxc12`
- **HA Token:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0YWM5MWI2N2I2OTM0Y2ZhOGQ4OGY4YzIzYmViNGQ5NSIsImlhdCI6MTc3NzQ2NDk3MSwiZXhwIjoyMDkyODI0OTcxfQ.qWN6mb2BHMb6ypJR-pYFY1MhDVGGBziGL7Vgvm-JfO8`
- **HA chạy trong Docker:** `sudo docker exec homeassistant ...`
- **Config path:** `/config` (mount từ host, shared với container)
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

client.exec_command('sudo rm -rf /config/custom_components/smartsolar_mppt/__pycache__')
client.exec_command('sudo docker restart homeassistant')
```

---

## Cấu trúc thư mục

```
D:/Code/SmartSolar/
├── SESSION.md                # File này — nhật ký toàn bộ quá trình
├── CLAUDE.md                 # Kiến trúc chi tiết, data flow
├── README.md                 # README chuyên nghiệp (English)
├── custom_components/
│   └── smartsolar_mppt/
│       ├── __init__.py       # Setup/unload, platform forward, service register
│       ├── manifest.json     # v1.2.1
│       ├── const.py          # Constants, SENSOR_TYPES, STATUS_MAPPING, build_device_info
│       ├── config_flow.py    # UI config flow (device/project mode)
│       ├── api.py            # SmartSolar Cloud API client
│       ├── coordinator.py    # DataUpdateCoordinator
│       ├── sensor.py         # Sensor entities (Device/Project/Synthesis/DeviceSensor)
│       ├── number.py         # UpdateInterval number entity
│       ├── services.yaml     # Service definitions
│       └── translations/     # en.json, vi.json
└── assets/                   # logo.png, icon.png
```

---

## Git log

```
869ddd2 docs: Update SESSION.md with v1.2.1 status
db5211e v1.2.1: Fix config entry data loss, per-device sensor discovery, orphan cleanup
0a169b3 docs: Professional README rewrite
734e0d4 v1.2.0: Bug fixes, performance optimization, and HAOS future compatibility
```

- **Repo:** https://github.com/ngoviet/smartsolar-ha
- **Local:** `D:/Code/SmartSolar`
- **Branch:** `main`
- **User:** ngoviet / ngoviet@github.com
