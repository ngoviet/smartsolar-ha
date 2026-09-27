<#
    SmartSolar entity/device cleanup helper.

    Removes the SmartSolar entries from Home Assistant's entity and device
    registries so a re-added integration recreates them cleanly.

    Audit fixes (this script used to be able to destroy the registries):

      * The filters only matched the CURRENT domain. After the v2.0.0 rename
        (smartsolar_mppt -> smartsolar_ha) the legacy entries were left behind and
        stayed 'unavailable' in the UI forever — which is the one thing this
        script exists to prevent.
      * `... | Where-Object { ... }` unrolls a single result into a scalar, so
        ConvertTo-Json wrote "entities": { ... } — or "entities": null when
        everything was removed. Home Assistant requires a LIST there, so the
        corrupted file takes the whole registry with it. Every assignment is now
        wrapped in @().
      * `Set-Content -Encoding UTF8` writes a BOM under Windows PowerShell 5.1,
        which breaks Home Assistant's JSON parsing of .storage files.
      * Home Assistant rewrites .storage when it shuts down, silently discarding
        an edit made while it runs. The script now refuses to run while HA still
        answers on its API unless -Force is passed.

    Usage:
        # 1. Stop Home Assistant first (it rewrites .storage on shutdown)
        ssh vokupt@192.168.10.15 "sudo docker stop homeassistant"
        # 2. Then run this script, then start HA again
        powershell -File clear_entities.ps1

    -ConfigRoot overrides where the HA config lives; it exists so the registry
    surgery can be exercised against a copy instead of the live instance.
#>
param(
    [string]$HaHost = "192.168.10.15",
    [string]$ConfigRoot = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $ConfigRoot) { $ConfigRoot = "\\$HaHost\config" }

# Both domains: the current one and the pre-v2.0.0 name.
$SmartSolarDomains = @("smartsolar_ha", "smartsolar_mppt")
$EntityRegistryPath = Join-Path $ConfigRoot ".storage\entity_registry.json"
$DeviceRegistryPath = Join-Path $ConfigRoot ".storage\device_registry.json"
$HaApiUrl = "http://${HaHost}:8123/api/"

function Test-HaRunning {
    <# True when something answers on HA's API port (even a 401 means it is up). #>
    try {
        Invoke-WebRequest -Uri $HaApiUrl -TimeoutSec 5 -UseBasicParsing | Out-Null
        return $true
    } catch {
        if ($_.Exception.Response) { return $true }
        return $false
    }
}

function Get-IdentifierDomains($Identifiers) {
    <#
        A device identifier is a [domain, value] pair, so `identifiers` is usually
        an array of arrays. A single pair can come back from ConvertFrom-Json
        unrolled as a flat two-element list, so both shapes are handled.
    #>
    $domains = @()
    foreach ($item in $Identifiers) {
        if ($item -is [System.Array]) { $domains += $item[0] } else { $domains += $item }
    }
    return $domains
}

