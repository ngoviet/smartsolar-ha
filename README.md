# SmartSolar MPPT - Sạc MPPT Mạnh Quân Home Assistant Integration

> **Keywords**: MPPT Mạnh Quân, Manh Quan, SmartSolar, Home Assistant, HACS, Sạc năng lượng mặt trời, Solar charger, 40A 45A 60A Wifi

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![maintenance](https://img.shields.io/badge/maintained%20by-ngoviet-blue.svg)](https://github.com/ngoviet)
[![GitHub release](https://img.shields.io/github/release/ngoviet/smartsolar-ha.svg)](https://github.com/ngoviet/smartsolar-ha/releases)
[![GitHub stars](https://img.shields.io/badge/github-stars-ngoviet.svg)](https://github.com/ngoviet/smartsolar-ha/stargazers)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=smartsolar-ha&category=integration)

Mở Home Assistant của bạn và mở repository trong Home Assistant Community Store.

## Tại sao mình tạo integration này? 🌞

Mình đã sử dụng sạc MPPT Mạnh Quân được vài năm rồi, và mỗi lần muốn xem pin sạc được bao nhiêu điện, mình phải mở app SmartSolar trên điện thoại. Thật sự bất tiện! 

Mình nghĩ: "Sao không tích hợp vào Home Assistant để xem ngay trên dashboard, cùng với các thiết bị khác trong nhà?" Và thế là integration này ra đời! 

Bây giờ mình có thể xem pin sạc được bao nhiêu điện mỗi ngày, ngay trên màn hình chính của Home Assistant. Thật tuyệt vời khi thấy số điện tăng lên từng giây, biết rằng mình đang góp phần bảo vệ môi trường! 🌱

## Những gì bạn sẽ có

Khi cài đặt integration này, bạn sẽ có thể:

* **Xem pin sạc được bao nhiêu điện** - ngay trên điện thoại, mọi lúc mọi nơi! 📱
* **Theo dõi 2 cách**:
  * **Một sạc**: Xem chi tiết từng sạc riêng lẻ
  * **Nhiều sạc**: Tổng hợp tất cả sạc trong nhà thành một bảng điều khiển
* **Xem đầy đủ thông tin**:
  * **Điện áp và dòng điện** từ tấm pin mặt trời
  * **Bao nhiêu điện đã nạp** vào ắc quy hôm nay
  * **Tổng số điện** từ trước đến giờ
  * **Nhiệt độ sạc** (để biết khi nào cần tản nhiệt)
  * **Trạng thái hoạt động** (đang sạc, dừng, lỗi...)
* **Tự động cập nhật** - không cần làm gì thêm, dữ liệu tự động refresh
* **Điều chỉnh tốc độ cập nhật** - từ 1 giây đến 30 giây, tùy ý bạn
* **Giao diện tiếng Việt** - dễ hiểu, gần gũi

![SmartSolar MPPT Dashboard](https://via.placeholder.com/800x400/2E7D32/FFFFFF?text=SmartSolar+MPPT+Dashboard)

## Thiết bị được hỗ trợ 🔋

### Sạc MPPT Mạnh Quân Wifi

Integration này được thiết kế đặc biệt cho dòng sạc **Mạnh Quân Wifi**:

* **40A Wifi** - Sạc 40A có Wifi 📡
* **45A Wifi** - Sạc 45A có Wifi 📡  
* **60A Wifi** - Sạc 60A có Wifi 📡

**Thông số kỹ thuật:**
- Điện áp PV: 18-100V
- Dòng sạc: 1-60A (tùy model)
- Điện áp sạc: 6-120V
- Kết nối: Wifi + SmartSolar API
- Bảo hành: 12 tháng

### Các thiết bị SmartSolar khác
* Tương thích với các thiết bị SmartSolar khác sử dụng cùng API

![SmartSolar MPPT Sensors](https://via.placeholder.com/800x400/1976D2/FFFFFF?text=SmartSolar+MPPT+Sensors)

## Làm sao để bắt đầu? 🚀

### Bước 1: Cài đặt qua HACS (dễ nhất!)
1. Mở **HACS** trong Home Assistant
2. Tìm **"SmartSolar MPPT"**
3. Click **"Tải xuống"**
4. Khởi động lại Home Assistant

### Bước 2: Kết nối với sạc của bạn
1. Vào **Settings** → **Devices & Services**
2. Click **"Thêm tích hợp"**
3. Tìm **"SmartSolar MPPT"**
4. Nhập tài khoản SmartSolar của bạn
5. Chọn thiết bị muốn theo dõi

**Xong!** Bây giờ bạn có thể xem pin sạc được bao nhiêu mỗi ngày 🌞

## Có gì hay ho? 🤔

**Tôi có thể xem gì?**
- Điện áp và dòng điện từ tấm pin
- Bao nhiêu điện đã nạp vào ắc quy
- Tổng số điện hôm nay và từ trước đến giờ
- Nhiệt độ sạc (để biết khi nào cần tản nhiệt)

**Có khó không?**
Không khó chút nào! Chỉ cần 5 phút để cài đặt.

**Tôi có nhiều sạc, có theo dõi được hết không?**
Được! Bạn có thể thêm bao nhiêu sạc cũng được.

**Dữ liệu có chính xác không?**
Dữ liệu lấy trực tiếp từ SmartSolar API, cập nhật mỗi 5 giây (hoặc tùy chỉnh theo ý bạn).

**Có cần cài đặt gì thêm không?**
Chỉ cần Home Assistant 2022.7.0 trở lên. Mọi thứ khác đều tự động!

## Cấu hình nâng cao ⚙️

### Điều chỉnh tốc độ cập nhật
Sau khi cài đặt, bạn có thể điều chỉnh tốc độ cập nhật:

1. Vào **Configuration** → **Devices & Services**
2. Tìm **SmartSolar MPPT** trong danh sách
3. Click vào integration
4. Tìm sensor **"Tần suất cập nhật"**
5. Điều chỉnh giá trị từ 1-30 giây

### Cài đặt thủ công (nếu cần)
1. Tải phiên bản mới nhất từ GitHub
2. Copy thư mục `custom_components/smartsolar_mppt` vào thư mục `custom_components/` của Home Assistant
3. Khởi động lại Home Assistant
4. Thêm integration qua **Configuration** → **Integrations**

## Xử lý sự cố 🔧

**Không có dữ liệu từ sensors:**
- Kiểm tra **tên đăng nhập và mật khẩu** có đúng không
- Xác nhận thiết bị **đang online** trong ứng dụng SmartSolar
- Xem lại trạng thái kết nối API trong logs

**Integration không load được:**
- Xác nhận tất cả **requirements** đã được cài đặt
- Kiểm tra **logs** của Home Assistant để tìm lỗi
- Thử xóa và thêm lại integration

**Lỗi kết nối API:**
- Kiểm tra kết nối internet
- Xác nhận API SmartSolar có thể truy cập

## Bạn muốn giúp đỡ? 💚

Mình rất vui nếu bạn muốn cùng phát triển integration này!

- **Báo lỗi**: Tạo Issue trên GitHub
- **Góp ý tính năng**: Cũng tạo Issue
- **Sửa code**: Tạo Pull Request

Mọi đóng góp, dù nhỏ hay lớn, đều được trân trọng! 💚

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

## Ủng hộ dự án ☕

Nếu integration này giúp bạn tiết kiệm điện, theo dõi năng lượng dễ dàng hơn, hoặc đơn giản là làm bạn vui, hãy cân nhắc mua cho mình một ly cà phê nhé! ☕

Mỗi sự ủng hộ, dù nhỏ hay lớn, đều giúp mình có động lực để tiếp tục phát triển và cải thiện integration này.

### Địa chỉ ví BSC (BEP20)

| Crypto | Mạng lưới | Địa chỉ ví BSC |
|--------|-----------|---------------|
| ![Bitcoin](https://img.shields.io/badge/Bitcoin-F7931A?style=flat&logo=bitcoin&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![Ethereum](https://img.shields.io/badge/Ethereum-3C3C3D?style=flat&logo=Ethereum&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![USDT](https://img.shields.io/badge/USDT-26a17b?style=flat&logo=tether&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![BNB](https://img.shields.io/badge/BNB-F3BA2F?style=flat&logo=binance&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![USDC](https://img.shields.io/badge/USDC-2775CA?style=flat&logo=circle&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![BUSD](https://img.shields.io/badge/BUSD-F0B90B?style=flat&logo=binance&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |
| ![CAKE](https://img.shields.io/badge/CAKE-D1884F?style=flat&logo=circle&logoColor=white) | **BSC (BEP20)** | `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa` |

> **Lưu ý**: Tất cả địa chỉ đều giống nhau vì cùng một ví BSC!

### 🔍 Cách gửi:
1. Mở ví (MetaMask, Trust Wallet, Binance, etc.)
2. Chọn "Gửi" hoặc "Send" → Chọn crypto muốn gửi
3. Chọn mạng **BSC** hoặc **BNB Smart Chain**
4. Paste địa chỉ: `0x57f07d44fb581cddc028a0c67d63a8cc05aa6caa`
5. Gửi với phí cực thấp (~$0.01)

### ✅ Lợi ích:
- **Phí cực thấp** (chỉ ~$0.01)
- **Tốc độ nhanh** (3-5 giây)
- **Dễ dàng và an toàn**
- **Hỗ trợ nhiều loại coin**

### 🎯 Các coin được hỗ trợ:
- **Bitcoin (BTC)** - Wrapped BTC trên BSC
- **Ethereum (ETH)** - Wrapped ETH trên BSC  
- **USDT** - Tether USD trên BSC
- **BNB** - Binance Coin (native)
- **USDC** - USD Coin trên BSC
- **BUSD** - Binance USD (native)
- **CAKE** - PancakeSwap token
- **Và nhiều coin khác** trên BSC!

Cảm ơn bạn đã tin tưởng và sử dụng! 🌟

---

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-☕-yellow.svg)](https://www.buymeacoffee.com/ngoviet)

---

**Được tạo với ❤️ bởi một người yêu năng lượng mặt trời**

Nếu bạn thích integration này, đừng quên cho mình một ⭐ trên GitHub nhé!