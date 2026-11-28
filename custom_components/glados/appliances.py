"""Appliances finishing: "the washing machine is done".

Label a power sensor (or the smart plug's device) glados_appliance. When it has
drawn power for a while (a run) and then stays below the idle level for a few
minutes, the cycle is done: the Announcer says so where people are, with how
long it ran, and GLaDOS adds a remark. Nobody home: their phones.

A run needs ten minutes above the running level, so a kettle or a flicker is
not a cycle, and the idle wait lets a washing machine pause mid-cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .const import CONF_APPLIANCES, LABEL_APPLIANCE, VOICE_ANNOUNCER
from .people import people_home, phones, real_people
from .registry import label_entities
from .setpieces import appliance_lines

if TYPE_CHECKING:
    from . import GladosData

RUNNING_ABOVE = 10.0  # watts
IDLE_BELOW = 3.0
MIN_RUN = timedelta(minutes=10)
IDLE_FOR = timedelta(minutes=4)


def _name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    name = state.name if state else entity_id
    for word in (" power", " Power", " plug", " Plug"):
        name = name.removesuffix(word)
    return name.strip()


class Appliances:
    """Watches labelled power sensors for a finished cycle."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    def _sensors(self) -> list[str]:
        return sorted(
            e for e in label_entities(self.hass, LABEL_APPLIANCE)
            if e.startswith("sensor.")
            and (s := self.hass.states.get(e)) is not None
            and (s.attributes.get("device_class") == "power"
                 or s.attributes.get("unit_of_measurement") in ("W", "kW"))
        )

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        if not self.data.options.get(CONF_APPLIANCES, True):
            return []
        now = dt_util.now()
        said = []
        for entity_id in self._sensors():
            state = self.hass.states.get(entity_id)
            try:
                watts = float(state.state) * (1000 if state.attributes.get("unit_of_measurement") == "kW" else 1)
            except (TypeError, ValueError):
                continue
            key = f"appliance {entity_id}"
            run = json.loads(self.data.memory.get(key) or "{}")
            if watts > RUNNING_ABOVE:
                run.setdefault("started", now.isoformat())
                run.pop("idle_since", None)
            elif watts < IDLE_BELOW and "started" in run:
                started = dt_util.parse_datetime(run["started"])
                run.setdefault("idle_since", now.isoformat())
                idle_since = dt_util.parse_datetime(run["idle_since"])
                if now - idle_since >= IDLE_FOR:
                    if idle_since - started >= MIN_RUN:
                        minutes = int((idle_since - started).total_seconds() // 60)
                        said.append(await self._done(entity_id, minutes))
                    run = {}
            self.data.memory.set(key, json.dumps(run))
        return said

    async def _done(self, entity_id: str, minutes: int) -> dict[str, Any]:
        announcer, glados = appliance_lines(_name(self.hass, entity_id), minutes)
        result = await self.data.announcer.async_announce(AnnounceRequest(
            facts=announcer, voice=VOICE_ANNOUNCER, glados_line=glados))
        if not result.get("spoken"):
            people = people_home(self.hass) or real_people(self.hass)
            targets = sorted({x for p in people for x in phones(self.hass, p)})
            if targets:
                await self.hass.services.async_call(
                    "notify", "send_message",
                    {"entity_id": targets, "title": "Done", "message": announcer}, blocking=True)
        return {**result, "appliance": entity_id}
