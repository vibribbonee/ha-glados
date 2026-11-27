"""The Last announcement sensor and the diagnostics."""

from __future__ import annotations

from homeassistant.setup import async_setup_component

from custom_components.glados.announce import AnnounceRequest
from custom_components.glados.const import DOMAIN
from custom_components.glados.diagnostics import async_get_config_entry_diagnostics

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from .conftest import Home


async def test_said_then_quiet(home: Home) -> None:
    hass = home.hass
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS",
                            options={"chat_agent": "conversation.x", "announcer_voice": "tts.p:a"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "assist_satellite", "announce")
    sensor = next(s.entity_id for s in hass.states.async_all("sensor")
                  if s.entity_id.endswith("last_announcement"))

    announcer = entry.runtime_data.announcer
    await announcer.async_announce(AnnounceRequest(facts="Train in ten.", voice="announcer",
                                                   ignore_schedule=True))
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "Train in ten."

    hass.states.async_set("binary_sensor.bed_occupancy", "on", {"device_class": "occupancy"})
    await announcer.async_announce(AnnounceRequest(facts="Psst.", voice="announcer"))
    await hass.async_block_till_done()
    state = hass.states.get(sensor)
    assert state.state == "Quiet: someone is in bed"
    assert len(state.attributes["history"]) == 2

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["announcements"][0]["reason"] == "someone is in bed"
    assert "alarms" in diag["heartbeat"]["features"]
