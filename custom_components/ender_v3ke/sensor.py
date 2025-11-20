"""Sensor entities for the Ender V3KE integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@dataclass
class EnderSensorEntityDescription(SensorEntityDescription):
    """Describe an Ender V3KE sensor."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None


SENSOR_DESCRIPTIONS: tuple[EnderSensorEntityDescription, ...] = (
    EnderSensorEntityDescription(
        key="progress",
        name="Print Progress",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("progress"),
        suggested_display_precision=1,
    ),
    EnderSensorEntityDescription(
        key="layer",
        name="Current Layer",
        value_fn=lambda data: data.get("layer"),
    ),
    EnderSensorEntityDescription(
        key="total_layers",
        name="Total Layers",
        value_fn=lambda data: data.get("total_layers"),
    ),
    EnderSensorEntityDescription(
        key="elapsed",
        name="Elapsed Print Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("elapsed"),
    ),
    EnderSensorEntityDescription(
        key="remaining",
        name="Remaining Print Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("remaining"),
    ),
    EnderSensorEntityDescription(
        key="nozzle_temp",
        name="Nozzle Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda data: data.get("nozzle_temp"),
    ),
    EnderSensorEntityDescription(
        key="bed_temp",
        name="Bed Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda data: data.get("bed_temp"),
    ),
    EnderSensorEntityDescription(
        key="used_filament",
        name="Used Filament Length",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("used_filament"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ender V3KE sensors based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = [
        EnderSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class EnderSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Ender V3KE sensor."""

    def __init__(
        self,
        coordinator,
        entry,
        description: EnderSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._entry = entry

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(data)
        return data.get(self.entity_description.key)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title or "Ender V3KE", 
            "manufacturer": "Creality",
            "model": "Ender V3KE",
        }

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        filename = data.get("filename")
        image_url = data.get("image_url")
        attrs = {}
        if filename:
            attrs["filename"] = filename
        if image_url:
            attrs["image_url"] = image_url
        return attrs or None
