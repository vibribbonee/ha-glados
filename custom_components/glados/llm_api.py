"""Her own tools, as a Home Assistant LLM API that any chat agent can use.

Turn on "GLaDOS" next to "Assist" under the chat agent's Control Home Assistant
setting, and the agent gets these tools beside the usual device control:

- set_reminder: a to-do with a due time on that person's own list
- set_leave_time: when someone leaves home, with the get-up time
- add_to_calendar: an appointment or all-day event
- upcoming_events: everything on every calendar, with real dates
- note_in_file: one fact for their permanent file

Dates are worked out here and returned spelled out ("Friday 27 November",
"in 3 days"), so a small model only has to read them. The formats match the
scripts they replace, so existing automations that read the lists and the
leave helpers keep working.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import re
from typing import TYPE_CHECKING, Any, override

import probatio as p

from homeassistant.components.calendar import CalendarEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.util import dt as dt_util

from .audio import audible_player, find_player
from .announce import blocked_reason
from .const import CONF_ROUTINE_MINUTES, DOMAIN, LABEL_GLADOS, LABEL_LEFT_ON
from .dates import days_away, parse_time, resolve_date, resolve_moment, spoken_date
from .people import (
    Person,
    all_people,
    android_phones,
    has_leave_helper,
    leave_helper,
    own_list,
    resolve_person,
    routine_minutes,
)
from .registry import area_name, area_of, label_entities
from .rooms import describe
from .speech import clean_for_speech

if TYPE_CHECKING:
    from . import GladosData

API_ID = DOMAIN
API_NAME = "GLaDOS"
REMINDER_NOTE = "Reminder set by voice"
CLEARED = "2000-01-01 00:00:00"
FILE_PROMPT_CHARS = 300
MAX_DAYS_AHEAD = 62

_WRITES = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=False)
_READS = llm.ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False)

_DAY = "today, tomorrow, a weekday such as monday, or a date as YYYY-MM-DD"
_PERSON = "Name of who it is for. Empty: the person speaking, or the only person at home."
_LEAVER = "Name of who is leaving. Empty: the person speaking, or the only person at home."


def _hm(value: datetime) -> str:
    return value.strftime("%H:%M")


def _user_id(llm_context: llm.LLMContext) -> str | None:
    return llm_context.context.user_id if llm_context.context else None


def _error(message: str) -> llm.ToolResult:
    return llm.ToolResult(data={"error": message}, error=True)


class GladosTool(llm.Tool):
    """A tool with validated arguments and access to the entry's data."""

    annotations = _WRITES

    def __init__(self, data: GladosData) -> None:
        self.data = data
        self.integration = DOMAIN

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        args = self.parameters(
            {k: v for k, v in tool_input.tool_args.items() if v not in (None, "")}
        )
        return await self.run(hass, args, llm_context)

    async def run(
        self, hass: HomeAssistant, args: dict[str, Any], llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        raise NotImplementedError


class SetReminder(GladosTool):
    name = "set_reminder"
    title = "Set reminder"
    description = (
        "For 'remind me to ...' at a time or in some minutes. Adds it to that person's "
        "own to-do list with a due time; at that time it is read out in the room they "
        "are in. Give what, and either in_minutes or time (with day). Not for leaving "
        "the house (set_leave_time) or for timers. Say the date and time as returned."
    )
    parameters = p.Schema(
        {
            p.Required("what", description="What to remind them of, short."): str,
            p.Optional("in_minutes", description="Remind after this many minutes."): p.All(
                p.Coerce(int), p.Range(min=1, max=1440)
            ),
            p.Optional("time", description="Time of day, such as 15:00."): str,
            p.Optional("day", description=f"{_DAY}. Empty: the next time it comes."): str,
            p.Optional("person", description=_PERSON): str,
        }
    )

    async def run(self, hass, args, llm_context):
        now = dt_util.now()
        if minutes := args.get("in_minutes"):
            at = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
        elif (t := parse_time(args.get("time"))) is not None:
            at = resolve_moment(args.get("day"), t, now)
        else:
            return _error("Ask when: a time or a number of minutes.")
        wanted = args.get("person", "")
        person = resolve_person(hass, wanted, _user_id(llm_context))
        if person is None and wanted:
            return _error(f"No person called {wanted}.")
        todo_list = own_list(hass, person)
        await hass.services.async_call(
            "todo",
            "add_item",
            {
                "entity_id": todo_list,
                "item": args["what"].strip(),
                "due_datetime": at.strftime("%Y-%m-%d %H:%M:%S"),
                "description": REMINDER_NOTE,
            },
            blocking=True,
            context=llm_context.context,
        )
        state = hass.states.get(todo_list)
        return llm.ToolResult(
            data={
                "reminder": args["what"].strip(),
                "for": person.name if person else "anyone at home",
                "time": _hm(at),
                "date": spoken_date(at),
                "day": days_away(at, now),
                "list": state.name if state else todo_list,
            }
        )


class SetLeaveTime(GladosTool):
    name = "set_leave_time"
    title = "Set leave time"
    description = (
        "When someone says when they have to leave the house. They are reminded 15 "
        "minutes before and at that time, in the room they are in, and get-up time "
        "follows from their morning routine. clear true for a stay-home day. Only for "
        "leaving the house, never for other reminders. Say the date as returned."
    )
    parameters = p.Schema(
        {
            p.Optional("time", description="Leave time, such as 07:45."): str,
            p.Optional("day", description=f"{_DAY}. Empty: the next time it comes."): str,
            p.Optional("person", description=_LEAVER): str,
            p.Optional("clear", description="No leave time, no reminder.", default=False): p.Boolean(),
        }
    )

    async def run(self, hass, args, llm_context):
        candidates = [x for x in all_people(hass) if has_leave_helper(hass, x)]
        if not candidates:
            return _error(
                "Nobody has a leave time helper. Create input_datetime.leave_home_<person>."
            )
        person: Person | None = resolve_person(
            hass, args.get("person", ""), _user_id(llm_context), among=candidates
        )
        if person is None:
            return _error(
                "Ask who is leaving. People with a leave time: "
                + ", ".join(x.name for x in candidates)
            )
        helper = leave_helper(person)
        t = parse_time(args.get("time"))
        if args["clear"] or t is None:
            await self._set(hass, helper, CLEARED, llm_context)
            return llm.ToolResult(data={"person": person.name, "leave": "none, no reminder"})
        now = dt_util.now()
        at = resolve_moment(args.get("day"), t, now)
        await self._set(hass, helper, at.strftime("%Y-%m-%d %H:%M:%S"), llm_context)
        routine = routine_minutes(hass, person, int(self.data.options[CONF_ROUTINE_MINUTES]))
        return llm.ToolResult(
            data={
                "person": person.name,
                "leave": _hm(at),
                "date": spoken_date(at),
                "day": days_away(at, now),
                "reminders": f"{_hm(at - timedelta(minutes=15))} and {_hm(at)}",
                "get_up_by": _hm(at - timedelta(minutes=routine)),
                "routine_minutes": routine,
            }
        )

    @staticmethod
    async def _set(hass, helper: str, value: str, llm_context) -> None:
        await hass.services.async_call(
            "input_datetime",
            "set_datetime",
            {"entity_id": helper, "datetime": value},
            blocking=True,
            context=llm_context.context,
        )


def writable_calendars(hass: HomeAssistant) -> list[str]:
    """Calendars that can take new events, the glados-labelled one first."""
    writable = [
        s.entity_id
        for s in hass.states.async_all("calendar")
        if int(s.attributes.get(ATTR_SUPPORTED_FEATURES) or 0) & CalendarEntityFeature.CREATE_EVENT
    ]
    labelled = label_entities(hass, LABEL_GLADOS)
    return sorted(writable, key=lambda e: e not in labelled)


class AddToCalendar(GladosTool):
    name = "add_to_calendar"
    title = "Add to calendar"
    description = (
        "Puts an appointment or plan on the calendar. Give what and day, and a start "
        "time (no time for an all-day event). calendar: a calendar's name, empty for "
        "the default. Not for reminders that should be spoken (set_reminder). Say the "
        "date as returned."
    )
    parameters = p.Schema(
        {
            p.Required("what", description="What it is."): str,
            p.Required("day", description=_DAY): str,
            p.Optional("time", description="Start time, such as 14:30. Empty: all day."): str,
            p.Optional("duration_minutes", default=60): p.All(p.Coerce(int), p.Range(min=5, max=1440)),
            p.Optional("location"): str,
            p.Optional("calendar", description="Calendar name. Empty: the default."): str,
        }
    )

    async def run(self, hass, args, llm_context):
        calendars = writable_calendars(hass)
        wanted = args.get("calendar", "").strip().lower()
        if wanted:
            calendars = [
                c for c in calendars
                if wanted in (hass.states.get(c).name or "").lower()
            ] or calendars
        if not calendars:
            return _error("No calendar here can take new events.")
        cal = calendars[0]
        now = dt_util.now()
        day = resolve_date(args["day"], now)
        data: dict[str, Any] = {"entity_id": cal, "summary": args["what"].strip()}
        if args.get("location"):
            data["location"] = args["location"]
        result: dict[str, Any] = {
            "added": args["what"].strip(),
            "calendar": hass.states.get(cal).name,
            "date": spoken_date(day),
            "day": days_away(day, now),
        }
        if (t := parse_time(args.get("time"))) is not None:
            start = datetime.combine(day, t, tzinfo=now.tzinfo)
            end = start + timedelta(minutes=args["duration_minutes"])
            data |= {
                "start_date_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date_time": end.strftime("%Y-%m-%d %H:%M:%S"),
            }
            result |= {"from": _hm(start), "until": _hm(end)}
        else:
            data |= {
                "start_date": day.isoformat(),
                "end_date": (day + timedelta(days=1)).isoformat(),
            }
            result["all_day"] = True
        await hass.services.async_call(
            "calendar", "create_event", data, blocking=True, context=llm_context.context
        )
        return llm.ToolResult(data=result)


class UpcomingEvents(GladosTool):
    name = "upcoming_events"
    title = "Upcoming events"
    description = (
        "Upcoming events from every calendar, sorted, each with its weekday, date and "
        "how many days away. For any question about plans, the schedule, appointments, "
        "birthdays, holidays or deliveries, and for 'how many days until'. days: 1 for "
        "today and tomorrow, 7 for this week, 31 for this month. Say the dates exactly "
        "as given, one event per sentence; never work out a date yourself."
    )
    annotations = _READS
    parameters = p.Schema(
        {
            p.Optional("days", description="How many days ahead.", default=7): p.All(
                p.Coerce(int), p.Range(min=1, max=MAX_DAYS_AHEAD)
            ),
        }
    )

    async def run(self, hass, args, llm_context):
        calendars = [
            s.entity_id
            for s in hass.states.async_all("calendar")
            if s.state not in ("unavailable", "unknown")
        ]
        now = dt_util.now()
        events: list[tuple[str, str]] = []
        if calendars:
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {"entity_id": calendars, "duration": {"days": args["days"]}},
                blocking=True,
                return_response=True,
            )
            for found in (response or {}).values():
                for ev in found.get("events", []):
                    events.append(_event_line(ev, now))
        lines = [line for _, line in sorted(events)]
        return llm.ToolResult(
            data={
                "now": f"{spoken_date(now)}, {_hm(now)}",
                "days_ahead": args["days"],
                "count": len(lines),
                "read_aloud": " ".join(lines) if lines else "Nothing scheduled.",
            }
        )


