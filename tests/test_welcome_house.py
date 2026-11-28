"""The live house summary, house notes, and the welcome home."""

from __future__ import annotations

from datetime import timedelta
import json

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.house import house_state
from custom_components.glados.welcome import Welcome

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x", "announcer_voice": "tts.p:a",
                                     **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_live_house(home: Home) -> None:
    hass = home.hass
    hass.states.async_set("calendar.personal", "off", {
        "friendly_name": "Personal", "message": "Birthday Yannick", "all_day": True,
        "start_time": "2026-11-28 00:00:00"})
    home.entity("sensor.bedroom_humidity", "61.4", area=home.bedroom, device_class="humidity")
    text = house_state(hass)
    assert "- Nico: home, in the Bedroom" in text
    assert "- Bedroom: 18 degrees, CO2 1240 parts per million, humidity 61 percent" in text
    assert "- Personal calendar, next: Birthday Yannick, tomorrow" in text
    assert len(text) <= 1400


async def test_notes_and_house_in_her_instructions(home: Home) -> None:
    hass = home.hass
    await _setup(hass, house_notes="Tycho is the dog. He is always in the way.")
    ctx = llm.LLMContext(platform="t", context=Context(), language="en",
                         assistant="conversation", device_id=None)
    prompt = (await llm.async_get_api(hass, DOMAIN, ctx)).api_prompt
    assert "House notes: Tycho is the dog." in prompt and "Live house at" in prompt


async def test_welcome_home_with_what_you_missed(home: Home, freezer) -> None:
    hass = home.hass
    entry = await _setup(hass)
    said = async_mock_service(hass, "assist_satellite", "announce")
    hass.states.async_set("calendar.postnl_deliveries", "on", {"friendly_name": "PostNL Deliveries"})
    from homeassistant.core import SupportsResponse
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
                       response={"calendar.postnl_deliveries": {"events": [
                           {"start": NOW.date().isoformat(), "end": NOW.date().isoformat(),
                            "summary": "Your parcel from Bol"}]}})
    welcome = Welcome(hass, entry.runtime_data)
    attrs = hass.states.get("person.nico").attributes
    await welcome.async_tick()  # home: noted

    hass.states.async_set("person.nico", "not_home", attrs)
    await welcome.async_tick()  # left at 10:00
    entry.runtime_data.memory.set("missed person.nico", json.dumps(
        [{"what": "Call the dentist", "at": (NOW + timedelta(hours=1)).isoformat()}]))

    freezer.move_to(NOW + timedelta(hours=2, minutes=30))
    hass.states.async_set("person.nico", "home", attrs)
    assert await welcome.async_tick() == []  # just in the door
    freezer.tick(timedelta(minutes=3))
    [greeting] = await welcome.async_tick()
    assert greeting["speech"].startswith("Welcome back, Nico. You were away for 2 hours and 30 minutes.")
    assert "While you were out: Call the dentist at 11:00." in greeting["speech"]
    assert "A delivery is due today: Your parcel from Bol." in greeting["speech"]
    assert greeting["after"]
    freezer.tick(timedelta(minutes=3))
    assert await welcome.async_tick() == []  # once


async def test_quick_trip_gets_nothing(home: Home, freezer) -> None:
    hass = home.hass
    entry = await _setup(hass)
    async_mock_service(hass, "assist_satellite", "announce")
    welcome = Welcome(hass, entry.runtime_data)
    attrs = hass.states.get("person.nico").attributes
    await welcome.async_tick()
    hass.states.async_set("person.nico", "not_home", attrs)
    await welcome.async_tick()
    freezer.tick(timedelta(minutes=20))
    hass.states.async_set("person.nico", "home", attrs)
    await welcome.async_tick()
    freezer.tick(timedelta(minutes=5))
    assert await welcome.async_tick() == []
