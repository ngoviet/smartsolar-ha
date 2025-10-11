# SmartSolar MPPT

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![maintenance](https://img.shields.io/badge/maintained%20by-ngoviet-blue.svg)](https://github.com/ngoviet)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![GitHub stars](https://img.shields.io/github/stars/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/stargazers)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar-ha&category=integration)

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar-ha&category=integration" target="_blank">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.">
</a>

Mở Home Assistant của bạn và mở repository trong Home Assistant Community Store.

Tích hợp Home Assistant cho thiết bị SmartSolar MPPT với giám sát thời gian thực qua API và hỗ trợ cả chế độ Device và Project.

![SmartSolar MPPT Dashboard](https://via.placeholder.com/800x400/2E7D32/FFFFFF?text=SmartSolar+MPPT+Dashboard)

## Tính năng

* **Giám sát thời gian thực** qua API SmartSolar
* **Hỗ trợ 2 chế độ tích hợp**:
  * **Device Mode**: Xem dữ liệu từ một thiết bị đơn lẻ
  * **Project Mode**: Tổng hợp dữ liệu từ nhiều thiết bị trong một nơi
* **Hỗ trợ sensor toàn diện** cho:
  * **Điện áp PV** (PV Voltage)
  * **Dòng điện PV** (PV Current) 
  * **Điện áp ắc quy** (Battery Voltage)
  * **Dòng điện ắc quy** (Battery Current)
  * **Công suất sạc** (Charge Power)
  * **Điện năng hôm nay** (Today kWh)
  * **Tổng điện năng** (Total kWh)
  * **Nhiệt độ** (Temperature)
  * **Trạng thái** (Status)
* **Tự động làm mới token** API (refresh 7 ngày trước khi hết hạn)
* **Khoảng thời gian cập nhật có thể cấu hình** (1-30 giây)
* **Giao diện tiếng Việt** và tiếng Anh
* **Xử lý lỗi mạnh mẽ** và logic kết nối lại

![SmartSolar MPPT Sensors](https://via.placeholder.com/800x400/1976D2/FFFFFF?text=SmartSolar+MPPT+Sensors)

## Thiết bị được hỗ trợ

* **Sạc MPPT Mạnh Quân** (Primary support)
* **Các thiết bị SmartSolar khác** (Tương thích)

## Cài đặt

### HACS (Khuyến nghị)

Mở Home Assistant của bạn và mở repository trong Home Assistant Community Store.

1. Mở **HACS** trong Home Assistant
2. Vào **Integrations**
3. Click **ba chấm** (⋮) ở góc trên bên phải
4. Chọn **Custom repositories**
5. Thêm repository này:
   * **Repository**: `https://github.com/ngoviet/smartsolar-ha`
   * **Category**: `Integration`
6. Click **Add**
7. Tìm kiếm **"SmartSolar MPPT"** và cài đặt
8. Khởi động lại Home Assistant
9. Thêm integration qua **Configuration** → **Integrations**

### Cài đặt thủ công

1. Tải phiên bản mới nhất từ GitHub
2. Copy thư mục `custom_components/smartsolar_mppt` vào thư mục `custom_components/` của Home Assistant
3. Khởi động lại Home Assistant
4. Thêm integration qua **Configuration** → **Integrations**

## Cấu hình

### Thêm Integration

1. Vào **Configuration** → **Integrations**
2. Click **Add Integration**
3. Tìm kiếm **"SmartSolar MPPT"**
4. Nhập thông tin đăng nhập:
   * **Tên đăng nhập**: Username SmartSolar của bạn
   * **Mật khẩu**: Password SmartSolar của bạn
5. Chọn chế độ tích hợp:
   * **Device**: Xem dữ liệu từ một thiết bị đơn lẻ
   * **Project**: Tổng hợp dữ liệu từ nhiều thiết bị
6. Nhập thông tin thiết bị:
   * **Device Mode**: Nhập ChipsetId của thiết bị
   * **Project Mode**: Nhập số lượng và ID của các thiết bị
7. Click **Submit**

### Cấu hình khoảng thời gian cập nhật

Sau khi cài đặt, bạn có thể điều chỉnh khoảng thời gian cập nhật:

1. Vào **Configuration** → **Devices & Services**
2. Tìm **SmartSolar MPPT** trong danh sách
3. Click vào integration
4. Tìm sensor **"Update Interval"**
5. Điều chỉnh giá trị từ 1-30 giây

## Yêu cầu

* **Home Assistant**: 2022.7.0 trở lên
* **Python packages**:
  * `aiohttp>=3.8.0`

## Sensors

### Sensors thời gian thực

* **PV Voltage**: Điện áp tấm pin mặt trời
* **PV Current**: Dòng điện tấm pin mặt trời
* **Battery Voltage**: Điện áp ắc quy
* **Battery Current**: Dòng điện ắc quy
* **Charge Power**: Công suất sạc
* **Today kWh**: Điện năng sản xuất hôm nay
* **Total kWh**: Tổng điện năng sản xuất
* **Temperature**: Nhiệt độ thiết bị
* **Status**: Trạng thái hoạt động

### Number Entity

* **Update Interval**: Khoảng thời gian cập nhật (1-30 giây)

## Xử lý sự cố

### Các vấn đề thường gặp

**"Unknown" values trong sensors:**

* ✅ **Đã sửa trong v1.0**: Parser hiện xử lý đúng cấu trúc dữ liệu API
* Đảm bảo bạn đang sử dụng phiên bản mới nhất

**Không có dữ liệu từ sensors:**

* Kiểm tra **tên đăng nhập và mật khẩu** có đúng không
* Xác nhận thiết bị **đang online** trong ứng dụng SmartSolar
* Xem lại trạng thái kết nối API trong logs
* Đảm bảo ChipsetId chính xác

**Integration không load được:**

* Xác nhận tất cả **requirements** đã được cài đặt
* Kiểm tra **logs** của Home Assistant để tìm lỗi
* Đảm bảo ChipsetId khớp chính xác
* Thử xóa và thêm lại integration

**Lỗi kết nối API:**

* Kiểm tra kết nối internet
* Xác nhận API SmartSolar có thể truy cập
* Xem lại cài đặt firewall

### Debug Logging

Bật logging chi tiết để xử lý sự cố:

```yaml
logger:
  default: info
  logs:
    custom_components.smartsolar_mppt: debug
    homeassistant.components.http: debug
```

## Changelog

### 1.0.0 (2025-01-11)

* 🎉 **Phát hành đầu tiên**
* Hỗ trợ Device và Project mode
* Tích hợp API SmartSolar với auto-refresh token
* Giao diện tiếng Việt và tiếng Anh
* 8 loại sensors đầy đủ
* Khoảng thời gian cập nhật có thể cấu hình
* Brand icons chính thức
* Sẵn sàng mở rộng cho các loại thiết bị khác

## Đóng góp

Chúng tôi hoan nghênh sự đóng góp! Đây là cách bạn có thể giúp:

1. **Fork** repository
2. **Tạo** feature branch (`git checkout -b feature/tinh-nang-tuyet-voi`)
3. **Commit** thay đổi (`git commit -m 'Thêm tinh năng tuyệt vời'`)
4. **Push** lên branch (`git push origin feature/tinh-nang-tuyet-voi`)
5. **Mở** Pull Request

### Thiết lập phát triển

1. Clone repository
2. Cài đặt dependencies phát triển
3. Thực hiện thay đổi
4. Test với thiết bị SmartSolar của bạn
5. Submit pull request

## Hỗ trợ

* 📧 **GitHub Issues**: Báo cáo lỗi hoặc yêu cầu tính năng
* 💬 **Home Assistant Community**: Tham gia thảo luận
* 📖 **Tài liệu**: Xem README này và comments trong code

## Giấy phép

Dự án này được cấp phép theo **MIT License** - xem file LICENSE để biết thêm chi tiết.

## Lời cảm ơn

* **SmartSolar** vì đã cung cấp API
* **Home Assistant Community** vì sự hỗ trợ và phản hồi
* **HACS** vì giúp việc cài đặt trở nên dễ dàng
* **Các contributors** giúp cải thiện integration này

## Ủng hộ

Nếu bạn thấy integration này hữu ích, hãy cân nhắc hỗ trợ phát triển:

[Buy me a coffee](https://www.buymeacoffee.com/ngoviet)

---

**Được tạo với ❤️ cho cộng đồng Home Assistant**
