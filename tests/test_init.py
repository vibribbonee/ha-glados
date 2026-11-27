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
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "voice_agent": "conversation.glados_voice",
            "announcer_voice": "tts.piper_2:announcer",
            "beep_in": "",
            "beep_out": "",
            "speaking_schedule": "schedule.glados_may_speak_up",
            "routine_minutes": 40,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.options["routine_minutes"] == 40


async def test_user_flow(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
