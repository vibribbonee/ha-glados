"""Bedtime per person: from their alarm, three nudges, the sensors."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.glados.bedtime import Bedtimes, bedtime_for
from custom_components.glados.const import DOMAIN
from custom_components.glados.people import all_people

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home

ALARM = (NOW + timedelta(days=1)).replace(hour=7, minute=30)  # Saturday 07:30


async def _bedtimes(home: Home, **options) -> tuple[Bedtimes, list]:
    hass: HomeAssistant = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x",
                                     "announcer_voice": "tts.piper:announcer", **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.pixel_9a_next_alarm", ALARM.isoformat(), {"device_class": "timestamp"})
    return Bedtimes(hass, entry.runtime_data), async_mock_service(hass, "assist_satellite", "announce")


def _nico(hass: HomeAssistant):
    return next(p for p in all_people(hass) if p.entity_id == "person.nico")


async def test_from_the_morning_alarm(home: Home) -> None:
    await _bedtimes(home)
    bt = bedtime_for(home.hass, {"sleep_goal_hours": 8, "minimum_sleep_hours": 6}, _nico(home.hass))
    assert bt.bedtime == ALARM - timedelta(hours=8)  # 23:30
    assert bt.last_call == ALARM - timedelta(hours=6)  # 01:30


async def test_three_nudges(home: Home, freezer) -> None:
    bedtimes, said = await _bedtimes(home)
    with patch("custom_components.glados.bedtime.async_briefing",
               AsyncMock(return_value={"say": "Nothing tomorrow. Restful.", "facts": ""})):
        freezer.move_to(ALARM - timedelta(hours=9))  # 22:30
        [heads_up] = await bedtimes.async_tick()
    assert heads_up["speech"] == "Bedtime is in an hour, at 23:30. Nothing tomorrow. Restful."
    assert await bedtimes.async_tick() == []

    freezer.move_to(ALARM - timedelta(hours=8))  # 23:30
    [bedtime] = await bedtimes.async_tick()
    assert bedtime["speech"].startswith("It is 23:30.")

    freezer.move_to(ALARM - timedelta(hours=6, minutes=30))  # 01:00, lights still on
    [last_call] = await bedtimes.async_tick()
    assert "Last call. Be in bed by 01:30" in last_call["speech"]
    assert "under 6 hours before the 07:30 alarm" in last_call["speech"] and last_call["after"]


async def test_no_last_call_in_the_dark_or_in_bed(home: Home, freezer) -> None:
    hass = home.hass
    bedtimes, said = await _bedtimes(home)
    hass.states.async_set("light.bedroom_main", "off")
    freezer.move_to(ALARM - timedelta(hours=6, minutes=30))
    assert await bedtimes.async_tick() == []
    hass.states.async_set("light.bedroom_main", "on")
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    freezer.move_to(ALARM - timedelta(hours=8))
    assert await bedtimes.async_tick() == []


async def test_usual_bedtime_without_an_alarm(home: Home) -> None:
    await _bedtimes(home)
    home.hass.states.async_set("sensor.pixel_9a_next_alarm", "unavailable")
    bt = bedtime_for(home.hass, {"usual_bedtime": "00:15"}, _nico(home.hass))
    assert bt.bedtime == (NOW + timedelta(days=1)).replace(hour=0, minute=15)
    assert bt.last_call is None
    assert bedtime_for(home.hass, {}, _nico(home.hass)).bedtime is None


async def test_bedtime_sensors(home: Home) -> None:
    await _bedtimes(home)
    await home.hass.async_block_till_done()
    from homeassistant.helpers import entity_registry as er
    ids = [e.entity_id for e in er.async_get(home.hass).entities.values()
           if e.platform == DOMAIN and e.domain == "sensor"]
    assert any("bedtime_nico" in i for i in ids) and any("last_call_nico" in i for i in ids)
