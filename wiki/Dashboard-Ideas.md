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

### Card nâng cao với Custom Components

Card này sử dụng các custom components để tạo giao diện chuyên nghiệp:

```yaml
type: custom:stack-in-card
mode: vertical
gap: 0
cards:
  - type: custom:button-card
    template: pv_progress_dyn
    entity: sensor.charge_power
    variables:
      design_w: 1400
      over_pct: 120
      color_cur: "#43A047"
      color_base: "#FFC107"
      color_over: "#D32F2F"
  - type: custom:mini-graph-card
    name: Công suất PV 24V – 48h
    entities:
      - entity: sensor.charge_power
        name: Sạc/Xả
    hours_to_show: 24
    points_per_hour: 12
    aggregate_func: avg
    line_width: 2
    height: 120
    color_thresholds:
      - value: 0
        color: "#40A96B"
      - value: 400
        color: "#12FF76"
    show:
      extrema: true
      average: false
      legend: false
      labels: true
    style: |
      ha-card {
        --primary-text-color: #8a8d93;
        border-radius: 10px;
      }
    lower_bound: 0
    upper_bound: 1400
  - type: custom:stack-in-card
    cards:
      - type: custom:mushroom-chips-card
        alignment: justify
        card_mod:
          style: |
            ha-card{
              background: transparent !important;
              box-shadow: none !important;
              --chip-height: 22px; --chip-icon-size: 18px; --chip-font-size: 12px;
              --chip-spacing: 8px; --chip-border-radius: 10px;
              padding: 2px 4px;
            }
        chips:
          - type: template
            icon: mdi:label-variant
            icon_color: grey
            content: PV (24V)
          - type: template
            entity: sensor.charge_power
            icon: mdi:solar-power
            icon_color: >
              {% set p = states('sensor.charge_power')|float(0) %} {{ 'amber' if
              p>0 else 'grey' }}
            content: PV {{ (states('sensor.charge_power')|float(0))|round(0) }} W
            tap_action:
              action: more-info
          - type: template
            entity: sensor.pv_voltage
            icon: mdi:current-ac
            icon_color: >
              {% set v = states('sensor.pv_voltage')|float(0) %} {{ 'blue' if
              v>0 else 'grey' }}
            content: V {{ (states('sensor.pv_voltage')|float(0))|round(1) }} V
            tap_action:
              action: more-info
          - type: template
            entity: sensor.pv_current
            icon: mdi:current-dc
            icon_color: >
              {% set i = states('sensor.pv_current')|float(0) %} {{ 'teal' if
              i>0 else 'grey' }}
            content: "{{ (states('sensor.pv_current')|float(0))|round(1) }} A"
            tap_action:
              action: more-info
      - type: custom:mushroom-chips-card
        alignment: justify
        card_mod:
          style: |
            ha-card{
              background: transparent !important;
              box-shadow: none !important;
              --chip-height: 22px; --chip-icon-size: 18px; --chip-font-size: 12px;
              --chip-spacing: 8px; --chip-border-radius: 10px;
              padding: 2px 4px;
            }
        chips:
          - type: template
            icon: mdi:label-variant
            icon_color: grey
            content: Battery (24V)
          - type: template
            entity: sensor.battery_voltage
            icon: mdi:battery
            icon_color: indigo
            content: V {{ (states('sensor.battery_voltage')|float(0))|round(2) }} V
            tap_action:
              action: more-info
          - type: template
            entity: sensor.battery_current
            icon: mdi:current-dc
            icon_color: >
              {% set bi = states('sensor.battery_current')|float(0) %} {{
              'green' if bi<0 else ('orange' if bi>0 else 'grey') }}
            content: "{{ (states('sensor.battery_current')|float(0))|round(1) }} A"
            tap_action:
              action: more-info
      - type: custom:mushroom-chips-card
        alignment: justify
        card_mod:
          style: |
            ha-card{
              background: transparent !important;
              box-shadow: none !important;
              --chip-height: 22px; --chip-icon-size: 18px; --chip-font-size: 12px;
              --chip-spacing: 8px; --chip-border-radius: 10px;
              padding: 2px 4px;
            }
        chips:
          - type: template
            icon: mdi:label-variant
            icon_color: grey
            content: Energy
          - type: template
            entity: sensor.today_kwh
            icon: mdi:counter
            icon_color: amber
            content: Today {{ (states('sensor.today_kwh')|float(0))|round(2) }} kWh
            tap_action:
              action: more-info
          - type: template
            entity: sensor.total_kwh
            icon: mdi:chart-line
            icon_color: blue
            content: Total {{ (states('sensor.total_kwh')|float(0))|round(1) }} kWh
            tap_action:
              action: more-info
      - type: custom:mushroom-chips-card
        alignment: justify
        card_mod:
          style: |
            ha-card{
              background: transparent !important;
              box-shadow: none !important;
              --chip-height: 22px; --chip-icon-size: 18px; --chip-font-size: 12px;
              --chip-spacing: 8px; --chip-border-radius: 10px;
              padding: 2px 4px;
            }
        chips:
          - type: template
            icon: mdi:label-variant
            icon_color: grey
            content: Status
          - type: template
            entity: sensor.temperature
            icon: mdi:thermometer
            icon_color: >
              {% set t = states('sensor.temperature')|float(0) %} {{ 'green' if
              t<40 else ('amber' if t<55 else 'red') }}
            content: Temp {{ (states('sensor.temperature')|float(0))|round(1) }} °C
            tap_action:
              action: more-info
    card_mod:
      style: >
        ha-card { background: transparent !important; box-shadow: none
        !important; }
```

**Yêu cầu Custom Components:**
- `custom:stack-in-card` - Tạo layout linh hoạt
- `custom:button-card` - Card nút tùy chỉnh
- `custom:mini-graph-card` - Biểu đồ mini
- `custom:mushroom-chips-card` - Chips hiển thị thông tin
- `card-mod` - Tùy chỉnh CSS

**Tính năng nổi bật:**
- **Progress bar** động cho công suất sạc
- **Biểu đồ** 24h với màu sắc thông minh
- **Chips** hiển thị thông tin chi tiết
- **Màu sắc** thay đổi theo giá trị
- **Tap action** để xem thông tin chi tiết

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
