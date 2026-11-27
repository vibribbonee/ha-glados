"""Reminders read out when they are due, and kept for later while people sleep.

Every open to-do with a due time, on a person's own list (todo.<person>_s_list)
or the shared one (todo.to_do), is said when it comes due:

- in the room that person is in, by the Announcer ("Reminder: call the dentist."),
  with the person's name when more than one person is home;
- to their phone when they are away, or when it cannot be said;
- while they sleep (in bed, a dark bedroom, before their alarm) it goes to their
  phone quietly and is kept: the first time that room is awake and she may speak,
  the Announcer says what came due in the night.

Reminders made by voice are ticked off once delivered; other to-dos stay open.
A reminder is never said twice, and one that came due during a restart is still
said, up to an hour late.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .const import CONF_REMINDERS, CONF_SCHEDULE, OWN_LIST_TEMPLATE, SHARED_LIST, VOICE_ANNOUNCER
from .people import Person, all_people, people_home, person_area, phones
from .rooms import describe

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(seconds=30)
LATE_LIMIT = timedelta(hours=1)  # a reminder missed during a restart, still said
HOLD_LIMIT = timedelta(hours=14)  # what came due in the night, said after waking
REMINDER_NOTE = "Reminder set by voice"
HELD_KEY = "held reminders"
_ASLEEP = ("someone is in bed", "the bedroom is dark", "people may be asleep")


def _lists(hass: HomeAssistant) -> dict[str, Person | None]:
    """Each reminder list and whose it is (None: the shared list)."""
    found: dict[str, Person | None] = {}
    for person in all_people(hass):
        entity_id = OWN_LIST_TEMPLATE.format(slug=person.slug)
        if hass.states.get(entity_id) is not None:
            found[entity_id] = person
    if hass.states.get(SHARED_LIST) is not None:
        found[SHARED_LIST] = None
    return found


def _due(item: dict[str, Any]) -> datetime | None:
    due = str(item.get("due") or "")
    if "T" not in due and " " not in due:
        return None  # a date without a time is a to-do, not a reminder
    at = dt_util.parse_datetime(due)
    return dt_util.as_local(at) if at else None


class Reminders:
    """Says due reminders, and keeps the night's for the morning."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    @property
    def enabled(self) -> bool:
        return bool(self.data.options.get(CONF_REMINDERS, True))

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Say what is due now, then what was kept from the night."""
        if not self.enabled:
            return []
        said = await self._due_now()
        said += await self._held()
        return said

    # Due now -------------------------------------------------------------

    async def _due_now(self) -> list[dict[str, Any]]:
        lists = _lists(self.hass)
        if not lists:
            return []
        response = await self.hass.services.async_call(
            "todo", "get_items", {"entity_id": list(lists), "status": "needs_action"},
            blocking=True, return_response=True,
        )
        now = dt_util.now()
        memory = self.data.memory
        said = []
        for todo_list, found in (response or {}).items():
            for item in found.get("items", []):
                at = _due(item)
                key = f"reminded {item.get('uid')}"
                if at is None or at > now or now - at > LATE_LIMIT or memory.get(key):
                    continue
                memory.set(key, at.isoformat())
                said.append(await self._deliver(todo_list, lists.get(todo_list), item, at))
        return said

    async def _deliver(
        self, todo_list: str, person: Person | None, item: dict[str, Any], at: datetime
    ) -> dict[str, Any]:
        what = str(item.get("summary") or "").strip()
        name = f"{person.name.capitalize()}, " if person and len(people_home(self.hass)) > 1 else ""
        home = person is None or person.home
        area = person_area(self.hass, person) if person else None
        result: dict[str, Any] = {"spoken": False, "reason": "away"}
        if home:
            result = await self.data.announcer.async_announce(
                AnnounceRequest(facts=f"{name}Reminder: {what}.", voice=VOICE_ANNOUNCER,
                                area=area, ignore_schedule=True)
            )
        if not result.get("spoken"):
            await self._to_phone(person, what)
            if home and any(r in result.get("reason", "") for r in _ASLEEP):
                self._hold(what, person, area, at)
        if str(item.get("description") or "") == REMINDER_NOTE:
            await self.hass.services.async_call(
                "todo", "update_item",
                {"entity_id": todo_list, "item": item.get("uid"), "status": "completed"},
                blocking=True,
            )
        return {**result, "what": what}

    async def _to_phone(self, person: Person | None, what: str) -> None:
        people = [person] if person else people_home(self.hass)
        targets = sorted({p for x in people if x for p in phones(self.hass, x)})
        if targets:
            await self.hass.services.async_call(
                "notify", "send_message",
                {"entity_id": targets, "title": "Reminder", "message": what},
                blocking=True,
            )

    # Kept from the night ----------------------------------------------------

    def held(self) -> list[dict[str, str]]:
        raw = self.data.memory.get(HELD_KEY)
        return json.loads(raw) if raw else []

    def _hold(self, what: str, person: Person | None, area: str | None, at: datetime) -> None:
        held = [*self.held(), {"what": what, "person": person.entity_id if person else "",
                               "area": area or "", "at": at.isoformat()}]
        self.data.memory.set(HELD_KEY, json.dumps(held))

    async def _held(self) -> list[dict[str, Any]]:
        held = self.held()
        if not held:
            return []
        now = dt_util.now()
        schedule = str(self.data.options.get(CONF_SCHEDULE) or "") or None
        keep, said = [], []
        by_area: dict[str, list[dict[str, str]]] = {}
        for h in held:
            if now - dt_util.parse_datetime(h["at"]) > HOLD_LIMIT:
                continue  # too old to mention
            by_area.setdefault(h["area"], []).append(h)
        for area, items in by_area.items():
            ctx = describe(self.hass, area or None, schedule)
            if ctx.sleeping or ctx.in_bed or ctx.dark_bedroom or not ctx.may_speak:
                keep.extend(items)
                continue
            lines = ", ".join(
                f"{i['what']} at {dt_util.parse_datetime(i['at']).strftime('%H:%M')}" for i in items
            )
            noun = "reminder" if len(items) == 1 else "reminders"
            result = await self.data.announcer.async_announce(
                AnnounceRequest(
                    facts=f"While you were in suspension, the following {noun} came due: {lines}.",
                    voice=VOICE_ANNOUNCER, area=area or None,
                )
            )
            if result.get("spoken"):
                said.append(result)
            else:
                keep.extend(items)
        self.data.memory.set(HELD_KEY, json.dumps(keep))
        return said
