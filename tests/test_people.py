"""Who is who, and their own settings."""

from __future__ import annotations

from custom_components.glados.people import (
    leave_time,
    own_list,
    person_area,
    phones,
    resolve_person,
    routine_minutes,
)

from .conftest import Home


async def test_resolve_by_name_user_or_only_one_home(home: Home) -> None:
    hass = home.hass
    assert resolve_person(hass, "Byte").entity_id == "person.byte"
    assert resolve_person(hass, "person.nico").slug == "nico"
    assert resolve_person(hass, user_id="user-nico").entity_id == "person.nico"
    # Nobody named: the only person at home.
    assert resolve_person(hass).entity_id == "person.nico"
    # A name that matches nobody is not guessed.
    assert resolve_person(hass, "Edo") is None


async def test_two_people_home_needs_a_name(home: Home) -> None:
    home.hass.states.async_set("person.byte", "home", {"friendly_name": "byte"})
    assert resolve_person(home.hass) is None


async def test_room_and_phones(home: Home) -> None:
    nico = resolve_person(home.hass, "nico")
    assert person_area(home.hass, nico) == home.bedroom
    # The watch is not a phone.
    assert phones(home.hass, nico) == ["notify.pixel_9a"]


async def test_routine_minutes_own_then_default(home: Home) -> None:
    hass = home.hass
    nico = resolve_person(hass, "nico")
    assert routine_minutes(hass, nico, 35) == 35
    hass.states.async_set("input_number.morning_routine_minutes", "40.0")
    assert routine_minutes(hass, nico) == 40
    hass.states.async_set("input_number.morning_routine_nico", "30.0")
    assert routine_minutes(hass, nico) == 30


async def test_cleared_leave_time_is_none(home: Home) -> None:
    hass = home.hass
    nico = resolve_person(hass, "nico")
    assert leave_time(hass, nico) is None
    hass.states.async_set("input_datetime.leave_home_nico", "2000-01-01 00:00:00")
    assert leave_time(hass, nico) is None
    hass.states.async_set("input_datetime.leave_home_nico", "2026-11-30 07:45:00")
    assert leave_time(hass, nico).strftime("%a %H:%M") == "Mon 07:45"


async def test_own_list_or_shared(home: Home) -> None:
    hass = home.hass
    nico = resolve_person(hass, "nico")
    assert own_list(hass, nico) == "todo.to_do"
    hass.states.async_set("todo.nico_s_list", "3")
    assert own_list(hass, nico) == "todo.nico_s_list"
