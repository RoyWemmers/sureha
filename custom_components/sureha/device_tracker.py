"""Support for Sure Petcare Flap sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType
from surepy.entities.pet import Pet as SurePet
from surepy.enums import Location

from . import SurePetcareAPI, SPC
from .const import DOMAIN, SURE_MANUFACTURER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sure Petcare device trackers."""
    _LOGGER.debug("Setting up device trackers")
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
            entities.append(
                SureDeviceTracker(spc.coordinator, surepy_entity.id, spc)
            )

    async_add_entities(entities)


class SureDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Pet device tracker."""

    _attr_force_update = False
    _attr_icon = "mdi:cat"

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        """Initialize the tracker."""
        super().__init__(coordinator)

        self._spc: SurePetcareAPI = spc
        self._coordinator = coordinator

        if _id is None:
            raise ValueError("Pet ID is required")

        self._id = _id
        self._attr_unique_id = f"{self._id}_pet_tracker"

        self._surepy_entity: SurePet = self._coordinator.data[self._id]
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = (
            # cover edge case where a device has no name set
            # (dont know how to do this but people have managed to do it  ¯\_(ツ)_/¯)
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        self._attr_name: str = f"{type_name} {name}"

        # picture of the pet that can be added via the sure app/website
        self._attr_entity_picture = self._surepy_entity.photo_url

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        return bool(self.location_name == "home")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        pet: SurePet
        attrs: dict[str, Any] = {}

        if pet := self._coordinator.data[self._id]:

            attrs = {
                "since": pet.location.since,
                "where": pet.location.where,
                **pet.raw_data(),
            }

        return attrs

    @property
    def location_name(self) -> str:
        """Return 'home' if the pet is at home."""

        pet: SurePet
        inside: bool = False

        if pet := self._coordinator.data[self._id]:
            inside = bool(pet.location.where == Location.INSIDE)

        return "home" if inside else "not_home"

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the pet."""
        return SourceType.GPS
