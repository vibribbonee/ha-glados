"""Alarms that ring on the room's speaker, and the backup for phone alarms.

A morning alarm goes to the person's phone, and HA keeps a backup that rings
the room only when the phone alarm failed:

- the alarm never showed up as the phone's next alarm (it was never set);
- the phone is unavailable (a flat battery, offline);
- it was not dismissed within the backup time: while a phone alarm rings or is
  snoozed, the phone's next alarm still points at it; dismissed, it moves on.

Any other alarm rings on the room's speaker.

A ringing alarm repeats a few minutes apart, at most three times, and stops as
soon as the room looks awake (out of bed and the light on), or when told to stop.
Alarms are the one thing allowed past the sleep rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .const import CONF_ANNOUNCER_VOICE, VOICE_ANNOUNCER, VOICE_GLADOS
from .rooms import describe
from .setpieces import alarm_lines, wake_lines

if TYPE_CHECKING:
    from . import GladosData

MEMORY_KEY = "alarms"
CHECK_EVERY = timedelta(seconds=30)
RING_EVERY = timedelta(minutes=3)
RINGS = 3
SNOOZE = timedelta(minutes=9)


@dataclass
class Alarm:
    """One alarm: when, where, and whether it only backs up a phone alarm."""

    at: str  # local ISO time it was set for
    area: str
    person: str = ""
    label: str = ""
    wake: bool = True  # a wake-up alarm (morning) or a labelled daytime one
    backup: bool = False  # rings only if they are still asleep
    next: str = ""  # when it rings next (ISO)
    rings: int = 0
    id: str = ""
    phone_sensor: str = ""  # the phone's next-alarm sensor, for a backup
    confirmed: bool = False  # the phone showed this alarm as its next one


def _awake(hass: HomeAssistant, area: str) -> bool:
    ctx = describe(hass, area, None)
    return not ctx.in_bed and not ctx.dark_bedroom


class AlarmClock:
    """Keeps the alarms, rings them, and lets them be stopped or snoozed."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    # Storage ----------------------------------------------------------------

    def alarms(self) -> list[Alarm]:
        raw = self.data.memory.get(MEMORY_KEY)
        return [Alarm(**a) for a in json.loads(raw)] if raw else []

    def _save(self, alarms: list[Alarm]) -> None:
        self.data.memory.set(MEMORY_KEY, json.dumps([asdict(a) for a in alarms]))

    def add(self, at: datetime, area: str, person: str = "", label: str = "",
            wake: bool = True, backup_after: timedelta | None = None,
            phone_sensor: str = "") -> Alarm:
        """Store an alarm; a backup is checked backup_after the alarm time."""
        ring_at = at + backup_after if backup_after is not None else at
        alarm = Alarm(at=at.isoformat(), area=area, person=person, label=label, wake=wake,
                      backup=backup_after is not None, next=ring_at.isoformat(),
                      id=uuid.uuid4().hex[:8], phone_sensor=phone_sensor)
        self._save([*self.alarms(), alarm])
        return alarm

    def stop(self, area: str | None = None, snooze: bool = False) -> list[Alarm]:
        """Stop (or snooze) the alarms ringing now, in one room or everywhere."""
        now = dt_util.now()
        keep, hit = [], []
        for a in self.alarms():
            ringing = a.rings > 0 or dt_util.parse_datetime(a.next) <= now
            if ringing and (area is None or a.area == area):
                hit.append(a)
                if snooze:
                    a.next, a.rings = (now + SNOOZE).isoformat(), 0
                    a.backup = False
                    keep.append(a)
            else:
                keep.append(a)
        self._save(keep)
        return hit

    # Ringing ----------------------------------------------------------------

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Ring whatever is due. Returns what was said."""
        now = dt_util.now()
        said: list[dict[str, Any]] = []
        keep: list[Alarm] = []
        changed = False
        for alarm in self.alarms():
            if alarm.backup and not alarm.confirmed and self._phone_points_at(alarm):
                alarm.confirmed, changed = True, True
            if dt_util.parse_datetime(alarm.next) > now:
                keep.append(alarm)
                continue
            changed = True
            if alarm.backup and alarm.rings == 0 and not self.phone_failed(alarm):
                continue  # the phone alarm rang and was dismissed
            if alarm.wake and alarm.rings and _awake(self.hass, alarm.area):
                continue  # up after the last ring
            said.append(await self._ring(alarm))
            alarm.rings += 1
            if alarm.wake and alarm.rings < RINGS:
                alarm.next = (now + RING_EVERY).isoformat()
                keep.append(alarm)
        if changed:
            self._save(keep)
        return said

    def _phone_alarm(self, alarm: Alarm) -> datetime | None | str:
        """The phone's next alarm: a time, None if unset, "gone" if unavailable."""
        state = self.hass.states.get(alarm.phone_sensor) if alarm.phone_sensor else None
        if state is None or state.state in ("unavailable", "unknown"):
            return "gone"
        return dt_util.parse_datetime(state.state)

    def _phone_points_at(self, alarm: Alarm) -> bool:
        found = self._phone_alarm(alarm)
        at = dt_util.parse_datetime(alarm.at)
        return isinstance(found, datetime) and abs(found - at) <= timedelta(minutes=1)

    def phone_failed(self, alarm: Alarm) -> bool:
        """At backup time: did the phone alarm fail to do its job?"""
        if not alarm.confirmed:
            return True  # it never showed up on the phone
        found = self._phone_alarm(alarm)
        if found == "gone":
            return True  # flat battery or offline
        at = dt_util.parse_datetime(alarm.at)
        # Still pointing at this alarm (ringing, snoozed): not dismissed.
        return isinstance(found, datetime) and found <= at + timedelta(minutes=1)

    async def _ring(self, alarm: Alarm) -> dict[str, Any]:
        time = dt_util.parse_datetime(alarm.at).strftime("%H:%M")
        if alarm.wake:
            announcer, glados = wake_lines(alarm.rings, time)
        else:
            announcer, glados = alarm_lines(time, alarm.label or "your alarm")
        has_announcer = bool(self.data.options.get(CONF_ANNOUNCER_VOICE))
        return await self.data.announcer.async_announce(
            AnnounceRequest(
                facts=announcer if has_announcer else f"{announcer} {glados}",
                voice=VOICE_ANNOUNCER if has_announcer else VOICE_GLADOS,
                area=alarm.area,
                glados_line=glados if has_announcer else f"{announcer} {glados}",
                wake=True,
            )
        )
