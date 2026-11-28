"""Room alarms, and the backup that rings only when the phone alarm failed."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.glados.alarms import AlarmClock
from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home

ALARM = NOW.replace(hour=10, minute=30)  # half an hour after "now"
PHONE = "sensor.pixel_9a_next_alarm"


async def _clock(hass: HomeAssistant) -> AlarmClock:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x",
                                     "announcer_voice": "tts.piper:announcer"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.alarms


def _phone(hass: HomeAssistant, value: str) -> None:
    hass.states.async_set(PHONE, value, {"device_class": "timestamp"})


async def _backup_case(home: Home, freezer, after: str | None) -> list:
    """Set a backup, show it on the phone, then put the phone in state `after`."""
    clock = await _clock(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    clock.add(ALARM, home.bedroom, "nico", backup_after=timedelta(minutes=10), phone_sensor=PHONE)
    if after is not None:
        _phone(home.hass, ALARM.isoformat())
        await clock.async_tick()  # the phone showed it: confirmed
        _phone(home.hass, after)
    freezer.move_to(ALARM + timedelta(minutes=10, seconds=5))
    await clock.async_tick()
    return calls


async def test_backup_quiet_when_dismissed(home: Home, freezer) -> None:
    tomorrow = (ALARM + timedelta(days=1)).isoformat()
    assert await _backup_case(home, freezer, tomorrow) == []


async def test_backup_rings_when_not_dismissed(home: Home, freezer) -> None:
    calls = await _backup_case(home, freezer, ALARM.isoformat())
    assert any("suspension" in c.data.get("media_id", "") for c in calls)


async def test_backup_rings_when_phone_is_gone(home: Home, freezer) -> None:
    assert await _backup_case(home, freezer, "unavailable")


async def test_backup_rings_when_phone_never_had_it(home: Home, freezer) -> None:
    assert await _backup_case(home, freezer, None)


async def test_room_alarm_repeats_until_awake(home: Home, freezer) -> None:
    clock = await _clock(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    clock.add(ALARM, home.bedroom, "nico")
    freezer.move_to(ALARM)
    said = await clock.async_tick()
    assert said[0]["spoken"]  # past the sleep rules: it is an alarm
    assert calls[0].data["entity_id"] == "assist_satellite.puck_3"
    freezer.tick(timedelta(minutes=3))
    assert len(await clock.async_tick()) == 1  # second ring
    # Up now: out of bed with the light on. No third ring.
    home.hass.states.async_set("binary_sensor.bed_occupancy", "off", {"device_class": "occupancy"})
    freezer.tick(timedelta(minutes=3))
    assert await clock.async_tick() == [] and clock.alarms() == []


async def test_stop_and_snooze(home: Home, freezer) -> None:
    clock = await _clock(home.hass)
    async_mock_service(home.hass, "assist_satellite", "announce")
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    clock.add(ALARM, home.bedroom)
    freezer.move_to(ALARM)
    await clock.async_tick()
    [snoozed] = clock.stop(home.bedroom, snooze=True)
    assert clock.alarms()[0].next > (ALARM + timedelta(minutes=8)).isoformat()
    freezer.move_to(ALARM + timedelta(minutes=10))
    await clock.async_tick()
    assert clock.stop(home.bedroom) and clock.alarms() == []


async def test_daytime_alarm_rings_once(home: Home, freezer) -> None:
    clock = await _clock(home.hass)
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    clock.add(ALARM, home.bedroom, label="oven", wake=False)
    freezer.move_to(ALARM)
    await clock.async_tick()
    assert "oven" in calls[0].data["media_id"] and clock.alarms() == []
