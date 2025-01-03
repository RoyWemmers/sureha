"""Support for Sure Petcare Flap sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import EntityType
from surepy.entities.devices import SurepyDevice

from . import SurePetcareAPI
from .const import DOMAIN, SPC

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sure Petcare sensors."""
    _LOGGER.debug("Setting up sensors")
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
        if surepy_entity.type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]:
            entities.append(
                BatterySensor(spc.coordinator, surepy_entity.id)
            )

    async_add_entities(entities)


class SurePetcareSensor(CoordinatorEntity, SensorEntity):
    """A binary sensor implementation for Sure Petcare Entities."""

    _attr_should_poll = False

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        """Initialize a Sure Petcare sensor."""
        super().__init__(coordinator)

        self._id = _id
        self._spc: SurePetcareAPI = spc

        self._coordinator = coordinator

        self._surepy_entity: SurepyEntity = self._coordinator.data[_id]
        self._state: dict[str, Any] = self._surepy_entity.raw_data()["status"]

        self._attr_available = bool(self._state)
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}"

        self._attr_extra_state_attributes = (
            {**self._surepy_entity.raw_data()} if self._state else {}
        )

        self._attr_name: str = (
            f"{self._surepy_entity.type.name.replace('_', ' ').title()} "
            f"{self._surepy_entity.name.capitalize()}"
        )

    @property
    def device_info(self):

        device = {}

        try:

            model = f"{self._surepy_entity.type.name.replace('_', ' ').title()}"
            if serial := self._surepy_entity.raw_data().get("serial_number"):
                model = f"{model} ({serial})"
            elif mac_address := self._surepy_entity.raw_data().get("mac_address"):
                model = f"{model} ({mac_address})"
            elif tag_id := self._surepy_entity.raw_data().get("tag_id"):
                model = f"{model} ({tag_id})"

            device = {
                "identifiers": {(DOMAIN, self._id)},
                "name": self._surepy_entity.name.capitalize(),
                "manufacturer": SURE_MANUFACTURER,
                "model": model,
            }

            if self._state:
                versions = self._state.get("version", {})

                if dev_fw_version := versions.get("device", {}).get("firmware"):
                    device["sw_version"] = dev_fw_version

                if (lcd_version := versions.get("lcd", {})) and (
                    rf_version := versions.get("rf", {})
                ):
                    device["sw_version"] = (
                        f"lcd: {lcd_version.get('version', lcd_version)['firmware']} | "
                        f"fw: {rf_version.get('version', rf_version)['firmware']}"
                    )

        except AttributeError:
            pass

        return device


