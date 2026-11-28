"""A usual bedtime for every person: "Usual bedtime <name>".

Bedtime on nights without a morning alarm. Empty (unknown) uses the house's
usual bedtime from the settings; that empty too, no nudges on such nights.
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .dates import parse_time
from .people import USUAL_BEDTIME_UNIQUE, Person, real_people


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(UsualBedtime(entry, p) for p in real_people(hass))


class UsualBedtime(TimeEntity, RestoreEntity):
    """When this person usually goes to bed, on nights with no morning alarm."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bed-clock"

    def __init__(self, entry: ConfigEntry, person: Person) -> None:
        self._attr_unique_id = USUAL_BEDTIME_UNIQUE.format(person.entity_id)
        self._attr_name = f"Usual bedtime {person.name}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            self._attr_native_value = parse_time(last.state)

    async def async_set_value(self, value: time) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
