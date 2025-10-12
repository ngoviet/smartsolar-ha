# Hướng dẫn cấu hình

## Cấu hình lần đầu

### Bước 1: Thêm Integration

1. Vào **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Tìm kiếm **"SmartSolar MPPT"**
4. Click vào integration

### Bước 2: Nhập thông tin đăng nhập

1. **Username**: Nhập tên đăng nhập SmartSolar của bạn
2. **Password**: Nhập mật khẩu SmartSolar của bạn
3. Click **Submit**

### Bước 3: Chọn chế độ tích hợp

#### Device Mode (Một thiết bị)
- Chọn **"Device"**
- Nhập **Chipset ID** của sạc MPPT
- Click **Submit**

#### Project Mode (Nhiều thiết bị)
- Chọn **"Project"**
- Chọn phương thức:
  - **Device IDs**: Nhập danh sách Chipset ID (cách nhau bởi dấu phẩy)
  - **Project ID**: Nhập Project ID từ SmartSolar web
- Click **Submit**

### Bước 4: Hoàn tất

1. Chờ integration tạo sensors
2. Kiểm tra **Devices & Services** để xem thiết bị mới
3. Thêm sensors vào dashboard

## Cấu hình nâng cao

### Điều chỉnh tần suất cập nhật

1. Vào **Settings** → **Devices & Services**
2. Tìm **SmartSolar MPPT** trong danh sách
3. Click vào integration
4. Tìm sensor **"Tần suất cập nhật"**
5. Điều chỉnh giá trị từ 1-30 giây

### Thêm nhiều thiết bị

Để thêm thiết bị khác:

1. Tạo integration mới (Device Mode)
2. Hoặc sử dụng Project Mode để quản lý tất cả

### Cấu hình Project ID

Nếu sử dụng Project ID:

1. Đăng nhập [SmartSolar Web](https://smartsolar.io.vn/)
2. Vào **Dự án** → Chọn project
3. Copy **Project ID** từ URL hoặc trang chi tiết
4. Paste vào integration

## Xử lý sự cố cấu hình

### Lỗi đăng nhập

- Kiểm tra username/password có đúng không
- Thử đăng nhập trên web SmartSolar
- Kiểm tra kết nối internet

### Không tìm thấy thiết bị

- Đảm bảo thiết bị đang online
- Kiểm tra Chipset ID có đúng không
- Xem logs Home Assistant

### Dữ liệu không cập nhật

- Kiểm tra tần suất cập nhật
- Xem trạng thái kết nối API
- Restart integration

## Cấu trúc dữ liệu

### Device Mode
- Mỗi integration = 1 thiết bị
- Sensors riêng biệt cho từng thiết bị
- Dễ quản lý và theo dõi

### Project Mode
- 1 integration = nhiều thiết bị
- Sensors tổng hợp + sensors riêng lẻ
- Tiết kiệm tài nguyên

## Tips cấu hình

### Tối ưu hiệu suất
- Sử dụng Project Mode cho nhiều thiết bị
- Đặt tần suất cập nhật phù hợp (5-10 giây)
- Tránh tạo quá nhiều integration

### Bảo mật
- Không chia sẻ thông tin đăng nhập
- Sử dụng mật khẩu mạnh
- Cập nhật integration thường xuyên
