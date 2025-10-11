# Icon cho SmartSolar MPPT Integration

## 🎨 Thêm icon cho integration

Để thêm icon cho integration, hãy tạo file `icon.png` trong thư mục này với các yêu cầu sau:

### **📐 Kích thước:**
- **256x256 pixels** (khuyến nghị)
- **Tối thiểu**: 192x192 pixels
- **Tối đa**: 512x512 pixels

### **🎨 Thiết kế:**
- **Nền trong suốt** (transparent background)
- **Màu sắc**: Xanh lá cây (solar theme) hoặc xanh dương
- **Biểu tượng**: Solar panel, battery, hoặc MPPT controller
- **Phong cách**: Material Design hoặc flat design

### **📁 Vị trí file:**
```
custom_components/smartsolar_mppt/
├── icon.png          ← Icon chính (256x256)
├── logo.png          ← Logo cho brand (256x256)
├── manifest.json
├── __init__.py
└── ...
```

### **🔧 Cách tạo icon:**

#### **Option 1: Sử dụng Material Design Icons**
1. Truy cập [Material Design Icons](https://materialdesignicons.com/)
2. Tìm icon phù hợp: "solar-power", "battery", "power-plug"
3. Download PNG 256x256
4. Đặt tên file là `icon.png`

#### **Option 2: Sử dụng online icon generator**
1. Truy cập [Favicon Generator](https://www.favicon-generator.org/)
2. Upload logo SmartSolar
3. Generate icon 256x256
4. Download và đặt tên `icon.png`

#### **Option 3: Tạo bằng GIMP/Photoshop**
1. Tạo canvas 256x256 pixels
2. Vẽ icon solar panel hoặc battery
3. Export as PNG với transparent background
4. Lưu thành `icon.png`

### **✅ Sau khi có icon:**
1. Copy file `icon.png` vào thư mục này
2. Restart Home Assistant
3. Icon sẽ xuất hiện trong:
   - **Settings** → **Devices & Services**
   - **Device registry**
   - **Integration list**

### **🎯 Gợi ý icon:**
- ☀️ Solar panel với tia sáng
- 🔋 Battery với dấu + (charging)
- ⚡ Lightning bolt (power)
- 🔌 Power plug
- 📊 Chart/graph (monitoring)

---

**Lưu ý**: File `icon.png` sẽ được tự động phát hiện bởi Home Assistant khi có trong thư mục integration.
