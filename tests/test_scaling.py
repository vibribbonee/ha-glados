"""It scales: per person without helpers, rooms without Bermuda, any language."""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er, label_registry as lr, llm
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.people import (
    all_people,
    leave_helper,
    leave_time,
    person_area,
    real_people,
    routine_minutes,
)
from custom_components.glados.rooms import is_bedroom

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import Home


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x", "routine_minutes": 40})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _person(hass: HomeAssistant, entity_id: str):
    return next(p for p in all_people(hass) if p.entity_id == entity_id)


async def test_everyone_gets_a_leave_time_and_routine(home: Home) -> None:
    hass = home.hass
    await _setup(hass)
    nico = _person(hass, "person.nico")
    helper = leave_helper(hass, nico)
    assert helper.startswith("datetime.")  # no input_datetime made by hand
    assert routine_minutes(hass, nico) == 40  # GLaDOS's own number, from the default

    ctx = llm.LLMContext(platform="t", context=Context(), language="en",
                         assistant="conversation", device_id=None)
    api = await llm.async_get_api(hass, DOMAIN, ctx)
    result = await api.async_call_tool(llm.ToolInput(
        tool_name="set_leave_time", tool_args={"time": "8:15", "day": "monday"}))
    await hass.async_block_till_done()
    assert result.data["leave"] == "08:15" and result.data["get_up_by"] == "07:35"
    assert leave_time(hass, nico).strftime("%A %H:%M") == "Monday 08:15"


async def test_own_helpers_still_win(home: Home) -> None:
    hass = home.hass
    await _setup(hass)
    hass.states.async_set("input_datetime.leave_home_nico", "2000-01-01 00:00:00")
    hass.states.async_set("input_number.morning_routine_nico", "25")
    nico = _person(hass, "person.nico")
    assert leave_helper(hass, nico) == "input_datetime.leave_home_nico"
    assert routine_minutes(hass, nico) == 25


async def test_room_without_bermuda(home: Home) -> None:
    hass = home.hass
    hass.states.async_set("sensor.nico_phone_area", "unknown")
    nico = _person(hass, "person.nico")
    # Only Nico home, only the bedroom shows presence: he is there.
    assert person_area(hass, nico) == home.bedroom
    # A second person home: no longer certain.
    hass.states.async_set("person.byte", "home", {"friendly_name": "byte", "user_id": "user-byte"})
    assert person_area(hass, nico) is None


async def test_bedroom_by_label_in_any_language(home: Home) -> None:
    hass = home.hass
    room = ar.async_get(hass).async_create("Chambre d'Ada")
    assert not is_bedroom(hass, room.id)
    label = lr.async_get(hass).async_create("glados_bedroom")
    ar.async_get(hass).async_update(room.id, labels={label.label_id})
    assert is_bedroom(hass, room.id)


async def test_only_real_occupants(home: Home) -> None:
    hass = home.hass
    hass.states.async_set("person.tablet", "home", {"friendly_name": "Tablet"})
    names = {p.name for p in real_people(hass)}
    assert "Tablet" not in names and "nico" in names


async def test_someone_moves_in(home: Home) -> None:
    hass = home.hass
    await _setup(hass)
    before = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == DOMAIN]
    hass.states.async_set("person.ada", "home", {"friendly_name": "Ada", "user_id": "u2"})
    er.async_get(hass).async_get_or_create("person", "person", "ada", suggested_object_id="ada")
    await hass.async_block_till_done()
    after = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == DOMAIN]
    assert any("ada" in e for e in set(after) - set(before))
