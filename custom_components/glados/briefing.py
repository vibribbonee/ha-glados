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
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BEDTIME_SENSOR,
    CONF_CHARGE_BELOW,
    CONF_KEEP_CHARGED,
    CONF_ROUTINE_MINUTES,
    LABEL_GLADOS,
)
from .dates import spoken_date
from .people import (
    Person,
    all_people,
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
_BATTERY_STATE = re.compile(r"^sensor\..*battery_state$")
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")

TASK_NIGHT = (
    "Bedtime briefing. Pick only the two or three facts that matter tonight: an early "
    "start, an alarm that is too late or missing, a birthday, a phone that needs "
    "charging, bad weather. Skip everything that is fine. Short spoken sentences, never "
    "a list, each time said once. End with one dry remark of your own."
)
TASK_MORNING = (
    "Morning briefing. Pick only what matters for the rest of today: the next "
    "commitment, a leave time, the weather only if it changes what to wear or carry. "
    "Skip everything that is fine. They have just woken up: two or three short spoken "
    "sentences at most, never a list, never a number they do not need. End with one dry remark of your own."
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
            unit = (state := hass.states.get(pick)) and state.attributes.get("wind_speed_unit")
            return {**f, "_wind_unit": unit or "km/h"}
    return None


_RAINY = ("rainy", "pouring", "lightning-rainy", "snowy", "snowy-rainy", "hail")
_WINDY_KMH = 30
_STORMY_KMH = 55


def _wind_kmh(f: dict[str, Any], unit: str) -> float:
    speed = float(f.get("wind_speed") or 0)
    return {"m/s": speed * 3.6, "mph": speed * 1.609, "kn": speed * 1.852}.get(unit, speed)


def _weather_line(f: dict[str, Any], label: str, wind_unit: str = "km/h") -> str:
    """The weather in words, only what changes what to wear or carry.

    One temperature, then rain, wind or sunscreen only when there is something to
    say: nobody needs the wind speed in kilometres per hour on waking.
    """
    condition = str(f.get("condition", ""))
    high = f.get("temperature")
    bits = [f"{round(high)} degrees"] if high is not None else []
    rain = float(f.get("precipitation") or 0)
    if condition.startswith("snowy"):
        bits.append("snow")
    elif condition in _RAINY or rain >= 1:
        bits.append("rain")
    elif rain >= 0.3:
        bits.append("a chance of a shower")
    wind = _wind_kmh(f, wind_unit)
    if condition == "windy" or wind >= _STORMY_KMH:
        bits.append("stormy" if wind >= _STORMY_KMH else "windy")
    elif wind >= _WINDY_KMH:
        bits.append("windy")
    uv = f.get("uv_index")
    if (uv is not None and float(uv) >= 5) or (condition == "sunny" and (high or 0) >= 25):
        bits.append("sunscreen weather")
    if not bits:
        return ""
    return f"Weather {label}: {', '.join(bits)}."


_CHARGING = ("charging", "full")
_CHARGING_BINARY = re.compile(r"^binary_sensor\..*(charging|plugged)")


def off_charger(
    hass: HomeAssistant, battery: str, settled: timedelta = timedelta(minutes=2)
) -> int | None:
    """A battery's level when its device is really off the charger; else None.

    Charging means a charger is attached (Android charger type), the battery says
    charging or full (Android, iOS, macOS), or a charging binary sensor is on.
    Wireless pads flicker for seconds when a phone is put down, and a phone or
    laptop held at 80 percent reports "not charging" on the charger: neither
    counts. Off the charger only once that has lasted `settled`.
    """
    level = hass.states.get(battery)
    if not (level and level.state.replace(".", "", 1).isdigit()):
        return None
    reg = er.async_get(hass)
    entry = reg.async_get(battery)
    siblings = device_entities(hass, entry.device_id) if entry and entry.device_id else []
    plug = next((hass.states.get(e) for e in siblings if _CHARGER.match(e)), None)
    states = [hass.states.get(e) for e in siblings
              if _BATTERY_STATE.match(e) or _CHARGING_BINARY.match(e)]
    states = [s for s in states if s is not None]
    if plug is not None and plug.state not in ("none", "unavailable", "unknown"):
        return None
    if any(s.state.lower() in _CHARGING or (s.domain == "binary_sensor" and s.state == "on")
           for s in states):
        return None
    watched = [s for s in [plug, *states] if s is not None]
    if not watched:
        return None  # nothing says whether it charges
    since = max(s.last_changed for s in watched)
    if dt_util.utcnow() - since < settled:
        return None  # a flicker, or just unplugged
    return round(float(level.state))


def phone_battery(
    hass: HomeAssistant, person: Person, settled: timedelta = timedelta(minutes=2)
) -> int | None:
    """Their phone's battery level when it is really off the charger; else None."""
    for device in tracker_devices(hass, person):
        ents = device_entities(hass, device)
        if not any(_NEXT_ALARM.match(e) for e in ents):
            continue  # only phones
        if battery := next((e for e in ents if _BATTERY.match(e)), None):
            return off_charger(hass, battery, settled)
    return None


def device_warnings(
    hass: HomeAssistant, options: dict[str, Any], people: list[Person] | None = None
) -> list[str]:
    """Other devices to charge overnight that are low and off the charger.

    A device that is one of someone's tracked devices is theirs: it is only
    mentioned to them. One nobody owns (a shared tablet) is mentioned to anyone.
    """
    below = float(options.get(CONF_CHARGE_BELOW, 40))
    owners = {d: p.entity_id for p in all_people(hass) for d in tracker_devices(hass, p)}
    told = {p.entity_id for p in people} if people is not None else None
    lines = []
    for battery in options.get(CONF_KEEP_CHARGED) or []:
        entry = er.async_get(hass).async_get(battery)
        owner = owners.get(entry.device_id) if entry and entry.device_id else None
        if owner and told is not None and owner not in told:
            continue  # someone else's laptop
        level = off_charger(hass, battery)
        if level is None or level >= below:
            continue
        device = dr.async_get(hass).async_get(entry.device_id) if entry and entry.device_id else None
        name = (device.name_by_user or device.name) if device else None
        name = name or str(hass.states.get(battery).name).replace(" battery level", "")
        lines.append(f"The {name} is at {level} percent and not charging.")
    return lines


def _phone_warnings(hass: HomeAssistant, people: list[Person]) -> list[str]:
    return [
        f"{person.name.capitalize()}'s phone is at {level} percent and not charging."
        for person in people
        if (level := phone_battery(hass, person)) is not None
    ]


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
        parts.extend(device_warnings(hass, options, people))
        sensor = str(options.get(CONF_BEDTIME_SENSOR) or "")
        if sensor and (state := hass.states.get(sensor)) and (bt := dt_util.parse_datetime(state.state)):
            passed = " (already passed)" if bt < now else ""
            parts.append(f"Planned bedtime {_hm(bt)}{passed}.")

    if forecast := await _forecast(hass, day):
        if line := _weather_line(forecast, "today" if morning else "tomorrow",
                                 forecast.get("_wind_unit", "km/h")):
            parts.append(line)
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
