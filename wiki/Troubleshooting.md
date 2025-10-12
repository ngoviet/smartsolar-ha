# Xử lý sự cố

## Sự cố thường gặp

### 1. Không có dữ liệu từ sensors

**Triệu chứng:**
- Tất cả sensors hiển thị "Unknown"
- Không có dữ liệu mới

**Nguyên nhân có thể:**
- Sai thông tin đăng nhập
- Thiết bị không online
- Lỗi kết nối API

**Cách khắc phục:**
1. Kiểm tra username/password có đúng không
2. Đăng nhập [SmartSolar Web](https://smartsolar.io.vn/) để xác nhận
3. Kiểm tra thiết bị có online không
4. Xem logs Home Assistant:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.smartsolar_mppt: debug
   ```

### 2. Integration không load được

**Triệu chứng:**
- Không thấy integration trong danh sách
- Lỗi khi thêm integration

**Nguyên nhân có thể:**
- Cài đặt không đúng
- Thiếu dependencies
- Lỗi cấu trúc file

**Cách khắc phục:**
1. Kiểm tra cấu trúc thư mục:
   ```
   config/custom_components/smartsolar_mppt/
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
2. Restart Home Assistant
3. Cài đặt lại từ đầu nếu cần

### 3. Lỗi kết nối API

**Triệu chứng:**
- Lỗi "Cannot connect to API"
- Timeout errors

**Nguyên nhân có thể:**
- Mất kết nối internet
- API SmartSolar bị lỗi
- Firewall chặn

**Cách khắc phục:**
1. Kiểm tra kết nối internet
2. Thử truy cập [SmartSolar Web](https://smartsolar.io.vn/)
3. Kiểm tra firewall/router settings
4. Thử lại sau vài phút

### 4. Dữ liệu không cập nhật

**Triệu chứng:**
- Dữ liệu cũ, không thay đổi
- Timestamp không cập nhật

**Nguyên nhân có thể:**
- Tần suất cập nhật quá thấp
- Lỗi coordinator
- API rate limiting

**Cách khắc phục:**
1. Kiểm tra tần suất cập nhật (1-30 giây)
2. Restart integration
3. Kiểm tra logs để tìm lỗi

### 5. Lỗi "Unknown" values

**Triệu chứng:**
- Một số sensors hiển thị "Unknown"
- Dữ liệu không đầy đủ

**Nguyên nhân có thể:**
- Parser lỗi
- API trả về dữ liệu không đúng format
- Thiết bị không gửi đầy đủ dữ liệu

**Cách khắc phục:**
1. Cập nhật lên phiên bản mới nhất
2. Kiểm tra logs để xem lỗi cụ thể
3. Báo cáo lỗi nếu vẫn tiếp tục

## Debug Logging

### Bật debug logging

Thêm vào `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smartsolar_mppt: debug
    homeassistant.components.http: debug
```

### Xem logs

1. Vào **Settings** → **System** → **Logs**
2. Filter với `smartsolar_mppt`
3. Tìm các dòng có `ERROR` hoặc `WARNING`

### Logs quan trọng

- `SmartSolar API Update` - Cập nhật dữ liệu
- `Login successful` - Đăng nhập thành công
- `Device discovered` - Phát hiện thiết bị mới
- `API error` - Lỗi API

## Reset Integration

### Xóa và tạo lại

1. Vào **Settings** → **Devices & Services**
2. Tìm **SmartSolar MPPT**
3. Click **Delete**
4. Xác nhận xóa
5. Thêm lại integration

### Xóa cấu hình cũ

Nếu vẫn có vấn đề:

1. Xóa integration
2. Restart Home Assistant
3. Xóa thư mục `custom_components/smartsolar_mppt`
4. Cài đặt lại từ đầu

## Liên hệ hỗ trợ

### Báo cáo lỗi

Khi báo cáo lỗi, hãy cung cấp:

1. **Phiên bản Home Assistant**
2. **Phiên bản integration**
3. **Logs lỗi** (có debug logging)
4. **Mô tả chi tiết** vấn đề
5. **Các bước** để tái tạo lỗi

### Tạo Issue

[Tạo Issue mới](https://github.com/ngoviet/smartsolar-ha/issues/new) với template:

```markdown
**Mô tả lỗi**
Mô tả ngắn gọn về lỗi

**Các bước tái tạo**
1. Vào '...'
2. Click '...'
3. Thấy lỗi

**Logs**
```
Paste logs ở đây
```

**Thông tin hệ thống**
- Home Assistant: 2023.x.x
- Integration: v1.1.2
- OS: Ubuntu/Docker/...
```

## Tips tránh lỗi

### Cài đặt đúng cách
- Luôn sử dụng HACS nếu có thể
- Không chỉnh sửa files integration
- Cập nhật thường xuyên

### Cấu hình hợp lý
- Không đặt tần suất cập nhật quá thấp (< 5 giây)
- Sử dụng Project Mode cho nhiều thiết bị
- Kiểm tra kết nối internet ổn định

### Monitoring
- Thường xuyên kiểm tra logs
- Monitor trạng thái integration
- Backup cấu hình quan trọng
