# SmartSolar MPPT MQ — Toàn Bộ Kiến Thức API & Tích Hợp

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

### Data Stream Field Names (9 loại sensor)

| API Field | Unit | Description | Device Class |
|-----------|------|-------------|-------------|
| `pv_voltage` | V | Điện áp tấm pin | `voltage` |
| `pv_current` | A | Dòng điện tấm pin | `current` |
| `bat_voltage` | V | Điện áp battery/ắc quy | `voltage` |
| `bat_current` | A | Dòng sạc vào battery | `current` |
| `charge_power` | W | Công suất sạc hiện tại | `power` |
| `today_kwh` | kWh | Năng lượng hôm nay | `energy` (total_increasing) |
| `total_kwh` | kWh | Tổng năng lượng tích lũy | `energy` (total_increasing) |
| `temperature` | °C | Nhiệt độ controller | `temperature` |
| `status` | — | Trạng thái (0-3) | — |

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
| HA Version | 2026.5.0 (Docker) |
| SSH | `vokupt@192.168.10.15` / `qweszxc12` |
| HA Token (long-lived) | Trong `HA_info.txt` |
| SMB Config | `\\192.168.10.15\config\` (user: vokupt) |
| SMB packages | `\\192.168.10.15\config\packages\` |
| SMB Frigate addon | `\\192.168.10.15\addon_configs\ccab4aaf_frigate\` |
| HA restart API | `POST /api/services/homeassistant/restart` |
| HA reload YAML | `POST /api/services/homeassistant/reload_all` (LƯU Ý: không reload được utility_meter) |

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

### 4.5 Tất Cả Entity Hiện Tại (29 entities)

#### Synthesis (Tổng) — 9 sensors
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
```

#### PV1 (GUID=547611) — 9 sensors
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
```

#### PV2 (GUID=14756976) — 9 sensors
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
```

#### Khác — 2 entities
```
number.smartsolar_mppt_project_update_frequency   ← Update Frequency (1-30s)
update.smartsolar_mppt_update                     ← HACS update entity
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

### 7.3 Lỗi đã fix (từ SESSION.md)

Xem `SESSION.md` sections "Đã fix trong v1.2.0" và "Nhật ký công việc" để biết chi tiết các bug đã sửa:
- Platform setup order (data trước khi setup sensor)
- Config entry data loss
- `__del__` unsafe, `assert` trong production, `FlowResult` deprecated
- Debug log noise, entity rác trong registry
- Entity naming dùng GUID → đổi sang PV1/PV2

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
Python: 3.12+
Home Assistant: 2024.1+
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

### Trong `D:\Code\SmartSolar\`
| File | Purpose |
|------|---------|
| `CLAUDE.md` | Hướng dẫn cho AI agents |
| `SESSION.md` | Nhật ký phát triển (2026-04-30) |
| `README.md` | README chuyên nghiệp |
| `KNOWLEDGE.md` | File này — kiến thức tổng hợp |
| `Home.md` | GitHub Wiki home |
| `logo.png` | Logo integration |

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
import paramiko, base64

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.10.15', username='vokupt', password='qweszxc12')

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
net use Z: \\192.168.10.15\config /user:vokupt qweszxc12
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
| MikroTik HA | `D:\Code\mikrotik-ha\` | Router monitoring integration |

---

*Last updated: 2026-06-22 — Compiled từ code, SESSION.md, HA packages, và CDP API discovery.*
