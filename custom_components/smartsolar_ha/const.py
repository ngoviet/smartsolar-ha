"""Constants for SmartSolar MPPT integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "smartsolar_ha"

_LOGGER = logging.getLogger(__name__)

# Integration release version — keep in sync with manifest.json / pyproject.toml
VERSION = "2.0.2"

# Child loggers so users can silence just the noisy parts:
#   logger:
#     logs:
#       custom_components.smartsolar_ha.coordinator: warning
#       custom_components.smartsolar_ha.sensor: warning
COORDINATOR_LOGGER = f"{DOMAIN}.coordinator"
SENSOR_LOGGER = f"{DOMAIN}.sensor"

# API Configuration
API_BASE_URL = "https://api.smartsolar.io.vn"
API_LOGIN_ENDPOINT = f"{API_BASE_URL}/Auth/Login?Key=Content-Type"
API_METRICS_ENDPOINT = f"{API_BASE_URL}/Metric/SynthesisMetrics"
API_PROJECT_METRICS_ENDPOINT = f"{API_BASE_URL}/Metric/ProjectMetrics"
API_DEVICE_STATUS_ENDPOINT = f"{API_BASE_URL}/Device/Status"

# Device Types
DEVICE_TYPE_SUN_GTIL2 = 1  # Inverter Sun-GTIL2
DEVICE_TYPE_MANH_QUAN = 2  # SmartSolar MPPT Mạnh Quân charger

# MQTT Configuration
MQTT_BROKER = "mqttx.smartsolar.io.vn"
MQTT_PORT = 8084
MQTT_TOPIC_PREFIX = "manhquan/device/mppt_charger/log"
MQTT_WS_PATH = "/mqtt"
MQTT_RECONNECT_DELAY = 5  # seconds

# MQTT → REST field name mapping (MQTT uses different names than REST API)
MQTT_FIELD_MAPPING: dict[str, str] = {
    "charging_power": "charge_power",
    "yield_today": "today_kwh",
    "yield_total": "total_kwh",
    "signalQuality": "signal_quality",
}

# Update intervals
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=5)  # 5 seconds
MIN_UPDATE_INTERVAL = 1  # 1 second
MAX_UPDATE_INTERVAL = 30  # 30 seconds
# MQTT messages arrive ~2/s per device. Without a cap every message triggers a
# full round of entity updates, which is wasted work when the poll interval is
# 5s. Values still merge into coordinator.data on every message; only the
# listener refresh is capped.
#
# NOTE: this does NOT reduce recorder volume. The sensors genuinely fluctuate
# ~1x/second (measured: 10 distinct values in 15 min; rounding to 2dp recovers
# only 15%), so the recorder writes on real change regardless of this cap.
MQTT_NOTIFY_THROTTLE = 1.0  # seconds
TOKEN_REFRESH_DAYS_BEFORE_EXPIRY = 7  # days
RETRY_MAX_ATTEMPTS = 3
# Exponential backoff between attempts. With RETRY_MAX_ATTEMPTS = 3 there are
# only two gaps, so the real waits are 1s then 2s — the comment here used to
# claim "1s, 2s, 4s", which would need four attempts.
RETRY_BACKOFF_FACTOR = 2

# Sensor definitions

# Charge power ceiling in watts: ~100 V x 60 A = 6000 W per MPPT; 15 kW is a
# safe ceiling. Values above it are firmware overflow sentinels (a real device
# has been observed reporting 2147483.647 W and 2.5e7 W) and must be dropped
# everywhere the value is consumed.
CHARGE_POWER_MAX_W = 15000

SENSOR_TYPES: dict[str, dict[str, Any]] = {
    "pv_voltage": {
        "name": "PV Voltage",
        "unit": "V",
        "icon": "mdi:lightning-bolt",
        "device_class": "voltage",
        "state_class": "measurement",
        "max_value": 150,  # Spec 18-100V; reject garbage above 150V
    },
    "pv_current": {
        "name": "PV Current",
        "unit": "A",
        "icon": "mdi:current-ac",
        "device_class": "current",
        "state_class": "measurement",
        "max_value": 100,  # 60A max; reject garbage above 100A
    },
    "bat_voltage": {
        "name": "Battery Voltage",
        "unit": "V",
        "icon": "mdi:battery",
        "device_class": "voltage",
        "state_class": "measurement",
        "max_value": 150,  # Spec 6-120V; reject garbage above 150V
    },
    "bat_current": {
        "name": "Battery Current",
        "unit": "A",
        "icon": "mdi:current-ac",
        "device_class": "current",
        "state_class": "measurement",
        "max_value": 100,  # 60A max; reject garbage above 100A
    },
    "charge_power": {
        "name": "Charge Power",
        "unit": "W",
        "icon": "mdi:solar-power",
        "device_class": "power",
        "state_class": "measurement",
        "max_value": CHARGE_POWER_MAX_W,
    },
    "today_kwh": {
        "name": "Today Energy",
        "unit": "kWh",
        "icon": "mdi:solar-panel",
        "device_class": "energy",
        # Home Assistant rejects state_class "measurement" combined with
        # device_class "energy": it logs a warning per entity and refuses to
        # build statistics. "total_increasing" is the correct class for a daily
        # production counter — the device resets it to 0 at local midnight and
        # HA's statistics engine treats that drop as a new meter cycle.
        "state_class": "total_increasing",
        "max_value": 500,  # Daily kWh ceiling
    },
    "total_kwh": {
        "name": "Total Energy",
        "unit": "kWh",
        "icon": "mdi:chart-line",
        "device_class": "energy",
        "state_class": "total_increasing",
        "max_value": 999999,  # Lifetime kWh ceiling
    },
    "temperature": {
        "name": "Temperature",
        "unit": "°C",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "state_class": "measurement",
        "max_value": 100,  # Electronics max temp
    },
    "signal_quality": {
        "name": "WiFi Signal",
        "unit": "%",
        "icon": "mdi:wifi",
        "device_class": None,
        "state_class": "measurement",
        "max_value": 100,  # 0-100% range
    },
    "status": {
        "name": "Status",
        "unit": None,
        "icon": "mdi:information",
        "device_class": None,
        "state_class": None,
        # No max_value — status is a string code
    },
}

# Statistics sensors — computed by HA from raw data.
# These provide daily stats the SmartSolar server doesn't store long-term.
# HA's recorder auto-persists total_increasing sensors to long-term statistics;
# utility_meter handles daily/monthly/yearly bucketing from total_kwh.
STATS_SENSOR_TYPES: dict[str, dict[str, Any]] = {
    "peak_power_today": {
        "name": "Peak Power Today",
        "unit": "W",
        "icon": "mdi:chart-peak-line",
        "device_class": "power",
        "state_class": "measurement",
    },
    "avg_power_today": {
        "name": "Avg Power Today",
        "unit": "W",
        "icon": "mdi:chart-bell-curve",
        "device_class": "power",
        "state_class": "measurement",
    },
    "production_hours_today": {
        "name": "Production Hours Today",
        "unit": "h",
        "icon": "mdi:sun-clock",
        "device_class": None,
        "state_class": "measurement",
    },
}

# All sensor types combined (for iteration)
ALL_SENSOR_TYPES: dict[str, dict[str, Any]] = {**SENSOR_TYPES, **STATS_SENSOR_TYPES}

# How to combine a sensor across the devices of a project when the server's
# ``synthesisStreams`` value is missing or unreliable.
#
#  * "sum"     — currents, power and energy add up
#  * "average" — voltage, temperature and WiFi signal are shared measurements;
#                summing them produces nonsense (26.6 V + 26.4 V = 53.0 V on a
#                24 V system)
#  * "max"     — a single value that describes the whole project is best taken
#                from the most affected device (status)
#
# Devices in one project sit on the SAME battery bus, so voltage/temperature
# must never be summed.
AGGREGATION: dict[str, str] = {
    "pv_current": "sum",
    "bat_current": "sum",
    "charge_power": "sum",
    "today_kwh": "sum",
    "total_kwh": "sum",
    "pv_voltage": "average",
    "bat_voltage": "average",
    "temperature": "average",
    "signal_quality": "average",
    "status": "max",
}

# Sensors whose server-side synthesisStreams value is known to be unreliable.
# For these we always aggregate from the individual deviceLogs instead.
UNRELIABLE_SYNTHESIS_SENSORS = frozenset({"charge_power", "pv_current", "bat_current", "signal_quality"})

# API response field name → internal sensor type
SYNTHESIS_FIELD_MAPPING: dict[str, str] = {
    "today_kwh": "yield_today",
    "total_kwh": "yield_total",
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
STATUS_MAPPING: dict[int, str] = {
    0: "Online",
    1: "Charging",
    2: "Idle (No Sun)",
    3: "Fault",
}


def get_sensor_info(sensor_type: str) -> dict[str, Any]:
    """Get sensor info from ALL_SENSOR_TYPES dict."""
    return ALL_SENSOR_TYPES.get(sensor_type, {})


def get_aggregation(sensor_type: str) -> str:
    """Get the cross-device aggregation strategy for a sensor type."""
    return AGGREGATION.get(sensor_type, "sum")


def build_device_info(entry_id: str, mode: str | None = None, project_id: str | None = None) -> DeviceInfo:
    """Build shared DeviceInfo dict for SmartSolar MPPT entities."""
    if mode == "project" and project_id:
        device_name = f"SmartSolar MPPT Project {project_id}"
    elif mode == "project":
        device_name = "SmartSolar MPPT Project"
    else:
        device_name = "SmartSolar MPPT Device"
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=device_name,
        manufacturer="SmartSolar",
        model="MPPT Controller",
        sw_version=VERSION,
        hw_version="MPPT",
        configuration_url="https://smartsolar.io.vn/",
    )
