"""Settings that differ per person: sleep goal, usual bedtime, their own calendar."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import entity_registry as er

from custom_components.glados.bedtime import bedtime_for
from custom_components.glados.llm_api import writable_calendars
from custom_components.glados.people import all_people

from .conftest import NOW, Home
from .sim import add_person, setup


def _person(hass, entity_id):
    return next(p for p in all_people(hass) if p.entity_id == entity_id)


async def test_each_person_their_own_bedtime(home: Home, freezer) -> None:
    hass = home.hass
    freezer.move_to(NOW)
    alarm = (NOW + timedelta(days=1)).replace(hour=7, minute=0)
    edo = add_person(home, "edo", "Office", alarm=alarm)
    hass.states.async_set("sensor.pixel_9a_next_alarm", alarm.isoformat(), {"device_class": "timestamp"})
    entry, _ = await setup(hass, {"usual_bedtime": "23:00:00", "sleep_goal_hours": 8})
    reg = er.async_get(hass)
    goal = reg.async_get_entity_id("number", "glados", f"sleep_goal_{edo}")
    usual = reg.async_get_entity_id("time", "glados", "usual_bedtime_person.nico")
    assert goal and usual
    await hass.services.async_call("number", "set_value", {"entity_id": goal, "value": 9.5},
                                   blocking=True)
    nico, edo_p = _person(hass, "person.nico"), _person(hass, edo)
    assert bedtime_for(hass, entry.options, nico).bedtime.strftime("%H:%M") == "23:00"
    assert bedtime_for(hass, entry.options, edo_p).bedtime.strftime("%H:%M") == "21:30"

    # No alarm: the usual bedtime, Nico's own over the house's.
    hass.states.async_set("sensor.pixel_9a_next_alarm", "unavailable", {"device_class": "timestamp"})
    await hass.services.async_call("time", "set_value", {"entity_id": usual, "time": "00:45:00"},
                                   blocking=True)
    assert bedtime_for(hass, entry.options, nico).bedtime.strftime("%H:%M") == "00:45"


async def test_my_calendar_is_the_speakers(home: Home) -> None:
    hass = home.hass
    feats = {"supported_features": 1}
    hass.states.async_set("calendar.family", "off", {"friendly_name": "Family", **feats})
    hass.states.async_set("calendar.edo", "off", {"friendly_name": "Edo's calendar", **feats})
    edo = add_person(home, "edo", "Office")
    assert writable_calendars(hass, _person(hass, edo))[0] == "calendar.edo"
    assert writable_calendars(hass, _person(hass, "person.nico"))[0] != "calendar.edo"


async def test_people_who_live_here_setting(home: Home) -> None:
    from custom_components.glados.people import real_people
    hass = home.hass
    hass.states.async_set("person.guest", "unknown", {"friendly_name": "Guest", "user_id": "u-guest"})
    entry, _ = await setup(hass, {})
    assert {p.entity_id for p in real_people(hass)} == {"person.nico", "person.guest"}
    hass.config_entries.async_update_entry(entry, options={**entry.options,
                                                           "occupants": ["person.nico"]})
    await hass.async_block_till_done()
    assert [p.entity_id for p in real_people(hass)] == ["person.nico"]


async def test_entities_of_someone_who_left_go(home: Home) -> None:
    hass = home.hass
    hass.states.async_set("person.guest", "unknown", {"friendly_name": "Guest", "user_id": "u-guest"})
    entry, _ = await setup(hass, {})
    reg = er.async_get(hass)
    assert reg.async_get_entity_id("number", "glados", "sleep_goal_person.guest")
    hass.config_entries.async_update_entry(entry, options={**entry.options,
                                                           "occupants": ["person.nico"]})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_entity_id("number", "glados", "sleep_goal_person.guest") is None
    assert reg.async_get_entity_id("number", "glados", "sleep_goal_person.nico")