function Save-JsonNoBom($Path, $Data) {
    <# Write UTF-8 without a BOM: a BOM makes Home Assistant fail to parse the file. #>
    $json = $Data | ConvertTo-Json -Depth 32
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

Write-Host "=== SmartSolar Entity Cleanup Script ===" -ForegroundColor Green

if ((Test-HaRunning) -and -not $Force) {
    Write-Host "Home Assistant is still running at $HaApiUrl" -ForegroundColor Red
    Write-Host "It rewrites .storage when it shuts down, so an edit made now would be discarded." -ForegroundColor Red
    Write-Host "Stop it first:  ssh vokupt@$HaHost 'sudo docker stop homeassistant'" -ForegroundColor Cyan
    Write-Host "Then run this script again (or pass -Force to override)." -ForegroundColor Cyan
    exit 1
}

# 1. Xóa __pycache__ để force reload code
Write-Host "1. Xóa Python cache..." -ForegroundColor Yellow
$cachePath = Join-Path $ConfigRoot "custom_components\smartsolar_ha\__pycache__"
if (Test-Path $cachePath) {
    Remove-Item $cachePath -Recurse -Force
    Write-Host "   ✓ Đã xóa __pycache__" -ForegroundColor Green
} else {
    Write-Host "   ✓ Không có cache để xóa" -ForegroundColor Green
}

# 2. Xóa entities cũ từ entity_registry.json
Write-Host "2. Xóa entities cũ từ entity registry..." -ForegroundColor Yellow

if (Test-Path $EntityRegistryPath) {
    Copy-Item $EntityRegistryPath "$EntityRegistryPath.backup" -Force
    Write-Host "   ✓ Đã backup entity registry" -ForegroundColor Green

    $registry = Get-Content $EntityRegistryPath -Raw | ConvertFrom-Json
    $originalCount = @($registry.data.entities).Count
    Write-Host "   - Tổng entities: $originalCount" -ForegroundColor Cyan

    # @() is required: without it a single remaining entity would be serialized
    # as an object instead of a list, and an empty result as null.
    $registry.data.entities = @(
        $registry.data.entities | Where-Object { $SmartSolarDomains -notcontains $_.platform }
    )
    $newCount = @($registry.data.entities).Count
    $removedCount = $originalCount - $newCount

    Write-Host "   - Đã xóa: $removedCount entities" -ForegroundColor Cyan
    Write-Host "   - Còn lại: $newCount entities" -ForegroundColor Cyan

    Save-JsonNoBom $EntityRegistryPath $registry
    Write-Host "   ✓ Đã cập nhật entity registry" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Không tìm thấy entity registry" -ForegroundColor Red
}

# 3. Xóa devices cũ từ device_registry.json
Write-Host "3. Xóa devices cũ từ device registry..." -ForegroundColor Yellow

if (Test-Path $DeviceRegistryPath) {
    Copy-Item $DeviceRegistryPath "$DeviceRegistryPath.backup" -Force
    Write-Host "   ✓ Đã backup device registry" -ForegroundColor Green

    $deviceRegistry = Get-Content $DeviceRegistryPath -Raw | ConvertFrom-Json
    $originalDeviceCount = @($deviceRegistry.data.devices).Count
    Write-Host "   - Tổng devices: $originalDeviceCount" -ForegroundColor Cyan

    $deviceRegistry.data.devices = @(
        $deviceRegistry.data.devices | Where-Object {
            # Match the identifier DOMAIN, not the whole stringified array:
            # `-notmatch` on an array filters it (returning elements) instead of
            # returning a boolean, which is easy to get subtly wrong.
            $domains = Get-IdentifierDomains $_.identifiers
            -not ($domains | Where-Object { $SmartSolarDomains -contains $_ })
        }
    )
    $newDeviceCount = @($deviceRegistry.data.devices).Count
    $removedDeviceCount = $originalDeviceCount - $newDeviceCount

    Write-Host "   - Đã xóa: $removedDeviceCount devices" -ForegroundColor Cyan
    Write-Host "   - Còn lại: $newDeviceCount devices" -ForegroundColor Cyan

    Save-JsonNoBom $DeviceRegistryPath $deviceRegistry
    Write-Host "   ✓ Đã cập nhật device registry" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Không tìm thấy device registry" -ForegroundColor Red
}

# 4. Khởi động lại Home Assistant
Write-Host "4. Khởi động lại Home Assistant..." -ForegroundColor Yellow
Write-Host "   - Dùng lệnh: ssh vokupt@$HaHost 'sudo docker start homeassistant'" -ForegroundColor Cyan
Write-Host "   - Hoặc vào Supervisor → System → Restart" -ForegroundColor Cyan

Write-Host "`n=== HOÀN THÀNH ===" -ForegroundColor Green
Write-Host "Sau khi restart HA, add lại SmartSolar integration để tạo entities mới với prefix đúng!" -ForegroundColor Yellow
