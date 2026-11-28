"""A room's climate comes from the room, not from a device's insides."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar

from custom_components.glados.rooms import describe

from .conftest import Home


async def test_cpu_and_printer_sensors_are_not_the_room(home: Home) -> None:
    office = ar.async_get(home.hass).async_create("Study").id
    home.entity("sensor.echo_show_cpu_temperature", "43", area=office, device_class="temperature")
    home.entity("sensor.p1s_bed_temperature", "60", area=office, device_class="temperature")
    home.entity("sensor.broken_thermometer", "-40", area=office, device_class="temperature")
    home.entity("sensor.study_climate_temperature", "19.5", area=office, device_class="temperature")
    home.entity("sensor.study_climate_humidity", "48", area=office, device_class="humidity")
    ctx = describe(home.hass, office)
    assert ctx.temperature == 19.5 and ctx.humidity == 48


async def test_a_labelled_sensor_always_wins(home: Home) -> None:
    office = ar.async_get(home.hass).async_create("Study").id
    home.entity("sensor.study_climate_temperature", "19.5", area=office, device_class="temperature")
    home.entity("sensor.desk_probe_temperature", "21", area=office, device_class="temperature",
                labels={"glados"})
    assert describe(home.hass, office).temperature == 21
