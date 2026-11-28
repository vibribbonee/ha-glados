"""The bedtime and morning briefing: plain facts, then in her voice.

A port of the Get bedtime briefing script. For the people in the room (or
everyone at home), for tomorrow at bedtime or the rest of today in the morning:

- the calendar: the first timed commitment, the ones after it, all-day items;
- alarms: each person's next phone alarm, and whether it is early enough for the
  first commitment (morning routine minutes before it, half an hour more when it
  has a location); no alarm, and whether one is needed;
- leave times: when they leave home, so when to be up, and whether an alarm
  covers it;
- phones that will not last the night: not charging, with the battery level;
- the bedtime sensor, when one is set;
- the weather for that day.

The facts are worked out here; the voice agent only picks the two or three that
matter and says them, so the small model never reads the whole list aloud.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_BEDTIME_SENSOR, CONF_ROUTINE_MINUTES, LABEL_GLADOS
from .dates import spoken_date
from .people import (
    Person,
    leave_time,
    next_alarms,
    people_home,
    people_in_area,
    routine_minutes,
    tracker_devices,
)
from .registry import device_entities, label_entities
from .voice import async_say

_BATTERY = re.compile(r"^sensor\..*battery_level$")
_CHARGER = re.compile(r"^sensor\..*charger_type$")
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")

TASK_NIGHT = (
    "Bedtime briefing. Pick only the two or three facts that matter tonight: an early "
    "start, an alarm that is too late or missing, a birthday, a phone that needs "
    "charging, bad weather. Skip everything that is fine. Short spoken sentences, never "
    "a list, each time said once. End with one dry remark of your own."
)
TASK_MORNING = (
    "Morning briefing. Pick only what matters for the rest of today: the next "
    "commitment, a leave time, the weather if it changes plans. Skip everything that is "
    "fine. Short spoken sentences, never a list. End with one dry remark of your own."
)


@dataclass
class Event:
    title: str
    all_day: bool
    start: datetime
    location: str = ""


def _hm(value: datetime) -> str:
    return dt_util.as_local(value).strftime("%H:%M")


DELIVERY_NAME = re.compile(r"deliver|parcel|package|pakket|bezorg|postnl|\b(dhl|ups|dpd|gls)\b", re.I)
LABEL_DELIVERIES = "glados_deliveries"


def delivery_calendars(hass: HomeAssistant) -> list[str]:
    """Calendars of deliveries: labelled glados_deliveries, or named like it (PostNL)."""
    labelled = label_entities(hass, LABEL_DELIVERIES)
    return [s.entity_id for s in hass.states.async_all("calendar")
            if s.state not in ("unavailable", "unknown")
            and (s.entity_id in labelled or DELIVERY_NAME.search(s.name or ""))]


async def deliveries_today(hass: HomeAssistant) -> list[str]:
    """What is due to be delivered today."""
    calendars = delivery_calendars(hass)
    if not calendars:
        return []
    start = dt_util.start_of_local_day()
    return [e.title for e in await _events(hass, start, start + timedelta(days=1), calendars)]


async def _events(hass: HomeAssistant, start: datetime, end: datetime,
                  calendars: list[str] | None = None) -> list[Event]:
    calendars = calendars if calendars is not None else [
        s.entity_id for s in hass.states.async_all("calendar")
        if s.state not in ("unavailable", "unknown")
    ]
    if not calendars:
        return []
    response = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": calendars, "start_date_time": start.isoformat(),
         "end_date_time": end.isoformat()},
        blocking=True, return_response=True,
    )
    events = []
    for found in (response or {}).values():
        for ev in found.get("events", []):
            raw = str(ev.get("start", ""))
            all_day = "T" not in raw
            at = (datetime.combine(date.fromisoformat(raw[:10]), datetime.min.time(),
                                   tzinfo=start.tzinfo)
                  if all_day else dt_util.as_local(dt_util.parse_datetime(raw)))
            events.append(Event(str(ev.get("summary") or "").strip(), all_day, at,
                                str(ev.get("location") or "")))
    return sorted(events, key=lambda e: (not e.all_day, e.start))


async def _forecast(hass: HomeAssistant, day: date) -> dict[str, Any] | None:
    weather = [s.entity_id for s in hass.states.async_all("weather")
               if s.state not in ("unavailable", "unknown")]
    if not weather:
        return None
    tagged = [w for w in weather if w in label_entities(hass, LABEL_GLADOS)]
    pick = (tagged or weather)[0]
    try:
        response = await hass.services.async_call(
            "weather", "get_forecasts", {"entity_id": pick, "type": "daily"},
            blocking=True, return_response=True,
        )
    except Exception:
        return None
    for f in (response or {}).get(pick, {}).get("forecast", []):
        at = dt_util.parse_datetime(str(f.get("datetime", "")))
        if at and dt_util.as_local(at).date() == day:
            return f
    return None


def _weather_line(f: dict[str, Any], label: str) -> str:
    condition = str(f.get("condition", "")).replace("partlycloudy", "partly cloudy").replace("-", " ")
    low = f.get("templow")
    temp = f"{round(low)} to {round(f['temperature'])}" if low is not None else f"{round(f['temperature'])}"
    rain = f", {round(f['precipitation'], 1)} millimetres of rain" if (f.get("precipitation") or 0) > 0 else ""
    wind = f", wind {round(f['wind_speed'])} kilometres per hour" if f.get("wind_speed") is not None else ""
    return f"Weather {label}: {condition}, {temp} degrees{rain}{wind}."


def _phone_warnings(hass: HomeAssistant, people: list[Person]) -> list[str]:
    lines = []
    for person in people:
        for device in tracker_devices(hass, person):
            ents = device_entities(hass, device)
            alarm = [e for e in ents if _NEXT_ALARM.match(e)]
            battery = [e for e in ents if _BATTERY.match(e)]
            charger = [e for e in ents if _CHARGER.match(e)]
            if not (alarm and battery and charger):
                continue  # only phones
            level = hass.states.get(battery[0])
            if hass.states.is_state(charger[0], "none") and level and level.state.isdigit():
                lines.append(f"{person.name.capitalize()}'s phone is at {level.state} percent "
                             "and not charging.")
    return lines


async def async_facts(
    hass: HomeAssistant, options: dict[str, Any], morning: bool = False, area: str | None = None
) -> str:
    """The briefing as plain, correct facts."""
    now = dt_util.now()
    midnight = dt_util.start_of_local_day(now) + timedelta(days=1)
    day = now.date() if morning else midnight.date()
    start, end = (now, midnight) if morning else (midnight, midnight + timedelta(days=1))
    people = (people_in_area(hass, area) if area else []) or people_home(hass)
    default_routine = int(options.get(CONF_ROUTINE_MINUTES, 35))

    events = await _events(hass, start, end)
    timed = [e for e in events if not e.all_day]
    all_day = [e.title for e in events if e.all_day]
    first = timed[0] if timed else None

    parts = [f"{'Today is' if morning else 'Tomorrow is'} {spoken_date(day)}."]
    if first:
        where = f" at {first.location}" if first.location else ""
        parts.append(f"First commitment: {first.title} at {_hm(first.start)}{where}.")
        if later := timed[1:4]:
            parts.append("Later: " + ", ".join(f"{e.title} at {_hm(e.start)}" for e in later) + ".")
    else:
        parts.append(f"Nothing timed on the calendars {'for the rest of today' if morning else 'tomorrow'}.")
    if all_day:
        parts.append("All day: " + ", ".join(all_day) + ".")

    for person in people:
        name = person.name.capitalize()
        routine = routine_minutes(hass, person, default_routine)
        wake = (first.start - timedelta(minutes=routine + (30 if first.location else 0))) if first else None
        leave = leave_time(hass, person)
        leave = leave if leave and dt_util.as_local(leave).date() == day else None
        get_up = leave - timedelta(minutes=routine) if leave else None
        need = min(t for t in (wake, get_up) if t) if (wake or get_up) else None
        if leave:
            parts.append(f"{name} leaves home {'today' if morning else 'tomorrow'} at "
                         f"{_hm(leave)}, so up by {_hm(get_up)}.")
        if morning:
            continue
        alarms = [t for _, t in next_alarms(hass, person) if now < t < now + timedelta(hours=30)]
        alarm = min(alarms) if alarms else None
        if alarm:
            hours = round((alarm - now).total_seconds() / 3600, 1)
            late = f", which is too late: set it for {_hm(need)} instead" if need and alarm > need else ""
            parts.append(f"{name} has an alarm at {_hm(alarm)}, {hours:g} hours from now{late}.")
        elif need and need.hour < 12:
            parts.append(f"{name} has no alarm set; set one for {_hm(need)}.")
        else:
            parts.append(f"{name} has no alarm set, and none is needed.")

    if not morning:
        parts.extend(_phone_warnings(hass, people))
        sensor = str(options.get(CONF_BEDTIME_SENSOR) or "")
        if sensor and (state := hass.states.get(sensor)) and (bt := dt_util.parse_datetime(state.state)):
            passed = " (already passed)" if bt < now else ""
            parts.append(f"Planned bedtime {_hm(bt)}{passed}.")

    if forecast := await _forecast(hass, day):
        parts.append(_weather_line(forecast, "today" if morning else "tomorrow"))
    return " ".join(parts)


async def async_briefing(
    hass: HomeAssistant, options: dict[str, Any], morning: bool = False,
    area: str | None = None, context: Context | None = None,
) -> dict[str, str]:
    """{say, facts}: the facts, and the two or three that matter in her voice."""
    facts = await async_facts(hass, options, morning, area)
    say = await async_say(
        hass, options, facts,
        request="good morning, what is on today" if morning else "good night",
        task=TASK_MORNING if morning else TASK_NIGHT,
        context=context,
    )
    return {"say": say, "facts": facts}
