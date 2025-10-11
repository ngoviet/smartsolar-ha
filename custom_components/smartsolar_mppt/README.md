# SmartSolar HA Integration cho Home Assistant

Tích hợp thiết bị SmartSolar vào Home Assistant thông qua HACS.

## Tính năng

- ✅ **Tự động refresh API token** - Token được làm mới tự động 7 ngày trước khi hết hạn
- ✅ **Hỗ trợ nhiều chế độ** - Device mode (1 thiết bị) và Project mode (nhiều thiết bị)
- ✅ **Hỗ trợ nhiều loại thiết bị** - Inverter Sun-GTIL2 và Sạc Mạnh Quân
- ✅ **Nhiều integration instances** - Có thể tạo nhiều integration cho cùng 1 user
- ✅ **Giao diện tiếng Việt** - UI hoàn toàn bằng tiếng Việt
- ✅ **8 loại sensors** - Điện áp, dòng điện, công suất, năng lượng, nhiệt độ

## Cài đặt

### Qua HACS (Khuyến nghị)

1. Mở HACS trong Home Assistant
2. Vào **Integrations** → **Custom repositories**
3. Thêm repository: `https://github.com/ngoviet/smartsolar-ha`
4. Chọn category: **Integration**
5. Cài đặt và restart Home Assistant

### Cài đặt thủ công

1. Tải về integration
2. Copy thư mục `smartsolar_mppt` vào `custom_components/`
3. Restart Home Assistant

## Cấu hình

1. Vào **Settings** → **Devices & Services** → **Add Integration**
2. Tìm kiếm "SmartSolar HA"
3. Nhập thông tin đăng nhập SmartSolar
4. Chọn chế độ tích hợp:
   - **Device**: Tích hợp 1 thiết bị
   - **Project**: Tích hợp nhiều thiết bị trong 1 dự án
5. Chọn loại thiết bị:
   - **Inverter Sun-GTIL2** (deviceType=1)
   - **Sạc Mạnh Quân** (deviceType=2)
6. Nhập ChipsetId:
   - **Device mode**: Nhập 1 ChipsetId
   - **Project mode**: Nhập nhiều ChipsetId, phân cách bằng dấu phẩy

## Sensors

### Device Mode
Tạo 8 sensors cho thiết bị được chọn:

| Sensor | Đơn vị | Mô tả |
|--------|--------|-------|
| PV Voltage | V | Điện áp tấm pin mặt trời |
| PV Current | A | Dòng điện tấm pin mặt trời |
| Battery Voltage | V | Điện áp pin |
| Battery Current | A | Dòng điện pin |
| Charge Power | W | Công suất sạc |
| Today Energy | kWh | Năng lượng sản xuất hôm nay |
| Total Energy | kWh | Tổng năng lượng sản xuất |
| Temperature | °C | Nhiệt độ thiết bị |

### Project Mode
Tạo 8 synthesis sensors (tổng hợp) + N sensors cho từng thiết bị:

- **Synthesis sensors**: Dữ liệu tổng hợp của toàn bộ dự án
- **Device sensors**: Dữ liệu riêng của từng thiết bị (có tên kèm ChipsetId)

## Services

### `smartsolar_mppt.refresh_token`

Làm mới API token thủ công.

**Service data:**
```yaml
entry_id: "config_entry_id"
```

## Troubleshooting

### Lỗi "Cannot connect"
- Kiểm tra kết nối internet
- Kiểm tra thông tin đăng nhập SmartSolar
- Kiểm tra API SmartSolar có hoạt động không

### Lỗi "Device not found"
- Kiểm tra ChipsetId có đúng không
- Đảm bảo thiết bị thuộc về tài khoản của bạn
- Kiểm tra loại thiết bị (deviceType) có đúng không

### Sensors không cập nhật
- Kiểm tra logs Home Assistant
- Thử restart integration
- Kiểm tra token có hết hạn không

## Logs

Để xem logs chi tiết, thêm vào `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.smartsolar_mppt: debug
```

## API Reference

### Endpoints
- **Login**: `POST https://api.smartsolar.io.vn/Account/Login`
- **Metrics**: `GET https://api.smartsolar.io.vn/Metric/SynthesisMetrics`

### Authentication
- Sử dụng Bearer token từ login endpoint
- Token hết hạn sau 30 ngày
- Tự động refresh 7 ngày trước khi hết hạn

## Hỗ trợ

- **Issues**: [GitHub Issues](https://github.com/ngoviet/smartsolar-ha/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ngoviet/smartsolar-ha/discussions)

## License

MIT License - Xem file [LICENSE](LICENSE) để biết thêm chi tiết.

## Brand Icons

Integration này bao gồm các brand icons chính thức:

- **icon.png** (256x256): Icon vuông cho integration
- **logo.png** (512x512): Logo brand cho SmartSolar

Icons được tối ưu hóa cho Home Assistant và tuân thủ chuẩn brand registry.

## Changelog

### v1.0.0
- Phiên bản đầu tiên
- Hỗ trợ Device và Project mode
- Hỗ trợ Sạc MPPT (GTIL Mạnh Quân) và Grid tie inverter (Sun GTIL2)
- Auto-refresh token
- Giao diện tiếng Việt
- 8 loại sensors đầy đủ
- Brand icons chính thức (icon.png, logo.png)
- Sẵn sàng mở rộng cho các loại thiết bị khác
