"""Per-person bedtime and last call, as timestamp sensors for dashboards."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .bedtime import bedtime_for
from .const import DOMAIN
from .people import Person, all_people

UPDATE_EVERY = timedelta(minutes=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """A bedtime and a last-call sensor for every person."""
    async_add_entities(
        BedtimeSensor(entry, person, kind)
        for person in all_people(hass)
        for kind in ("bedtime", "last_call")
    )


class BedtimeSensor(SensorEntity):
    """When this person should be asleep, or their last call."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, person: Person, kind: str) -> None:
        self._entry = entry
        self._person = person.entity_id
        self._kind = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}_{person.entity_id}"
        self._attr_name = f"{'Bedtime' if kind == 'bedtime' else 'Last call'} {person.name}"
        self._attr_icon = "mdi:bed-clock" if kind == "bedtime" else "mdi:alarm-light"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    async def async_added_to_hass(self) -> None:
        self._refresh()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._refresh, UPDATE_EVERY)
        )

    @callback
    def _refresh(self, now: datetime | None = None) -> None:
        state = self.hass.states.get(self._person)
        if state is None:
            return
        person = Person(state.entity_id, state.name, state.state)
        bt = bedtime_for(self.hass, {**self._entry.options}, person)
        value: datetime | None = bt.bedtime if self._kind == "bedtime" else bt.last_call
        self._attr_native_value = value
        self._attr_extra_state_attributes = {
            "alarm": bt.alarm.isoformat() if bt.alarm else None,
        }
        self.async_write_ha_state()
