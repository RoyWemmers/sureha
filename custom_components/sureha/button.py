"""Support for Sure Petcare buttons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType
from surepy.entities.pet import Pet as SurePet

from . import SurePetcareAPI, SPC
from .const import DOMAIN, SURE_MANUFACTURER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sure Petcare buttons."""
    _LOGGER.debug("Setting up buttons")
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
            _LOGGER.debug("Adding indoor-only buttons for pet: %s", surepy_entity.name)
            entities.extend([
                EnableIndoorOnlyButton(spc.coordinator, spc, surepy_entity.id),
                DisableIndoorOnlyButton(spc.coordinator, spc, surepy_entity.id)
            ])

    _LOGGER.debug("Adding %d buttons", len(entities))
    async_add_entities(entities)


class IndoorOnlyButtonBase(CoordinatorEntity, ButtonEntity):
    """Base class for indoor-only mode buttons."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator, spc: SurePetcareAPI, pet_id: int
    ) -> None:
        """Initialize the Sure Petcare Indoor Only button."""
        super().__init__(coordinator)
        self._spc = spc
        self._id = pet_id

        if pet_id is None:
            raise ValueError("Pet ID is required")

        self._surepy_entity: SurePet = self.coordinator.data[self._id]
        pet_data = self._surepy_entity.raw_data()
        
        # Set up name and model
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = self._surepy_entity.name if self._surepy_entity.name else f"Unnamed {type_name}"
        model = type_name
        if tag_id := pet_data.get("tag_id"):
            model = f"{model} ({tag_id})"

        # Set up unique ID and device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": name,
            "manufacturer": SURE_MANUFACTURER,
            "model": model,
            "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._id in self.coordinator.data


class EnableIndoorOnlyButton(IndoorOnlyButtonBase):
    """Button to enable indoor-only mode."""

    _attr_translation_key = "enable_indoor_only_mode"

    def __init__(self, coordinator, spc: SurePetcareAPI, pet_id: int) -> None:
        """Initialize the button."""
        super().__init__(coordinator, spc, pet_id)
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-enable-indoor-only"
        self._attr_name = f"{self._surepy_entity.name} Enable Indoor Only Mode"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Enabling indoor-only mode for pet: %s", self._surepy_entity.name)
        await self._spc.set_indoor_only(self._id, True)
        await self.coordinator.async_request_refresh()


class DisableIndoorOnlyButton(IndoorOnlyButtonBase):
    """Button to disable indoor-only mode."""

    _attr_translation_key = "disable_indoor_only_mode"

    def __init__(self, coordinator, spc: SurePetcareAPI, pet_id: int) -> None:
        """Initialize the button."""
        super().__init__(coordinator, spc, pet_id)
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-disable-indoor-only"
        self._attr_name = f"{self._surepy_entity.name} Disable Indoor Only Mode"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Disabling indoor-only mode for pet: %s", self._surepy_entity.name)
        await self._spc.set_indoor_only(self._id, False)
        await self.coordinator.async_request_refresh()
