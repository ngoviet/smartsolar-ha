# Ý tưởng tạo Dashboard đẹp

## Dashboard cơ bản

### Card năng lượng mặt trời

```yaml
type: vertical-stack
cards:
  - type: gauge
    entity: sensor.charge_power
    name: "Công suất sạc"
    unit: W
    min: 0
    max: 1000
    severity:
      green: 0
      yellow: 500
      red: 800
  - type: entities
    title: "Thông tin PV"
    entities:
      - sensor.pv_voltage
      - sensor.pv_current
  - type: entities
    title: "Thông tin Ắc quy"
    entities:
      - sensor.battery_voltage
      - sensor.battery_current
```

### Card điện năng hôm nay

```yaml
type: statistics-graph
entity: sensor.today_kwh
name: "Điện năng hôm nay"
hours_to_show: 24
refresh_interval: 300
```

## Dashboard nâng cao

### Card tổng quan hệ thống

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      # 🌞 Hệ thống năng lượng mặt trời
      **Trạng thái:** {{ states('sensor.status') }}
      **Nhiệt độ:** {{ states('sensor.temperature') }}°C
  - type: horizontal-stack
    cards:
      - type: gauge
        entity: sensor.charge_power
        name: "Công suất"
        unit: W
      - type: gauge
        entity: sensor.battery_voltage
        name: "Điện áp ắc quy"
        unit: V
      - type: gauge
        entity: sensor.pv_voltage
        name: "Điện áp PV"
        unit: V
```

### Card biểu đồ năng lượng

```yaml
type: history-graph
entities:
  - sensor.charge_power
  - sensor.today_kwh
hours_to_show: 12
refresh_interval: 60
```

## Dashboard cho nhiều thiết bị

### Card tổng hợp Project

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      # 🏠 Tổng quan năng lượng mặt trời
      **Tổng công suất:** {{ states('sensor.charge_power') }}W
      **Điện năng hôm nay:** {{ states('sensor.today_kwh') }}kWh
  - type: entities
    title: "Thiết bị 1"
    entities:
      - sensor.pv_voltage_14756976
      - sensor.battery_voltage_14756976
      - sensor.charge_power_14756976
  - type: entities
    title: "Thiết bị 2"
    entities:
      - sensor.pv_voltage_547611
      - sensor.battery_voltage_547611
      - sensor.charge_power_547611
```

## Dashboard tự động

### Card thông báo thông minh

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.charge_power
    above: 500
card:
  type: markdown
  content: |
    # ⚡ Sạc mạnh!
    Hệ thống đang sạc với công suất cao: {{ states('sensor.charge_power') }}W
```

### Card cảnh báo nhiệt độ

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.temperature
    above: 50
card:
  type: markdown
  content: |
    # 🔥 Cảnh báo nhiệt độ cao!
    Nhiệt độ: {{ states('sensor.temperature') }}°C
    Cần kiểm tra hệ thống tản nhiệt
```

## Template Sensors hữu ích

### Tính hiệu suất sạc

```yaml
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

### Tính thời gian sạc ước tính

```yaml
template:
  - sensor:
      - name: "Estimated Charge Time"
        unit_of_measurement: "giờ"
        state: >
          {% set battery_capacity = 100 %}  # Ah
          {% set current = states('sensor.battery_current') | float %}
          {% if current > 0 %}
            {{ (battery_capacity / current) | round(1) }}
          {% else %}
            0
          {% endif %}
```

## Themes đẹp

### Theme năng lượng mặt trời

```yaml
# themes/solar.yaml
solar_theme:
  primary-color: "#FFA726"  # Cam năng lượng
  accent-color: "#FFC107"   # Vàng
  background-color: "#FFF3E0"  # Nền sáng
  card-background-color: "#FFFFFF"
  text-primary-color: "#E65100"
```

### Theme tối cho màn hình

```yaml
# themes/solar_dark.yaml
solar_dark_theme:
  primary-color: "#FFB74D"
  accent-color: "#FFD54F"
  background-color: "#1A1A1A"
  card-background-color: "#2D2D2D"
  text-primary-color: "#FFFFFF"
```

## Automation hữu ích

### Thông báo khi sạc đầy

```yaml
automation:
  - alias: "Battery Full Notification"
    trigger:
      - platform: numeric_state
        entity_id: sensor.battery_voltage
        above: 13.8
    condition:
      - condition: state
        entity_id: sensor.status
        state: "1"  # Đang sạc
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🔋 Pin đã sạc đầy!"
          message: "Điện áp: {{ states('sensor.battery_voltage') }}V"
```

### Tắt thiết bị khi trời tối

```yaml
automation:
  - alias: "Turn off when dark"
    trigger:
      - platform: numeric_state
        entity_id: sensor.pv_voltage
        below: 5
    condition:
      - condition: time
        after: "18:00:00"
    action:
      - service: switch.turn_off
        entity_id: switch.some_device
```

## Tips tạo dashboard đẹp

### Sử dụng màu sắc phù hợp
- **Xanh lá**: Năng lượng sạch
- **Cam/Vàng**: Năng lượng mặt trời
- **Xanh dương**: Nước, mát mẻ
- **Đỏ**: Cảnh báo, nhiệt độ cao

### Bố cục hợp lý
- Thông tin quan trọng ở trên
- Biểu đồ ở giữa
- Chi tiết ở dưới
- Sử dụng cards nhóm

### Responsive design
- Test trên mobile
- Sử dụng horizontal-stack
- Tránh cards quá rộng

### Performance
- Không refresh quá thường xuyên
- Sử dụng history-graph thay vì real-time
- Cache dữ liệu khi có thể
