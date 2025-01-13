"""Constants for the Sure Petcare component."""
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "sureha"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR, Platform.BUTTON]
SCAN_INTERVAL = timedelta(minutes=3)

SURE_API_TIMEOUT = 60
SURE_BATT_VOLTAGE_FULL = 1.6
SURE_BATT_VOLTAGE_LOW = 1.25

SURE_MANUFACTURER = "Sure Petcare"

# Service attributes
ATTR_FLAP_ID = "flap_id"
ATTR_PET_ID = "pet_id"
ATTR_LOCK_STATE = "lock_state"
ATTR_WHERE = "where"
ATTR_ENABLED = "enabled"
ATTR_VOLTAGE_FULL = "voltage_full"
ATTR_VOLTAGE_LOW = "voltage_low"

# Services
SERVICE_SET_LOCK_STATE = "set_lock_state"
SERVICE_PET_LOCATION = "set_pet_location"
SERVICE_SET_INDOOR_ONLY_MODE = "set_indoor_only_mode"
