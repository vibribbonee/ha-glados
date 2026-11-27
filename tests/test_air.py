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
