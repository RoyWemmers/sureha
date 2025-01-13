"""Support for Sure Petcare cat/pet flaps."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import async_timeout
import voluptuous as vol
from surepy import Surepy
from surepy.client import SureAPIClient
from surepy.const import BASE_RESOURCE
from surepy.entities import SurepyEntity
from surepy.entities.pet import Pet
from surepy.enums import EntityType, Location, LockState
from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_ENABLED,
    ATTR_FLAP_ID,
    ATTR_LOCK_STATE,
    ATTR_PET_ID,
    ATTR_VOLTAGE_FULL,
    ATTR_VOLTAGE_LOW,
    ATTR_WHERE,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL,
    SERVICE_PET_LOCATION,
    SERVICE_SET_INDOOR_ONLY_MODE,
    SERVICE_SET_LOCK_STATE,
    SURE_API_TIMEOUT,
    SURE_BATT_VOLTAGE_FULL,
    SURE_BATT_VOLTAGE_LOW,
    SURE_MANUFACTURER,
)

_LOGGER = logging.getLogger(__name__)

SPC = "spc"

CATS = [
    "/ᐠ｡▿｡ᐟ\\*ᵖᵘʳʳ",
    "/ᐠ_ꞈ_ᐟ\\ɴʸᴀ~",
    "/ᐠ ._. ᐟ\\ﾉ",
    "/ᐠ. ｡.ᐟ\\ᵐᵉᵒʷˎˊ",
    "ᶠᵉᵉᵈ ᵐᵉ /ᐠ-ⱉ-ᐟ\\ﾉ",
    "(≗ᆽ ≗)ﾉ",
]

SET_LOCK_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FLAP_ID): vol.Coerce(str),
        vol.Required(ATTR_LOCK_STATE): vol.Coerce(str),
    }
)

SET_PET_LOCATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PET_ID): vol.Coerce(str),
        vol.Required(ATTR_WHERE): vol.Coerce(str),
    }
)

SET_INDOOR_ONLY_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PET_ID): vol.Coerce(str),
        vol.Required(ATTR_ENABLED): vol.Coerce(bool),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Sure Petcare component."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        return True

    _LOGGER.debug("Setting up Sure Petcare component")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up."""
    _LOGGER.debug("Setting up Sure Petcare integration")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    # set option defaults
    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                ATTR_VOLTAGE_FULL: SURE_BATT_VOLTAGE_FULL,
                ATTR_VOLTAGE_LOW: SURE_BATT_VOLTAGE_LOW,
            },
        )

    websession = async_get_clientsession(hass)

    try:
        surepy = Surepy(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            auth_token=entry.data.get(CONF_TOKEN),
            api_timeout=SURE_API_TIMEOUT,
            session=websession,
        )

        await surepy.sac.get_token()

    except SurePetcareAuthenticationError as err:
        raise ConfigEntryAuthFailed from err

    spc = SurePetcareAPI(hass, entry, surepy)

    async def async_update_data():
        try:
            async with async_timeout.timeout(20):
                return await spc.async_update_states()
        except SurePetcareAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except SurePetcareError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    spc.coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sureha_sensors",
        update_method=async_update_data,
        update_interval=timedelta(seconds=150),
    )

    await spc.coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id][SPC] = spc

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LOCK_STATE,
        spc.handle_set_lock_state,
        schema=SET_LOCK_STATE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PET_LOCATION,
        spc.handle_set_pet_location,
        schema=SET_PET_LOCATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INDOOR_ONLY_MODE,
        spc.handle_set_indoor_only_mode,
        schema=SET_INDOOR_ONLY_MODE_SCHEMA,
    )

    await spc.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    _LOGGER.debug("Removing Sure Petcare integration")
    
    # Get the device registry
    device_registry = dr.async_get(hass)
    
    # Find all devices associated with this config entry
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    
    # Remove all devices
    for device in devices:
        _LOGGER.debug("Removing device: %s", device.id)
        device_registry.async_remove_device(device.id)


