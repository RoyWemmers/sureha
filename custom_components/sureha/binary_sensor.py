"""Support for Sure Petcare Flap sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType, SurepyEntity
from surepy.entities.pet import Pet as SurePet
from surepy.enums import Location

from . import SurePetcareAPI, SPC
from .const import DOMAIN, SURE_MANUFACTURER

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 2


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: Any,
    discovery_info: Any = None,
) -> None:
    """Set up Sure PetCare binary-sensor platform."""
    await async_setup_entry(hass, config, async_add_entities)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up config entry Sure PetCare Flaps sensors."""

    _LOGGER.debug("Setting up binary sensors")
    try:
        spc: SurePetcareAPI = hass.data[DOMAIN][config_entry.entry_id][SPC]
    except KeyError:
        _LOGGER.error(
            "Integration not ready yet. Current data: %s",
            hass.data.get(DOMAIN, {}),
        )
        return

    entities: list[SurePetcareBinarySensor] = []

    for surepy_entity in spc.coordinator.data.values():

        if surepy_entity.type == EntityType.PET:
            entities.append(Pet(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.HUB and surepy_entity.raw_data().get("status", {}).get("led_mode", {}):
            entities.append(Hub(spc.coordinator, surepy_entity.id, spc))

        # connectivity
        elif surepy_entity.type in [
            EntityType.CAT_FLAP,
            EntityType.PET_FLAP,
            EntityType.FEEDER,
            EntityType.FELAQUA,
        ]:
            entities.append(DeviceConnectivity(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]:
            entities.append(BatteryLowSensor(spc.coordinator, surepy_entity.id))

    async_add_entities(entities, True)


class SurePetcareBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A binary sensor implementation for Sure Petcare Entities."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        device_class: str,
    ):
        """Initialize a Sure Petcare binary sensor."""
        super().__init__(coordinator)

        self._id: int = _id
        self._spc: SurePetcareAPI = spc

        self._coordinator = coordinator

        self._surepy_entity: SurepyEntity = self._coordinator.data[self._id]
        self._state: Any = self._surepy_entity.raw_data().get("status", {})

        type_name = self._surepy_entity.type.name.replace("_", " ").title()

        self._name: str = (
            # cover edge case where a device has no name set
            # (dont know how to do this but people have managed to do it  ¯\_(ツ)_/¯)
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        self._attr_available = bool(self._state)

        self._attr_device_class = None if not device_class else device_class
        self._attr_name: str = f"{type_name} {self._name}"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}"

        if self._state:
            self._attr_extra_state_attributes = {**self._surepy_entity.raw_data()}

    @property
    def device_info(self):
        """Return device info."""
        try:
            type_name = self._surepy_entity.type.name.replace("_", " ").title()
            name = self._surepy_entity.name if self._surepy_entity.name else f"Unnamed {type_name}"
            model = type_name
            
            if serial := self._surepy_entity.raw_data().get("serial_number"):
                model = f"{model} ({serial})"
            elif mac_address := self._surepy_entity.raw_data().get("mac_address"):
                model = f"{model} ({mac_address})"
            elif tag_id := self._surepy_entity.raw_data().get("tag_id"):
                model = f"{model} ({tag_id})"

            return {
                "identifiers": {(DOMAIN, str(self._id))},
                "name": name,
                "manufacturer": SURE_MANUFACTURER,
                "model": model,
                "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
            }
        except (KeyError, AttributeError) as err:
            _LOGGER.debug("Could not get device info for entity %s: %s", self._id, err)
            return None


class Hub(SurePetcareBinarySensor):
    """Sure Petcare Pet."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare Hub."""
        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.CONNECTIVITY)

        if self._attr_device_info:
            self._attr_device_info["identifiers"] = {(DOMAIN, str(self._id))}

        self._attr_available = self.is_on

    @property
    def is_on(self) -> bool:
        """Return True if the hub is on."""

        hub: SurepyEntity
        online: bool = False

        if hub := self._coordinator.data[self._id]:

            self._attr_extra_state_attributes = {
                "led_mode": int(hub.raw_data()["status"]["led_mode"]),
                "pairing_mode": bool(hub.raw_data()["status"]["pairing_mode"]),
            }

            online = hub.online

        return online


class Pet(SurePetcareBinarySensor):
    """Sure Petcare Pet."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare Pet."""
        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.PRESENCE)

        # explicit typing
        self._surepy_entity: SurePet

        # picture of the pet that can be added via the sure app/website
        self._attr_entity_picture = self._surepy_entity.photo_url

        # Set device info
        pet_data = self._surepy_entity.raw_data()
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = self._surepy_entity.name if self._surepy_entity.name else f"Unnamed {type_name}"
        model = type_name
        if tag_id := pet_data.get("tag_id"):
            model = f"{model} ({tag_id})"

        self._attr_name = f"{name} Presence"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": name,
            "manufacturer": SURE_MANUFACTURER,
            "model": model,
            "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
        }

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
    def is_on(self) -> bool:
        """Return True if the pet is at home."""

        pet: SurePet
        inside: bool = False

        if pet := self._coordinator.data[self._id]:
            inside = bool(pet.location.where == Location.INSIDE)

        return inside


class DeviceConnectivity(SurePetcareBinarySensor):
    """Sure Petcare Connectivity Sensor."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        """Initialize a Sure Petcare device connectivity sensor."""

        super().__init__(coordinator, _id, spc, BinarySensorDeviceClass.CONNECTIVITY)

        self._attr_name = f"{self._name} Connectivity"
        self._attr_unique_id = (
            f"{self._surepy_entity.household_id}-{self._id}-connectivity"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        device: SurepyEntity
        attrs: dict[str, Any] = {}

        if (device := self._coordinator.data[self._id]) and (
            state := device.raw_data().get("status")
        ):
            attrs = {
                "device_rssi": f'{state["signal"]["device_rssi"]:.2f}',
                "hub_rssi": f'{state["signal"]["hub_rssi"]:.2f}',
            }

        return attrs

    @property
    def is_on(self) -> bool:
        """Return True if the pet is at home."""
        return bool(self.extra_state_attributes)


class BatteryLowSensor(CoordinatorEntity, BinarySensorEntity):
    """Sure Petcare Battery Low Sensor."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY

    def __init__(self, coordinator, _id: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._id = _id
        self._surepy_entity: SurepyEntity = coordinator.data[_id]

        # Set up unique ID and device info
        type_name = self._surepy_entity.type.name.replace("_", " ").title()
        name: str = (
            self._surepy_entity.name
            if self._surepy_entity.name
            else f"Unnamed {type_name}"
        )

        self._attr_name = f"{name} Battery Low"
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}-battery-low"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": name,
            "manufacturer": SURE_MANUFACTURER,
            "model": type_name,
            "via_device": (DOMAIN, f"household_{self._surepy_entity.household_id}"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        """Return True if battery is low."""
        try:
            device: SurepyEntity = self.coordinator.data[self._id]
            return device.raw_data().get("battery", {}).get("low", False)
        except (KeyError, AttributeError) as err:
            _LOGGER.warning("Could not get battery state for device %s: %s", self._id, err)
            return False
