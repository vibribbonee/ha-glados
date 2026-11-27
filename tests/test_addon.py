"""The add-on interface: tools, instructions and jobs from other integrations."""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component
import probatio as p

from custom_components.glados.addon import (
    Addon,
    AnnounceRequest,
    GladosTool,
    async_announce,
    async_register_addon,
    glados_data,
    registered_addons,
)
from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import Home


class NextTrain(GladosTool):
    name = "next_train"
    description = "When the next train leaves."
    parameters = p.Schema({})

    async def run(self, hass, args, llm_context):
        return llm.ToolResult(data={"departs": "08:12"})


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS", options={"chat_agent": "conversation.x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ctx() -> llm.LLMContext:
    return llm.LLMContext(platform="t", context=Context(), language="en",
                          assistant="conversation", device_id=None)


async def test_addon_tools_prompt_and_job(home: Home) -> None:
    hass = home.hass
    events: list[str] = []

    @callback
    def start(hass: HomeAssistant, data) -> callback:
        events.append("start")
        return lambda: events.append("stop")

    trains = Addon(domain="glados_trains", name="Trains",
                   tools=lambda data: [NextTrain(data)],
                   prompt=lambda hass: "For trains, use next_train.", start=start)
    remove = async_register_addon(hass, trains)  # before GLaDOS is loaded
    assert events == []
    entry = await _setup(hass)
    assert events == ["start"]  # started with her

    api = await llm.async_get_api(hass, DOMAIN, _ctx())
    [tool] = [t for t in api.tools if t.name == "next_train"]
    assert tool.integration == "glados_trains"
    assert "For trains, use next_train." in api.api_prompt
    result = await api.async_call_tool(llm.ToolInput(tool_name="next_train", tool_args={}))
    assert result.data == {"departs": "08:12"}

    remove()
    assert events == ["start", "stop"] and registered_addons(hass) == []
    api = await llm.async_get_api(hass, DOMAIN, _ctx())
    assert not [t for t in api.tools if t.name == "next_train"]

    # Registered while she runs: started at once; stopped when she unloads.
    async_register_addon(hass, trains)
    assert events[-1] == "start"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert events[-1] == "stop" and glados_data(hass) is None


async def test_addon_can_announce(home: Home) -> None:
    hass = home.hass
    assert (await async_announce(hass, AnnounceRequest(facts="x")))["spoken"] is False
    await _setup(hass)
    calls = async_mock_service(hass, "assist_satellite", "announce")
    result = await async_announce(
        hass, AnnounceRequest(facts="Train in ten.", voice="announcer", ignore_schedule=True)
    )
    assert result["spoken"] and calls[0].data["entity_id"] == "assist_satellite.puck_3"
