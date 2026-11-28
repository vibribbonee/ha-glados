"""Per-person numbers: "Morning routine <name>" and "Sleep goal <name>".

Minutes from the alarm to the door, used for the time to get up and for the
leave time that follows a morning alarm. A person who has their own
input_number.morning_routine_<person> keeps using that one instead.

The sleep goal sets each person's bedtime before a morning alarm; it starts at
the house setting.
"""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ROUTINE_MINUTES, CONF_SLEEP_GOAL, DEFAULTS, DOMAIN
from .people import ROUTINE_UNIQUE, SLEEP_GOAL_UNIQUE, Person, real_people


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    options = {**DEFAULTS, **entry.options}
    people = real_people(hass)
    async_add_entities(
        [MorningRoutine(entry, p, int(options[CONF_ROUTINE_MINUTES])) for p in people]
        + [SleepGoal(entry, p, float(options[CONF_SLEEP_GOAL])) for p in people]
    )


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


class SleepGoal(MorningRoutine):
    """Hours of sleep this person wants before a morning alarm."""

    _attr_icon = "mdi:sleep"
    _attr_native_min_value = 4
    _attr_native_max_value = 12
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(self, entry: ConfigEntry, person: Person, default: float) -> None:
        super().__init__(entry, person, 0)
        self._attr_unique_id = SLEEP_GOAL_UNIQUE.format(person.entity_id)
        self._attr_name = f"Sleep goal {person.name}"
        self._attr_native_value = default
