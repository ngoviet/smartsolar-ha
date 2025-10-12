# Hướng dẫn cài đặt

## Yêu cầu hệ thống

- **Home Assistant**: 2022.7.0 trở lên
- **HACS**: Đã cài đặt và hoạt động
- **Tài khoản SmartSolar**: Có sẵn username/password
- **Thiết bị MPPT**: Đã kết nối Wifi và hoạt động

## Cài đặt qua HACS (Khuyến nghị)

### Bước 1: Thêm Custom Repository

1. Mở **HACS** trong Home Assistant
2. Vào **Integrations**
3. Click **ba chấm** (⋮) ở góc trên bên phải
4. Chọn **Custom repositories**
5. Thêm thông tin:
   - **Repository**: `https://github.com/ngoviet/smartsolar-ha`
   - **Category**: `Integration`
6. Click **Add**

### Bước 2: Cài đặt Integration

1. Tìm kiếm **"SmartSolar MPPT"** trong HACS
2. Click vào integration
3. Click **Download**
4. Chờ quá trình tải xuống hoàn tất

### Bước 3: Khởi động lại Home Assistant

1. Vào **Settings** → **System**
2. Click **Restart**
3. Chờ Home Assistant khởi động lại

## Cài đặt thủ công

Nếu không thể sử dụng HACS:

### Bước 1: Tải xuống

1. Vào [GitHub Releases](https://github.com/ngoviet/smartsolar-ha/releases)
2. Tải phiên bản mới nhất
3. Giải nén file ZIP

### Bước 2: Copy files

1. Copy thư mục `custom_components/smartsolar_mppt`
2. Paste vào thư mục `custom_components/` của Home Assistant
3. Đảm bảo cấu trúc thư mục đúng:
   ```
   config/
   └── custom_components/
       └── smartsolar_mppt/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── sensor.py
           ├── coordinator.py
           ├── api.py
           ├── const.py
           ├── number.py
           ├── strings.json
           └── translations/
               ├── vi.json
               └── en.json
   ```

### Bước 3: Khởi động lại

1. Restart Home Assistant
2. Kiểm tra logs để đảm bảo không có lỗi

## Xác minh cài đặt

Sau khi cài đặt thành công:

1. Vào **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Tìm kiếm **"SmartSolar MPPT"**
4. Nếu thấy integration trong danh sách = cài đặt thành công! ✅

## Bước tiếp theo

Sau khi cài đặt xong, hãy xem [Cấu hình](Cấu-hình) để thiết lập integration lần đầu.

## Xử lý sự cố

### Không thấy integration trong danh sách

- Kiểm tra logs Home Assistant
- Đảm bảo cấu trúc thư mục đúng
- Restart Home Assistant lần nữa

### Lỗi "Integration not found"

- Xóa thư mục `custom_components/smartsolar_mppt`
- Cài đặt lại từ đầu
- Kiểm tra quyền truy cập file

### HACS không tìm thấy integration

- Kiểm tra repository URL có đúng không
- Thử refresh HACS
- Restart Home Assistant
