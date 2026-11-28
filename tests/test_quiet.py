"""Quiet mode and "what did you say?"."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.glados.announce import AnnounceRequest
from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import NOW, Home


async def _setup(hass: HomeAssistant) -> tuple[MockConfigEntry, llm.APIInstance]:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x", "announcer_voice": "tts.p:a"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctx = llm.LLMContext(platform="t", context=Context(), language="en",
                         assistant="conversation", device_id=None)
    return entry, await llm.async_get_api(hass, DOMAIN, ctx)


async def _call(api, tool, **args):
    return await api.async_call_tool(llm.ToolInput(tool_name=tool, tool_args=args))


def _switch(hass: HomeAssistant) -> str:
    return next(s.entity_id for s in hass.states.async_all("switch")
                if s.entity_id.endswith("quiet_mode"))


async def test_quiet_for_half_an_hour(home: Home, freezer) -> None:
    hass = home.hass
    entry, api = await _setup(hass)
    async_mock_service(hass, "assist_satellite", "announce")
    announcer = entry.runtime_data.announcer
    assert (await _call(api, "quiet_mode", minutes=30)).data == {"quiet_until": "10:30", "day": "today"}
    await hass.async_block_till_done()
    assert hass.states.get(_switch(hass)).state == "on"

    quiet = await announcer.async_announce(AnnounceRequest(facts="Psst.", voice="announcer",
                                                           ignore_schedule=True))
    assert quiet == {**quiet, "spoken": False, "reason": "quiet mode until 10:30"}
    # An alarm still rings.
    alarm = await announcer.async_announce(AnnounceRequest(facts="Wake up.", voice="announcer",
                                                           wake=True))
    assert alarm["spoken"]

    freezer.move_to(NOW + timedelta(minutes=31))
    again = await announcer.async_announce(AnnounceRequest(facts="Hello.", voice="announcer",
                                                           ignore_schedule=True))
    assert again["spoken"]
    await hass.async_block_till_done()
    assert hass.states.get(_switch(hass)).state == "off"


async def test_switch_and_talk_again(home: Home) -> None:
    hass = home.hass
    entry, api = await _setup(hass)
    switch = _switch(hass)
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(switch).attributes["until"] is None  # until switched off
    await _call(api, "quiet_mode", off=True)
    await hass.async_block_till_done()
    assert hass.states.get(switch).state == "off"


async def test_what_did_you_say(home: Home) -> None:
    hass = home.hass
    entry, api = await _setup(hass)
    async_mock_service(hass, "assist_satellite", "announce")
    assert (await _call(api, "repeat_last")).error
    await entry.runtime_data.announcer.async_announce(AnnounceRequest(
        facts="Departure time. Leave the house now.", voice="announcer", ignore_schedule=True,
        glados_line="Late again."))
    said = (await _call(api, "repeat_last")).data["said"]
    assert said[0] == {"when": "10:00", "where": "Bedroom",
                       "text": "Departure time. Leave the house now. Late again."}


async def test_switch_goes_off_on_time(home: Home, freezer) -> None:
    hass = home.hass
    entry, api = await _setup(hass)
    await _call(api, "quiet_mode", minutes=10)
    freezer.move_to(NOW + timedelta(minutes=11))
    await entry.runtime_data.heartbeat.async_beat()
    await hass.async_block_till_done()
    assert hass.states.get(_switch(hass)).state == "off"