def _event_line(ev: dict[str, Any], now: datetime) -> tuple[str, str]:
    start = str(ev.get("start", ""))
    all_day = "T" not in start
    if all_day:
        when_date = resolve_date(start[:10], now)
        sort_key, clock = start[:10], ""
    else:
        at = dt_util.as_local(dt_util.parse_datetime(start))
        when_date, sort_key, clock = at.date(), at.isoformat(), f" at {_hm(at)}"
    away = days_away(when_date, now)
    when = (
        f"{away.capitalize()}, {spoken_date(when_date)}"
        if away in ("today", "tomorrow")
        else f"{spoken_date(when_date)}, {away}"
    )
    return sort_key, f"{when}{clock}, {ev.get('summary', '').strip()}."


class NoteInFile(GladosTool):
    name = "note_in_file"
    title = "Note in permanent file"
    description = (
        "Writes one short fact about a person into their permanent file, such as a "
        "preference, a plan, a habit or a failure. Use when someone tells you something "
        "about themselves worth keeping, or asks you to remember something."
    )
    parameters = p.Schema(
        {p.Required("note", description="One short fact, with the person's name."): str}
    )

    async def run(self, hass, args, llm_context):
        note = args["note"].strip()[:80]
        self.data.memory.add_note(note)
        return llm.ToolResult(data={"noted": note})


