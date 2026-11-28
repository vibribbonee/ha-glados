"""Mornings: the night noted, the alarm, out of bed, then one greeting a day."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.morning import Mornings, birthday_names
from custom_components.glados.people import all_people

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home

WAKE = NOW.replace(hour=7, minute=0)


async def _mornings(home: Home, events: list[dict] | None = None) -> tuple[Mornings, list]:
    hass: HomeAssistant = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x",
                                     "announcer_voice": "tts.piper:announcer",
                                     "birthday_names": "nico: Sjors"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("calendar.personal", "off")
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
                       response={"calendar.personal": {"events": events or []}})
    return Mornings(hass, entry.runtime_data), async_mock_service(hass, "assist_satellite", "announce")


def _nico(hass: HomeAssistant):
    return next(p for p in all_people(hass) if p.entity_id == "person.nico")


def test_birthday_names(hass: HomeAssistant) -> None:
    from custom_components.glados.people import Person
    nico = Person("person.nico", "Nico", "home")
    assert birthday_names("nico: Sjors, Nicolaas; byte: Bee", nico) == ["nico", "nicolaas", "sjors"]


async def test_alarm_then_out_of_bed_then_greeting(home: Home, freezer) -> None:
    hass = home.hass
    phone = er.async_get(hass).async_get("device_tracker.pixel_9a").device_id
    home.entity("sensor.pixel_9a_charger_type", "none", device=phone)
    mornings, said = await _mornings(home)

    # 23:30: on the wireless charger, so asleep from then.
    freezer.move_to(WAKE - timedelta(hours=7, minutes=30))
    hass.states.async_set("sensor.pixel_9a_charger_type", "wireless")
    await mornings.async_tick()
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})

    # 07:00: the alarm. Still in bed, so no greeting yet.
    freezer.move_to(WAKE)
    hass.states.async_set("sensor.pixel_9a_next_alarm", WAKE.isoformat(), {"device_class": "timestamp"})
    with patch("custom_components.glados.morning.async_say", AsyncMock(return_value="Up. Finally.")):
        assert await mornings.async_tick() == []
        freezer.move_to(WAKE + timedelta(minutes=3))
        assert await mornings.async_tick() == []  # in bed
        hass.states.async_set("binary_sensor.bed_occupancy", "off", {"device_class": "occupancy"})
        [greeting] = await mornings.async_tick()
    assert "You have been in suspension for 7 hours and 33 minutes" in greeting["speech"]
    assert greeting["after"] == "Up. Finally."
    # Once a day: a light later does not greet again.
    hass.states.async_set("light.bedroom_main", "off")
    await mornings.async_tick()
    hass.states.async_set("light.bedroom_main", "on")
    assert await mornings.async_tick() == []


async def test_birthday(home: Home) -> None:
    mornings, said = await _mornings(home, [
        {"start": "2026-11-27", "end": "2026-11-28", "summary": "Sjors' birthday"},
        {"start": "2026-11-27T13:00:00+01:00", "end": "2026-11-27T14:00:00+01:00", "summary": "Lunch"},
    ])
    result = await mornings.async_greet(_nico(home.hass))
    assert result["birthday"] and result["speech"].startswith("Happy birthday, Nico.")
    assert "Your first commitment today is Lunch at 13:00. Try to be on time." in result["speech"]


async def test_no_alarm_first_light(home: Home) -> None:
    hass = home.hass
    mornings, said = await _mornings(home)
    hass.states.async_set("light.bedroom_main", "off")
    await mornings.async_tick()
    hass.states.async_set("light.bedroom_main", "on")
    with patch("custom_components.glados.morning.async_say", AsyncMock(return_value="Oh. Awake.")):
        [greeting] = await mornings.async_tick()
    assert greeting["speech"] == "Oh. Awake."  # no night noted: no suspension line


async def test_quiet_in_bed_in_the_dark(home: Home) -> None:
    hass = home.hass
    mornings, said = await _mornings(home)
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    hass.states.async_set("light.bedroom_main", "off")
    assert await mornings.async_greet(_nico(hass)) is None and not said


async def test_greet_on_a_chosen_speaker(home: Home) -> None:
    mornings, said = await _mornings(home, [
        {"start": "2026-11-27", "end": "2026-11-28", "summary": "Sjors' birthday"}])
    mornings.data.options = {**mornings.data.options, "birthday_song": "media-source://song.mp3"}
    result = await mornings.async_greet(_nico(home.hass), satellite="assist_satellite.office_puck")
    assert result["birthday"]
    assert {c.data["entity_id"] for c in said} == {"assist_satellite.office_puck"}
    assert said[0].data["media_id"] == "media-source://song.mp3"
