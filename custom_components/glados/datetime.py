"""A leave time for every person: "Leave home <name>".

Set by voice with the Set leave time tool, or on a dashboard. A person who has
their own input_datetime.leave_home_<person> keeps using that one instead.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .people import LEAVE_UNIQUE, Person, real_people


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(LeaveTime(entry, p) for p in real_people(hass))


class LeaveTime(DateTimeEntity, RestoreEntity):
    """When this person leaves home. The year 2000 means no leave time."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:door-open"

    def __init__(self, entry: ConfigEntry, person: Person) -> None:
        self._attr_unique_id = LEAVE_UNIQUE.format(person.entity_id)
        self._attr_name = f"Leave home {person.name}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) and (at := dt_util.parse_datetime(last.state)):
            self._attr_native_value = at

    async def async_set_value(self, value: datetime) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
