# Changelog

## [1.1.0] - 2025-10-12

### Added
- Dynamic entity creation for individual device sensors
- Custom exception classes for better error handling (SmartSolarAuthenticationError, SmartSolarConnectionError, SmartSolarNotFoundError)
- Performance optimizations for data parsing with O(1) lookup
- Device discovery tracking in coordinator
- Cached sensor info function for better performance
- Device discovery callbacks for dynamic entity management

### Fixed
- Critical indentation error in SmartSolarAPIError class
- Property override issues in sensor.py (removed unnecessary available property)
- All linter errors and warnings (13 errors fixed)
- Type checking issues with Home Assistant version compatibility
- Exception handling with specific exception types instead of generic Exception

### Changed
- Improved error handling with specific exceptions for different error types
- Better device discovery and tracking with coordinator callbacks
- Optimized sensor value parsing using dictionary lookup instead of list iteration
- Enhanced API error messages with more context
- Better token refresh logic with specific error handling

### Technical Improvements
- Added `# type: ignore[override]` comments for Home Assistant compatibility
- Implemented device tracking in SmartSolarDataUpdateCoordinator
- Added callback system for dynamic entity creation
- Optimized data stream parsing from O(n) to O(1) complexity
- Enhanced error handling throughout the codebase

## [1.0.2] - 2025-10-12

### Added
- Project ID support for SmartSolar integration
- Individual device sensors for project mode
- Localized error messages in Vietnamese and English
- Update interval control via Number entity

### Fixed
- KeyError issues with chipset_ids in coordinator and sensor
- Status sensor mapping for text values
- Update interval persistence after restart

## [1.0.1] - 2025-10-12

### Fixed
- Initial bug fixes and stability improvements

## [1.0.0] - 2025-10-12

### Added
- Initial release of SmartSolar MPPT integration
- Support for Sạc MPPT Mạnh Quân devices
- Device and Project mode configurations
- Real-time sensor data monitoring
- Home Assistant integration via HACS
