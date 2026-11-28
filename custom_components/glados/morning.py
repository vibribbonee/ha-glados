"""Mornings: when they fell asleep, the wake-up, and the greeting.

- Asleep: between 20:00 and 05:00, a phone going on a wireless charger notes the
  start of that person's "suspension" (a re-dock within 20 minutes is ignored).
- Wake-up: a phone alarm reaching its time, or an alarm clock's "alarm ringing"
  sensor, between 04:00 and 13:00. The lights labelled glados_wakeup in that room
  fade on while it is still dark; a person without a leave time for today gets
  one: the alarm plus their morning routine. Once they are out of bed (waited for
  up to 45 minutes), she greets them.
- No alarm: the first time a light labelled glados goes on in the room a person
  is in, she greets them there.

The greeting, once per person per day: on their birthday the birthday song and
a fixed birthday line, with their first commitment. Otherwise the Announcer's
"you have been in suspension for" (when the night was noted), then GLaDOS with
the morning briefing. Quiet while someone is in bed in the dark, on Do Not
Disturb, during a video or without a speaker.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .briefing import async_facts
from .const import (
    CONF_BIRTHDAY_NAMES,
    CONF_BIRTHDAY_SONG,
    CONF_HOME_TOWN,
    CONF_MORNING,
    CONF_ROUTINE_MINUTES,
    LABEL_GLADOS,
    VOICE_ANNOUNCER,
    VOICE_GLADOS,
)
from .people import (
    Person,
    all_people,
    async_set_leave,
    has_leave_helper,
    leave_time,
    people_in_area,
    person_area,
    routine_minutes,
    tracker_devices,
)
from .registry import area_entities, area_of, device_entities, device_of, label_entities
from .rooms import describe
from .setpieces import birthday_line, suspension_line
from .voice import async_say

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(seconds=30)
WAIT_FOR_UP = timedelta(minutes=45)
AFTER_ALARM = timedelta(minutes=2)
LABEL_WAKEUP = "glados_wakeup"
_CHARGER = re.compile(r"^sensor\..*charger_type$")
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")
_RINGING = re.compile(r"^binary_sensor\..*alarm_ringing$")
_BIRTHDAY = re.compile(r"birthday|bday|verjaardag|jarig|compleanno|geburtstag", re.I)
PENDING_KEY = "morning pending"

TASK = (
    "Good morning, said directly to {name}, as you, never in the third person. In this "
    "order: first any birthdays and other all-day items today; then the first commitment "
    "if there is one; then the weather only if it changes what to wear or carry, in "
    "words, never wind speeds or rain amounts. They have just woken up, so keep it "
    "brief: two or three short sentences, the last a dry remark about them finally "
    "being conscious."
)


def _morning(now: datetime) -> bool:
    return 4 <= now.hour < 13


def birthday_names(option: str, person: Person) -> list[str]:
    """The names a person's birthday goes by: their own, plus the setting's.

    Setting format: "nico: Sjors, Nico; byte: Bee".
    """
    names = {person.name.lower(), person.slug.lower()}
    for part in (option or "").split(";"):
        key, _, value = part.partition(":")
        if key.strip().lower() in names:
            names.update(v.strip().lower() for v in value.split(",") if v.strip())
    return sorted(n for n in names if n)


class Mornings:
    """Notes the night, watches for the wake-up, and greets."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data
        self._lights_on: set[str] = set()

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    @property
    def enabled(self) -> bool:
        return bool(self.data.options.get(CONF_MORNING, True))

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        now = dt_util.now()
        self._note_sleep(now)
        said: list[dict[str, Any]] = []
        if _morning(now):
            await self._alarms_now(now)
            said += await self._greet_pending(now)
            said += await self._lights_mornings(now)
        return said

    # The night ---------------------------------------------------------------

    def _note_sleep(self, now: datetime) -> None:
        if 5 <= now.hour < 20:
            return
        memory = self.data.memory
        for person in all_people(self.hass):
            if person.away:
                continue
            docked = any(
                self.hass.states.is_state(e, "wireless")
                for d in tracker_devices(self.hass, person)
                for e in device_entities(self.hass, d) if _CHARGER.match(e)
            )
            key = f"asleep {person.entity_id}"
            last = memory.age(key)
            if docked and (last is None or last > timedelta(minutes=20)) and not memory.get(f"docked {person.entity_id}"):
                memory.set(key, now.isoformat())
            memory.set(f"docked {person.entity_id}", "yes" if docked else "")

    def slept_minutes(self, person: Person, now: datetime) -> int | None:
        at = self.data.memory.stored_at(f"asleep {person.entity_id}")
        if at is None:
            return None
        minutes = int((now - at).total_seconds() // 60)
        return minutes if 120 <= minutes <= 960 else None

    # The wake-up -------------------------------------------------------------

    def _owner(self, entity_id: str) -> list[Person]:
        device = device_of(self.hass, entity_id)
        owners = [p for p in all_people(self.hass) if device and device in tracker_devices(self.hass, p)]
        if owners:
            return owners
        area = area_of(self.hass, entity_id)
        return people_in_area(self.hass, area) if area else []

    def _pending(self) -> dict[str, dict[str, str]]:
        raw = self.data.memory.get(PENDING_KEY)
        return json.loads(raw) if raw else {}

    def _save_pending(self, pending: dict[str, dict[str, str]]) -> None:
        self.data.memory.set(PENDING_KEY, json.dumps(pending))

    async def _alarms_now(self, now: datetime) -> None:
        minute = now.strftime("%Y-%m-%d %H:%M")
        ringing = []
        for state in self.hass.states.async_all("sensor"):
            if _NEXT_ALARM.match(state.entity_id) and (t := dt_util.parse_datetime(state.state)):
                if dt_util.as_local(t).strftime("%Y-%m-%d %H:%M") == minute:
                    ringing.append(state.entity_id)
        for state in self.hass.states.async_all("binary_sensor"):
            if _RINGING.match(state.entity_id) and state.state == "on":
                ringing.append(state.entity_id)
        if not ringing:
            return
        pending = self._pending()
        for entity_id in ringing:
            for person in self._owner(entity_id):
                if person.away or person.entity_id in pending or self._greeted(person, now):
                    continue
                area = area_of(self.hass, entity_id) or person_area(self.hass, person) or ""
                pending[person.entity_id] = {"at": now.isoformat(), "area": area}
                await self._wake_lights(area)
                await self._leave_follows_alarm(person, now)
        self._save_pending(pending)

    async def _wake_lights(self, area: str) -> None:
        if not area or not self.hass.states.is_state("sun.sun", "below_horizon"):
            return
        lights = [e for e in label_entities(self.hass, LABEL_WAKEUP)
                  if e.startswith("light.") and e in area_entities(self.hass, area)
                  and self.hass.states.is_state(e, "off")]
        if lights:
            await self.hass.services.async_call(
                "light", "turn_on",
                {"entity_id": lights, "brightness_pct": 35, "transition": 180}, blocking=False,
            )

    async def _leave_follows_alarm(self, person: Person, now: datetime) -> None:
        if not has_leave_helper(self.hass, person):
            return
        leave = leave_time(self.hass, person)
        if leave and dt_util.as_local(leave).date() == now.date():
            return
        minutes = routine_minutes(self.hass, person, int(self.data.options.get(CONF_ROUTINE_MINUTES, 35)))
        at = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
        await async_set_leave(self.hass, person, at)

    async def _greet_pending(self, now: datetime) -> list[dict[str, Any]]:
        pending = self._pending()
        if not pending:
            return []
        said, keep = [], {}
        for entity_id, info in pending.items():
            at = dt_util.parse_datetime(info["at"])
            if now - at > WAIT_FOR_UP:
                continue  # never got up, or slept through: no greeting
            if now - at < AFTER_ALARM or describe(self.hass, info["area"] or None, None).in_bed:
                keep[entity_id] = info
                continue
            person = next((p for p in all_people(self.hass) if p.entity_id == entity_id), None)
            if person and (result := await self.async_greet(person, info["area"] or None)):
                said.append(result)
        self._save_pending(keep)
        return said

    async def _lights_mornings(self, now: datetime) -> list[dict[str, Any]]:
        """No alarm: the first real light on in the room someone is in."""
        lights = {e for e in label_entities(self.hass, LABEL_GLADOS) if e.startswith("light.")}
        on_now = {e for e in lights if self.hass.states.is_state(e, "on")}
        switched_on, self._lights_on = on_now - self._lights_on, on_now
        if not switched_on:
            return []
        said = []
        for person in all_people(self.hass):
            area = person_area(self.hass, person)
            if (person.home and area and not self._greeted(person, now)
                    and person.entity_id not in self._pending()
                    and any(area_of(self.hass, e) == area for e in switched_on)):
                if result := await self.async_greet(person, area):
                    said.append(result)
        return said

    # The greeting -------------------------------------------------------------

    def _greeted(self, person: Person, now: datetime) -> bool:
        at = self.data.memory.stored_at(f"greeted {person.entity_id}")
        return at is not None and dt_util.as_local(at).date() == now.date()

    async def _birthday(self, person: Person) -> bool:
        names = birthday_names(str(self.data.options.get(CONF_BIRTHDAY_NAMES) or ""), person)
        start = dt_util.start_of_local_day()
        calendars = [s.entity_id for s in self.hass.states.async_all("calendar")
                     if s.state not in ("unavailable", "unknown")]
        if not calendars:
            return False
        response = await self.hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": calendars, "start_date_time": start.isoformat(),
             "end_date_time": (start + timedelta(days=1)).isoformat()},
            blocking=True, return_response=True,
        )
        for found in (response or {}).values():
            for ev in found.get("events", []):
                title = str(ev.get("summary") or "").lower()
                if _BIRTHDAY.search(title) and any(
                    re.search(rf"(^|[^a-z]){re.escape(n)}([^a-z]|$)", title) for n in names
                ):
                    return True
        return False

    async def async_greet(
        self, person: Person, area: str | None = None, context: Context | None = None,
        pretend_birthday: bool = False, satellite: str | None = None,
    ) -> dict[str, Any] | None:
        """Greet one person, once a day. None when already greeted or it cannot be said."""
        now = dt_util.now()
        if self._greeted(person, now):
            return None
        if satellite:  # a test on a chosen speaker
            area = area_of(self.hass, satellite)
        area = area or person_area(self.hass, person)
        ctx = describe(self.hass, area, None)
        speaker = satellite or ctx.satellite
        if (ctx.in_bed and ctx.dark_bedroom) or ctx.quiet or ctx.watching or not speaker:
            return None
        name = person.name.capitalize()
        options = self.data.options
        announcer = self.data.announcer
        if pretend_birthday or await self._birthday(person):
            if song := str(options.get(CONF_BIRTHDAY_SONG) or ""):
                await announcer._play(speaker, media_id=song, preannounce=False)
            facts = await async_facts(self.hass, options, morning=True, area=area)
            plan = re.search(r"First commitment: ([^.]*)\.", facts)
            line = birthday_line(name, str(options.get(CONF_HOME_TOWN) or ""))
            if plan:
                line += f" Your first commitment today is {plan.group(1)}. Try to be on time."
            result = await announcer.async_announce(
                AnnounceRequest(facts=line, voice=VOICE_GLADOS, area=area, glados_line=line,
                                ignore_schedule=True, satellite=satellite or ""), context)
            result["birthday"] = True
        else:
            facts = await async_facts(self.hass, options, morning=True, area=area)
            slept = self.slept_minutes(person, now)
            spoken = await async_say(self.hass, options, facts, task=TASK.format(name=name),
                                     context=context)
            if slept is not None:
                result = await announcer.async_announce(
                    AnnounceRequest(facts=suspension_line(slept), voice=VOICE_ANNOUNCER,
                                    area=area, glados_line=spoken, ignore_schedule=True, satellite=satellite or ""), context)
            else:
                result = await announcer.async_announce(
                    AnnounceRequest(facts=spoken, voice=VOICE_GLADOS, area=area,
                                    glados_line=spoken, ignore_schedule=True, satellite=satellite or ""), context)
        if result.get("spoken"):
            self.data.memory.set(f"greeted {person.entity_id}", now.isoformat())
            self.data.memory.forget(f"asleep {person.entity_id}")
        return {**result, "person": person.entity_id}
