"""Support for Tailscale sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from tailscale import Device as TailscaleDevice

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TailscaleEntity
from .const import DOMAIN


@dataclass
class TailscaleSensorEntityDescriptionMixin:
    """Mixin for required keys."""

    value_fn: Callable[[TailscaleDevice], datetime | None]


@dataclass
class TailscaleSensorEntityDescription(
    SensorEntityDescription, TailscaleSensorEntityDescriptionMixin
):
    """Describes a Tailscale sensor entity."""


SENSORS: tuple[TailscaleSensorEntityDescription, ...] = (
    TailscaleSensorEntityDescription(
        key="expires",
        name="Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda device: device.expires,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Tailscale sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        TailscaleSensorEntity(
            coordinator=coordinator,
            device=device,
            description=description,
        )
        for device in coordinator.data.values()
        for description in SENSORS
    )


class TailscaleSensorEntity(TailscaleEntity, SensorEntity):
    """Defines a Tailscale sensor."""

    entity_description: TailscaleSensorEntityDescription

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data[self.device_id])
