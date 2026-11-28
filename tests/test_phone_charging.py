"""A phone off the charger at bedtime, told apart from a flaky wireless pad."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import entity_registry as er

from custom_components.glados.briefing import _weather_line, phone_battery

from .conftest import NOW, Home
from .test_bedtime import _bedtimes, _nico

NIGHT = NOW.replace(hour=23, minute=30)


def _phone(home: Home, level: str, plug: str, status: str) -> None:
    device = er.async_get(home.hass).async_get("sensor.pixel_9a_next_alarm").device_id
    home.entity("sensor.pixel_9a_battery_level", level, device=device)
    home.entity("sensor.pixel_9a_charger_type", plug, device=device)
    home.entity("sensor.pixel_9a_battery_state", status, device=device)


async def test_a_flicker_on_the_pad_is_not_off_the_charger(home: Home, freezer) -> None:
    hass = home.hass
    freezer.move_to(NIGHT)
    _phone(home, "40", "wireless", "charging")
    assert phone_battery(hass, _nico(hass)) is None
    hass.states.async_set("sensor.pixel_9a_charger_type", "none")  # the pad blinks
    hass.states.async_set("sensor.pixel_9a_battery_state", "discharging")
    freezer.tick(timedelta(seconds=7))
    assert phone_battery(hass, _nico(hass)) is None
    freezer.tick(timedelta(minutes=3))
    assert phone_battery(hass, _nico(hass)) == 40  # really off it now


async def test_full_or_paused_on_the_pad_is_charging(home: Home, freezer) -> None:
    freezer.move_to(NIGHT)
    _phone(home, "80", "wireless", "not_charging")  # adaptive charging holds at 80
    freezer.tick(timedelta(hours=1))
    assert phone_battery(home.hass, _nico(home.hass)) is None


async def test_in_bed_without_the_charger_gets_one_push(home: Home, freezer) -> None:
    hass = home.hass
    freezer.move_to(NIGHT)
    bedtimes, said = await _bedtimes(home)
    from pytest_homeassistant_custom_component.common import async_mock_service
    pushed = async_mock_service(hass, "notify", "send_message")
    _phone(home, "35", "none", "discharging")
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    freezer.tick(timedelta(minutes=5))
    await bedtimes.async_tick()
    assert not pushed  # maybe still scrolling
    freezer.tick(timedelta(minutes=6))
    await bedtimes.async_tick()
    freezer.tick(timedelta(minutes=30))
    await bedtimes.async_tick()
    [push] = pushed
    assert push.data["message"] == "Your phone is at 35 percent and not charging. Your 07:30 alarm is on it."
    assert not said  # never a voice in bed


def test_weather_in_words() -> None:
    calm = {"condition": "cloudy", "temperature": 8.4, "precipitation": 0, "wind_speed": 12}
    assert _weather_line(calm, "today") == "Weather today: 8 degrees."
    wet = {"condition": "rainy", "temperature": 3, "precipitation": 4.5, "wind_speed": 38}
    assert _weather_line(wet, "today") == "Weather today: 3 degrees, rain, windy."
    summer = {"condition": "sunny", "temperature": 27, "uv_index": 7, "wind_speed": 9}
    assert _weather_line(summer, "today") == "Weather today: 27 degrees, sunscreen weather."
    gale = {"condition": "windy", "temperature": 10, "wind_speed": 20, "precipitation": 0.4}
    assert _weather_line({**gale, "wind_speed": 20}, "tomorrow", "m/s") == (
        "Weather tomorrow: 10 degrees, a chance of a shower, stormy.")
