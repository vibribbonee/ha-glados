"""Room context, compared with what the glados_room_context script returns."""

from __future__ import annotations

from datetime import timedelta

from custom_components.glados.rooms import describe

from .conftest import NOW, Home

SCHEDULE = "schedule.glados_may_speak_up"


async def test_finds_the_room_people_are_in(home: Home) -> None:
    ctx = describe(home.hass, None, SCHEDULE)
    assert ctx.area == home.bedroom
    assert ctx.area_name == "Bedroom"
    assert ctx.people == ["nico"]
    assert ctx.occupied and ctx.anyone_home and ctx.may_speak
    assert ctx.co2 == 1240
    assert ctx.temperature == 17.9
    assert ctx.outside == 0.4
    assert ctx.windows == ["binary_sensor.bedroom_window"]
    assert ctx.open_windows == []
    assert ctx.satellite == "assist_satellite.puck_3"
    assert ctx.ask_satellite == "assist_satellite.puck_3"
    assert not ctx.sleeping


async def test_another_room_has_no_people(home: Home) -> None:
    ctx = describe(home.hass, home.office, SCHEDULE)
    assert ctx.people == []
    assert not ctx.occupied
    assert ctx.satellite == "assist_satellite.office_puck"
    assert ctx.ask_satellite == ""


async def test_dark_bedroom_counts_as_sleeping(home: Home) -> None:
    home.hass.states.async_set("light.bedroom_main", "off")
    ctx = describe(home.hass, home.bedroom, SCHEDULE)
    assert ctx.dark_bedroom and ctx.sleeping


async def test_bed_sensor(home: Home) -> None:
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    ctx = describe(home.hass, home.bedroom, SCHEDULE)
    assert ctx.in_bed and ctx.sleeping
    # The bed does not count as sitting in the room.
    assert ctx.occupied_minutes == 0


async def test_morning_alarm_still_to_ring(home: Home) -> None:
    alarm = (NOW + timedelta(hours=1)).isoformat()
    home.hass.states.async_set("sensor.pixel_9a_next_alarm", alarm, {"device_class": "timestamp"})
    assert describe(home.hass, home.bedroom, SCHEDULE).before_alarm == "11:00"


async def test_afternoon_alarm_is_not_a_morning_alarm(home: Home) -> None:
    alarm = (NOW + timedelta(hours=4)).isoformat()
    home.hass.states.async_set("sensor.pixel_9a_next_alarm", alarm, {"device_class": "timestamp"})
    assert describe(home.hass, home.bedroom, SCHEDULE).before_alarm == ""


async def test_video_keeps_her_quiet_but_music_does_not(home: Home) -> None:
    home.entity("media_player.bedroom_tv", "playing", area=home.bedroom, media_content_type="movie")
    assert describe(home.hass, home.bedroom, SCHEDULE).watching == ["media_player.bedroom_tv"]
    home.hass.states.async_set("media_player.bedroom_tv", "playing", {"media_content_type": "music"})
    assert describe(home.hass, home.bedroom, SCHEDULE).watching == []


async def test_do_not_disturb_label(home: Home) -> None:
    home.entity("input_boolean.dnd", "on", labels={"glados_quiet"})
    assert describe(home.hass, home.bedroom, SCHEDULE).quiet == ["input_boolean.dnd"]


async def test_heaters_in_the_room_or_unplaced(home: Home) -> None:
    home.entity("switch.blanket", "off", labels={"glados_heating"})
    assert describe(home.hass, home.bedroom, SCHEDULE).heaters == ["switch.blanket"]
    home.entity("switch.bedroom_heater", "off", area=home.bedroom, labels={"glados_heating"})
    assert describe(home.hass, home.bedroom, SCHEDULE).heaters == ["switch.bedroom_heater"]


async def test_glados_label_picks_the_sensor(home: Home) -> None:
    home.entity("sensor.better_co2", "600", area=home.bedroom,
                labels={"glados"}, device_class="carbon_dioxide")
    assert describe(home.hass, home.bedroom, SCHEDULE).co2 == 600


async def test_no_one_home_falls_back_to_presence(home: Home) -> None:
    home.hass.states.async_set("person.nico", "not_home", {"friendly_name": "nico"})
    ctx = describe(home.hass, None, SCHEDULE)
    assert ctx.area == home.bedroom
    assert ctx.people == []
