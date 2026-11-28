"""Bedtime per person: when, and the nudges.

Each person's bedtime is their next morning alarm minus their sleep goal; with
no alarm, the usual bedtime if one is set. Their last call is the alarm minus
the minimum sleep. While they are home and awake, in the room they are in:

- an hour before bedtime: bedtime in an hour, and the one thing that matters for
  tomorrow (from the briefing);
- at bedtime: GLaDOS says so;
- half an hour before the last call, only if lights are still on in their room:
  the Announcer's last call, with one GLaDOS sting;
- at bedtime and last call, a phone low and off the charger is said; going to bed
  with it (in bed, or the bedroom dark) gets one push on the phone, never a voice.

Never for someone in bed or in a dark room, never on Do Not Disturb or during
a video; outside the speaking schedule it still speaks, since bedtime is late.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .briefing import async_briefing, phone_battery
from .const import (
    CONF_BEDTIME,
    CONF_MIN_SLEEP,
    CONF_SLEEP_GOAL,
    CONF_USUAL_BEDTIME,
    LABEL_GLADOS,
    MORNING_ENDS_HOUR,
    VOICE_ANNOUNCER,
    VOICE_GLADOS,
)
from .dates import parse_time
from .people import Person, next_alarms, people_home, person_area, phones
from .registry import area_of, label_entities
from .rooms import describe
from .setpieces import bedtime_glados, last_call_lines

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(seconds=30)
CATCH_UP = timedelta(minutes=5)
HEADS_UP = timedelta(hours=1)
LAST_CALL_BEFORE = timedelta(minutes=30)
# A phone below this, off the charger at bedtime, may not last the night (and the
# morning alarm is on it).
PHONE_LOW = 60
OFF_CHARGER_IN_BED = timedelta(minutes=10)  # past the pad's flicker and a last scroll
NIGHT_FROM, NIGHT_UNTIL = 21, 4


@dataclass
class Bedtime:
    person: Person
    bedtime: datetime | None
    last_call: datetime | None
    alarm: datetime | None


def morning_alarm(hass: HomeAssistant, person: Person, now: datetime) -> datetime | None:
    """Their next phone alarm, if it is a morning one within the next day."""
    found = [
        dt_util.as_local(t) for _, t in next_alarms(hass, person)
        if now < t < now + timedelta(hours=30) and dt_util.as_local(t).hour < MORNING_ENDS_HOUR
    ]
    return min(found) if found else None


def bedtime_for(hass: HomeAssistant, options: dict[str, Any], person: Person,
                now: datetime | None = None) -> Bedtime:
    """When this person should be asleep, and their last call."""
    now = now or dt_util.now()
    alarm = morning_alarm(hass, person, now)
    goal = timedelta(hours=float(options.get(CONF_SLEEP_GOAL, 8)))
    minimum = timedelta(hours=float(options.get(CONF_MIN_SLEEP, 6)))
    if alarm:
        return Bedtime(person, alarm - goal, alarm - minimum, alarm)
    usual = parse_time(str(options.get(CONF_USUAL_BEDTIME) or ""))
    if usual is None:
        return Bedtime(person, None, None, None)
    at = datetime.combine(now.date(), usual, tzinfo=now.tzinfo)
    if at + timedelta(hours=6) < now:
        at += timedelta(days=1)  # tonight's, unless last night's was only just now
    return Bedtime(person, at, None, None)


class Bedtimes:
    """Nudges each person towards bed."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        if not self.data.options.get(CONF_BEDTIME, True):
            return []
        now = dt_util.now()
        said = []
        for person in people_home(self.hass):
            bt = bedtime_for(self.hass, self.data.options, person, now)
            moments = []
            if bt.bedtime:
                moments += [("heads_up", bt.bedtime - HEADS_UP), ("bedtime", bt.bedtime)]
            if bt.last_call:
                moments.append(("last_call", bt.last_call - LAST_CALL_BEFORE))
            for kind, at in moments:
                key = f"bedtime {kind} {person.entity_id}"
                if not (at <= now < at + CATCH_UP) or self.data.memory.get(key) == at.isoformat():
                    continue
                self.data.memory.set(key, at.isoformat())
                if result := await self._nudge(person, kind, bt):
                    said.append(result)
            if result := await self._phone_in_bed(person, now):
                said.append(result)
        return said

    def _phone_line(self, person: Person) -> str:
        level = phone_battery(self.hass, person)
        if level is None or level >= PHONE_LOW:
            return ""
        return f"Your phone is at {level} percent and not on the charger. Plug it in."

    async def _phone_in_bed(self, person: Person, now: datetime) -> dict[str, Any] | None:
        """Gone to bed with the phone off the charger: a push, never a voice in the dark."""
        if not (now.hour >= NIGHT_FROM or now.hour < NIGHT_UNTIL):
            return None
        ctx = describe(self.hass, person_area(self.hass, person), None)
        if not (ctx.in_bed or ctx.dark_bedroom):
            return None
        night = (now - timedelta(hours=NIGHT_UNTIL + 1)).date().isoformat()
        key = f"phone warned {person.entity_id}"
        level = phone_battery(self.hass, person, OFF_CHARGER_IN_BED)
        if level is None or level >= PHONE_LOW or self.data.memory.get(key) == night:
            return None
        targets = phones(self.hass, person)
        if not targets:
            return None
        self.data.memory.set(key, night)
        alarm = morning_alarm(self.hass, person, now)
        message = f"Your phone is at {level} percent and not charging." + (
            f" Your {alarm.strftime('%H:%M')} alarm is on it." if alarm else "")
        await self.hass.services.async_call(
            "notify", "send_message",
            {"entity_id": targets, "title": "Charge your phone", "message": message},
            blocking=True,
        )
        return {"kind": "phone", "person": person.entity_id, "speech": message}

    def _lights_on(self, area: str | None) -> bool:
        return any(
            e.startswith("light.") and area_of(self.hass, e) == area
            and self.hass.states.is_state(e, "on")
            for e in label_entities(self.hass, LABEL_GLADOS)
        )

    async def _nudge(self, person: Person, kind: str, bt: Bedtime) -> dict[str, Any] | None:
        area = person_area(self.hass, person)
        ctx = describe(self.hass, area, None)
        if ctx.in_bed or ctx.dark_bedroom:
            return None  # already on the way
        bed = bt.bedtime.strftime("%H:%M") if bt.bedtime else ""
        if kind == "heads_up":
            brief = await async_briefing(self.hass, self.data.options, False, area)
            line = f"Bedtime is in an hour, at {bed}. {brief['say']}".strip()
            req = AnnounceRequest(facts=line, voice=VOICE_GLADOS, area=area,
                                  glados_line=line, ignore_schedule=True, awake=True)
        elif kind == "bedtime":
            line = f"It is {bed}. {self._phone_line(person)} {bedtime_glados()}".replace("  ", " ")
            req = AnnounceRequest(facts=line, voice=VOICE_GLADOS, area=area,
                                  glados_line=line, ignore_schedule=True, awake=True)
        else:
            if not self._lights_on(area):
                return None
            minimum = float(self.data.options.get(CONF_MIN_SLEEP, 6))
            announcer, glados = last_call_lines(
                bt.last_call.strftime("%H:%M"), minimum, bt.alarm.strftime("%H:%M"))
            if phone := self._phone_line(person):
                announcer = f"{announcer} {phone}"
            req = AnnounceRequest(facts=announcer, voice=VOICE_ANNOUNCER, area=area,
                                  glados_line=glados, ignore_schedule=True, awake=True)
        result = await self.data.announcer.async_announce(req)
        return {**result, "kind": kind, "person": person.entity_id}
