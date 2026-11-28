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


async def test_no_push_once_asleep(home: Home, freezer) -> None:
    hass = home.hass
    freezer.move_to(NIGHT)
    bedtimes, said = await _bedtimes(home)
    from pytest_homeassistant_custom_component.common import async_mock_service
    pushed = async_mock_service(hass, "notify", "send_message")
    _phone(home, "35", "wireless", "charging")
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    await bedtimes.async_tick()  # in bed, phone on the pad
    freezer.tick(timedelta(hours=3))  # 02:30: it slid off the pad
    hass.states.async_set("sensor.pixel_9a_charger_type", "none")
    hass.states.async_set("sensor.pixel_9a_battery_state", "discharging")
    freezer.tick(timedelta(minutes=20))
    await bedtimes.async_tick()
    assert not pushed and not said  # the backup alarm covers a dead phone


def _laptop(home: Home, level: str, status: str, owner: bool = False) -> str:
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    source = MockConfigEntry(domain="mobile_app")
    source.add_to_hass(home.hass)
    device = dr.async_get(home.hass).async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("mobile_app", "mac")}, name="MacBook Pro").id
    battery = home.entity("sensor.macbook_pro_internal_battery_level", level, device=device,
                          device_class="battery")
    home.entity("sensor.macbook_pro_internal_battery_state", status, device=device)
    if owner:
        home.entity("device_tracker.macbook_pro", "home", device=device)
        attrs = dict(home.hass.states.get("person.nico").attributes)
        attrs["device_trackers"] = [*attrs["device_trackers"], "device_tracker.macbook_pro"]
        home.hass.states.async_set("person.nico", "home", attrs)
    return battery


async def test_laptop_to_keep_charged(home: Home, freezer) -> None:
    from custom_components.glados.briefing import device_warnings
    hass = home.hass
    freezer.move_to(NIGHT)
    battery = _laptop(home, "80", "Not Charging")
    options = {"keep_charged": [battery], "charge_below": 40}
    freezer.tick(timedelta(hours=1))
    assert device_warnings(hass, options) == []  # held at 80 on the charger, or fine anyway
    hass.states.async_set(battery, "23", {"device_class": "battery"})
    assert device_warnings(hass, options) == [
        "The MacBook Pro is at 23 percent and not charging."]
    hass.states.async_set("sensor.macbook_pro_internal_battery_state", "Charging")
    assert device_warnings(hass, options) == []


async def test_someone_elses_laptop_is_not_mentioned(home: Home, freezer) -> None:
    from custom_components.glados.briefing import device_warnings
    hass = home.hass
    freezer.move_to(NIGHT)
    battery = _laptop(home, "20", "Not Charging", owner=True)
    freezer.tick(timedelta(hours=1))
    options = {"keep_charged": [battery], "charge_below": 40}
    assert device_warnings(hass, options, [_nico(hass)]) == [
        "The MacBook Pro is at 20 percent and not charging."]
    assert device_warnings(hass, options, []) == []  # told to someone else: not theirs
