# Hướng dẫn Submit SmartSolar MPPT lên Home Assistant Brands Repository

## 📋 Tổng quan

Để submit brand icons của SmartSolar MPPT lên Home Assistant brands repository, làm theo các bước sau:

## 🔧 Bước 1: Fork Repository

1. Truy cập: https://github.com/home-assistant/brands
2. Click **Fork** để tạo fork của repository
3. Clone fork về máy local:
   ```bash
   git clone https://github.com/YOUR_USERNAME/brands.git
   cd brands
   ```

## 📁 Bước 2: Tạo Branch mới

```bash
git checkout -b add-smartsolar-mppt-brand
```

## 📂 Bước 3: Copy Files

Copy files từ `brands_prep/custom_integrations/smartsolar_mppt/` vào `custom_integrations/smartsolar_mppt/`:

```bash
# Tạo thư mục
mkdir -p custom_integrations/smartsolar_mppt

# Copy files
cp brands_prep/custom_integrations/smartsolar_mppt/* custom_integrations/smartsolar_mppt/
```

## 📝 Bước 4: Commit và Push

```bash
git add custom_integrations/smartsolar_mppt/
git commit -m "Add SmartSolar MPPT brand assets

- Add icon.png (256x256) for integration
- Add logo.png (512x512) for brand
- Add README.md with brand guidelines
- Domain: smartsolar_mppt
- Repository: https://github.com/ngoviet/smartsolar-ha"

git push origin add-smartsolar-mppt-brand
```

## 🔄 Bước 5: Tạo Pull Request

1. Truy cập: https://github.com/YOUR_USERNAME/brands
2. Click **Compare & pull request**
3. Điền thông tin:
   - **Title**: `Add SmartSolar MPPT brand assets`
   - **Description**:
     ```
     ## SmartSolar MPPT Brand Assets
     
     This PR adds brand assets for the SmartSolar MPPT Home Assistant integration.
     
     ### Files Added
     - `icon.png` (256x256): Square icon for the integration
     - `logo.png` (512x512): Brand logo for SmartSolar
     - `README.md`: Brand guidelines and usage information
     
     ### Integration Details
     - **Domain**: `smartsolar_mppt`
     - **Name**: SmartSolar MPPT
     - **Repository**: https://github.com/ngoviet/smartsolar-ha
     - **Documentation**: https://github.com/ngoviet/smartsolar-ha
     
     ### Brand Guidelines
     - Icons are optimized for Home Assistant display
     - PNG format with transparent background
     - Material Design inspired
     - Solar/MPPT theme with green/blue colors
     
     ### Usage
     These brand assets will be used in:
     - Home Assistant integration list
     - HACS (Home Assistant Community Store)
     - Device registry
     - Integration info pages
     ```

## ⏳ Bước 6: Chờ Review

- Maintainers sẽ review PR
- Có thể có feedback và yêu cầu chỉnh sửa
- Respond nhanh chóng và professional

## ✅ Bước 7: Merge và Hoàn thành

- Sau khi PR được merge, brand icons sẽ có sẵn trong Home Assistant
- Integration sẽ hiển thị icon chính thức
- Có thể remove fork nếu muốn

## 📞 Liên hệ

Nếu có vấn đề, liên hệ:
- GitHub: @ngoviet
- Repository: https://github.com/ngoviet/smartsolar-ha
