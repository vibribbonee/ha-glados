"""Appliances: a finished cycle is said once; a kettle or a pause is not."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import label_registry as lr

from .conftest import NOW, Home
from .sim import run_between, setup


def _washer(home: Home) -> None:
    lr.async_get(home.hass).async_create("glados_appliance")
    home.entity("sensor.washing_machine_power", "0", labels={"glados_appliance"},
                device_class="power", unit_of_measurement="W", friendly_name="Washing machine power")


def _watts(home: Home, value: float):
    return lambda: home.hass.states.async_set(
        "sensor.washing_machine_power", str(value),
        {"device_class": "power", "unit_of_measurement": "W", "friendly_name": "Washing machine power"})


async def test_a_wash_with_a_pause(home: Home, freezer, caplog) -> None:
    freezer.move_to(NOW)
    _washer(home)
    entry, run = await setup(home.hass, {})
    t = NOW
    await run_between(home.hass, freezer, run, t, t + timedelta(hours=1, minutes=10), {
        t + timedelta(minutes=1): _watts(home, 450),
        t + timedelta(minutes=20): _watts(home, 1),  # soaking: a pause, not the end
        t + timedelta(minutes=22): _watts(home, 300),
        t + timedelta(minutes=51): _watts(home, 0.5),  # done
    })
    assert "the other features carry on" not in caplog.text
    done = [x for x in run.texts() if "completed%20its%20cycle" in x]
    assert len(done) == 1
    assert "The%20Washing%20machine%20has%20completed%20its%20cycle%2C%20after%2050%20minutes" in done[0]


async def test_a_kettle_is_not_a_cycle(home: Home, freezer) -> None:
    freezer.move_to(NOW)
    _washer(home)
    entry, run = await setup(home.hass, {})
    await run_between(home.hass, freezer, run, NOW, NOW + timedelta(minutes=20), {
        NOW + timedelta(minutes=1): _watts(home, 2000),
        NOW + timedelta(minutes=4): _watts(home, 0),
    })
    assert not [x for x in run.texts() if "completed" in x]


async def test_nobody_home_goes_to_the_phone(home: Home, freezer) -> None:
    hass = home.hass
    freezer.move_to(NOW)
    _washer(home)
    hass.states.async_set("person.nico", "not_home", hass.states.get("person.nico").attributes)
    entry, run = await setup(hass, {})
    await run_between(hass, freezer, run, NOW, NOW + timedelta(minutes=40), {
        NOW + timedelta(minutes=1): _watts(home, 450),
        NOW + timedelta(minutes=30): _watts(home, 0),
    })
    assert any("Washing machine has completed" in p["message"] for p in run.phone)
