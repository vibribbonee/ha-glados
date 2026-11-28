"""Run the real heartbeat through a stretch of time in the test house."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

BEAT = timedelta(seconds=30)


@dataclass
class Said:
    satellite: str
    text: str


@dataclass
class Run:
    said: list[Said] = field(default_factory=list)
    phone: list[dict] = field(default_factory=list)

    def texts(self, satellite: str | None = None) -> list[str]:
        return [s.text for s in self.said if satellite is None or s.satellite == satellite]

    def count(self, fragment: str, satellite: str | None = None) -> int:
        return sum(fragment in t for t in self.texts(satellite))


async def setup(hass: HomeAssistant, options: dict, todos: list[dict] | None = None,
                events: list[dict] | None = None) -> tuple[MockConfigEntry, Run]:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS", options={
        "chat_agent": "conversation.x", "announcer_voice": "tts.p:a", **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    run = Run()
    said = async_mock_service(hass, "assist_satellite", "announce")
    run_ref = run

    phone = async_mock_service(hass, "notify", "send_message")
    for service in ("homeassistant.turn_on", "todo.update_item", "input_datetime.set_datetime",
                    "light.turn_on"):
        domain, name = service.split(".")
        async_mock_service(hass, domain, name)
    async_mock_service(hass, "assist_satellite", "ask_question",
                       supports_response=SupportsResponse.ONLY, response={"id": "no"})
    hass.states.async_set("calendar.personal", "off")
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY,
                       response={"calendar.personal": {"events": events or []}})
    lists = {}
    for todo in todos or []:
        lists.setdefault(todo.pop("list"), []).append(todo)
    for entity_id in lists:
        hass.states.async_set(entity_id, "1")
    async_mock_service(hass, "todo", "get_items", supports_response=SupportsResponse.ONLY,
                       response={k: {"items": v} for k, v in lists.items()})

    def collect() -> None:
        run_ref.said = [Said(c.data["entity_id"], c.data.get("message") or c.data.get("media_id", ""))
                        for c in said]
        run_ref.phone = [c.data for c in phone]

    run.collect = collect  # type: ignore[attr-defined]
    return entry, run


async def run_between(hass: HomeAssistant, freezer, run: Run, start: datetime, end: datetime,
                      changes: dict[datetime, Callable[[], None]] | None = None) -> Run:
    """Beat from start to end, applying the changes at their times. The model is offline."""
    changes = dict(changes or {})
    with patch("custom_components.glados.voice.conversation.async_converse",
               AsyncMock(side_effect=Exception("no model in tests"))), \
         patch("custom_components.glados.character.random.randrange", return_value=1):
        t = start
        while t < end:
            for at, change in sorted(changes.items()):
                if at <= t:
                    change()
                    changes.pop(at)
            freezer.move_to(t)
            async_fire_time_changed(hass, t)
            await hass.async_block_till_done()
            t += BEAT
    run.collect()  # type: ignore[attr-defined]
    return run


def add_person(home, name: str, room: str, alarm: datetime | None = None) -> str:
    """Another person with a phone and a room tracker."""
    hass = home.hass
    source = next(iter(hass.config_entries.async_entries("test")))
    devices = dr.async_get(hass)
    tracker = devices.async_get_or_create(config_entry_id=source.entry_id,
                                          identifiers={("test", f"bermuda_{name}")}).id
    phone = devices.async_get_or_create(config_entry_id=source.entry_id,
                                        identifiers={("test", f"phone_{name}")}).id
    home.entity(f"device_tracker.bermuda_{name}", "home", device=tracker)
    home.entity(f"sensor.{name}_phone_area", room, device=tracker)
    home.entity(f"device_tracker.{name}_phone", "home", device=phone)
    home.entity(f"sensor.{name}_phone_next_alarm", alarm.isoformat() if alarm else "unavailable",
                device=phone, device_class="timestamp")
    home.entity(f"notify.{name}_phone", "unknown", device=phone)
    hass.states.async_set(f"person.{name}", "home", {
        "friendly_name": name, "user_id": f"user-{name}",
        "device_trackers": [f"device_tracker.bermuda_{name}", f"device_tracker.{name}_phone"]})
    return f"person.{name}"
