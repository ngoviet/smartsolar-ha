# Danh sách Sensors

## Sensors thời gian thực

### PV (Tấm pin mặt trời)

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| **PV Voltage** | V | Điện áp từ tấm pin mặt trời |
| **PV Current** | A | Dòng điện từ tấm pin mặt trời |

### Battery (Ắc quy)

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| **Battery Voltage** | V | Điện áp ắc quy |
| **Battery Current** | A | Dòng điện sạc vào ắc quy |

### Power (Công suất)

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| **Charge Power** | W | Công suất sạc hiện tại |

### Energy (Điện năng)

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| **Today kWh** | kWh | Điện năng sản xuất hôm nay |
| **Total kWh** | kWh | Tổng điện năng sản xuất |

### System (Hệ thống)

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| **Temperature** | °C | Nhiệt độ thiết bị |
| **Status** | - | Trạng thái hoạt động |

## Number Entity

### Update Interval

| Thuộc tính | Giá trị | Mô tả |
|------------|---------|-------|
| **Min Value** | 1 | Tần suất tối thiểu (giây) |
| **Max Value** | 30 | Tần suất tối đa (giây) |
| **Step** | 1 | Bước nhảy |
| **Unit** | giây | Đơn vị |

## Trạng thái Status

| Giá trị | Ý nghĩa |
|---------|---------|
| **0** | Đang online |
| **1** | Đang sạc |
| **2** | Dừng sạc, trời hết nắng |
| **3** | Lỗi |

## Cách sử dụng Sensors

### Thêm vào Dashboard

1. Vào **Settings** → **Dashboards**
2. Chọn dashboard muốn chỉnh sửa
3. Click **Add Card**
4. Chọn **Entities**
5. Thêm sensors cần thiết

### Tạo Automation

```yaml
# Ví dụ: Thông báo khi sạc đầy
automation:
  - alias: "Battery Full Notification"
    trigger:
      - platform: numeric_state
        entity_id: sensor.battery_voltage
        above: 13.8  # Điện áp sạc đầy
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Pin đã sạc đầy! 🔋"
```

### Tạo Template Sensors

```yaml
# Ví dụ: Tính hiệu suất sạc
template:
  - sensor:
      - name: "Solar Efficiency"
        unit_of_measurement: "%"
        state: >
          {% set pv_power = states('sensor.pv_voltage') | float * states('sensor.pv_current') | float %}
          {% set charge_power = states('sensor.charge_power') | float %}
          {% if pv_power > 0 %}
            {{ (charge_power / pv_power * 100) | round(1) }}
          {% else %}
            0
          {% endif %}
```

## Lưu ý quan trọng

### Độ chính xác
- Dữ liệu lấy trực tiếp từ SmartSolar API
- Cập nhật theo tần suất đã cấu hình
- Có thể có độ trễ 1-2 giây

### Xử lý lỗi
- Giá trị "Unknown" = không có dữ liệu
- Kiểm tra kết nối API nếu lỗi liên tục
- Restart integration nếu cần

### Tối ưu hiệu suất
- Không cần thiết phải thêm tất cả sensors
- Chỉ thêm những gì cần thiết
- Sử dụng Project Mode cho nhiều thiết bị
