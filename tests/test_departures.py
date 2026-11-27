"""Leave-time reminders: a heads-up, then leave now with what is still on."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.departures import Departures

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home

LEAVE = NOW.replace(hour=10, minute=30)


async def _departures(home: Home) -> tuple[Departures, list, list]:
    hass: HomeAssistant = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x",
                                     "announcer_voice": "tts.piper:announcer"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("input_datetime.leave_home_nico", LEAVE.strftime("%Y-%m-%d %H:%M:%S"),
                          {"has_date": True, "has_time": True})
    return (Departures(hass, entry.runtime_data),
            async_mock_service(hass, "assist_satellite", "announce"),
            async_mock_service(hass, "notify", "send_message"))


async def test_heads_up_then_leave_now(home: Home, freezer) -> None:
    dep, said, phone = await _departures(home)
    home.entity("switch.soldering_iron", "on", labels={"glados_left_on"}, friendly_name="Soldering Iron")
    freezer.move_to(LEAVE - timedelta(minutes=15))
    [heads_up] = await dep.async_tick()
    assert heads_up["spoken"] and "Departure in 15 minutes. At 10:30." in heads_up["speech"]
    assert "Outside temperature: 0 degrees." in heads_up["speech"]
    assert await dep.async_tick() == []  # once
    freezer.move_to(LEAVE + timedelta(minutes=1))  # a minute late still counts
    [leave] = await dep.async_tick()
    assert "Leave the house now. Still on: Soldering Iron." in leave["speech"]
    assert leave["after"]  # GLaDOS adds one remark
    assert not phone


async def test_asleep_goes_to_the_phone(home: Home, freezer) -> None:
    dep, said, phone = await _departures(home)
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    freezer.move_to(LEAVE)
    await dep.async_tick()
    assert not said and phone[0].data["title"] == "Leave now"


async def test_nothing_when_away_or_cleared(home: Home, freezer) -> None:
    dep, said, phone = await _departures(home)
    home.hass.states.async_set("input_datetime.leave_home_nico", "2000-01-01 00:00:00")
    freezer.move_to(LEAVE)
    assert await dep.async_tick() == []
