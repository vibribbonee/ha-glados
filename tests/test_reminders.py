"""Reminders: said when due, once; to the phone when away; kept while asleep."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN
from custom_components.glados.reminders import Reminders

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home

DUE = NOW.replace(hour=10, minute=0)


async def _reminders(home: Home, items: list[dict]) -> tuple[Reminders, dict]:
    hass: HomeAssistant = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x",
                                     "announcer_voice": "tts.piper:announcer"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("todo.nico_s_list", str(len(items)), {"friendly_name": "Nico's list"})
    calls = {
        "say": async_mock_service(hass, "assist_satellite", "announce"),
        "phone": async_mock_service(hass, "notify", "send_message"),
        "done": async_mock_service(hass, "todo", "update_item"),
    }
    async_mock_service(hass, "todo", "get_items", supports_response=SupportsResponse.ONLY,
                       response={"todo.nico_s_list": {"items": items}})
    return Reminders(hass, entry.runtime_data), calls


def _item(uid: str = "a", what: str = "Call the dentist", due=DUE, voice: bool = True) -> dict:
    return {"uid": uid, "summary": what, "due": due.isoformat(), "status": "needs_action",
            "description": "Reminder set by voice" if voice else ""}


async def test_said_once_in_their_room(home: Home) -> None:
    rem, calls = await _reminders(home, [_item(), _item("b", "Later", DUE + timedelta(hours=2))])
    said = await rem.async_tick()
    assert [s["what"] for s in said] == ["Call the dentist"]
    assert "Reminder%3A%20Call%20the%20dentist" in calls["say"][0].data["media_id"]
    assert calls["say"][0].data["entity_id"] == "assist_satellite.puck_3"
    assert calls["done"][0].data["item"] == "a"  # a voice reminder is ticked off
    assert await rem.async_tick() == []  # never twice


async def test_other_todos_stay_open(home: Home) -> None:
    rem, calls = await _reminders(home, [_item(voice=False)])
    await rem.async_tick()
    assert calls["say"] and not calls["done"]


async def test_away_goes_to_the_phone(home: Home) -> None:
    home.hass.states.async_set("person.nico", "not_home", home.hass.states.get("person.nico").attributes)
    rem, calls = await _reminders(home, [_item()])
    await rem.async_tick()
    assert not calls["say"]
    assert calls["phone"][0].data == {"entity_id": ["notify.pixel_9a"], "title": "Reminder",
                                      "message": "Call the dentist"}


async def test_kept_while_asleep_and_said_after_waking(home: Home) -> None:
    home.hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    rem, calls = await _reminders(home, [_item()])
    await rem.async_tick()
    assert calls["phone"] and not calls["say"]  # quietly to the phone
    assert rem.held()[0]["what"] == "Call the dentist"
    await rem.async_tick()
    assert not calls["say"]  # still asleep
    home.hass.states.async_set("binary_sensor.bed_occupancy", "off", {"device_class": "occupancy"})
    said = await rem.async_tick()
    assert said and "While%20you%20were%20in%20suspension" in calls["say"][0].data["media_id"]
    assert "10%3A00" in calls["say"][0].data["media_id"] and rem.held() == []


async def test_too_late_is_dropped(home: Home) -> None:
    rem, calls = await _reminders(home, [_item(due=DUE - timedelta(hours=2))])
    assert await rem.async_tick() == [] and not calls["say"]
