"""Her tools: dates worked out in Python, formats the old scripts used."""

from __future__ import annotations

from datetime import datetime, time

from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.dates import resolve_moment
from custom_components.glados.llm_api import CLEARED

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home


async def _api(hass: HomeAssistant) -> llm.APIInstance:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS", options={"chat_agent": "conversation.x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctx = llm.LLMContext(
        platform="test", context=Context(), language="en", assistant="conversation", device_id=None
    )
    return await llm.async_get_api(hass, DOMAIN, ctx)


async def _call(api: llm.APIInstance, tool: str, **args) -> llm.ToolResult:
    return await api.async_call_tool(llm.ToolInput(tool_name=tool, tool_args=args))


def test_moments() -> None:
    # Friday 27 November 10:00.
    assert resolve_moment("", time(9, 0), NOW) == datetime(2026, 11, 28, 9, 0, tzinfo=NOW.tzinfo)
    assert resolve_moment("", time(15, 0), NOW).day == 27
    assert resolve_moment("monday", time(7, 45), NOW).day == 30
    assert resolve_moment("friday", time(9, 0), NOW).day == 4  # next week's
    assert resolve_moment("2026-12-12", time(8, 0), NOW).day == 12


async def test_reminder(home: Home) -> None:
    api = await _api(home.hass)
    calls = async_mock_service(home.hass, "todo", "add_item")
    result = await _call(api, "set_reminder", what="call the dentist", time="15:00", day="tomorrow")
    assert result.data == {
        "reminder": "call the dentist", "for": "nico", "time": "15:00",
        "date": "Saturday 28 November", "day": "tomorrow", "list": "todo.to_do",
    }
    assert calls[0].data["due_datetime"] == "2026-11-28 15:00:00"
    assert calls[0].data["description"] == "Reminder set by voice"

    result = await _call(api, "set_reminder", what="laundry", in_minutes="20")
    assert result.data["time"] == "10:20" and result.data["day"] == "today"

    assert (await _call(api, "set_reminder", what="x")).error
    assert (await _call(api, "set_reminder", what="x", in_minutes=5, person="Edo")).error


async def test_leave_time(home: Home) -> None:
    home.hass.states.async_set("input_datetime.leave_home_nico", CLEARED)
    home.hass.states.async_set("input_number.morning_routine_nico", "40")
    api = await _api(home.hass)
    calls = async_mock_service(home.hass, "input_datetime", "set_datetime")
    result = await _call(api, "set_leave_time", time="7:45", day="monday")
    assert result.data == {
        "person": "nico", "leave": "07:45", "date": "Monday 30 November", "day": "in 3 days",
        "reminders": "07:30 and 07:45", "get_up_by": "07:05", "routine_minutes": 40,
    }
    assert calls[0].data == {
        "entity_id": "input_datetime.leave_home_nico", "datetime": "2026-11-30 07:45:00"
    }
    await _call(api, "set_leave_time", clear=True)
    assert calls[-1].data["datetime"] == CLEARED


async def test_calendar(home: Home) -> None:
    home.hass.states.async_set("calendar.personal", "off", {"supported_features": 7, "friendly_name": "Personal"})
    home.hass.states.async_set("calendar.holidays", "off", {"supported_features": 0})
    api = await _api(home.hass)
    created = async_mock_service(home.hass, "calendar", "create_event")
    result = await _call(api, "add_to_calendar", what="Dentist", day="tuesday", time="14:30")
    assert result.data == {
        "added": "Dentist", "calendar": "Personal", "date": "Tuesday 1 December",
        "day": "in 4 days", "from": "14:30", "until": "15:30",
    }
    assert created[0].data["entity_id"] == "calendar.personal"
    result = await _call(api, "add_to_calendar", what="Party", day="2026-12-12")
    assert result.data["all_day"] and created[-1].data["start_date"] == "2026-12-12"

    async_mock_service(
        home.hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
        response={
            "calendar.personal": {"events": [
                {"start": "2026-11-28", "end": "2026-11-29", "summary": "Birthday Yannick"},
                {"start": "2026-11-27T18:30:00+01:00", "end": "2026-11-27T19:30:00+01:00",
                 "summary": "Dinner"},
                {"start": "2026-12-05", "end": "2026-12-06", "summary": "Sinterklaas"},
            ]},
        },
    )
    result = await _call(api, "upcoming_events", days="10")
    assert result.data["read_aloud"] == (
        "Today, Friday 27 November at 18:30, Dinner. "
        "Tomorrow, Saturday 28 November, Birthday Yannick. "
        "Saturday 5 December, in 8 days, Sinterklaas."
    )


async def test_permanent_file(home: Home) -> None:
    api = await _api(home.hass)
    assert "still empty" in api.api_prompt and "Friday 27 November" in api.api_prompt
    assert (await _call(api, "note_in_file", note="Nico hates mushrooms")).data == {
        "noted": "Nico hates mushrooms"
    }
    ctx = llm.LLMContext(platform="t", context=None, language="en", assistant="c", device_id=None)
    again = await llm.async_get_api(home.hass, DOMAIN, ctx)
    assert "Nico hates mushrooms" in again.api_prompt
