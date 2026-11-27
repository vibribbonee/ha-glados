"""A morning routine for every person: "Morning routine <name>".

Minutes from the alarm to the door, used for the time to get up and for the
leave time that follows a morning alarm. A person who has their own
input_number.morning_routine_<person> keeps using that one instead.
"""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ROUTINE_MINUTES, DEFAULTS, DOMAIN
from .people import ROUTINE_UNIQUE, Person, real_people


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    default = int({**DEFAULTS, **entry.options}[CONF_ROUTINE_MINUTES])
    async_add_entities(MorningRoutine(entry, p, default) for p in real_people(hass))


class MorningRoutine(RestoreNumber):
    """Minutes this person needs from the alarm to the door."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-sand"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 5
    _attr_native_max_value = 180
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, entry: ConfigEntry, person: Person, default: int) -> None:
        self._attr_unique_id = ROUTINE_UNIQUE.format(person.entity_id)
        self._attr_name = f"Morning routine {person.name}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}
        self._attr_native_value = float(default)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
