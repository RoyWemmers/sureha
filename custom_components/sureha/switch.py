"""Support for Sure Petcare Flap switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepy.entities import SurepyEntity
from surepy.entities.devices import Flap as SureFlap
from surepy.enums import EntityType

from . import SurePetcareAPI
from .const import DOMAIN, SPC

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sure Petcare switches."""
    spc: SurePetcareAPI = hass.data[DOMAIN][config_entry.entry_id][SPC]

    entities = []

    for surepy_entity in spc.coordinator.data.values():
        if surepy_entity.type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]:
            entities.append(IndoorOnlyModeSwitch(spc.coordinator, surepy_entity.id, spc))

    async_add_entities(entities, True)


class IndoorOnlyModeSwitch(SwitchEntity):
    """Sure Petcare Indoor Only Mode Switch."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize the switch."""
        super().__init__()
        self._coordinator = coordinator
        self._id = _id
        self._spc: SurePetcareAPI = spc

        self._surepy_entity: SureFlap = self._coordinator.data[self._id]
        self._attr_name = f"{self._surepy_entity.name} Indoor Only Mode"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-indoor-only"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._id)},
            "name": self._surepy_entity.name,
            "manufacturer": "Sure Petcare",
            "model": self._surepy_entity.type.name.replace("_", " ").title(),
        }

    @property
    def is_on(self) -> bool:
        """Return true if indoor only mode is on."""
        return self._surepy_entity.indoor_only_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the indoor only mode on."""
        await self._spc.set_indoor_only_mode(self._id, True)
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the indoor only mode off."""
        await self._spc.set_indoor_only_mode(self._id, False)
        await self._coordinator.async_request_refresh()
