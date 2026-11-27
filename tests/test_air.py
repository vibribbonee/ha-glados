"""CO2 warnings: once when it gets worse, a reminder later, quiet when empty."""

from __future__ import annotations

from datetime import timedelta
import re

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.glados.air import AirWatch
from custom_components.glados.const import DOMAIN
from custom_components.glados.setpieces import _GLADOS_ALONE, co2_glados_alone

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import Home

REMIND = timedelta(minutes=30)


async def _watch(hass: HomeAssistant, style: str = "announcer") -> AirWatch:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="GLaDOS",
        options={"chat_agent": "conversation.x", "co2_alerts": style,
                 "announcer_voice": "tts.piper:announcer"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return AirWatch(hass, entry.runtime_data)


async def test_warns_once_then_reminds(home: Home, freezer) -> None:
    watch = await _watch(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    check = watch.async_check_room

    first = await check(home.bedroom, "Bedroom", 1240, True, "announcer", REMIND)
    assert first["spoken"] and "stale" in calls[0].data["media_id"]
    assert first["after"]  # GLaDOS replies after the Announcer

    # Same level a minute later: nothing.
    assert await check(home.bedroom, "Bedroom", 1260, True, "announcer", REMIND) is None
    # Worse: warned again at once.
    worse = await check(home.bedroom, "Bedroom", 1600, True, "announcer", REMIND)
    assert worse["spoken"] and "1600" in worse["speech"]
    # Still bad half an hour later: the reminder.
    freezer.tick(REMIND + timedelta(seconds=1))
    again = await check(home.bedroom, "Bedroom", 1550, True, "announcer", REMIND)
    assert again["spoken"] and re.search(r"remains|repeat", again["speech"], re.I)
    # No reminder when it is switched off.
    freezer.tick(REMIND * 2)
    assert await check(home.bedroom, "Bedroom", 1550, True, "announcer", timedelta(0)) is None


async def test_quiet_when_empty_and_fresh_again(home: Home) -> None:
    watch = await _watch(home.hass)
    async_mock_service(home.hass, "assist_satellite", "announce")
    check = watch.async_check_room
    assert await check(home.bedroom, "Bedroom", 1700, False, "announcer", REMIND) is None
    await check(home.bedroom, "Bedroom", 1700, True, "announcer", REMIND)
    # Just under stale is not fresh yet; well under it is, quietly.
    assert await check(home.bedroom, "Bedroom", 950, True, "announcer", REMIND) is None
    assert watch.data.memory.get(f"air {home.bedroom}") == "critical"
    await check(home.bedroom, "Bedroom", 700, True, "announcer", REMIND)
    assert watch.data.memory.get(f"air {home.bedroom}") == "fine"


async def test_glados_alone_carries_the_warning(home: Home) -> None:
    watch = await _watch(home.hass, "glados")
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    result = await watch.async_check_room(home.bedroom, "Bedroom", 1500, True, "glados", REMIND)
    assert result["spoken"] and "1500" in result["speech"]
    assert "media_id" not in calls[0].data  # no Announcer, her own voice
    for level, lines in _GLADOS_ALONE.items():
        for line in lines:
            text = line.format(room="Bedroom", ppm=1500)
            assert "1500" in text and "Bedroom" in text, text
            if level != "fine":
                assert "window" in text.lower(), text
    assert "Bedroom" in co2_glados_alone("Bedroom", 1500, reminder=True)


async def test_the_minute_check(home: Home, freezer) -> None:
    # Bedroom at 1240 with Nico in it: one stale warning within a minute, then quiet.
    await _watch(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    freezer.tick(timedelta(minutes=1, seconds=1))
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    async_fire_time_changed(home.hass)
    await home.hass.async_block_till_done()
    assert any("1240" in (c.data.get("media_id") or "") for c in calls)
    count = len(calls)
    freezer.tick(timedelta(minutes=1, seconds=1))
    async_fire_time_changed(home.hass)
    await home.hass.async_block_till_done()
    assert len(calls) == count


async def test_window_open_in_the_cold(home: Home, freezer) -> None:
    from custom_components.glados.rooms import describe
    watch = await _watch(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    home.hass.states.async_set("sensor.bedroom_co2", "700", {"device_class": "carbon_dioxide"})
    home.hass.states.async_set("binary_sensor.bedroom_window", "on",
                               {"device_class": "window", "friendly_name": "Bedroom window"})
    # Not yet: only open for a few minutes.
    assert await watch.async_check_windows_here(describe(home.hass, home.bedroom)) is None
    freezer.tick(timedelta(minutes=21))
    result = await watch.async_check_windows_here(describe(home.hass, home.bedroom))
    assert result["spoken"] and "21 minutes" in result["speech"]
    assert "0 degrees" in result["speech"]  # weather.home reads 0.4
    # Once per opening.
    freezer.tick(timedelta(minutes=5))
    assert await watch.async_check_windows_here(describe(home.hass, home.bedroom)) is None
    # Warm outside: never.
    home.hass.states.async_set("binary_sensor.bedroom_window", "off", {"device_class": "window"})
    home.hass.states.async_set("binary_sensor.bedroom_window", "on", {"device_class": "window"})
    home.hass.states.async_set("weather.home", "sunny", {"temperature": 15})
    freezer.tick(timedelta(minutes=30))
    assert await watch.async_check_windows_here(describe(home.hass, home.bedroom)) is None
    assert len([c for c in calls if c.data.get("media_id", "").startswith("media-source://tts")]) == 1


async def test_window_in_an_empty_room(home: Home, freezer) -> None:
    from custom_components.glados.rooms import describe
    watch = await _watch(home.hass, "glados")
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    home.entity("binary_sensor.office_window", "on", area=home.office, device_class="window",
                friendly_name="Office window")
    freezer.tick(timedelta(minutes=25))
    rooms = {a: describe(home.hass, a) for a in (home.bedroom, home.office)}
    result = await watch.async_check_loose_windows(rooms)
    # Said where Nico is, about the office, by GLaDOS herself.
    assert result["spoken"] and result["area"] == home.bedroom
    assert "Office window has been open" in result["speech"] and "nobody" in result["speech"]
    assert calls[0].data["entity_id"] == "assist_satellite.puck_3"
    assert await watch.async_check_loose_windows(rooms) is None


async def test_fresh_again_close_the_window(home: Home) -> None:
    from custom_components.glados.rooms import describe
    watch = await _watch(home.hass, "glados")
    async_mock_service(home.hass, "assist_satellite", "announce")
    watch.data.memory.set(f"air {home.bedroom}", "critical")
    home.hass.states.async_set("binary_sensor.bedroom_window", "on",
                               {"device_class": "window", "friendly_name": "Bedroom window"})
    home.hass.states.async_set("sensor.bedroom_co2", "700", {"device_class": "carbon_dioxide"})
    ctx = describe(home.hass, home.bedroom)
    result = await watch.async_check_room(home.bedroom, "Bedroom", 700, True, "glados", REMIND, ctx)
    assert result["spoken"] and "breathable again" in result["speech"]
    assert "close the window" in result["speech"]
