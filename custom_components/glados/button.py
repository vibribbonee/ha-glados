"""A button that plays a test announcement: beeps, the Announcer and GLaDOS."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the test button."""
    async_add_entities([TestAnnouncementButton(entry)])


class TestAnnouncementButton(ButtonEntity):
    """Plays the whole show once in the room people are in."""

    _attr_has_entity_name = True
    _attr_translation_key = "test_announcement"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bullhorn"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_test_announcement"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    async def async_press(self) -> None:
        """Beep, Announcer, GLaDOS, beep."""
        await self._entry.runtime_data.announcer.async_test(context=self._context)
