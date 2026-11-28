"""A whole day in the house, through the real heartbeat.

Every feature on, beat by beat from 06:00 to midnight, with an alarm, a
reminder, a leave time, an afternoon out, stale air, a cold room and bedtime.
Checks that nothing errors, nothing is said twice, and the day's moments come
out in the right order.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from .conftest import NOW, Home

DAY = NOW.replace(hour=6, minute=0)
BEAT = timedelta(seconds=30)


async def test_a_whole_day(home: Home, freezer, caplog) -> None:
    hass: HomeAssistant = home.hass
    freezer.move_to(DAY)
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS", options={
        "chat_agent": "conversation.x", "announcer_voice": "tts.p:a",
        "co2_alerts": "announcer", "usual_bedtime": "23:00",
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    said = async_mock_service(hass, "assist_satellite", "announce")
    phone = async_mock_service(hass, "notify", "send_message")
    async_mock_service(hass, "assist_satellite", "ask_question",
                       supports_response=SupportsResponse.ONLY, response={"id": "yes"})
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "todo", "update_item")
    async_mock_service(hass, "input_datetime", "set_datetime")
    async_mock_service(hass, "light", "turn_on")
    hass.states.async_set("calendar.personal", "off")
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
                       response={"calendar.personal": {"events": [
                           {"start": DAY.replace(hour=14).isoformat(),
                            "end": DAY.replace(hour=15).isoformat(), "summary": "Dentist"}]}})
    hass.states.async_set("todo.nico_s_list", "1")
    async_mock_service(hass, "todo", "get_items", supports_response=SupportsResponse.ONLY,
                       response={"todo.nico_s_list": {"items": [{
                           "uid": "r1", "summary": "Water the plants", "status": "needs_action",
                           "due": DAY.replace(hour=9).isoformat(),
                           "description": "Reminder set by voice"}]}})
    home.entity("switch.heater", "off", area=home.bedroom, labels={"glados_heating"},
                friendly_name="Heater")
    attrs = hass.states.get("person.nico").attributes
    # The night: asleep on the charger, in bed, an alarm at 07:00, leaving at 13:00.
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    hass.states.async_set("sensor.pixel_9a_next_alarm", DAY.replace(hour=7).isoformat(),
                          {"device_class": "timestamp"})
    hass.states.async_set("input_datetime.leave_home_nico",
                          DAY.replace(hour=13).strftime("%Y-%m-%d %H:%M:%S"))

    events = {
        DAY.replace(hour=7, minute=4): lambda: hass.states.async_set(
            "binary_sensor.bed_occupancy", "off", {"device_class": "occupancy"}),
        DAY.replace(hour=11): lambda: hass.states.async_set(
            "sensor.bedroom_co2", "1600", {"device_class": "carbon_dioxide"}),
        DAY.replace(hour=11, minute=40): lambda: hass.states.async_set(
            "sensor.bedroom_co2", "700", {"device_class": "carbon_dioxide"}),
        DAY.replace(hour=13, minute=5): lambda: hass.states.async_set("person.nico", "not_home", attrs),
        DAY.replace(hour=17): lambda: hass.states.async_set("person.nico", "home", attrs),
        DAY.replace(hour=19): lambda: hass.states.async_set(
            "sensor.bedroom_temperature", "14.5", {"device_class": "temperature"}),
    }

    with patch("custom_components.glados.voice.conversation.async_converse",
               AsyncMock(side_effect=Exception("no model in tests"))), \
         patch("custom_components.glados.character.random.randrange", return_value=1):
        t = DAY
        while t < DAY.replace(hour=23, minute=59):
            for at, change in list(events.items()):
                if at <= t:
                    change()
                    events.pop(at)
            freezer.move_to(t)
            async_fire_time_changed(hass, t)
            await hass.async_block_till_done()
            t += BEAT

    # No feature failed at any point in the day.
    assert "the other features carry on" not in caplog.text, caplog.text[-3000:]
    spoken = [c.data.get("message") or c.data.get("media_id", "") for c in said]
    text = " | ".join(spoken)

    def count(fragment: str) -> int:
        return sum(fragment in s for s in spoken)

    # The morning greeting, once, after getting up.
    assert count("suspension") <= 1
    # The reminder, once.
    assert count("Water%20the%20plants") + count("Water the plants") == 1
    # Leave times: heads-up and leave now, once each.
    assert count("Departure%20in%2015%20minutes") == 1, text
    assert count("Leave%20the%20house%20now") == 1
    # Stale air: one warning, then one reminder half an hour later; not one per beat.
    co2 = [x for x in spoken if "1600%20parts%20per%20million" in x]
    assert len([x for x in co2 if "remain" in x or "repeat" in x]) == 1, co2
    assert len(co2) == 2, co2
    # Home again after four hours: one welcome.
    assert count("Welcome%20back") == 1
    # Bedtime: the hour before and at bedtime.
    assert count("It is 23:00.") == 1
    assert not [p for p in phone if "Water" in p.data.get("message", "")]
