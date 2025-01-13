"""The surepetcare integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from random import choice
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from surepy import Surepy
from surepy.entities import SurepyEntity
from surepy.enums import EntityType, Location, LockState
from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError
import voluptuous as vol

from .const import (
    ATTR_ENABLED,
    ATTR_FLAP_ID,
    ATTR_LOCK_STATE,
    ATTR_PET_ID,
    ATTR_VOLTAGE_FULL,
    ATTR_VOLTAGE_LOW,
    ATTR_WHERE,
    DOMAIN,
    SERVICE_PET_LOCATION,
    SERVICE_SET_INDOOR_ONLY_MODE,
    SERVICE_SET_LOCK_STATE,
    SPC,
    SURE_API_TIMEOUT,
    SURE_BATT_VOLTAGE_FULL,
    SURE_BATT_VOLTAGE_LOW,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR, Platform.SWITCH]
SCAN_INTERVAL = timedelta(minutes=3)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Optional(ATTR_VOLTAGE_FULL, default=SURE_BATT_VOLTAGE_FULL): cv.positive_float,
                    vol.Optional(ATTR_VOLTAGE_LOW, default=SURE_BATT_VOLTAGE_LOW): cv.positive_float,
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA,
)

CATS = [
    "/ᐠ｡▿｡ᐟ\\*ᵖᵘʳʳ",
    "/ᐠ_ꞈ_ᐟ\\ɴʏᴀ~",
    "/ᐠ ._. ᐟ\\ﾉ",
    "/ᐠ. ｡.ᐟ\\ᵐᵉᵒʷˎˊ",
    "ᶠᵉᵉᵈ ᵐᵉ /ᐠ-ⱉ-ᐟ\\ﾉ",
    "(≗ᆽ ≗)ﾉ",
]

SET_LOCK_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FLAP_ID): cv.string,
        vol.Required(ATTR_LOCK_STATE): cv.string,
    }
)

SET_PET_LOCATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PET_ID): cv.string,
        vol.Required(ATTR_WHERE): cv.string,
    }
)

SET_INDOOR_ONLY_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PET_ID): cv.string,
        vol.Required(ATTR_ENABLED): cv.boolean,
    }
)


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

    await spc.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


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

    async def set_indoor_only_mode(self, pet_id: int, enabled: bool) -> None:
        """Update the indoor-only mode of a pet."""
        await self.surepy.sac.set_indoor_only(pet_id, pet_id, enabled)

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

        await self.set_indoor_only_mode(pet_id, enabled)
        await self.coordinator.async_request_refresh()

    async def async_setup(self) -> None:
        """Set up the Sure Petcare integration."""
        _LOGGER.debug("Setting up services")

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SET_LOCK_STATE,
            self.handle_set_lock_state,
            schema=SET_LOCK_STATE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_PET_LOCATION,
            self.handle_set_pet_location,
            schema=SET_PET_LOCATION_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SET_INDOOR_ONLY_MODE,
            self.handle_set_indoor_only_mode,
            schema=SET_INDOOR_ONLY_MODE_SCHEMA,
        )
