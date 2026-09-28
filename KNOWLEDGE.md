# SmartSolar MPPT MQ — Toàn Bộ Kiến Thức API & Tích Hợp

> **Trạng thái**: ✅ LIVE · **Phiên bản**: **v2.0.1** (2026-09-27) · **Nguồn sự thật**: [../STATUS.md](../STATUS.md) · **Cập nhật**: 2026-09-27
>
> ⚠️ **v2.0.0 đổi domain `smartsolar_mppt` → `smartsolar_ha`** (thư mục, `manifest.domain`,
> import, tên service, đường dẫn deploy). HA xác định integration theo **tên thư mục** phải
> trùng `manifest["domain"]` (`loader.Integration.resolve_from_root()` tìm
> `custom_components/<domain>/manifest.json`), và domain chỉ được gồm chữ thường + gạch dưới —
> nên `smartsolar-ha` (gạch ngang) **không phải domain hợp lệ**, và đổi tên thư mục mà không đổi
> domain thì HA không tìm thấy integration. (Tên **repository GitHub** không liên quan: repo
> tình cờ cũng là `smartsolar_ha`, nhưng HA không bao giờ đọc nó.)
> Đây là **breaking change** với config entry cũ: hoặc migrate entry tại chỗ (đổi domain trong
> `.storage` — quy trình đã kiểm chứng, xem `CLAUDE.md` §Deploying to HA), hoặc xoá entry rồi
> thêm lại. Tên entity giữ nguyên nên entity_id / dashboard / long-term statistics vẫn khớp.
>
> Các chuỗi `smartsolar_mppt` còn lại trong tài liệu này là **dữ liệu lịch sử** (đường dẫn cũ,
> log cũ, ví dụ entity_id sinh từ tên thiết bị), không phải cấu hình hiện hành.
>
> ⚠️ Nội dung tổng hợp **2026-06-22**, đã bổ sung mục [7.4 — audit v1.5.1](#74-đã-fix-trong-v151-2026-09-27--audit-toàn-diện).
> Đối chiếu lại entity thực tế nếu có sai lệch.
>
> 📌 **v2.0.1 (27 bug đã fix, test 366 → 551)** — bảng audit đầy đủ nằm ở
> [`CLAUDE.md`](CLAUDE.md). Các thay đổi hành vi cần biết khi đọc tài liệu này:
> - Poll REST lỗi **không còn** làm entity `unavailable` khi MQTT vẫn đang có dữ liệu
>   sống; entity `Update Frequency` luôn available.
> - **Device mode chỉ nhận 1 Chipset ID** (trước đây nhận nhiều rồi âm thầm bỏ qua, và dữ
>   liệu của sạc thứ hai có thể hiện lên sensor của sạc thứ nhất).
> - Tên field legacy (`charging_power`, `yield_today`, `yield_total`) trong `dataStreams`
>   của MQTT **đã được map** như ở dạng flat.
> - Giá trị `synthesisStreams` được kiểm tra như mọi giá trị khác (NaN/Infinity và trần
>   `max_value` bị loại; fallback về tổng hợp theo từng thiết bị).
> - `sensor.…_wifi_signal` của firmware cũ vẫn `unknown` là **đúng** (payload không có
>   `signalQuality`).
> - `allow_multiple_instances` **không phải** thuộc tính của HA (đã xoá); sensor **không**
>   khôi phục giá trị cũ khi restart.

> **Mục đích:** Tài liệu tham khảo đầy đủ để viết lại integration từ đầu hoặc nâng cấp lên GitHub.
> **Ngày tổng hợp:** 2026-06-22
> **Phạm vi:** 2 sạc MPPT Mạnh Quân (PV1 60A GUID=547611 + PV2 40A GUID=14756976), Project ID 1072, hệ 24V off-grid.

---

## Mục lục

1. [SmartSolar Cloud API](#1-smartsolar-cloud-api)
2. [Phương pháp khám phá API (CDP)](#2-phương-pháp-khám-phá-api-cdp)
3. [Kiến trúc HA Integration Hiện Tại](#3-kiến-trúc-ha-integration-hiện-tại)
4. [Triển khai thực tế trên HA](#4-triển-khai-thực-tế-trên-ha)
5. [Thống kê năng lượng dẫn xuất (HA Config)](#5-thống-kê-năng-lượng-dẫn-xuất-ha-config)
6. [Dashboard Lovelace](#6-dashboard-lovelace)
7. [Các bug đã biết & Cần sửa khi viết lại](#7-các-bug-đã-biết--cần-sửa-khi-viết-lại)
8. [Hướng dẫn viết lại](#8-hướng-dẫn-viết-lại)

---

## 1. SmartSolar Cloud API

### Base URL
```
https://api.smartsolar.io.vn
```

### 1.1 Authentication — `POST /Auth/Login`

**Endpoint:** `POST https://api.smartsolar.io.vn/Auth/Login?Key=Content-Type`

**Request:**
```json
{
  "username": "<email_or_phone>",
  "password": "<password>"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiration": "2026-07-22T10:30:00.000Z",
  "userId": "...",
  "username": "..."
}
```

**Lưu ý:**
- Token JWT, hết hạn ~30 ngày
- Field `expiration` có thể ở định dạng ISO 8601 với `Z` suffix → cần chuẩn hóa trước khi parse
- Nếu không có `expiration`, mặc định 30 ngày
- Token được gửi qua header: `Authorization: Bearer <token>`

### 1.2 Project Metrics — `GET /Metric/ProjectMetrics`

**Endpoint:** `GET https://api.smartsolar.io.vn/Metric/ProjectMetrics?projectId={projectId}`

**Headers:** `Authorization: Bearer <token>`

**Response format (cho Project ID 1072):**
```json
{
  "synthesisStreams": [
    {"name": "yield_today", "value": "2.15", "unit": "kWh"},
    {"name": "yield_total", "value": "899.2", "unit": "kWh"},
    {"name": "co2", "value": "..."},
    {"name": "tree", "value": "..."},
    {"name": "coal", "value": "..."}
  ],
  "deviceLogs": [
    {
      "deviceGuid": "547611",
      "deviceName": "PV1 60A",
      "deviceType": 2,
      "dataStreams": [
        {"name": "pv_voltage", "value": "44.5", "unit": "V"},
        {"name": "pv_current", "value": "0.04", "unit": "A"},
        {"name": "bat_voltage", "value": "27.3", "unit": "V"},
        {"name": "bat_current", "value": "0.06", "unit": "A"},
        {"name": "charge_power", "value": "1.7", "unit": "W"},
        {"name": "today_kwh", "value": "0.01", "unit": "kWh"},
        {"name": "total_kwh", "value": "223.9", "unit": "kWh"},
        {"name": "temperature", "value": "35.2", "unit": "°C"},
        {"name": "status", "value": "1", "unit": ""}
      ]
    },
    {
      "deviceGuid": "14756976",
      "deviceName": "PV2 40A",
      "deviceType": 2,
      "dataStreams": [
        {"name": "pv_voltage", "value": "70.0", "unit": "V"},
        {"name": "pv_current", "value": "3.10", "unit": "A"},
        {"name": "bat_voltage", "value": "27.3", "unit": "V"},
        {"name": "bat_current", "value": "7.93", "unit": "A"},
        {"name": "charge_power", "value": "216.7", "unit": "W"},
        {"name": "today_kwh", "value": "0.59", "unit": "kWh"},
        {"name": "total_kwh", "value": "675.4", "unit": "kWh"},
        {"name": "temperature", "value": "42.1", "unit": "°C"},
        {"name": "status", "value": "1", "unit": ""}
      ]
    }
  ]
}
```

### 1.3 Project Summary (time range) — `GET /Metric/ProjectSummary`

**Endpoint (với time range):**
```
GET https://api.smartsolar.io.vn/Metric/ProjectSummary?projectId={projectId}&timeRange=1m
GET https://api.smartsolar.io.vn/Metric/ProjectSummary?projectId={projectId}
```

**Time range values:** `1d`, `1w`, `1m`, `1y`, hoặc để trống (all time)

### 1.4 Device Status — `GET /Device/Status`

**Endpoint:**
```
GET https://api.smartsolar.io.vn/Device/Status?deviceGuid={guid}
```

**Response format:**
```json
{
  "lastMessage": {
    "dataStreams": [
      {"name": "pv_voltage", "value": "44.5", "unit": "V"},
      ...
    ]
  }
}
```

### 1.5 Synthesis Metrics (multi-device) — `GET /Metric/SynthesisMetrics`

**Endpoint:**
```
GET https://api.smartsolar.io.vn/Metric/SynthesisMetrics?deviceType=2&deviceGuids=547611&deviceGuids=14756976
```

**Lưu ý:** Nhiều tham số `deviceGuids` (mỗi GUID 1 tham số). Response giống `ProjectMetrics`.

### Data Stream Field Names (10 loại sensor — v1.4.0)

| API Field | Unit | Description | Device Class | Source |
|-----------|------|-------------|-------------|--------|
| `pv_voltage` | V | Điện áp tấm pin | `voltage` | REST + MQTT |
| `pv_current` | A | Dòng điện tấm pin | `current` | REST + MQTT |
| `bat_voltage` | V | Điện áp battery/ắc quy | `voltage` | REST + MQTT |
| `bat_current` | A | Dòng sạc vào battery | `current` | REST + MQTT |
| `charge_power` | W | Công suất sạc hiện tại | `power` | REST + MQTT |
| `today_kwh` | kWh | Năng lượng hôm nay | `energy` (total_increasing) | REST + MQTT |
| `total_kwh` | kWh | Tổng năng lượng tích lũy | `energy` (total_increasing) | REST + MQTT |
| `temperature` | °C | Nhiệt độ controller | `temperature` | REST + MQTT |
| `signal_quality` | % | WiFi Signal (cường độ sóng WiFi) | — | MQTT + REST |
| `status` | — | Trạng thái (0-3) | — | REST + MQTT |

### Status Codes

| Code | Ý nghĩa |
|------|---------|
| 0 | Online |
| 1 | Charging (đang sạc) |
| 2 | Idle (không có nắng) |
| 3 | Fault (lỗi) |

### Device Types

| Type ID | Name |
|---------|------|
| 1 | Sun-GTIL2 (inverter) |
| 2 | Sạc MPPT Mạnh Quân |

### API Response Field Mapping

Lưu ý: API synthesis trả về field name khác với device data streams:

| Device dataStreams name | SynthesisStreams name |
|------------------------|----------------------|
| `today_kwh` | `yield_today` |
| `total_kwh` | `yield_total` |
| `charge_power` | *(không có trong synthesis)* → tính từ deviceLogs |
| `pv_voltage` | *(không có trong synthesis)* → tính từ deviceLogs |

### Token Refresh Strategy

- Token JWT hết hạn sau ~30 ngày
- Refresh khi còn ≤ 7 ngày trước khi hết hạn
- Không có endpoint refresh riêng — gọi lại `POST /Auth/Login` để lấy token mới
- Token được lưu trong memory (không persist ra disk)

---

## 2. Phương Pháp Khám Phá API (CDP)

SmartSolar không có public API documentation. Toàn bộ API được khám phá bằng Chrome DevTools Protocol (CDP).

### Phương pháp

1. **Mở Chrome headless** với remote debugging port 9222:
   ```bash
   chrome.exe --remote-debugging-port=9222 --headless
   ```

2. **Kết nối CDP** qua WebSocket:
   ```python
   from websocket import create_connection
   ws = create_connection(f"ws://localhost:9222/devtools/page/{page_id}")
   ```

3. **Enable Network domain** để bắt request/response:
   ```python
   ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
   ```

4. **Navigate đến web app** và trigger fetch():
   ```python
   # Gọi API từ context của page để bắt request
   ws.send(json.dumps({
       "id": 2,
       "method": "Runtime.evaluate",
       "params": {
           "expression": """
               fetch('/Metric/ProjectMetrics?projectId=1072', {
                   headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
               }).then(r => r.json()).then(d => console.log(JSON.stringify(d)))
           """
       }
   }))
   ```

5. **Bắt response body** qua `Network.getResponseBody`:
   ```python
   # Khi nhận được event Network.responseReceived, lấy requestId
   # Sau đó gọi:
   ws.send(json.dumps({
       "id": 3,
       "method": "Network.getResponseBody",
       "params": {"requestId": request_id}
   }))
   ```

### Web App URL

```
https://smartsolar.io.vn/  (web dashboard)
```

Web app lưu token trong `localStorage` sau khi login. API endpoints được phát hiện bằng cách theo dõi network requests khi web app tải dữ liệu.

### Các endpoint đã phát hiện

| Endpoint | Method | Phát hiện qua |
|----------|--------|--------------|
| `/Auth/Login?Key=Content-Type` | POST | Login page network request |
| `/Metric/ProjectSummary?projectId=X&timeRange=Y` | GET | Dashboard load |
| `/Metric/ProjectMetrics?projectId=X` | GET | Project detail page |
| `/Metric/SynthesisMetrics?deviceType=X&deviceGuids=Y` | GET | Multi-device view |
| `/Device/Status?deviceGuid=X` | GET | Device detail page |

---

## 3. Kiến Trúc HA Integration Hiện Tại

### 3.1 Cấu trúc file

```
custom_components/smartsolar_mppt/
├── __init__.py          # Entry point: setup, forward platforms, register services
├── manifest.json        # v1.2.2, domain=smartsolar_mppt, iot_class=cloud_polling
├── const.py             # Constants: SENSOR_TYPES, STATUS_MAPPING, API URLs
├── config_flow.py       # Multi-step UI config flow (auth → mode → device/project)
├── api.py               # HTTP API client: login, get_metrics, get_project_metrics
├── coordinator.py       # DataUpdateCoordinator: poll API every N seconds
├── sensor.py            # 3 sensor classes: Device, ProjectSynthesis, ProjectDevice
├── number.py            # UpdateInterval number entity (1-30 seconds)
├── services.yaml        # refresh_token service
├── strings.json         # UI strings
└── translations/        # en.json, vi.json
```

### 3.2 Data Flow

```
┌─────────────────────────────────────────────────────────┐
│ SmartSolar Cloud API (api.smartsolar.io.vn)              │
│   POST /Auth/Login?Key=Content-Type → JWT token          │
│   GET /Metric/ProjectMetrics?projectId=1072 → metrics    │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS (aiohttp)
┌────────────────────▼────────────────────────────────────┐
│ SmartSolarAPI (api.py)                                   │
│   - login() → lưu token + expiry                        │
│   - refresh_token_if_needed() → tự động refresh 7d      │
│   - get_project_metrics(project_id) → dict              │
│   - get_metrics(device_type, chipset_ids, mode) → dict │
│   - test_connection() → login + close                   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ SmartSolarDataUpdateCoordinator (coordinator.py)        │
│   - Polling interval: default 5s (configurable 1-30s)   │
│   - _async_update_data(): gọi API → return dict         │
│   - Tự động discover device GUIDs từ deviceLogs          │
│   - always_update=False (chỉ notify khi data thay đổi)  │
└────────────────────┬────────────────────────────────────┘
                     │ coordinator.data
         ┌───────────┼───────────┐
         ▼                       ▼
┌─────────────────┐    ┌──────────────────┐
│ Sensor Entities │    │ Number Entity    │
│ (sensor.py)     │    │ (number.py)      │
│                 │    │                  │
│ 3 classes:      │    │ UpdateInterval   │
│ - DeviceSensor  │    │ (1-30 seconds)   │
│ - ProjSynthesis │    │                  │
│ - ProjDevice    │    │                  │
└─────────────────┘    └──────────────────┘
```

### 3.3 Sensor Classes

#### SmartSolarDeviceSensor (Device mode)
- Data source: `coordinator.data.lastMessage.dataStreams[]`
- 1 device → 9 sensors
- Entity ID pattern: `sensor.smartsolar_mppt_d_{guid}_{type}`

#### SmartSolarProjectSynthesisSensor (Project mode - Tổng)
- Data source: `coordinator.data.synthesisStreams[]` (primary)
- Fallback: sum từ `deviceLogs[]` khi synthesisStreams không có field đó
- 9 sensors cho toàn bộ project
- Entity name: "Tổng PV Voltage", "Tổng Charge Power", ...
- Entity ID pattern: `sensor.smartsolar_mppt_project_{projectId}_{type}`

#### SmartSolarProjectDeviceSensor (Project mode - từng thiết bị)
- Data source: `coordinator.data.deviceLogs[{deviceGuid}].dataStreams[]`
- 9 sensors × N devices
- Entity name: "PV1 Voltage", "PV2 Current", ... (đánh số theo thứ tự GUID)
- Entity ID pattern: `sensor.technology_smartsolar_mppt_project_{projectId}_pv{N}_{type}`

### 3.4 Entity ID Convention

HA tự sinh entity_id từ tên entity (transliterate tiếng Việt → lowercase không dấu + underscore):

| Entity Name | Entity ID (HA generated) |
|------------|--------------------------|
| Tổng PV Voltage | `sensor.smartsolar_mppt_project_1072_pv_voltage` |
| Tổng Charge Power | `sensor.smartsolar_mppt_project_1072_charge_power` |
| Tổng Today Energy | `sensor.smartsolar_mppt_project_1072_today_energy` |
| Tổng Total Energy | `sensor.smartsolar_mppt_project_1072_total_energy` |
| Tổng Temperature | `sensor.smartsolar_mppt_project_1072_temperature` |
| PV1 Charge Power | `sensor.technology_smartsolar_mppt_project_1072_pv1_charge_power` |
| PV1 Today Energy | `sensor.technology_smartsolar_mppt_project_1072_pv1_today_energy` |
| PV1 Total Energy | `sensor.technology_smartsolar_mppt_project_1072_pv1_total_energy` |
| PV2 Charge Power | `sensor.technology_smartsolar_mppt_project_1072_pv2_charge_power` |
| PV2 Today Energy | `sensor.technology_smartsolar_mppt_project_1072_pv2_today_energy` |
| PV2 Total Energy | `sensor.technology_smartsolar_mppt_project_1072_pv2_total_energy` |
| Update Frequency | `number.smartsolar_mppt_project_update_frequency` |

> **QUAN TRỌNG:** Entity ID được HA tự động sinh từ tên, không phải do code set. Prefix `technology_` xuất hiện vì HA thêm technology prefix khi có nhiều device cùng loại.

### 3.5 Config Flow Steps

```
Step 1: async_step_user
  → Nhập username + password
  → Test login (gọi /Auth/Login)
  → Nếu OK → Step 2

Step 2: async_step_mode
  → Chọn "device" hoặc "project"
  → Device → Step 3a
  → Project → Step 3b

Step 3a: async_step_chipset_ids (Device mode)
  → Nhập 1 Chipset ID
  → Test API (gọi /Device/Status)
  → Tạo config entry

Step 3b: async_step_project_method (Project mode)
  → Chọn "Theo Project ID" hoặc "Theo danh sách Device IDs"
  → Project ID → Step 4a
  → Device IDs → Step 4b

Step 4a: async_step_project_id
  → Nhập Project ID
  → Test API (gọi /Metric/ProjectMetrics)
  → Tạo config entry

Step 4b: async_step_project_devices
  → Nhập danh sách Device IDs (comma-separated)
  → Test API (gọi /Metric/SynthesisMetrics)
  → Tạo config entry
```

### 3.6 Config Entry Data

```json
{
  "username": "vokupt",
  "password": "<password>",
  "mode": "project",
  "device_type": 2,
  "project_id": "1072",
  "chipset_ids": []
}
```

### 3.7 Token & API Error Handling

```python
# Error hierarchy:
SmartSolarAPIError(Exception)
├── SmartSolarAuthenticationError  # 401 — sai credentials
├── SmartSolarConnectionError      # aiohttp.ClientError — mất mạng
└── SmartSolarNotFoundError        # 404 — sai project/device ID

# Token refresh:
# - Kiểm tra expiry mỗi lần gọi API
# - Refresh nếu còn ≤ 7 ngày trước khi hết hạn
# - Gọi lại login() để lấy token mới
```

---

## 4. Triển Khai Thực Tế Trên HA

### 4.1 Thông tin kết nối

| Item | Value |
|------|-------|
| HA URL | `http://192.168.10.15:8123` |
| HA Version | **2026.9.3** (HA Supervised, Docker) — đo 2026-09-27 |
| HA Python | 3.14.6 — nên venv test local phải là Python **3.14** |
| SSH | `vokupt@192.168.10.15` — password via `HA_PASS` env var |
| HA Token (long-lived) | Trong `HA_info.txt` / `.env` |
| SMB Config | `\\192.168.10.15\config\` (user: vokupt) |
| SMB packages | `\\192.168.10.15\config\packages\` |
| SMB Frigate addon | `\\192.168.10.15\addon_configs\ccab4aaf_frigate\` |
| HA restart API | `POST /api/services/homeassistant/restart` (503/504 = thành công) |
| HA reload YAML | `POST /api/services/homeassistant/reload_all` (LƯU Ý: không reload được utility_meter) |
| Deploy chuẩn | `python deploy_to_ha.py` (có gate lint/mypy/test) rồi `python verify_live.py` |

### 4.2 Config Entry Hiện Tại

```
Entry ID: 01K7DZBBS75AS1WBR48FVXVQZ1
Mode: Project (by ID)
Project ID: 1072
Device Type: 2 (MPPT Mạnh Quân)
State: LOADED
```

### 4.3 Hệ thống Solar 24V — Hardware

| Component | Thông số |
|-----------|----------|
| **MPPT 1 (PV Phụ)** | Mạnh Quân 60A WiFi, GUID=547611, 3×200W panels (~600W) |
| **MPPT 2 (PV Chính)** | Mạnh Quân 40A WiFi, GUID=14756976, 1× Longi 540W panel (~540W) |
| **Battery** | 8S LFP 280Ah (~7kWh @ 24V, 25.6V nominal, 28.8V full) |
| **BMS** | JK BMS 24V 280Ah (ESP32, sensor `sensor.jk_power`, `sensor.jk_mosfet_temperature`) |
| **Network** | VLAN 20 (192.168.20.0/24) qua WiFi "Ga", cross-VLAN với HA tại VLAN 10 (192.168.10.15) |
| **Loại hệ** | Off-grid — không nối lưới, toàn bộ PV là năng lượng tự sản xuất |

### 4.4 Thiết bị MPPT (theo dữ liệu thực tế)

| Label | GUID | Model | PV Power | Total Energy | Vai trò |
|-------|------|-------|----------|-------------|---------|
| **Tổng** | — | — | ~218W | ~899 kWh | Aggregate |
| **PV1** (PV Phụ) | 547611 | 60A | ~2W | ~224 kWh | Panel nhỏ (3×200W) |
| **PV2** (PV Chính) | 14756976 | 40A | ~217W | ~675 kWh | Panel lớn (1×540W) |

> **Cảnh báo:** PV1/PV2 labeling phụ thuộc vào thứ tự GUID trong API response. Không ổn định giữa các lần restart. Cần cơ chế sort cố định (theo GUID hoặc theo tên thiết bị).
>
> **Ghi nhận inconsistency:** YAML header (`30_solar_24v_energy_stats.yaml`) ghi PV1=GUID 547611, PV2=GUID 14756976. Nhưng một số entity cũ (dạng `charge_power_<GUID>`) trong Lovelace dashboard cũ map ngược lại: `pv1_power` → GUID 14756976, `pv2_power` → GUID 547611. Các entity mới dạng `technology_...pv1_*`/`technology_...pv2_*` do HA tự sinh tên dựa trên thứ tự GUID trong API response, có thể khác với entity GUID-suffixed cũ. Khi viết lại, cần cố định mapping: PV Chính = GUID 14756976 (40A, ~217W), PV Phụ = GUID 547611 (60A, ~2W).

### 4.5 Tất Cả Entity Hiện Tại (38 entity — v1.5.1)

> Đo trực tiếp `GET /api/states` ngày **2026-09-27** sau khi deploy v1.5.1.
> Trước đó chỉ 32 entity vì bản 1.3.0 đang chạy thiếu 6 sensor thống kê.

#### Synthesis (Tổng) — 10 sensors
```
sensor.smartsolar_mppt_project_1072_pv_voltage       ← "Tổng PV Voltage"
sensor.smartsolar_mppt_project_1072_pv_current        ← "Tổng PV Current"
sensor.smartsolar_mppt_project_1072_bat_voltage       ← "Tổng Battery Voltage"
sensor.smartsolar_mppt_project_1072_bat_current       ← "Tổng Battery Current"
sensor.smartsolar_mppt_project_1072_charge_power      ← "Tổng Charge Power" ★
sensor.smartsolar_mppt_project_1072_today_energy      ← "Tổng Today Energy" ★
sensor.smartsolar_mppt_project_1072_total_energy      ← "Tổng Total Energy" ★
sensor.smartsolar_mppt_project_1072_temperature       ← "Tổng Temperature" ★
sensor.smartsolar_mppt_project_1072_status            ← "Tổng Status"
sensor.technology_smartsolar_mppt_project_1072_total_wifi_signal  ← "Tổng WiFi Signal" 🆕
```

#### PV1 (GUID=547611) — 10 sensors
```
sensor.technology_smartsolar_mppt_project_1072_pv1_pv_voltage
sensor.technology_smartsolar_mppt_project_1072_pv1_pv_current
sensor.technology_smartsolar_mppt_project_1072_pv1_bat_voltage
sensor.technology_smartsolar_mppt_project_1072_pv1_bat_current
sensor.technology_smartsolar_mppt_project_1072_pv1_charge_power
sensor.technology_smartsolar_mppt_project_1072_pv1_today_energy  ★
sensor.technology_smartsolar_mppt_project_1072_pv1_total_energy  ★
sensor.technology_smartsolar_mppt_project_1072_pv1_temperature
sensor.technology_smartsolar_mppt_project_1072_pv1_status
sensor.technology_smartsolar_mppt_project_1072_pv1_wifi_signal   🆕
```

#### PV2 (GUID=14756976) — 10 sensors
```
sensor.technology_smartsolar_mppt_project_1072_pv2_pv_voltage
sensor.technology_smartsolar_mppt_project_1072_pv2_pv_current
sensor.technology_smartsolar_mppt_project_1072_pv2_bat_voltage
sensor.technology_smartsolar_mppt_project_1072_pv2_bat_current
sensor.technology_smartsolar_mppt_project_1072_pv2_charge_power
sensor.technology_smartsolar_mppt_project_1072_pv2_today_energy  ★
sensor.technology_smartsolar_mppt_project_1072_pv2_total_energy  ★
sensor.technology_smartsolar_mppt_project_1072_pv2_temperature
sensor.technology_smartsolar_mppt_project_1072_pv2_status
sensor.technology_smartsolar_mppt_project_1072_pv2_wifi_signal   ⚠️ unknown — API trả signalQuality=null cho GUID này (xem 7.4.9)
```

#### Thống kê trong ngày (3 sensor × 2 thiết bị = 6) — 🆕 v1.5.1

Do coordinator tự tính (`get_daily_stats()`), server SmartSolar **không** lưu
lịch sử dài hạn. Reset lúc nửa đêm theo giờ local.

```
sensor.technology_smartsolar_mppt_project_1072_pv1_peak_power_today        ← W, đỉnh công suất
sensor.technology_smartsolar_mppt_project_1072_pv1_avg_power_today         ← W, công suất trung bình
sensor.technology_smartsolar_mppt_project_1072_pv1_production_hours_today  ← h, số giờ có nắng (>5 W)
sensor.technology_smartsolar_mppt_project_1072_pv2_peak_power_today
sensor.technology_smartsolar_mppt_project_1072_pv2_avg_power_today
sensor.technology_smartsolar_mppt_project_1072_pv2_production_hours_today
```

> ⚠️ Trước v1.5.1, 6 entity này **có trong registry nhưng luôn `unavailable`**
> vì bản đang chạy trên HA là 1.3.0 không có class `SmartSolarStatsSensor`.
> Xem [7.4.1](#741-phát-hiện-quan-trọng-nhất--ha-đang-chạy-bản-cũ).

#### Khác — 2 entities
```
number.technology_smartsolar_mppt_project_1072_update_frequency   ← Update Frequency (1-30s)
update.smartsolar_mppt_sac_mppt_manh_quan_update                  ← HACS update entity
```

★ = Entity được dùng trong thống kê năng lượng dẫn xuất

#### Legacy Entity IDs (định dạng GUID-suffixed cũ)

Các entity này được tạo bởi phiên bản integration cũ (trước khi có PV1/PV2 naming). **Không còn active** trên HA hiện tại (đã được clean up):

```
sensor.smartsolar_mppt_project_1072_charge_power_14756976   ← GUID 14756976
sensor.smartsolar_mppt_project_1072_pv_voltage_14756976
sensor.smartsolar_mppt_project_1072_pv_current_14756976
sensor.smartsolar_mppt_project_1072_charge_power_547611     ← GUID 547611
sensor.smartsolar_mppt_project_1072_pv_voltage_547611
sensor.smartsolar_mppt_project_1072_pv_current_547611
```

Nếu thấy các entity này trong registry, có thể xóa an toàn (đã được thay thế bởi `technology_...pv1_*`/`technology_...pv2_*`).

### 4.6 JK BMS 24V — Entity liên quan

```
sensor.jk_power                     ← Công suất battery (W): dương=xả, âm=sạc
sensor.jk_mosfet_temperature        ← Nhiệt độ MOSFET (°C)
```

JK BMS cung cấp battery power để tính tổng tải DC: `Load = MPPT charge_power + JK power`

---

## 5. Thống Kê Năng Lượng Dẫn Xuất (HA Config)

File: `d:\Code\HA-Config\packages\30_solar_24v_energy_stats.yaml` (v2.0)

### 5.1 Tổng quan data flow

```
SmartSolar API → HA Integration sensors (W, kWh)
     │
     ├─→ Template sensors (VND savings + load power)
     │
     ├─→ Integration sensor (W→kWh Riemann sum)
     │
     └─→ Utility meters (daily/monthly/yearly từ total_energy)
           │
           └─→ Template savings sensors dùng utility meter values
```

### 5.2 Template Sensors (6 cái)

| Entity ID | Purpose | Source |
|-----------|---------|--------|
| `sensor.solar_24v_tong_cong_suat_tai` | Tổng công suất tải 24V (W) | MPPT charge_power + JK power |
| `sensor.solar_24v_tiet_kiem_hom_nay` | Tiết kiệm hôm nay (VND) | PV today × giá bậc thang × 1.08 VAT |
| `sensor.solar_24v_tiet_kiem_thang` | Tiết kiệm tháng (VND) | PV monthly × giá bậc thang × 1.08 VAT |
| `sensor.solar_24v_tiet_kiem_nam` | Tiết kiệm năm (VND) | PV yearly × giá bậc thang × 1.08 VAT |
| `sensor.solar_24v_tiet_kiem_tong_bo` | Tiết kiệm tổng bộ (VND) | PV total × giá bậc thang × 1.08 VAT |
| `sensor.solar_24v_project_summary` | Tổng quan (attributes) | Tổng hợp tất cả metrics |

### 5.3 Công thức tính tiết kiệm (giá bậc thang VN)

```python
# Giá điện bậc thang (VNĐ/kWh) — chưa VAT:
BAC_1 = 1984   # 0-50 kWh
BAC_2 = 2050   # 51-100 kWh
BAC_3 = 2380   # 101-200 kWh
BAC_4 = 2998   # 201-300 kWh
BAC_5 = 3350   # 301-400 kWh
BAC_6 = 3460   # 401+ kWh

VAT = 1.08     # 8% VAT

def tiered_cost(kwh):
    """Tính tiền điện theo bậc thang (chưa VAT)."""
    if kwh <= 0: return 0
    if kwh <= 50: return kwh * 1984
    if kwh <= 100: return 99200 + (kwh - 50) * 2050
    if kwh <= 200: return 201700 + (kwh - 100) * 2380
    if kwh <= 300: return 439700 + (kwh - 200) * 2998
    if kwh <= 400: return 739500 + (kwh - 300) * 3350
    return 1074500 + (kwh - 400) * 3460

def savings(kwh):
    """Tiết kiệm = tiered_cost(kwh) * VAT."""
    return round(tiered_cost(kwh) * 1.08)
```

**Lưu ý:** Vì hệ off-grid, toàn bộ sản lượng PV được tính là tiết kiệm (không trừ grid import).

### 5.4 Integration Sensor (1 cái)

```yaml
sensor:
  - platform: integration
    source: sensor.solar_24v_tong_cong_suat_tai
    name: "Solar 24V Tổng Năng Lượng Tải"
    unique_id: solar_24v_load_energy_v1
    unit_prefix: k       # W → kW
    unit_time: h         # → kWh
    method: left         # Riemann sum left method
    round: 3
```

→ Entity ID: `sensor.solar_24v_tong_nang_luong_tai`

### 5.5 Utility Meters (12 cái)

| Entity ID | Source | Cycle |
|-----------|--------|-------|
| `sensor.solar_24v_pv_daily` | `sensor.smartsolar_mppt_project_1072_total_energy` | daily |
| `sensor.solar_24v_pv_monthly` | `sensor.smartsolar_mppt_project_1072_total_energy` | monthly |
| `sensor.solar_24v_pv_yearly` | `sensor.smartsolar_mppt_project_1072_total_energy` | yearly |
| `sensor.solar_24v_pv1_daily` | `sensor.technology_..._pv1_total_energy` | daily |
| `sensor.solar_24v_pv1_monthly` | `sensor.technology_..._pv1_total_energy` | monthly |
| `sensor.solar_24v_pv1_yearly` | `sensor.technology_..._pv1_total_energy` | yearly |
| `sensor.solar_24v_pv2_daily` | `sensor.technology_..._pv2_total_energy` | daily |
| `sensor.solar_24v_pv2_monthly` | `sensor.technology_..._pv2_total_energy` | monthly |
| `sensor.solar_24v_pv2_yearly` | `sensor.technology_..._pv2_total_energy` | yearly |
| `sensor.solar_24v_load_daily` | `sensor.solar_24v_tong_nang_luong_tai` | daily |
| `sensor.solar_24v_load_monthly` | `sensor.solar_24v_tong_nang_luong_tai` | monthly |
| `sensor.solar_24v_load_yearly` | `sensor.solar_24v_tong_nang_luong_tai` | yearly |

**Yêu cầu:** Source sensor phải có `state_class: total_increasing` để utility_meter hoạt động.

### 5.6 HA Version Caveats

- **HA 2026.5.0:** `history_stats` với template `start`/`end` không hoạt động
- **HA 2026.5.0:** `reload_all` không reload được utility_meter → cần restart HA
- **HA 2026.5.0:** `async_config_entry_first_refresh` từ chối khi state = LOADED → dùng `async_refresh()`
- **HA 2026.9.x:** `device_class: energy` + `state_class: measurement` bị **từ chối** —
  log warning mỗi entity và **không dựng statistics**. Phải dùng `total` hoặc
  `total_increasing` (đã sửa cho `today_kwh` ở v1.5.1)
- **HA 2026.9.x:** `DataUpdateCoordinator.__init__` phát usage-report nếu **không**
  truyền `config_entry=` (dựa vào ContextVar). Truyền `config_entry=entry` — và
  việc này **không** gây reload vòng lặp, nó chỉ đăng ký `async_on_unload`
- **HA 2026.9.x:** `DataUpdateCoordinator.async_shutdown` là **coroutine** → phải `await`
- **HA 2026.9.x:** `ConfigEntry.version` / `.data` **không set trực tiếp được**
  (`UPDATE_ENTRY_CONFIG_ENTRY_ATTRS`) → phải dùng `hass.config_entries.async_update_entry()`
- **Jinja2 sandbox:** Không hỗ trợ `{% macro %}` — phải inline toàn bộ logic

---

## 6. Dashboard Lovelace

### 6.1 Vị trí

Dashboard Mushroom, view "Solar" (view index 2), Section 1 (mới nhất, trên cùng).

### 6.2 Cấu trúc card

```
vertical-stack
├── mushroom-title-card: "☀️ Solar 24V — MPPT MQ Mạnh Quân"
├── horizontal-stack (header): Ngày | Tháng | Năm | Tổng (chips)
├── horizontal-stack (PV1 60A): H.nay | Tháng | Năm | T.bộ
├── horizontal-stack (PV2 40A): H.nay | Tháng | Năm | T.bộ
├── horizontal-stack (PV Tổng): H.nay | Tháng | Năm | T.bộ
├── horizontal-stack (DC Load): H.nay | Tháng | Năm | T.bộ
├── horizontal-stack (Tiết kiệm): H.nay | Tháng | Năm | T.bộ
└── mushroom-chips-card (footer): "Dữ liệu từ SmartSolar Cloud API"
```

### 6.3 Color scheme

| Column | Color (hex) | Ý nghĩa |
|--------|-------------|---------|
| H.nay (Today) | `#00e5ff` | Cyan |
| Tháng (Month) | `#ffea00` | Yellow |
| Năm (Year) | `#76ff03` | Light green |
| T.bộ (Total) | `#ff9100` | Orange |

### 6.4 Deploy method

Dashboard được deploy qua SMB trực tiếp vào file `.storage/lovelace.lovelace` (JSON, không phải YAML):
1. Backup: `cp lovelace.lovelace lovelace.lovelace.bak_<timestamp>`
2. Đọc JSON → Python `json.load()`
3. Chèn card mới vào đúng vị trí → `json.dump(indent=2)`
4. Upload lại qua SMB
5. Browser hard refresh (Ctrl+F5)

**QUAN TRỌNG:** Lovelace config nằm trong `.storage/` — là JSON, không phải YAML. Không thể dùng REST API (`/api/lovelace/*` trả về 404 trong HA 2026.5.0).

File tham khảo dashboard YAML: `d:\Code\HA-Config\packages\dashboard_solar_24v.md`

---

## 7. Các Bug Đã Biết & Cần Sửa Khi Viết Lại

### 7.1 Bugs hiện tại (từ CLAUDE.md)

1. **`lru_cache` trên `get_sensor_info` không cần thiết** — `const.py:134`: `@lru_cache(maxsize=None)` cho 1 dict lookup đơn giản. Overhead cache > lookup.

2. **`async_get_translations` gọi trong coordinator update** — `coordinator.py:74`: Gọi translation fetch mỗi lần update nếu chipset_ids rỗng. Đây là error path, không nên gọi translation.

3. **Thiếu `RestoreEntity` cho Number entity** — `number.py`: UpdateInterval entity mất state khi restart HA.

4. **Không có `async_migrate_entry`** — Nếu tăng VERSION, config entry cũ sẽ không migrate được.

5. **Hardcoded Vietnamese status strings trong code cũ** — Đã sửa 1 phần (đổi sang English keys) nhưng logic status mapping vẫn dùng số → text cứng.

6. **Không có retry logic** — API errors trong coordinator raise `UpdateFailed` nhưng không retry.

7. **No `__slots__` cho 1 số class** — Đã thêm 1 phần nhưng có thể chưa đầy đủ.

### 7.2 Vấn đề thiết kế

1. **PV1/PV2 labeling không ổn định** — Thứ tự phụ thuộc vào thứ tự GUID trong API response. Nên sort theo GUID hoặc cho phép user gán label trong config flow.

2. **Entity ID prefix `technology_`** — HA tự thêm prefix `technology_` cho per-device sensors. Không kiểm soát được từ code. Có thể fix bằng cách set `entity_id` trong config flow hoặc dùng `suggested_entity_id`.

3. **Synthesis sensor fallback** — Khi synthesisStreams thiếu field, fallback về sum từ deviceLogs. Điều này ok nhưng không nhất quán (một số field có sẵn, một số phải tính).

4. **`always_update=False`** — Coordinator chỉ notify khi data thay đổi. Nhưng các sensor như `charge_power` thay đổi liên tục → vẫn notify thường xuyên.

5. **Không persist token** — Token chỉ lưu trong memory. Sau restart HA phải login lại. Nên persist token (encrypted) vào config entry data.

### 7.3 Lỗi đã fix — v1.2.1 (session 2026-04-30)

5 bug chặn integration hoạt động, phát hiện và sửa trong session 2026-04-30.

#### Bug A — Thiếu per-device sensors trong Project mode

**Phát hiện:** Entity registry có 27 entity nhưng chỉ 11 active — thiếu toàn bộ 18 sensor cho 2 thiết bị riêng lẻ.

**Root cause:** Trong `__init__.py`, `async_forward_entry_setups` (platform setup) được gọi **TRƯỚC** `async_refresh`. Khi `sensor.py` chạy `async_setup_entry`, `coordinator.data` còn rỗng → `deviceLogs` không có → `device_guids = []` → không tạo được `SmartSolarProjectDeviceSensor` cho từng thiết bị.

```python
# Thứ tự SAI (v1.2.0):
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)  # sensor.py chạy, data rỗng
await coordinator.async_config_entry_first_refresh()                    # data mới có

# Thứ tự ĐÚNG (v1.2.1):
await coordinator.async_refresh()                                       # data có trước
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS) # sensor.py thấy deviceLogs
```

**Cạm bẫy:** `async_config_entry_first_refresh()` bị HA 2026.4.4 từ chối khi state = LOADED (chỉ chấp nhận `SETUP_IN_PROGRESS`) → phải dùng `async_refresh()` (không check state).

#### Bug B — Config entry mất field ("Missing device_type in configuration")

**Root cause:** Config entry data CHỈ CÒN `username` và `password`; `mode`, `device_type`, `project_id`, `chipset_ids` biến mất. Không xác định được nguyên nhân gốc — nghi do migration từ version cũ, hoặc `async_update_entry` trong `number.py` ghi đè data.

**Fix:** Sửa trực tiếp `/config/.storage/core.config_entries` bằng Python:
```python
e["data"]["mode"] = "project"
e["data"]["device_type"] = 2           # DEVICE_TYPE_MANH_QUAN
e["data"]["project_id"] = "1072"
e["data"]["chipset_ids"] = []
```
Suy luận từ `unique_id` = `vokupt_project_2_1072`.

#### Bug C — `AttributeError: '_device_discovery_callbacks'`

**Root cause:** v1.2.0 xóa `_device_discovery_callbacks` khỏi `__slots__`/`__init__` (coi là dead code) nhưng `_async_update_data` (dòng 91-95) vẫn gọi nó.

**Fix:** Xóa vòng lặp callback khỏi `_async_update_data`.

#### Bug D — 29 entity rác trong registry

Entity mồ côi từ các lần cài đặt cũ: 9 × `sensor.pv_voltage` (không prefix), 9 × `sensor.pv_voltage_<GUID>`, `update.smartsolar_mppt_update`, `switch.smartsolar_mppt_pre_release`.

**Fix:** Lọc entity_registry, giữ entity có `smartsolar_mppt_project` trong `unique_id`, xóa phần còn lại.

#### Bug E — Entity naming dùng GUID

**Vấn đề:** Tên entity dạng `PV Voltage (14756976)` — không biết GUID nào là thiết bị vật lý nào.

**Fix:** Thêm tham số `device_index` vào `SmartSolarSensor.__init__`. Trong project mode, device đánh số theo thứ tự xuất hiện trong `deviceLogs` → index 1 = `PV1 Voltage`, index 2 = `PV2 Voltage`, synthesis = `Tổng PV Voltage`.

#### Đã fix trong v1.2.0 (session trước)

| Vấn đề | Fix |
|--------|-----|
| `NameError` — biến `mode`/`project_id`/`chipset_ids` dùng trước khi khai báo | Đưa khai báo lên trước debug log |
| `assert` trong production code (config_flow.py) | Thay bằng `if ... is None: raise ValueError(...)` |
| `FlowResult` deprecated | Thay bằng `ConfigFlowResult` |
| API session leak — `test_connection()` không gọi `close()` | Thêm `finally: await self.close()` |
| `__del__` method unsafe trong api.py | Đã xóa |
| Private API access trong number.py (`_unsub_refresh`, `_schedule_refresh`) | Dùng public API `update_interval` |
| `@cached_property` name override không cần thiết | Đã xóa, dùng `_attr_name` |
| `DATA_STREAM_INDICES`, `CONF_UPDATE_INTERVAL` unused | Đã xóa |
| Debug log noise (~650 logs/min) | Giảm xuống 0 trong hot path |
| Thiếu `__slots__` | Đã thêm vào coordinator, sensors, number |
| Thiếu `MINOR_VERSION` | `MINOR_VERSION = 1` |
| `STATUS_MAPPING` hardcoded tiếng Việt | Đổi sang English keys |
| `DeviceInfo` trùng lặp 3 nơi | `build_device_info()` shared helper trong const.py |
| `from datetime import timedelta` import lười trong number.py | Đưa lên module top |

### 7.5 Cạm bẫy khi thao tác với HA (rút ra từ session 2026-04-30)

- **Không dùng `grep -v` để xóa dòng khỏi JSON** — làm hỏng cấu trúc. Luôn `json.load()` → sửa → `json.dump()`.
- **Kiểm tra cả `entities` và `deleted_entities`** trong entity_registry.
- **File trong `/config/.storage/` phải có owner `root:root`.**
- **Không dùng `async_config_entry_first_refresh`** khi config entry đã LOADED — dùng `async_refresh()`.
- **Print UTF-8 từ Windows sang console** gây lỗi cp1252. Ghi output ra file rồi đọc lại.
- **Deploy code:** base64 encode → SSH paramiko → decode trên host → `sudo rm -rf __pycache__` → restart HA. (Nay dùng `upload_to_ha.py`.)

### 7.4 Đã fix trong v1.5.1 (2026-09-27) — audit toàn diện

> Nguồn: [CLAUDE.md](CLAUDE.md#v151--audit-fixes-2026-09-27) (bảng đầy đủ 12 bug).
> Test: **261 passed** (trước 121). `ruff` + `mypy` sạch, `mypy` nay là gate cứng trong CI.

#### 7.4.1 Phát hiện quan trọng nhất — HA đang chạy bản CŨ

`/homeassistant/custom_components/smartsolar_mppt/` trên HA là bản **1.3.0 tải từ 2026-06-27**,
KHÔNG phải bản trong repo:

| Kiểm tra | Kết quả |
|---|---|
| `manifest.json` trên HA | `"version": "1.3.0"`... (thực tế `1.4.0` trong manifest cũ) |
| `grep -c peak_power` trên HA | **0** ở cả `coordinator.py`, `sensor.py`, `const.py` |
| `sw_version` trong `build_device_info()` trên HA | `"1.3.0"` |
| md5 9 file `.py` | **DRIFT toàn bộ** so với repo |

**Hệ quả đo được:** 6 sensor `*_peak_power_today` / `*_avg_power_today` /
`*_production_hours_today` **tồn tại trong entity registry nhưng mãi mãi
`unavailable`** — vì bản đang chạy không hề có class `SmartSolarStatsSensor`.
Chúng là entity mồ côi, không phải sensor lỗi. Sau khi deploy bản mới, cả 6
sensor báo số bình thường.

**Bài học:** "sensor `unavailable`" chưa chắc là bug logic — phải so **md5 file
đang chạy** với repo trước khi đọc code. Backup bản cũ nằm ở
`_local_archive/deployed/smartsolar_mppt_20260927-222119.tar.gz`.

#### 7.4.2 Điện áp pin tổng bị CỘNG thay vì lấy trung bình

`SmartSolarProjectSynthesisSensor` cộng mọi sensor không nằm trong
`_ADDITIVE_SENSORS`, nên `total_battery_voltage` = 26.6 + 26.4 = **53.0 V** trên
hệ 24 V khi `synthesisStreams` thiếu field đó. Đã thay bằng bảng
`const.AGGREGATION`:

| Chiến lược | Sensor |
|---|---|
| `sum` | pv_current, bat_current, charge_power, today_kwh, total_kwh |
| `average` | pv_voltage, bat_voltage, temperature, signal_quality |
| `max` | status (xấu nhất) |

#### 7.4.3 Sensor `status` tổng luôn `unknown`

`_calculate_from_device_logs()` map status → chuỗi **trước khi** tổng hợp, rồi
cộng chuỗi → luôn `None`. Nay tổng hợp **mã số** trước, map text sau
(`_device_log_value(..., raw_status=True)`).

#### 7.4.4 MQTT nhận dữ liệu của NGƯỜI KHÁC

Broker `mqttx.smartsolar.io.vn` **dùng chung cho mọi khách hàng SmartSolar**.
Probe `manhquan/device/mppt_charger/log/+/#` thấy hàng trăm thiết bị lạ
(GUID `8646193`, `1186348`, `14901856`, ...). Code cũ gọi
`_merge_mqtt_into_data()` cho **mọi** GUID nhận được → có thể chèn deviceLog lạ
vào dữ liệu của mình. Nay có `_is_tracked_device()` chặn.

#### 7.4.5 Retry/backoff là code chết

`_request_with_retry()` được viết đầy đủ (exponential backoff, không retry
401/404) nhưng **không method nào gọi nó**. Nay mọi GET đi qua
`_authed_get()` → `_request_with_retry()`.

#### 7.4.6 `async_shutdown()` là coroutine nhưng không được await

`async_unload_entry` gọi `coordinator.async_shutdown()` trần → timer poll và
listener nửa đêm **rò rỉ mỗi lần reload**. Nay `await`.

#### 7.4.7 `today_kwh` khai báo state_class sai

`state_class: measurement` + `device_class: energy` bị HA từ chối: log cảnh báo
mỗi entity và **không dựng statistics**. Đổi sang `total_increasing` (reset lúc
nửa đêm = chu kỳ công tơ mới).

#### 7.4.8 Nhãn PV1/PV2 không ổn định

Thứ tự `deviceLogs` do server trả về không đảm bảo → tên entity (và entity_id)
đảo giữa các lần restart. Nay sort GUID **theo số** (`guid_sort_key`):
`547611` → PV1, `14756976` → PV2.

#### 7.4.9 Giới hạn đã biết — sạc 40A không báo sóng WiFi

API trả `signalQuality: null` cho GUID `14756976` (đo trực tiếp
`/Metric/ProjectMetrics`), và firmware này phát MQTT dạng cũ
(`command: updateDeviceLog`) **không có** field `signalQuality`. Vì vậy
`sensor.…_pv2_wifi_signal = unknown` là **đúng**, không phải bug. Sạc 60A
(`547611`) phát dạng mới `update_device_metrics` → có `signalQuality` → báo 100%.

#### 7.4.10 Công cụ mới

| File | Việc |
|---|---|
| `deploy_to_ha.py` | Gate đầy đủ: ruff + format + mypy + pytest → backup → upload → xoá `__pycache__` → restart → chờ API sống lại |
| `verify_live.py` | Assert entity trên HA thật: sensor stats có số, điện áp pin không bị cộng, PV1 = GUID nhỏ, WiFi đúng nguồn |
| `tests/test_e2e.py` | Chạy `async_setup_entry` / `async_unload_entry` thật trên `HomeAssistant` core thật. **Không** dùng `pytest-homeassistant-custom-component` vì package đó import `fcntl` (chỉ POSIX) → không load được trên Windows |
| `.venv` | Python **3.14** — HA 2026.x yêu cầu `>= 3.14.2`, và bản HA trên PyPI chỉ có tới 2025.1 cho Python 3.12 |

#### 7.4.11 Đã fix trong v1.4.0

- **`sw_version` hiển thị sai "1.3.0"** → `sw_version` nay lấy từ `const.VERSION`
  (1.5.1), một nguồn sự thật duy nhất cùng `manifest.json` / `pyproject.toml`.

### 7.6 `async_set_updated_data` bóp chết HTTP poll (fix 2026-09-12)

**Triệu chứng:** recorder ghi ~2 lần/giây cho mỗi sensor smartsolar (1,740 lần/giờ trên một sensor, so với kỳ vọng ~720 khi `update_interval = 5s`). smartsolar chiếm **32% tổng số state** của toàn hệ thống.

**Nguyên nhân gốc [VERIFIED-HIGH]** — `coordinator.async_process_mqtt_data()` gọi `self.async_set_updated_data(self.data)` cho **mỗi message MQTT**:

```python
# coordinator.py (bản cũ) — dòng 70
if self.data is not None:
    self._merge_mqtt_into_data(self.data, device_guid, data)
    self.async_set_updated_data(self.data)   # <-- THỦ PHẠM
```

Đọc source HA (`helpers/update_coordinator.py`):

```python
def async_set_updated_data(self, data):
    """Manually update data, notify listeners and reset refresh interval."""
    self._async_unsub_refresh()        # <-- HUY timer poll
    self._debounced_refresh.async_cancel()
    self.data = data
    ...
    if self._listeners:
        self._schedule_refresh()       # <-- DAT LAI timer poll tu dau
    self.async_update_listeners()
```

`always_update=False` **không cứu được** — nó chỉ được kiểm tra trong `_async_refresh()` (đường poll định kỳ), còn `async_set_updated_data()` gọi thẳng `async_update_listeners()`.

**Hai hậu quả, không phải một:**

| Hậu quả | Bằng chứng |
|---|---|
| Recorder ghi ~2 state/s/sensor | 1,740 lần/giờ vs kỳ vọng 720 |
| **HTTP poll chết hoàn toàn** | Đo 40s: **0** poll bắt đầu, **0** kết thúc, **0** lỗi |

Thiết bị phát ~2 msg/s trong khi `update_interval = 5s` → timer bị reset trước khi kịp nổ → `_async_update_data()` không bao giờ chạy. Hệ quả phụ: `refresh_token_if_needed()` cũng không chạy, và API cloud chết sẽ **không** được phát hiện (vì `async_set_updated_data` đặt `last_update_success = True`).

**Cách đo** (bật debug runtime, không cần restart):
```python
POST /api/services/logger/set_level {"custom_components.smartsolar_mppt": "debug"}
# đếm trong log: "SmartSolar API Update Complete" (poll) vs
#                "Manually updated SmartSolar MPPT data" (MQTT notify)
```

**Fix:** thay `async_set_updated_data()` bằng `async_update_listeners()` trực tiếp, có throttle 1Hz bằng `async_call_later`. Giá trị vẫn merge vào `self.data` ở **mọi** message — chỉ nhịp *notify entity* bị chặn.

```python
@callback
def _schedule_mqtt_notify(self) -> None:
    if self._mqtt_notify_unsub is not None:
        return                      # dang trong cooldown 1s
    self.async_update_listeners()   # KHONG dung den timer poll
    self._mqtt_notify_unsub = async_call_later(
        self.hass, MQTT_NOTIFY_THROTTLE, self._async_mqtt_notify_done)
```

**Kết quả sau fix:**

| Chỉ số | Trước | Sau |
|---|---|---|
| HTTP poll / 40s | **0** | **7** (đúng nhịp 5s) |
| Token refresh | không chạy | ✅ `Token is still valid` |
| Lỗi API | không phát hiện được | 0 |
| HA container | — | CPU 1.56%, RAM 788 MB |

**⚠️ Bài học quan trọng — throttle KHÔNG giảm recorder:**

Số state ghi vẫn ~3,500/15 phút (26.6% tổng), **không đổi**. Lý do: giá trị **dao động thật** ~1 lần/giây, không phải nhiễu float.

```
pv2_pv_voltage (8 mẫu liên tiếp):
  26.09000015 / 26.13999939 / 26.09000015 / 26.18000031
  26.04999924 / 26.09000015 / 26.04999924 / 26.18000031
```

Đo `count(distinct state)` trong 15 phút: **10 giá trị khác nhau thật**; làm tròn 2 chữ số thập phân chỉ cắt được **15%**. Vì vậy **làm tròn `native_value` không phải đòn bẩy** cho bài toán này.

Nếu muốn giảm recorder thật sự, các lựa chọn còn lại là:
1. Nâng `update_interval` (number entity, 1–30s) — đánh đổi độ mịn dữ liệu.
2. `recorder.exclude` cho các sensor smartsolar ít giá trị.
3. Chấp nhận — 1.56% CPU không phải vấn đề hiệu năng.

**Thứ tự ưu tiên đã đúng:** sửa đường MQTT trước (nó là lỗi đúng/sai, không phải đánh đổi), rồi mới cân nhắc giảm tần suất (đánh đổi thật).

### 7.7 Bật/tắt DEBUG runtime — và cái bẫy khi đọc lại log

**Cách bật DEBUG không cần restart:**
```python
POST /api/services/logger/set_level
{"custom_components.smartsolar_mppt": "debug"}
```

Nhưng **cẩn thận khi diễn giải log sau đó:**

1. **Phải tắt lại bằng `warning`, không phải `info`** nếu config gốc không đặt gì cho component đó. Trong HA này config đặt `custom_components.smartsolar_mppt: info`, nên khi tắt phải trả về **`info`** cho khớp. Trả về `warning` là lệch config.

2. **Log DEBUG trong quá khứ không chứng minh config đang bật DEBUG.** Em đã suýt kết luận sai rằng "flood DEBUG là do integration". Thực tế: cửa sổ DEBUG 02:23:14–02:23:49 là **do chính probe của em bật**, không phải config.

   **Cách phân biệt:** đọc `configuration.yaml` phần `logger:` xem mức đặt cho component, rồi so với mốc thời gian. Nếu DEBUG chỉ xuất hiện trong một cửa sổ ngắn có mốc trùng với lúc chạy probe → đó là do probe.

   ```yaml
   logger:
     default: warning
     logs:
       custom_components.smartsolar_mppt: info   # <- muc THAT
   ```

3. **`docker logs` giữ log cũ hơn `home-assistant.log`** — HA 2026.x không ghi file log nữa (log ra stdout). Lấy bằng `sudo docker logs --tail N homeassistant`, lọc phía PC1. Endpoint `/api/error_log` **đã bị bỏ** (trả 404).

**Hệ quả phụ đáng chú ý:** đổi log level phát sự kiện `logging_changed`, và **ESPHome crash** khi nhận sự kiện đó:

```
ERROR (MainThread) [homeassistant.core] Error running job:
  <Job listen logging_changed ... ESPHomeManager._async_handle_logging_changed>
  File ".../components/esphome/manager.py", line 1083, in _async_handle_logging_changed
    self._async_subscribe_logs(new_log_level)
  File ".../components/esphome/manager.py", line 576, in _async_subscribe_logs
```

Đây là **bug HA core 2026.9.1**, không phải lỗi config — mỗi lần đổi log level (kể cả từ UI Developer Tools) đều sinh 1 ERROR. Không ảnh hưởng chức năng, nhưng làm bẩn log audit.

---

## 8. Hướng Dẫn Viết Lại

### 8.1 Những gì nên giữ

- **API client pattern:** Tách biệt API client (`api.py`) với HA-specific code
- **DataUpdateCoordinator pattern:** Tiêu chuẩn HA, hoạt động tốt
- **3 sensor classes:** Device / ProjectSynthesis / ProjectDevice — đúng kiến trúc
- **Config flow UI:** Multi-step flow dễ dùng cho người dùng
- **Shared `build_device_info`:** Tránh trùng lặp DeviceInfo
- **SENSOR_TYPES dict:** Định nghĩa tập trung, dễ mở rộng

### 8.2 Những gì nên cải thiện

1. **API client:**
   - Persist token (dùng `config_entry.data` hoặc `hass.helpers.storage`)
   - Thêm retry với exponential backoff
   - Xử lý rate limiting (nếu có)
   - Type hints đầy đủ hơn

2. **Coordinator:**
   - Thêm retry logic khi API fail
   - Xóa translation fetch khỏi hot path
   - Sort device GUIDs cố định (theo GUID numeric hoặc theo tên thiết bị)

3. **Sensors:**
   - Set `entity_id` hoặc `has_entity_name` + `suggested_object_id` để kiểm soát entity ID
   - Tránh prefix `technology_` từ HA
   - Thêm `extra_state_attributes` cho thông tin bổ sung
   - Cho phép user chọn PV label (PV1/PV2) dựa trên GUID

4. **Config flow:**
   - Thêm `async_migrate_entry` cho future version upgrades
   - Cho phép chọn thiết bị từ danh sách (fetch từ API thay vì nhập GUID)
   - Hiển thị tên thiết bị (deviceName) trong quá trình config
   - Cho phép đặt tên thiết bị (PV Chính / PV Phụ thay vì PV1/PV2)

5. **New features nên có:**
   - **Battery sensor:** Tổng hợp battery voltage/current từ JK BMS nếu có
   - **Load calculation:** Tự động tính tổng tải DC = MPPT + battery
   - **Energy statistics:** Tích hợp sẵn utility_meter (daily/monthly/yearly)
   - **Savings calculation:** Tích hợp giá bậc thang VN (có thể config)
   - **WebSocket push:** Nếu API hỗ trợ WebSocket thay vì polling 5s
   - **Diagnostics sensor:** API latency, error count, token expiry countdown

### 8.3 Code Quality Targets

```
Python: 3.14+
Home Assistant: 2026.9+
Dependencies: aiohttp (không thêm dependency nặng)
Test coverage: pytest + pytest-asyncio cho API client
Type hints: mypy strict
Linting: ruff
```

### 8.4 Tài liệu cần cập nhật khi release

- `README.md` — English, badges, install guide
- `README.vi.md` — Tiếng Việt cho người dùng VN
- `CLAUDE.md` — cho AI agents
- `KNOWLEDGE.md` — file này, cập nhật theo version mới
- Wiki pages trên GitHub (nếu có)

---

## Appendix A: File Manifest

### Trong `D:\Code\SmartSolar\` (repo riêng, tách khỏi HA-Config 2026-09-27)
| File | Purpose |
|------|---------|
| `CLAUDE.md` | Hướng dẫn cho AI agents |
| `README.md` | README chuyên nghiệp |
| `KNOWLEDGE.md` | File này — kiến thức tổng hợp |
| `logo.png` | Logo integration |
| `pyproject.toml` | Cấu hình ruff / mypy / pytest + extra `[test]` (ghim `homeassistant`) |
| `deploy_to_ha.py` | **Deploy có gate**: ruff + format + mypy + pytest → backup → upload → restart → chờ API |
| `verify_live.py` | Assert entity trên HA thật sau deploy |
| `upload_to_ha.py` | Uploader tối giản (không gate) |
| `tests/` | 261 test, gồm `test_e2e.py` chạy entry thật trên HA core thật |
| `_local_archive/deployed/` | Backup bản đã deploy trên HA (local-only, gitignored) |
| `.venv/` | Python 3.14 — HA 2026.x yêu cầu `>= 3.14.2` |

> `SESSION.md`, `Home.md`, `AGENTS.md` đã được gộp vào file này và xoá (2026-09-11).

### Trong `D:\Code\HA-Config\packages\`
| File | Purpose |
|------|---------|
| `30_solar_24v_energy_stats.yaml` | Backend: template + integration + utility_meter |
| `dashboard_solar_24v.md` | Dashboard Lovelace YAML + entity reference |
| `30_nhietdo_doam_nguyhiem.yaml` | Temperature alerts (references SmartSolar temp) |
| `HA_info.txt` | Credentials (HA token, IP, SMB) |

### Trên HA server
| Path | Purpose |
|------|---------|
| `/config/custom_components/smartsolar_mppt/` | Integration code |
| `/config/packages/30_solar_24v_energy_stats.yaml` | Energy stats package |
| `/config/.storage/core.config_entries` | Config entry data |
| `/config/.storage/core.entity_registry` | Entity registry |
| `/config/.storage/lovelace.lovelace` | Dashboard JSON |

---

## Appendix B: Deploy Pipeline

### Deploy Python code lên HA
```python
import os
import paramiko, base64

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.10.15', username='vokupt', password=os.environ['HA_PASS'])

# Encode file → base64 → echo lên server → decode → write
with open('file.py', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()

client.exec_command(f'echo "{b64}" > /tmp/file.b64')

decode_script = '''
import base64
data = base64.b64decode(open("/tmp/file.b64").read()).decode()
open("/config/custom_components/smartsolar_mppt/file.py", "w").write(data)
'''
b64_script = base64.b64encode(decode_script.encode()).decode()
client.exec_command(f'echo "{b64_script}" > /tmp/decode.b64 && base64 -d /tmp/decode.b64 > /tmp/decode.py && sudo /usr/bin/python3 /tmp/decode.py')

# Cleanup & restart
client.exec_command('sudo rm -rf /config/custom_components/smartsolar_mppt/__pycache__')
client.exec_command('sudo docker restart homeassistant')
```

### Deploy YAML packages lên HA (qua SMB)
```powershell
# Mount SMB
net use Z: \\192.168.10.15\config /user:vokupt %HA_PASS%
# Copy
copy "D:\Code\HA-Config\packages\30_solar_24v_energy_stats.yaml" "Z:\packages\"
# Restart HA
curl -X POST -H "Authorization: Bearer <token>" http://192.168.10.15:8123/api/services/homeassistant/restart
```

### Kiểm tra config entry (khi data bị mất)
```bash
ssh vokupt@192.168.10.15
sudo cat /config/.storage/core.config_entries | python3 -m json.tool
# Tìm entry với domain=smartsolar_mppt
# Sửa nếu thiếu field: dùng Python json.load() → sửa → json.dump()
```

---

## Appendix C: Related Projects & Dependencies

| Project | Path | Relation |
|---------|------|----------|
| HA Config | `D:\Code\HA-Config\` | Chứa packages dùng SmartSolar entities |
| System Info | `D:\Code\System_info\` | Credentials, network topology |
| Shared Scripts | `D:\Code\scripts\` | `vm_inventory.py`, `vm-config.sh` |
| Lumentree | `D:\Code\Lumentree\` | Inverter cũ (đã thay bằng Luxpower) |
| MikroTik HA | HACS `tomaae/homeassistant-mikrotik_router` | Router monitoring integration (fork ngoviet/mikrotik-ha đã xoá 2026-09-11) |

---

*Last updated: 2026-09-27 — audit v1.5.1 (12 bug đã sửa, 261 test, deploy + verify live).*
*v2.0.0 (2026-09-27): đổi domain sang `smartsolar_ha`, 13 bug thật đã sửa kèm test hồi quy — 366 test. Xem `CLAUDE.md` mục "v2.0.0 — Domain Rename + Audit Fixes".*
