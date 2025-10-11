# SmartSolar MPPT Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![GitHub stars](https://img.shields.io/github/stars/ngoviet/smartsolar-ha.svg?style=social&label=Star)](https://github.com/ngoviet/smartsolar-ha)

Tích hợp thiết bị SmartSolar MPPT vào Home Assistant với giao diện tiếng Việt hoàn chỉnh.

## ✨ Tính năng

- ✅ **Hỗ trợ Sạc MPPT Mạnh Quân** - Tích hợp thiết bị sạc MPPT
- ✅ **2 chế độ tích hợp** - Device (đơn lẻ) và Project (nhiều thiết bị)
- ✅ **Giao diện tiếng Việt** - Hoàn toàn localized
- ✅ **Tự động refresh token** - API key tự động gia hạn
- ✅ **Cấu hình linh hoạt** - Tần suất cập nhật có thể điều chỉnh
- ✅ **Sensors đầy đủ** - Điện áp, dòng điện, công suất, nhiệt độ, năng lượng
- ✅ **Number entity** - Điều chỉnh tần suất cập nhật trực tiếp trong UI

## 📊 Sensors

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| `pv_voltage` | V | Điện áp PV |
| `pv_current` | A | Dòng điện PV |
| `bat_voltage` | V | Điện áp Pin |
| `bat_current` | A | Dòng điện Pin |
| `charge_power` | W | Công suất sạc |
| `today_kwh` | kWh | Năng lượng hôm nay |
| `total_kwh` | kWh | Tổng năng lượng |
| `temperature` | °C | Nhiệt độ |
| `status` | - | Trạng thái thiết bị |

## 🚀 Cài đặt

### HACS (Khuyến nghị)

1. Mở **HACS** trong Home Assistant
2. Vào **Integrations**
3. Click **⋮** → **Custom repositories**
4. Thêm repository: `https://github.com/ngoviet/smartsolar-ha`
5. Chọn **Integration** làm category
6. Tìm **SmartSolar MPPT** và cài đặt
7. Restart Home Assistant

### Thủ công

1. Download và giải nén [latest release](https://github.com/ngoviet/smartsolar-ha/releases)
2. Copy thư mục `custom_components/smartsolar_mppt` vào `/config/custom_components/`
3. Restart Home Assistant

## ⚙️ Cấu hình

### Bước 1: Thêm Integration

1. Vào **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Tìm **SmartSolar MPPT**
4. Nhập thông tin đăng nhập SmartSolar

### Bước 2: Chọn chế độ tích hợp

#### **Device Mode** (Thiết bị đơn lẻ)
- Xem dữ liệu từ một thiết bị đơn lẻ
- Nhập ChipsetId của thiết bị

#### **Project Mode** (Dự án)
- Tổng hợp dữ liệu từ nhiều thiết bị trong một nơi
- Nhập số lượng và ID của các thiết bị Sạc MPPT Mạnh Quân

### Bước 3: Cấu hình tần suất cập nhật

Sau khi cài đặt, bạn sẽ thấy entity **"Tần suất cập nhật"** trong Controls:
- Click vào entity này để thay đổi tần suất cập nhật
- Giá trị từ 1-30 giây
- Thay đổi có hiệu lực ngay lập tức

## 🔧 Cấu hình nâng cao

### Environment Variables

```yaml
# configuration.yaml
smartsolar_mppt:
  username: !secret smartsolar_username
  password: !secret smartsolar_password
```

### Services

#### `smartsolar_mppt.refresh_token`

Làm mới API token thủ công.

```yaml
service: smartsolar_mppt.refresh_token
data:
  entry_id: "your_entry_id"
```

## 📱 Giao diện

### Device Mode
```
SmartSolar MPPT Device
├── Controls
│   └── Tần suất cập nhật (5 giây)
└── Sensors
    ├── Điện áp PV (59 V)
    ├── Dòng điện PV (4.96 A)
    ├── Điện áp Pin (28 V)
    ├── Dòng điện Pin (9.66 A)
    ├── Công suất sạc (295 W)
    ├── Năng lượng hôm nay (2.11 kWh)
    ├── Tổng năng lượng (345.85 kWh)
    ├── Nhiệt độ (31.0 °C)
    └── Trạng thái (0.0)
```

### Project Mode
```
SmartSolar MPPT Project (3 devices)
├── Controls
│   └── Tần suất cập nhật (30 giây)
└── Sensors
    └── [Tương tự Device Mode cho mỗi thiết bị]
```

## 🌐 Hỗ trợ đa ngôn ngữ

- ✅ **Tiếng Việt** - Hoàn chỉnh
- ✅ **English** - Cơ bản

## 🔗 Liên kết

- **SmartSolar Website**: [https://smartsolar.io.vn/](https://smartsolar.io.vn/)
- **Đăng ký tài khoản**: [https://smartsolar.io.vn/](https://smartsolar.io.vn/)
- **GitHub Issues**: [https://github.com/ngoviet/smartsolar-ha/issues](https://github.com/ngoviet/smartsolar-ha/issues)
- **GitHub Discussions**: [https://github.com/ngoviet/smartsolar-ha/discussions](https://github.com/ngoviet/smartsolar-ha/discussions)

## 📄 License

MIT License - Xem [LICENSE](LICENSE) để biết thêm chi tiết.

## 👨‍💻 Tác giả

**@ngoviet** - [GitHub](https://github.com/ngoviet)

## 🙏 Cảm ơn

- SmartSolar team cho API tuyệt vời
- Home Assistant community cho sự hỗ trợ
- HACS team cho platform tuyệt vời

---

**⭐ Nếu bạn thích integration này, hãy cho một star trên GitHub!**
