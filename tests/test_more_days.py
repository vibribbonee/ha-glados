"""More days in the house: two people, a night, an empty house."""

from __future__ import annotations

from datetime import timedelta

from .conftest import NOW, Home
from .sim import add_person, run_between, setup

DAY = NOW.replace(hour=6, minute=0)
NICO = "assist_satellite.puck_3"  # bedroom
BYTE = "assist_satellite.office_puck"  # office


async def test_two_people_each_get_their_own(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    home.entity("binary_sensor.office_presence", "on", area=home.office, device_class="presence")
    add_person(home, "byte", "Office")
    entry, run = await setup(hass, {}, todos=[
        {"list": "todo.byte_s_list", "uid": "b1", "summary": "Feed the cat",
         "due": DAY.replace(hour=9).isoformat(), "status": "needs_action",
         "description": "Reminder set by voice"},
        {"list": "todo.nico_s_list", "uid": "n1", "summary": "Call the dentist",
         "due": DAY.replace(hour=10).isoformat(), "status": "needs_action",
         "description": "Reminder set by voice"},
    ])
    hass.states.async_set("input_datetime.leave_home_byte", DAY.replace(hour=12).strftime("%Y-%m-%d %H:%M:%S"))
    await run_between(hass, freezer, run, DAY, DAY.replace(hour=13))

    assert "the other features carry on" not in caplog.text
    # Each reminder in its owner's room, with their name since both are home.
    assert run.count("Byte%2C%20Reminder%3A%20Feed%20the%20cat", BYTE) == 1
    assert run.count("Feed%20the%20cat", NICO) == 0
    assert run.count("Nico%2C%20Reminder%3A%20Call%20the%20dentist", NICO) == 1
    # Byte's leave time in the office, named; nothing of it in the bedroom.
    assert run.count("Byte%3A%20Departure", BYTE) == 2  # heads-up and leave now
    assert run.count("Departure", NICO) == 0


async def test_a_night_reminder_waits_for_the_morning(home: Home, freezer, caplog) -> None:
    hass = home.hass
    night = (NOW - timedelta(days=1)).replace(hour=23, minute=30)
    freezer.move_to(night)
    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    hass.states.async_set("light.bedroom_main", "off")
    entry, run = await setup(hass, {}, todos=[
        {"list": "todo.nico_s_list", "uid": "n1", "summary": "Take the bins out",
         "due": NOW.replace(hour=3).isoformat(), "status": "needs_action",
         "description": "Reminder set by voice"}])
    morning = NOW.replace(hour=7, minute=30)
    await run_between(hass, freezer, run, night, morning + timedelta(minutes=10), {
        morning: lambda: (hass.states.async_set("binary_sensor.bed_occupancy", "off",
                                                {"device_class": "occupancy"}),
                          hass.states.async_set("light.bedroom_main", "on")),
    })
    assert "the other features carry on" not in caplog.text
    night_said = [s for s in run.said if "Take" in s.text and "suspension" not in s.text]
    assert not night_said  # nothing out loud in the night
    assert any("Take the bins out" in p.get("message", "") for p in run.phone)  # quietly to the phone
    assert run.count("While%20you%20were%20in%20suspension") == 1  # said after waking
    assert run.count("03%3A00") >= 1


async def test_nothing_said_in_an_empty_house(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(DAY)
    attrs = hass.states.get("person.nico").attributes
    hass.states.async_set("person.nico", "not_home", attrs)
    hass.states.async_set("binary_sensor.bedroom_presence", "off", {"device_class": "presence"})
    hass.states.async_set("sensor.nico_phone_area", "unknown")
    entry, run = await setup(hass, {"co2_alerts": "announcer", "usual_bedtime": "22:00"}, todos=[
        {"list": "todo.nico_s_list", "uid": "n1", "summary": "Buy milk",
         "due": DAY.replace(hour=11).isoformat(), "status": "needs_action",
         "description": "Reminder set by voice"}])
    hass.states.async_set("sensor.bedroom_co2", "1700", {"device_class": "carbon_dioxide"})
    await run_between(hass, freezer, run, DAY, DAY.replace(hour=23))
    assert "the other features carry on" not in caplog.text
    assert run.said == [], [s.text for s in run.said]
    assert [p["message"] for p in run.phone] == ["Buy milk"]
