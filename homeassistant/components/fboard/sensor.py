from datetime import timedelta
import logging
from typing import Any, List

import async_timeout
from fireboard_cloud_api_client import (
    FireboardAPI,
    FireboardApiAuthError,
    FireboardApiError,
)
from fireboard_cloud_api_client.api import TEMP_CELSIUS
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    PERCENTAGE,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType, QueryType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> bool:

    api_client = hass.data[DOMAIN][entry.entry_id]

    async def async_update_data():
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                device_list_data = await api_client.list_devices()
                entities = {}
                for device_data in device_list_data:
                    unit_of_measurement = (
                        TEMP_FAHRENHEIT
                        if device_data["degreetype"] == 2
                        else TEMP_CELSIUS
                    )
                    parent_device = {
                        "hardware_id": device_data["hardware_id"],
                        "uuid": device_data["uuid"],
                        "id": device_data["id"],
                        "manufacturer": "Fireboard Labs",
                        "model": device_data["model"],
                        "name": device_data["title"],
                        "sw_version": device_data["version"],
                        "mac_id": device_data["device_log"]["macNIC"],
                        "battery": device_data["last_battery_reading"] * 100,
                        "unit_of_measurement": unit_of_measurement,
                    }
                    battery_unique_id = f"{parent_device['hardware_id']}_battery"
                    battery_sensor = {
                        "parent_device": parent_device,
                        "unique_id": battery_unique_id,
                    }
                    entities[battery_unique_id] = battery_sensor

                    for channel_data in device_data["channels"]:
                        channel_temp = next(
                            (
                                x["temp"]
                                for x in device_data["latest_temps"]
                                if x["channel"] == channel_data["channel"]
                            ),
                            None,
                        )

                        sensor_entity = {
                            **channel_data,
                            "parent_device": parent_device,
                            "state": channel_temp,
                        }
                        unique_id = f"{parent_device['hardware_id']}_{sensor_entity['channel']:02}"
                        sensor_entity["unique_id"] = unique_id
                        entities[unique_id] = sensor_entity
                return entities

        except FireboardApiAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except FireboardApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        # Name of the data. For logging purposes.
        name="fireboard",
        update_method=async_update_data,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=timedelta(seconds=20),
    )

    await coordinator.async_config_entry_first_refresh()

    fireboardEntities = []
    for k, v in coordinator.data.items():
        if "battery" in k:
            fireboardEntities.append(FireboardBattery(coordinator, k))
        else:
            fireboardEntities.append(FireboardSensor(coordinator, k))

    async_add_entities(fireboardEntities)


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the sensor platform."""
    LOGGER.info("async_setup_platform")


class FireboardBattery(CoordinatorEntity, SensorEntity):
    """An entity that represents a fireboard probe sensor."""

    def __init__(self, coordinator, unique_id):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self._unique_id = unique_id

    @property
    def raw_data(self) -> dict:
        return self.coordinator.data[self._unique_id]

    @property
    def unique_id(self) -> str:
        """Return The unique id of this sensor."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return The name of this sensor."""
        return f"{self.raw_data['parent_device']['name']} Battery"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Fireboard device."""
        return {
            "manufacturer": self.raw_data["parent_device"]["manufacturer"],
            "model": self.raw_data["parent_device"]["model"],
            "name": self.raw_data["parent_device"]["name"],
            "sw_version": self.raw_data["parent_device"]["sw_version"],
            "identifiers": {
                ("fireboard", self.raw_data["parent_device"]["hardware_id"])
            },
            "connections": {
                (dr.CONNECTION_NETWORK_MAC, self.raw_data["parent_device"]["mac_id"])
            },
        }

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_BATTERY

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return PERCENTAGE

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.raw_data["parent_device"]["battery"]


class FireboardSensor(CoordinatorEntity, SensorEntity):
    """An entity that represents a fireboard probe sensor."""

    def __init__(self, coordinator, unique_id):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self._unique_id = unique_id

    @property
    def raw_data(self) -> dict:
        return self.coordinator.data[self._unique_id]

    @property
    def name(self) -> str:
        """Return The name of this sensor."""
        channel_label = self.raw_data["channel_label"]
        return f"{self.raw_data['parent_device']['name']} {channel_label}"

    @property
    def unique_id(self) -> str:
        """Return The unique id of this sensor."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Fireboard device."""
        return {
            "manufacturer": self.raw_data["parent_device"]["manufacturer"],
            "model": self.raw_data["parent_device"]["model"],
            "name": self.raw_data["parent_device"]["name"],
            "sw_version": self.raw_data["parent_device"]["sw_version"],
            "identifiers": {
                ("fireboard", self.raw_data["parent_device"]["hardware_id"])
            },
            "connections": {
                (dr.CONNECTION_NETWORK_MAC, self.raw_data["parent_device"]["mac_id"])
            },
        }

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_TEMPERATURE

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self.raw_data["parent_device"]["unit_of_measurement"]

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.raw_data["state"]
