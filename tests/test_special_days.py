"""Special days: a weekend, a birthday, quiet mode, a guest staying over."""

from __future__ import annotations

from datetime import timedelta

from .conftest import NOW, Home
from .sim import run_between, setup

DAY = NOW.replace(hour=6, minute=0)
NICO = "assist_satellite.puck_3"


def _asleep(home: Home) -> None:
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    home.hass.states.async_set("light.bedroom_main", "off")


def _up(home: Home):
    def change() -> None:
        home.hass.states.async_set("binary_sensor.bed_occupancy", "off", {"device_class": "occupancy"})
        home.hass.states.async_set("light.bedroom_main", "on")
    return change


async def test_weekend_without_an_alarm(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    _asleep(home)
    entry, run = await setup(hass, {})
    await run_between(hass, freezer, run, DAY, DAY.replace(hour=12), {
        DAY.replace(hour=9, minute=40): _up(home),
        DAY.replace(hour=10, minute=30): lambda: hass.states.async_set("light.bedroom_main", "off"),
        DAY.replace(hour=10, minute=31): lambda: hass.states.async_set("light.bedroom_main", "on"),
    })
    assert "the other features carry on" not in caplog.text
    greetings = [t for t in run.texts(NICO) if "Today is" in t or "commitment" in t
                 or "Nothing timed" in t]
    assert len(greetings) == 1, run.texts()  # once, at the first light, not again at 10:31


async def test_birthday_morning(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    _asleep(home)
    hass.states.async_set("sensor.pixel_9a_next_alarm", DAY.replace(hour=7).isoformat(),
                          {"device_class": "timestamp"})
    entry, run = await setup(hass, {"birthday_song": "media-source://media_source/local/hum.mp3"},
                             events=[{"start": DAY.date().isoformat(),
                                      "end": (DAY + timedelta(days=1)).date().isoformat(),
                                      "summary": "Nico's birthday"}])
    await run_between(hass, freezer, run, DAY, DAY.replace(hour=9), {
        DAY.replace(hour=7, minute=5): _up(home)})
    assert "the other features carry on" not in caplog.text
    assert run.count("hum.mp3", NICO) == 1
    assert run.count("Happy birthday, Nico.", NICO) == 1
    assert run.count("suspension", NICO) == 0  # the birthday replaces the usual greeting


async def test_a_day_in_quiet_mode(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    entry, run = await setup(hass, {"co2_alerts": "announcer"}, todos=[
        {"list": "todo.nico_s_list", "uid": "n1", "summary": "Stretch",
         "due": DAY.replace(hour=10).isoformat(), "status": "needs_action",
         "description": "Reminder set by voice"}])
    from custom_components.glados.switch import FOREVER
    entry.runtime_data.announcer.set_quiet(FOREVER)
    clock = entry.runtime_data.alarms
    clock.add(DAY.replace(hour=11), home.bedroom, "nico", label="oven", wake=False)
    hass.states.async_set("sensor.bedroom_co2", "1700", {"device_class": "carbon_dioxide"})
    await run_between(hass, freezer, run, DAY, DAY.replace(hour=12))
    assert "the other features carry on" not in caplog.text
    assert [p["message"] for p in run.phone] == ["Stretch"]  # reminder to the phone
    assert run.count("oven") == 1  # the alarm still rang
    # And nothing else was said: no reminder, no CO2 warning.
    assert not [t for t in run.texts() if "Stretch" in t or "1700" in t], run.texts()


async def test_a_guest_is_not_an_occupant(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    hass.states.async_set("person.guest", "home", {"friendly_name": "Guest"})
    entry, run = await setup(hass, {"usual_bedtime": "22:00"})
    await run_between(hass, freezer, run, DAY.replace(hour=20), DAY.replace(hour=23))
    assert "the other features carry on" not in caplog.text
    assert not [t for t in run.texts() if "Guest" in t]
    from homeassistant.helpers import entity_registry as er
    ours = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == "glados"]
    assert not [e for e in ours if "guest" in e]
