"""Constants for the Sure Petcare integration."""

DOMAIN = "sureha"

SPC = "spc"

SURE_API_TIMEOUT = 30

# Battery voltage levels
SURE_BATT_VOLTAGE_FULL = 1.6  # voltage when batteries are full
SURE_BATT_VOLTAGE_LOW = 1.25  # voltage when batteries are low

# Manufacturer
SURE_MANUFACTURER = "Sure Petcare"

# Service names
SERVICE_SET_LOCK_STATE = "set_lock_state"
SERVICE_PET_LOCATION = "set_pet_location"
SERVICE_SET_INDOOR_ONLY_MODE = "set_indoor_only_mode"

# Attributes
ATTR_FLAP_ID = "flap_id"
ATTR_PET_ID = "pet_id"
ATTR_WHERE = "where"
ATTR_LOCK_STATE = "state"
ATTR_ENABLED = "enabled"
ATTR_VOLTAGE_FULL = "voltage_full"
ATTR_VOLTAGE_LOW = "voltage_low"
