"""Constants for SmartSolar MPPT integration."""

from datetime import timedelta

DOMAIN = "smartsolar_mppt"

# API Configuration
API_BASE_URL = "https://api.smartsolar.io.vn"
API_LOGIN_ENDPOINT = f"{API_BASE_URL}/Auth/Login?Key=Content-Type"
API_METRICS_ENDPOINT = f"{API_BASE_URL}/Metric/SynthesisMetrics"

# Device Types
DEVICE_TYPE_SUN_GTIL2 = 1  # Inverter Sun-GTIL2
DEVICE_TYPE_MANH_QUAN = 2  # Sạc MPPT Mạnh Quân

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
        "unit": "",
        "icon": "mdi:information",
        "device_class": None,
        "state_class": "measurement",
    },
}

# Data stream indices (based on API response structure)
DATA_STREAM_INDICES = {
    "pv_voltage": 0,
    "pv_current": 1, 
    "bat_voltage": 2,
    "bat_current": 3,
    "charge_power": 4,
    "today_kwh": 5,
    "total_kwh": 6,
    "temperature": 7,
    "status": 8,
}

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_MODE = "mode"
CONF_DEVICE_TYPE = "device_type"
CONF_CHIPSET_IDS = "chipset_ids"
CONF_UPDATE_INTERVAL = "update_interval"

# Integration modes
MODE_DEVICE = "device"
MODE_PROJECT = "project"

# Error messages
ERROR_INVALID_CREDENTIALS = "invalid_credentials"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNKNOWN = "unknown"
