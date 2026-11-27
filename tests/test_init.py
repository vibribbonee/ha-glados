"""Setting up the entry and calling the services."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import Home


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _call(hass: HomeAssistant, service: str, **data):
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


async def test_services(home: Home) -> None:
    hass = home.hass
    entry = await _setup(hass)

    assert (await _call(hass, "clean_text", text="It is -3°C"))["text"] == "It is minus 3 degrees"

    ctx = await _call(hass, "room_context")
    assert ctx["area"] == home.bedroom and ctx["people"] == ["nico"]

    who = await _call(hass, "who", person="")
    assert who["name"] == "nico" and who["area"] == home.bedroom
    assert who["phones"] == ["notify.pixel_9a"] and who["list"] == "todo.to_do"
    assert (await _call(hass, "who", person="Edo")) == {"found": False}

    await hass.services.async_call(
        DOMAIN, "remember", {"key": "greeted person.nico", "value": "yes"}, blocking=True
    )
    recall = await _call(hass, "recall", key="greeted person.nico")
    assert recall["value"] == "yes" and recall["today"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, "announce")


async def test_options_flow(home: Home) -> None:
    hass = home.hass
    entry = await _setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    # The form comes in sections; only Brain is open.
    sections = [k.schema for k in flow["data_schema"].schema]
    assert sections == ["brain", "voices", "warnings", "initiative", "days", "nights"]
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "brain": {"chat_agent": "conversation.chat", "personality": False,
                      "voice_agent": "conversation.glados_voice"},
            "voices": {"announcer_voice": "tts.piper_2:announcer",
                       "speaking_schedule": "schedule.glados_may_speak_up"},
            "warnings": {"co2_alerts": "announcer", "co2_reminder_minutes": 30,
                         "cold_outside_below": 8},
            "days": {"reminders": True, "leave_heads_up_minutes": 15, "routine_minutes": 40,
                     "alarm_backup_minutes": 10},
            "nights": {"morning_greeting": True, "bedtime_nudges": False,
                       "sleep_goal_hours": 8, "minimum_sleep_hours": 6},
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    options = entry.runtime_data.options
    assert options["routine_minutes"] == 40 and options["co2_alerts"] == "announcer"
    assert options["bedtime_nudges"] is False and options["beep_in"] == ""  # stored flat

    # A section left out keeps what was there: CO2 warnings stay on.
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        flow["flow_id"], {"brain": {"chat_agent": "conversation.chat", "personality": False}})
    await hass.async_block_till_done()
    assert entry.runtime_data.options["co2_alerts"] == "announcer"


async def test_user_flow(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"chat_agent": "conversation.chat", "personality": True}
    )
    assert result["type"] == "create_entry"
    options = result["result"].options
    assert options["chat_agent"] == "conversation.chat" and options["personality"]
    assert options["announcer_voice"] == "" and options["speaking_schedule"] == ""
