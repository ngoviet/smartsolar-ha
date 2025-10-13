# Script tự động xóa SmartSolar entities cũ và restart HA
Write-Host "=== SmartSolar Entity Cleanup Script ===" -ForegroundColor Green

# 1. Xóa __pycache__ để force reload code
Write-Host "1. Xóa Python cache..." -ForegroundColor Yellow
$cachePath = "\\192.168.10.15\config\custom_components\smartsolar_mppt\__pycache__"
if (Test-Path $cachePath) {
    Remove-Item $cachePath -Recurse -Force
    Write-Host "   ✓ Đã xóa __pycache__" -ForegroundColor Green
} else {
    Write-Host "   ✓ Không có cache để xóa" -ForegroundColor Green
}

# 2. Xóa entities cũ từ entity_registry.json
Write-Host "2. Xóa entities cũ từ entity registry..." -ForegroundColor Yellow
$registryPath = "\\192.168.10.15\config\.storage\entity_registry.json"

if (Test-Path $registryPath) {
    # Backup registry trước khi sửa
    $backupPath = "\\192.168.10.15\config\.storage\entity_registry.json.backup"
    Copy-Item $registryPath $backupPath -Force
    Write-Host "   ✓ Đã backup entity registry" -ForegroundColor Green
    
    # Đọc và filter entities
    $registry = Get-Content $registryPath | ConvertFrom-Json
    $originalCount = $registry.data.entities.Count
    Write-Host "   - Tổng entities: $originalCount" -ForegroundColor Cyan
    
    # Xóa tất cả entities có domain smartsolar_mppt
    $registry.data.entities = $registry.data.entities | Where-Object { $_.platform -ne "smartsolar_mppt" }
    $newCount = $registry.data.entities.Count
    $removedCount = $originalCount - $newCount
    
    Write-Host "   - Đã xóa: $removedCount entities" -ForegroundColor Cyan
    Write-Host "   - Còn lại: $newCount entities" -ForegroundColor Cyan
    
    # Lưu registry đã clean
    $registry | ConvertTo-Json -Depth 10 | Set-Content $registryPath -Encoding UTF8
    Write-Host "   ✓ Đã cập nhật entity registry" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Không tìm thấy entity registry" -ForegroundColor Red
}

# 3. Xóa devices cũ từ device_registry.json
Write-Host "3. Xóa devices cũ từ device registry..." -ForegroundColor Yellow
$deviceRegistryPath = "\\192.168.10.15\config\.storage\device_registry.json"

if (Test-Path $deviceRegistryPath) {
    # Backup device registry
    $deviceBackupPath = "\\192.168.10.15\config\.storage\device_registry.json.backup"
    Copy-Item $deviceRegistryPath $deviceBackupPath -Force
    Write-Host "   ✓ Đã backup device registry" -ForegroundColor Green
    
    # Đọc và filter devices
    $deviceRegistry = Get-Content $deviceRegistryPath | ConvertFrom-Json
    $originalDeviceCount = $deviceRegistry.data.devices.Count
    Write-Host "   - Tổng devices: $originalDeviceCount" -ForegroundColor Cyan
    
    # Xóa tất cả devices có identifiers chứa smartsolar_mppt
    $deviceRegistry.data.devices = $deviceRegistry.data.devices | Where-Object { 
        $_.identifiers -notmatch "smartsolar_mppt" 
    }
    $newDeviceCount = $deviceRegistry.data.devices.Count
    $removedDeviceCount = $originalDeviceCount - $newDeviceCount
    
    Write-Host "   - Đã xóa: $removedDeviceCount devices" -ForegroundColor Cyan
    Write-Host "   - Còn lại: $newDeviceCount devices" -ForegroundColor Cyan
    
    # Lưu device registry đã clean
    $deviceRegistry | ConvertTo-Json -Depth 10 | Set-Content $deviceRegistryPath -Encoding UTF8
    Write-Host "   ✓ Đã cập nhật device registry" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Không tìm thấy device registry" -ForegroundColor Red
}

# 4. Restart Home Assistant
Write-Host "4. Restart Home Assistant..." -ForegroundColor Yellow
Write-Host "   ⚠ Bạn cần restart Home Assistant manually!" -ForegroundColor Red
Write-Host "   - Vào Supervisor → System → Restart" -ForegroundColor Cyan
Write-Host "   - Hoặc dùng lệnh: docker restart homeassistant" -ForegroundColor Cyan

Write-Host "`n=== HOÀN THÀNH ===" -ForegroundColor Green
Write-Host "Sau khi restart HA, add lại SmartSolar integration để tạo entities mới với prefix đúng!" -ForegroundColor Yellow