class SetVolume(GladosTool):
    name = "set_volume"
    title = "Set volume"
    description = (
        "Every volume change: louder, quieter, a little up, or a level. device: the "
        "name said, such as the TV; empty for whatever is playing. A TV whose sound "
        "comes out of a soundbar is handled here: the soundbar is changed. Report "
        "the device and level it returns, never a guess."
    )
    parameters = p.Schema(
        {
            p.Optional("device", description="Name of the TV or speaker. Empty: what is playing."): str,
            p.Optional("change", description="up or down."): p.In(["up", "down"]),
            p.Optional("step", description="Percent to change by.", default=10): p.All(
                p.Coerce(int), p.Range(min=1, max=50)
            ),
            p.Optional("level", description="Set to this percent instead."): p.All(
                p.Coerce(int), p.Range(min=0, max=100)
            ),
        }
    )

    async def run(self, hass, args, llm_context):
        here = None
        if llm_context.device_id:
            device = dr.async_get(hass).async_get(llm_context.device_id)
            here = device.area_id if device else None
        wanted = args.get("device", "")
        asked = find_player(hass, wanted, here)
        if asked is None:
            return _error(f"No speaker or TV called {wanted}." if wanted else "Nothing is playing.")
        target = audible_player(hass, asked)
        state = hass.states.get(target)
        current = state.attributes.get("volume_level") if state else None
        if "level" in args:
            new = args["level"]
        elif current is None:
            return _error(f"{state.name if state else target} does not report its volume.")
        else:
            delta = args["step"] if args.get("change", "up") == "up" else -args["step"]
            new = min(100, max(0, round(current * 100) + delta))
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": target, "volume_level": new / 100},
            blocking=True,
            context=llm_context.context,
        )
        result = {"device": state.name if state else target, "volume": f"{new} percent"}
        if target != asked:
            result["note"] = f"The {hass.states.get(asked).name} plays through it."
        return llm.ToolResult(data=result)


