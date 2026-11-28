"""Quiet mode: no unprompted speech while it is on. Alarms still ring.

Switched on by hand it stays on until switched off; by voice ("be quiet for an
hour") it ends by itself, and the switch goes off again.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN

FOREVER = datetime(2100, 1, 1, tzinfo=dt_util.UTC)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([QuietMode(entry)])


class QuietMode(SwitchEntity):
    """On: she keeps her remarks, warnings and reminders to herself (phones still get them)."""

    _attr_has_entity_name = True
    _attr_translation_key = "quiet_mode"
    _attr_icon = "mdi:volume-off"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_quiet_mode"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    @property
    def _announcer(self):
        return self._entry.runtime_data.announcer

    async def async_added_to_hass(self) -> None:
        listeners = self._announcer.listeners
        listeners.append(self._changed)
        self.async_on_remove(lambda: listeners.remove(self._changed))

    @callback
    def _changed(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._announcer.quiet_until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        until = self._announcer.quiet_until()
        return {"until": until.isoformat() if until and until < FOREVER else None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._announcer.set_quiet(FOREVER)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._announcer.set_quiet(None)
