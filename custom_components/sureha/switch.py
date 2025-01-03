"""Support for Sure Petcare Pet switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import SurepyEntity
from surepy.entities.pet import Pet as SurePet
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
    _LOGGER.debug("Setting up Sure Petcare switches")

    for surepy_entity in spc.coordinator.data.values():
        _LOGGER.debug(
            "Found entity: %s (type: %s, id: %s)",
            surepy_entity.name,
            surepy_entity.type,
            surepy_entity.id,
        )
        if surepy_entity.type == EntityType.PET:
            _LOGGER.debug("Adding indoor-only switch for pet: %s", surepy_entity.name)
            entities.append(IndoorOnlyModeSwitch(spc.coordinator, surepy_entity.id, spc))

    _LOGGER.debug("Adding %d switches", len(entities))
    async_add_entities(entities, True)


class IndoorOnlyModeSwitch(CoordinatorEntity, SwitchEntity):
    """Sure Petcare Indoor Only Mode Switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._id = _id
        self._spc: SurePetcareAPI = spc

        self._surepy_entity: SurePet = self.coordinator.data[self._id]
        self._attr_name = f"{self._surepy_entity.name} Indoor Only Mode"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-indoor-only"
        
        # Set up device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": self._surepy_entity.name,
            "manufacturer": "Sure Petcare",
            "model": "Pet",
            "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        """Return true if indoor only mode is on."""
        return bool(self.coordinator.data[self._id].indoor_only_mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the indoor only mode on."""
        _LOGGER.debug("Turning on indoor-only mode for pet: %s", self._surepy_entity.name)
        await self._spc.set_indoor_only_mode(self._id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the indoor only mode off."""
        _LOGGER.debug("Turning off indoor-only mode for pet: %s", self._surepy_entity.name)
        await self._spc.set_indoor_only_mode(self._id, False)
        await self.coordinator.async_request_refresh()
