"""Constants for SmartSolar MPPT integration."""

from datetime import timedelta
from typing import Any

DOMAIN = "smartsolar_mppt"

# API Configuration
API_BASE_URL = "https://api.smartsolar.io.vn"
API_LOGIN_ENDPOINT = f"{API_BASE_URL}/Auth/Login?Key=Content-Type"
API_METRICS_ENDPOINT = f"{API_BASE_URL}/Metric/SynthesisMetrics"

# Device Types
DEVICE_TYPE_SUN_GTIL2 = 1  # Inverter Sun-GTIL2
DEVICE_TYPE_MANH_QUAN = 2  # S?c MPPT M?nh Qu?n

# Update intervals
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=5)  # 5 seconds
MIN_UPDATE_INTERVAL = 1  # 1 second
MAX_UPDATE_INTERVAL = 30  # 30 seconds
TOKEN_REFRESH_DAYS_BEFORE_EXPIRY = 7  # days

# Sensor definitions
SENSOR_TYPES = {
    "pv_voltage": {
        "name": "PV Voltage",
        "unit": "V",
        "icon": "mdi:lightning-bolt",
        "device_class": "voltage",
        "state_class": "measurement",
    },
    "pv_current": {
        "name": "PV Current", 
        "unit": "A",
        "icon": "mdi:current-ac",
        "device_class": "current",
        "state_class": "measurement",
    },
    "bat_voltage": {
        "name": "Battery Voltage",
        "unit": "V", 
        "icon": "mdi:battery",
        "device_class": "voltage",
        "state_class": "measurement",
    },
    "bat_current": {
        "name": "Battery Current",
        "unit": "A",
        "icon": "mdi:current-ac", 
        "device_class": "current",
        "state_class": "measurement",
    },
    "charge_power": {
        "name": "Charge Power",
        "unit": "W",
        "icon": "mdi:solar-power",
        "device_class": "power",
        "state_class": "measurement",
    },
    "today_kwh": {
        "name": "Today Energy",
        "unit": "kWh",
        "icon": "mdi:solar-panel",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "total_kwh": {
        "name": "Total Energy", 
        "unit": "kWh",
        "icon": "mdi:chart-line",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "temperature": {
        "name": "Temperature",
        "unit": "°C",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    "status": {
        "name": "Status",
        "unit": None,
        "icon": "mdi:information",
        "device_class": None,
        "state_class": None,
    },
}

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_MODE = "mode"
CONF_DEVICE_TYPE = "device_type"
CONF_CHIPSET_IDS = "chipset_ids"
CONF_PROJECT_ID = "project_id"

# Integration modes
MODE_DEVICE = "device"
MODE_PROJECT = "project"

# Project mode configuration types
PROJECT_MODE_BY_ID = "project_by_id"
PROJECT_MODE_BY_DEVICES = "project_by_devices"

# Error messages
ERROR_INVALID_CREDENTIALS = "invalid_credentials"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNKNOWN = "unknown"

# Status mapping (English keys, Vietnamese in translation files)
STATUS_MAPPING = {
    0: "Online",
    1: "Charging",
    2: "Idle (No Sun)",
    3: "Fault",
}


def get_sensor_info(sensor_type: str) -> dict:
    """Get sensor info from SENSOR_TYPES dict."""
    return SENSOR_TYPES.get(sensor_type, {})


def build_device_info(entry_id: str, mode: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Build shared DeviceInfo dict for SmartSolar MPPT entities."""
    if mode == "project" and project_id:
        device_name = f"SmartSolar MPPT Project {project_id}"
    elif mode == "project":
        device_name = "SmartSolar MPPT Project"
    else:
        device_name = "SmartSolar MPPT Device"
    return {
        "identifiers": {(DOMAIN, entry_id)},
        "name": device_name,
        "manufacturer": "SmartSolar",
        "model": "MPPT Controller",
        "sw_version": "1.2.0",
        "hw_version": "MPPT",
        "configuration_url": "https://smartsolar.io.vn/",
    }
