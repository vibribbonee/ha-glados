"""Shared fixtures: a small home with the same patterns as the real one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=dt_util.get_time_zone("Europe/Amsterdam"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return


@dataclass
class Home:
    """Handles to the fake home, so tests can change it."""

    hass: HomeAssistant
    bedroom: str
    office: str

    def entity(self, entity_id: str, state: str, area: str | None = None,
               device: str | None = None, labels: set[str] | None = None,
               **attributes) -> str:
        """Register an entity and set its state."""
        domain, object_id = entity_id.split(".", 1)
        reg = er.async_get(self.hass)
        entry = reg.async_get_or_create(
            domain, "test", entity_id, suggested_object_id=object_id, device_id=device
        )
        assert entry.entity_id == entity_id
        reg.async_update_entity(entity_id, area_id=area, labels=labels or set())
        self.hass.states.async_set(entity_id, state, attributes)
        return entity_id


@pytest.fixture
async def home(hass: HomeAssistant, freezer) -> Home:
    """Nico in the bedroom, with a phone, a Puck and the usual sensors."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(NOW)

    areas = ar.async_get(hass)
    bedroom = areas.async_create("Bedroom").id
    office = areas.async_create("Office").id
    labels = lr.async_get(hass)
    for name in ("glados", "glados_quiet", "glados_heating", "glados_cooling", "glados_own_chime"):
        labels.async_create(name)

    source = MockConfigEntry(domain="test")
    source.add_to_hass(hass)
    devices = dr.async_get(hass)
    bermuda = devices.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("test", "bermuda_nico")}, name="Nico phone"
    ).id
    phone = devices.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("test", "pixel")}, name="Pixel 9a"
    ).id
    watch = devices.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("test", "watch")}, name="Galaxy Watch"
    ).id

    h = Home(hass, bedroom, office)
    h.entity("device_tracker.bermuda_nico", "home", device=bermuda)
    h.entity("sensor.nico_phone_area", "Bedroom", device=bermuda)
    h.entity("device_tracker.pixel_9a", "home", device=phone)
    h.entity("sensor.pixel_9a_next_alarm", "unavailable", device=phone, device_class="timestamp")
    h.entity("notify.pixel_9a", "unknown", device=phone)
    h.entity("device_tracker.galaxy_watch", "home", device=watch)
    h.entity("notify.galaxy_watch", "unknown", device=watch)
    hass.states.async_set(
        "person.nico", "home",
        {"friendly_name": "nico", "user_id": "user-nico",
         "device_trackers": ["device_tracker.bermuda_nico", "device_tracker.pixel_9a",
                             "device_tracker.galaxy_watch"]},
    )
    hass.states.async_set("person.byte", "not_home", {"friendly_name": "byte", "device_trackers": []})

    h.entity("binary_sensor.bedroom_presence", "on", area=bedroom, device_class="presence")
    h.entity("binary_sensor.bed_occupancy", "off", area=bedroom, device_class="occupancy")
    h.entity("light.bedroom_main", "on", area=bedroom, labels={"glados"})
    h.entity("sensor.bedroom_co2", "1240", area=bedroom, device_class="carbon_dioxide")
    h.entity("sensor.bedroom_temperature", "17.9", area=bedroom, device_class="temperature")
    h.entity("binary_sensor.bedroom_window", "off", area=bedroom, device_class="window",
             friendly_name="Bedroom window")
    h.entity("assist_satellite.puck_3", "idle", area=bedroom, supported_features=3)
    h.entity("assist_satellite.office_puck", "idle", area=office, supported_features=1)
    hass.states.async_set("weather.home", "sunny", {"temperature": 0.4})
    hass.states.async_set("schedule.glados_may_speak_up", "on")
    return h
