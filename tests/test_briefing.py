"""The briefing: the right facts for tomorrow or today, and only her line spoken."""

from __future__ import annotations

from datetime import timedelta

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_registry as er

from custom_components.glados.briefing import async_facts

from pytest_homeassistant_custom_component.common import async_mock_service

from .conftest import Home

OPTIONS = {"routine_minutes": 35}


def _calendar(hass: HomeAssistant, events: list[dict]) -> None:
    hass.states.async_set("calendar.personal", "off", {"friendly_name": "Personal"})
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
                       response={"calendar.personal": {"events": events}})


def _weather(hass: HomeAssistant) -> None:
    async_mock_service(hass, "weather", "get_forecasts", supports_response=SupportsResponse.ONLY,
                       response={"weather.home": {"forecast": [
                           {"datetime": "2026-11-28T11:00:00+00:00", "condition": "partlycloudy",
                            "templow": 0.2, "temperature": 3.2, "wind_speed": 38.5}]}})


async def test_bedtime_alarm_too_late_for_the_dentist(home: Home) -> None:
    hass = home.hass
    _calendar(hass, [
        {"start": "2026-11-28T09:00:00+01:00", "end": "2026-11-28T09:30:00+01:00",
         "summary": "Dentist", "location": "Westerstraat 1"},
        {"start": "2026-11-28", "end": "2026-11-29", "summary": "Birthday Yannick"},
    ])
    _weather(hass)
    hass.states.async_set("sensor.pixel_9a_next_alarm", "2026-11-28T07:30:00+00:00",
                          {"device_class": "timestamp"})  # 08:30 local
    facts = await async_facts(hass, OPTIONS)
    assert facts.startswith("Tomorrow is Saturday 28 November.")
    assert "First commitment: Dentist at 09:00 at Westerstraat 1." in facts
    assert "All day: Birthday Yannick." in facts
    # 35 minutes routine plus half an hour for the trip: up by 07:55.
    assert "alarm at 08:30, 22.5 hours from now, which is too late: set it for 07:55" in facts
    assert "Weather tomorrow: 3 degrees, windy." in facts


async def test_phone_that_will_not_last(home: Home, freezer) -> None:
    hass = home.hass
    _calendar(hass, [])
    phone = er.async_get(hass).async_get("device_tracker.pixel_9a").device_id
    home.entity("sensor.pixel_9a_battery_level", "44", device=phone)
    home.entity("sensor.pixel_9a_charger_type", "none", device=phone)
    freezer.tick(timedelta(minutes=3))  # off the charger, not a flicker
    facts = await async_facts(hass, OPTIONS)
    assert "Nothing timed on the calendars tomorrow." in facts
    assert "Nico has no alarm set, and none is needed." in facts
    assert "Nico's phone is at 44 percent and not charging." in facts


async def test_morning_leave_time(home: Home) -> None:
    hass = home.hass
    _calendar(hass, [])
    hass.states.async_set("input_datetime.leave_home_nico", "2026-11-27 13:15:00",
                          {"has_date": True, "has_time": True})
    facts = await async_facts(hass, OPTIONS, morning=True)
    assert facts.startswith("Today is Friday 27 November.")
    assert "Nico leaves home today at 13:15, so up by 12:40." in facts
    assert "alarm" not in facts  # alarms are for bedtime


async def test_her_tool_returns_only_the_spoken_line(home: Home) -> None:
    from .test_llm_api import _api, _call
    _calendar(home.hass, [])
    api = await _api(home.hass)
    with patch("custom_components.glados.briefing.async_say",
               AsyncMock(return_value="Nothing tomorrow. How restful for you.")):
        result = await _call(api, "briefing")
    assert result.data == {"say": "Nothing tomorrow. How restful for you."}