class Flap(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFlap

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = None

        if self._state:
            self._attr_extra_state_attributes = {
                "learn_mode": bool(self._state["learn_mode"]),
                **self._surepy_entity.raw_data(),
            }

            if locking := self._state.get("locking"):
                self._attr_state = LockState(locking["mode"]).name.casefold()

    @property
    def state(self) -> str | None:
        """Return battery level in percent."""
        if (
            state := cast(SureFlap, self._coordinator.data[self._id])
            .raw_data()
            .get("status")
        ):
            return LockState(state["locking"]["mode"]).name.casefold()


class Felaqua(SurePetcareSensor):
    """Sure Petcare Felaqua."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFelaqua

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = UnitOfVolume.MILLILITERS

    @property
    def state(self) -> float | None:
        """Return the remaining water."""
        if felaqua := cast(SureFelaqua, self._coordinator.data[self._id]):
            return int(felaqua.water_remaining) if felaqua.water_remaining else None


class FeederBowl(SurePetcareSensor):
    """Sure Petcare Feeder Bowl."""

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        bowl_data: dict[str, int | str],
    ):
        """Initialize a Bowl sensor."""
        super().__init__(coordinator, _id, spc)

        _LOGGER.debug("bowl_data: %s", pprint.pformat(bowl_data))

        self.feeder_id = _id

        # todo: index parameter is not available in the bowl_data anymore
        # for now we use a random number...
        self.bowl_id = random.randint(
            1, 10
        )  # int(bowl_data.get("index", random.randint(1, 10)))

        self._id = int(f"{_id}{str(self.bowl_id)}")
        self._spc: SurePetcareAPI = spc

        self._surepy_feeder_entity: SurepyEntity = self._coordinator.data[_id]

        self._state: dict[str, Any] = bowl_data

        # https://github.com/PyCQA/pylint/issues/2062
        # pylint: disable=no-member
        self._attr_name = (
            f"{EntityType.FEEDER.name.replace('_', ' ').title()} "
            f"{self._surepy_entity.name.capitalize()}"
        )

        self._attr_icon = "mdi:bowl"

        if hasattr(self._surepy_entity, "weight"):
            self._attr_state = int(self._surepy_entity.weight)

        self._attr_unique_id = (
            f"{self._surepy_feeder_entity.household_id}-{self.feeder_id}-{self.bowl_id}"
        )
        self._attr_unit_of_measurement = UnitOfMass.GRAMS

    @property
    def state(self) -> float | None:
        """Return the remaining water."""

        _LOGGER.debug(
            "self._coordinator.data[%d]: %s",
            self.feeder_id,
            pprint.pformat(self._coordinator.data[self.feeder_id]),
        )

        if (
            (feeder := cast(SureFeeder, self._coordinator.data[self.feeder_id]))
            and len(feeder.bowls) > 0
            and hasattr(feeder.bowls[self.bowl_id], "weight")
            and (weight := feeder.bowls[self.bowl_id].weight)
        ):
            return int(weight) if weight and weight > 0 else None


class Feeder(SurePetcareSensor):
    """Sure Petcare Feeder."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFeeder

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = UnitOfMass.GRAMS

    @property
    def state(self) -> float | None:
        """Return the total remaining food."""
        if feeder := cast(SureFeeder, self._coordinator.data[self._id]):
            return int(feeder.total_weight) if feeder.total_weight else None


class Battery(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        voltage_full: float,
        voltage_low: float,
    ):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SurepyDevice

        self._attr_name = f"{self._attr_name} Battery Level"

        self.voltage_low = voltage_low
        self.voltage_full = voltage_full

        self._attr_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_unique_id = (
            f"{self._surepy_entity.household_id}-{self._surepy_entity.id}-battery"
        )

    @property
    def state(self) -> int | None:
        """Return battery level in percent."""

        if battery := cast(SurepyDevice, self._coordinator.data[self._id]):

            self._surepy_entity = battery
            self.device_class = SensorDeviceClass.BATTERY
            self.native_unit_of_measurement = PERCENTAGE
            battery_level = battery.calculate_battery_level(
                voltage_full=self.voltage_full, voltage_low=self.voltage_low
            )

            # return batterie level between 0 and 100
            return battery_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        attrs = {}

        if (device := cast(SurepyDevice, self._coordinator.data[self._id])) and (
            state := device.raw_data().get("status")
        ):
            self._surepy_entity = device

            voltage = float(state["battery"])

            attrs = {
                "battery_level": device.battery_level,
                ATTR_VOLTAGE: f"{voltage:.2f}",
                f"{ATTR_VOLTAGE}_per_battery": f"{voltage / 4:.2f}",
            }

        return attrs


class BatterySensor(SurePetcareSensor):
    """Sure Petcare Battery Sensor."""

    def __init__(self, coordinator, _id: int):
        super().__init__(coordinator, _id, None)

        self._surepy_entity: SurepyDevice

        self._attr_name = f"{self._attr_name} Battery Level"

        self._attr_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_unique_id = (
            f"{self._surepy_entity.household_id}-{self._surepy_entity.id}-battery"
        )

    @property
    def state(self) -> int | None:
        """Return battery level in percent."""

        if battery := cast(SurepyDevice, self._coordinator.data[self._id]):

            self._surepy_entity = battery
            self.device_class = SensorDeviceClass.BATTERY
            self.native_unit_of_measurement = PERCENTAGE
            battery_level = battery.calculate_battery_level()

            # return batterie level between 0 and 100
            return battery_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        attrs = {}

        if (device := cast(SurepyDevice, self._coordinator.data[self._id])) and (
            state := device.raw_data().get("status")
        ):
            self._surepy_entity = device

            voltage = float(state["battery"])

            attrs = {
                "battery_level": device.battery_level,
                ATTR_VOLTAGE: f"{voltage:.2f}",
                f"{ATTR_VOLTAGE}_per_battery": f"{voltage / 4:.2f}",
            }

        return attrs