class SetAlarm(GladosTool):
    name = "set_alarm"
    title = "Set alarm"
    description = (
        "'Wake me at 7:30' or 'set an alarm for tomorrow at 6': sets a real alarm on "
        "that person's own phone, within the next 24 hours. person: empty for the "
        "person speaking. For anything later, or not to wake up, use set_reminder. Say "
        "the time and day as returned."
    )
    parameters = p.Schema(
        {
            p.Required("time", description="Alarm time, such as 07:30."): str,
            p.Optional("day", description="today or tomorrow. Empty: the next time it comes."): str,
            p.Optional("person", description=_PERSON): str,
            p.Optional("label", description="Short alarm label, such as Dentist."): str,
        }
    )

    async def run(self, hass, args, llm_context):
        t = parse_time(args["time"])
        if t is None:
            return _error("Ask for the time, such as seven thirty.")
        now = dt_util.now()
        at = resolve_moment(args.get("day"), t, now)
        if at - now > timedelta(hours=24):
            return _error("A phone alarm can only be set for the next 24 hours. Use set_reminder.")
        wanted = args.get("person", "")
        person = resolve_person(hass, wanted, _user_id(llm_context))
        if person is None:
            return _error(f"No person called {wanted}." if wanted else "Ask whose alarm it is.")
        services = android_phones(hass, person)
        if not services:
            return _error(f"{person.name} has no Android phone with the Home Assistant app.")
        extras = (
            f"android.intent.extra.alarm.HOUR:{at.hour},"
            f"android.intent.extra.alarm.MINUTES:{at.minute},"
            "android.intent.extra.alarm.SKIP_UI:true,"
            f"android.intent.extra.alarm.MESSAGE:{re.sub(r'[,:]', ' ', args.get('label') or 'GLaDOS')}"
        )
        await hass.services.async_call(
            "notify",
            services[0],
            {
                "message": "command_activity",
                "data": {"intent_action": "android.intent.action.SET_ALARM", "intent_extras": extras},
            },
            blocking=True,
            context=llm_context.context,
        )
        return llm.ToolResult(
            data={"alarm": _hm(at), "day": days_away(at, now), "date": spoken_date(at),
                  "person": person.name, "phone": services[0].removeprefix("mobile_app_")}
        )


