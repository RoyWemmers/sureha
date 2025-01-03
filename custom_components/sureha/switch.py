"""Support for Sure Petcare Pet switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType
from surepy.entities.pet import Pet as SurePet

from . import SurePetcareAPI
from .const import DOMAIN, SPC

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sure Petcare switches."""
    _LOGGER.debug("Setting up switches")
    try:
        spc: SurePetcareAPI = hass.data[DOMAIN][config_entry.entry_id][SPC]
    except KeyError:
        _LOGGER.error(
            "Integration not ready yet. Current data: %s",
            hass.data.get(DOMAIN, {}),
        )
        return

    entities = []

    for surepy_entity in spc.coordinator.data.values():
        if surepy_entity.type == EntityType.PET:
            _LOGGER.debug("Adding indoor-only switch for pet: %s", surepy_entity.name)
            entities.append(IndoorOnlyModeSwitch(spc.coordinator, surepy_entity.id, spc))

    _LOGGER.debug("Adding %d switches", len(entities))
    async_add_entities(entities)


class IndoorOnlyModeSwitch(CoordinatorEntity, SwitchEntity):
    """Sure Petcare Indoor Only Mode Switch."""

    _attr_has_entity_name = True
    _attr_translation_key = "indoor_only_mode"
    _attr_entity_category = None

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._id = _id
        self._spc: SurePetcareAPI = spc

        if _id is None:
            raise ValueError("Pet ID is required")

        self._surepy_entity: SurePet = self.coordinator.data[self._id]
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = (
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        # Set up unique ID and device info
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-indoor-only"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": name,
            "manufacturer": "Sure Petcare",
            "model": type_name,
            "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        """Return true if indoor only mode is on."""
        try:
            pet_data = self.coordinator.data[self._id]
            raw_data = pet_data.raw_data()
            _LOGGER.debug("Pet %s raw data: %s", self._id, raw_data)
            return bool(raw_data.get("indoor_only", False))
        except (KeyError, AttributeError) as err:
            _LOGGER.warning("Could not get indoor_only state for pet %s: %s", self._id, err)
            return False

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