class SurePetcareAPI:
    """Define a generic Sure Petcare object."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, surepy: Surepy
    ) -> None:
        """Initialize the Sure Petcare object."""

        self.coordinator: DataUpdateCoordinator

        self.hass = hass
        self.config_entry = config_entry
        self.surepy = surepy

        self.states: dict[int, Any] = {}

    async def async_update_states(self):
        """Get all devices and their states."""
        return await self.surepy.get_entities()

    async def set_pet_location(self, pet_id: int, location: Location) -> None:
        """Update the location of a pet."""
        await self.surepy.sac.update_pet_location(pet_id, location)

    async def set_lock_state(self, flap_id: int, state: str) -> None:
        """Update the lock state of a flap."""
        await self.surepy.sac.update_flap_lock_state(flap_id, LockState[state.upper()])

    async def set_indoor_only_mode(self, device_id: int, tag_id: int, enabled: bool) -> None:
        """Set indoor only mode for a pet.

        Args:
            device_id (int): The ID of the device
            tag_id (int): The ID of the pet's tag
            enabled (bool): True to enable indoor only mode, False to disable
        """
        _LOGGER.debug("Setting indoor-only mode for device %s and tag %s to %s", device_id, tag_id, enabled)
        profile = 3 if enabled else 2
        resource = f"{BASE_RESOURCE}/device/{device_id}/tag/{tag_id}"
        data = {"profile": profile}
        _LOGGER.debug("Making API call to %s with data: %s", resource, data)
        response = await self.surepy.sac.call(method="PUT", resource=resource, data=data)
        _LOGGER.debug("API response: %s", response)

    async def set_indoor_only(self, pet_id: int, enabled: bool) -> None:
        """Set indoor-only mode for a pet."""
        _LOGGER.debug("Setting indoor-only mode to %s for pet %s", enabled, pet_id)
        
        # Get the pet data
        pet_data = self.coordinator.data[pet_id]
        raw_data = pet_data.raw_data()
        
        # Get the device and tag IDs
        tag_id = raw_data.get('tag_id')
        device_id = raw_data.get('status', {}).get('activity', {}).get('device_id')
        
        if not tag_id or not device_id:
            _LOGGER.error("Could not find tag_id or device_id for pet %s", pet_id)
            return
        
        # Set the profile (3 for indoor-only, 1 for normal)
        profile = 3 if enabled else 1
        resource = f"{BASE_RESOURCE}/device/{device_id}/tag/{tag_id}"
        data = {"profile": profile}
        
        try:
            await self.surepy.sac.call(method="PUT", resource=resource, data=data)
            _LOGGER.debug("Successfully set indoor-only mode to %s for pet %s", enabled, pet_id)
        except Exception as err:
            _LOGGER.error("Failed to set indoor-only mode: %s", err)
            raise

    async def handle_set_pet_location(self, call: Any) -> None:
        """Call when setting pet location."""
        pet_id = int(call.data[ATTR_PET_ID])
        where = call.data[ATTR_WHERE]

        await self.set_pet_location(pet_id, Location[where.upper()])
        await self.coordinator.async_request_refresh()

    async def handle_set_lock_state(self, call: Any) -> None:
        """Call when setting the lock state."""
        flap_id = int(call.data[ATTR_FLAP_ID])
        state = call.data[ATTR_LOCK_STATE]

        await self.set_lock_state(flap_id, state)
        await self.coordinator.async_request_refresh()

    async def handle_set_indoor_only_mode(self, call: Any) -> None:
        """Call when setting indoor-only mode."""
        pet_id = int(call.data[ATTR_PET_ID])
        enabled = call.data[ATTR_ENABLED]

        await self.set_indoor_only(pet_id, enabled)
        await self.coordinator.async_request_refresh()

    async def async_setup(self) -> None:
        """Set up the Sure Petcare integration."""
        _LOGGER.debug("Setting up services")
