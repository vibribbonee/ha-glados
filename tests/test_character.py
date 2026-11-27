"""Her own initiative: comfort offers, facility notices, the idle remark."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.glados.character import Character
from custom_components.glados.const import DOMAIN
from custom_components.glados.rooms import describe

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home


async def _character(home: Home, reply: str | None = "yes") -> tuple[Character, dict]:
    hass: HomeAssistant = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x", "announcer_voice": "tts.p:a"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    home.entity("switch.heater", "off", area=home.bedroom, labels={"glados_heating"},
                friendly_name="Heater")
    calls = {
        "ask": async_mock_service(hass, "assist_satellite", "ask_question",
                                  supports_response=SupportsResponse.ONLY,
                                  response={"id": reply} if reply else {}),
        "say": async_mock_service(hass, "assist_satellite", "announce"),
        "on": async_mock_service(hass, "homeassistant", "turn_on"),
    }
    return Character(hass, entry.runtime_data), calls


def _cold(home: Home) -> None:
    home.hass.states.async_set("sensor.bedroom_temperature", "14.2", {"device_class": "temperature"})


async def test_offers_heat_and_turns_it_on(home: Home, freezer) -> None:
    char, calls = await _character(home)
    _cold(home)
    freezer.tick(timedelta(minutes=15))  # settled in
    result = await char.async_comfort(describe(home.hass, home.bedroom), NOW + timedelta(minutes=15))
    assert result["kind"] == "heat" and result["answer"] == "yes"
    question = calls["ask"][0].data["question"]
    assert "14 degrees in the Bedroom" in question and question.endswith("Shall I switch on the Heater?")
    assert calls["on"][0].data["entity_id"] == ["switch.heater"]
    assert "Heater is on" in calls["say"][0].data["message"] or "heater" in calls["say"][0].data["message"].lower()
    # A yes holds for three hours: no second offer.
    assert await char.async_comfort(describe(home.hass, home.bedroom), NOW + timedelta(minutes=20)) is None


async def test_a_no_holds_for_the_day(home: Home, freezer) -> None:
    char, calls = await _character(home, reply="no")
    _cold(home)
    freezer.tick(timedelta(minutes=15))
    later = NOW + timedelta(minutes=15)
    assert (await char.async_comfort(describe(home.hass, home.bedroom), later))["answer"] == "no"
    assert not calls["on"]
    assert await char.async_comfort(describe(home.hass, home.bedroom), later + timedelta(hours=5)) is None


async def test_no_heat_with_the_window_open_or_just_arrived(home: Home, freezer) -> None:
    char, calls = await _character(home)
    _cold(home)
    home.hass.states.async_set("binary_sensor.bedroom_presence", "on", {"device_class": "presence"})
    assert await char.async_comfort(describe(home.hass, home.bedroom), NOW) is None  # just arrived
    freezer.tick(timedelta(minutes=15))
    home.hass.states.async_set("binary_sensor.bedroom_window", "on", {"device_class": "window"})
    assert await char.async_comfort(describe(home.hass, home.bedroom), NOW) is None
    assert not calls["ask"]


async def test_late_notice_once_a_night(home: Home, freezer) -> None:
    hass = home.hass
    char, calls = await _character(home)
    alarm = (NOW + timedelta(days=1)).replace(hour=7, minute=30)
    hass.states.async_set("sensor.pixel_9a_next_alarm", alarm.isoformat(), {"device_class": "timestamp"})
    late = alarm - timedelta(hours=7)  # bedtime 23:30, an hour past it
    freezer.move_to(late)
    result = await char.async_late_notice(late)
    assert result["spoken"] and "Testing hours have ended" in result["speech"]
    assert await char.async_late_notice(late + timedelta(minutes=30)) is None


async def test_idle_remark_once_a_day(home: Home, freezer) -> None:
    char, calls = await _character(home)
    freezer.tick(timedelta(minutes=30))
    rooms = [describe(home.hass, home.bedroom)]
    with patch("custom_components.glados.character.async_say",
               AsyncMock(return_value="Thirty minutes in one room. A personal best.")):
        result = await char.async_idle(rooms, NOW + timedelta(minutes=30))
        assert result["speech"] == "Thirty minutes in one room. A personal best."
        assert await char.async_idle(rooms, NOW + timedelta(hours=2)) is None
