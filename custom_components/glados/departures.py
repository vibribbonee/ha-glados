"""Leave-time reminders: a heads-up, then leave now, for each person.

Each person with a leave-time helper (input_datetime.leave_home_<person>, set
by voice with the Set leave time tool) gets, while they are home:

- a heads-up some minutes before (setting; 15 by default), with the outside
  temperature, by the Announcer in the room they are in;
- "leave now" at the time itself, with what is still on (devices labelled
  glados_left_on) and which windows are open, then one GLaDOS remark.

It speaks outside the speaking schedule (mornings start early), but not where
someone sleeps or on Do Not Disturb; then it goes to that person's phone. A
minute missed during a restart is caught up, up to five minutes late.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .const import CONF_LEAVE_HEADS_UP, LABEL_LEFT_ON, VOICE_ANNOUNCER
from .people import Person, has_leave_helper, leave_time, people_home, person_area, phones
from .registry import area_of, label_entities
from .rooms import describe
from .setpieces import leave_glados

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(seconds=30)
CATCH_UP = timedelta(minutes=5)
_ON = ("on", "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "playing")


def still_on(hass: HomeAssistant) -> tuple[list[str], list[str]]:
    """(devices still on that should not be, open windows and doors that are placed)."""
    on = sorted(
        s.name for e in label_entities(hass, LABEL_LEFT_ON)
        if (s := hass.states.get(e)) is not None and s.state in _ON
    )
    tagged = label_entities(hass, "glados")
    open_ = sorted(
        s.name for s in hass.states.async_all("binary_sensor")
        if s.attributes.get("device_class") in ("window", "door", "garage_door", "opening")
        and s.state == "on" and (area_of(hass, s.entity_id) or s.entity_id in tagged)
    )
    return on, open_


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class Departures:
    """Says when to leave."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = dt_util.now()
        heads_up = timedelta(minutes=int(self.data.options.get(CONF_LEAVE_HEADS_UP, 15) or 0))
        home = people_home(self.hass)
        said = []
        for person in home:
            if not has_leave_helper(self.hass, person):
                continue
            leave = leave_time(self.hass, person)
            if leave is None:
                continue
            leave = dt_util.as_local(leave)
            moments = [("leave", leave)]
            if heads_up:
                moments.insert(0, ("heads_up", leave - heads_up))
            for kind, at in moments:
                key = f"{kind} {person.entity_id}"
                if not (at <= now < at + CATCH_UP) or self.data.memory.get(key) == at.isoformat():
                    continue
                self.data.memory.set(key, at.isoformat())
                said.append(await self._say(person, kind, leave, heads_up, len(home) > 1))
        return said

    async def _say(self, person: Person, kind: str, leave: datetime, heads_up: timedelta,
                   several: bool) -> dict[str, Any]:
        to = f"{person.name.capitalize()}: " if several else ""
        area = person_area(self.hass, person)
        if kind == "heads_up":
            outside = describe(self.hass, area, None).outside
            temp = f" Outside temperature: {round(outside)} degrees." if outside is not None else ""
            minutes = int(heads_up.total_seconds() // 60)
            line = (f"{to}Departure in {minutes} minutes. At {leave.strftime('%H:%M')}.{temp} "
                    "Please collect your belongings.")
            glados = ""
        else:
            on, open_ = still_on(self.hass)
            notes = ""
            if on:
                notes += f" Still on: {_join(on)}."
            if open_:
                notes += f" Still open: {_join(open_)}."
            line = f"{to}Departure time. Leave the house now.{notes}"
            glados = leave_glados()
        result = await self.data.announcer.async_announce(
            AnnounceRequest(facts=line, voice=VOICE_ANNOUNCER, area=area,
                            ignore_schedule=True, glados_line=glados)
        )
        if not result.get("spoken") and (targets := phones(self.hass, person)):
            await self.hass.services.async_call(
                "notify", "send_message",
                {"entity_id": targets,
                 "title": "Leave now" if kind == "leave" else "Leave soon", "message": line},
                blocking=True,
            )
        return {**result, "kind": kind}