class Broadcast(GladosTool):
    name = "broadcast"
    title = "Broadcast"
    description = (
        "'Tell everyone dinner is ready' or 'announce that I'm leaving': says a message "
        "on the voice satellites in every other room, except where someone is asleep, "
        "on Do Not Disturb or watching a video. Write the message as you would say it, "
        "one or two short sentences. Report the rooms it returns."
    )
    parameters = p.Schema(
        {p.Required("message", description="What to say, in your voice."): str}
    )

    async def run(self, hass, args, llm_context):
        message = clean_for_speech(args["message"])
        here = None
        if llm_context.device_id:
            device = dr.async_get(hass).async_get(llm_context.device_id)
            here = device.area_id if device else None
        sent: list[str] = []
        skipped: dict[str, str] = {}
        seen: set[str] = set()
        for state in hass.states.async_all("assist_satellite"):
            area = area_of(hass, state.entity_id)
            if state.state == "unavailable" or not area or area == here or area in seen:
                continue
            seen.add(area)
            ctx = describe(hass, area, None)
            room = area_name(hass, area)
            if reason := blocked_reason(ctx, ignore_schedule=True, anywhere=False):
                skipped[room] = reason
                continue
            await hass.services.async_call(
                "assist_satellite",
                "announce",
                {"entity_id": ctx.satellite or state.entity_id, "message": message},
                blocking=True,
                context=llm_context.context,
            )
            sent.append(room)
        if not sent:
            return _error("Nobody else could hear it: " + (
                ", ".join(f"{r}: {why}" for r, why in skipped.items()) or "no other room has a speaker"
            ))
        return llm.ToolResult(data={"said_in": sent, "skipped": skipped, "message": message})


class LeavingCheck(GladosTool):
    name = "leaving_check"
    title = "Leaving check"
    description = (
        "When someone says they are leaving, going out, going to bed, or asks if "
        "everything is off: what is still on that should not be, and which windows are "
        "open. Mention each item by name; turn things off only when they ask."
    )
    annotations = _READS
    parameters = p.Schema({})

    async def run(self, hass, args, llm_context):
        left_on = sorted(
            hass.states.get(e).name
            for e in label_entities(hass, LABEL_LEFT_ON)
            if hass.states.get(e) is not None
            and hass.states.get(e).state in ("on", "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "playing")
        )
        windows = sorted(
            s.name
            for s in hass.states.async_all("binary_sensor")
            if s.attributes.get("device_class") in ("window", "door", "garage_door", "opening")
            and s.state == "on"
        )
        return llm.ToolResult(
            data={
                "still_on": left_on or "nothing",
                "open": windows or "nothing",
                "all_clear": not left_on and not windows,
            }
        )


TOOLS = (SetReminder, SetLeaveTime, AddToCalendar, UpcomingEvents, NoteInFile, SetVolume,
         SetAlarm, Broadcast, LeavingCheck)


class GladosAPI(llm.API):
    """Her tools, plus today's date and her permanent file."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        super().__init__(hass=hass, id=API_ID, name=API_NAME)
        self.data = data

    def prompt(self) -> str:
        now = dt_util.now()
        notes, used = [], 0
        for note in self.data.memory.notes():
            if used + len(note) > FILE_PROMPT_CHARS:
                break
            notes.append(note)
            used += len(note) + 2
        file = (
            "Their permanent file, everything you know about them: " + "; ".join(notes) + "."
            if notes
            else "Their permanent file is still empty."
        )
        return (
            f"Today is {spoken_date(now)}, {_hm(now)}. Use these tools for reminders, "
            "leave times, the calendar and the permanent file. Dates and times come back "
            "already worked out: say them as given and never calculate one yourself. "
            "Report only what a tool returned; if it failed, say so. When told to be "
            "quiet, stop or shut up, answer in at most three words. Never end a reply "
            "with a question or an offer of more help. "
            f"{file}"
        )

    @override
    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=self.prompt(),
            llm_context=llm_context,
            tools=[tool(self.data) for tool in TOOLS],
        )
