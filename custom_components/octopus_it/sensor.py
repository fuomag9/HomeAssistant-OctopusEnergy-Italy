from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TYPES


def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up sensors for Octopus Italy from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for sensor_key, (name, unit, _) in SENSOR_TYPES.items():
        entities.append(
            OctopusSensor(coordinator, entry.entry_id, sensor_key, name, unit)
        )

    async_add_entities(entities)


class OctopusSensor(CoordinatorEntity, SensorEntity):
    """Defines an Octopus Italy sensor for daily usage (total or F1/F2/F3)."""

    def __init__(self, coordinator, entry_id, sensor_key, friendly_name, unit):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._sensor_key = sensor_key
        self._attr_name = f"Octopus IT {friendly_name}"
        self._attr_unique_id = f"{entry_id}_{sensor_key}"
        self._attr_icon = "mdi:flash"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def state(self):
        """Return the state of the sensor (a float value)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._sensor_key)

    @property
    def extra_state_attributes(self):
        """Optionally expose additional attributes (e.g. last update timestamp)."""
        return {"last_updated": self.coordinator.last_update_success}

    async def async_update(self):
        """Disabled because we let the coordinator do the polling."""
        pass