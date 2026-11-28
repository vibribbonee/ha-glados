"""The live house, in a few lines, for her tool instructions.

What a person asks about most, worked out in Python and kept short, so a small
model gets the facts without a long template eating its context:

- each room's climate (temperature, CO2, humidity) where there is a sensor;
- who is home, and in which room;
- windows and doors that are open (placed ones only);
- the weather outside now;
- each person's next alarm and leave time;
- the next item on each calendar, with its day spelled out.

Capped at MAX_CHARS; the least important lines go first.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util

from .dates import days_away
from .departures import still_on
from .people import leave_time, next_alarms, person_area, real_people
from .const import LABEL_GLADOS
from .registry import area_entities, area_name, label_entities
from .rooms import describe

MAX_CHARS = 1400


def _when(hass: HomeAssistant, start: str, all_day: bool) -> str:
    at = dt_util.parse_datetime(start) if start else None
    if at is None:
        return ""
    if at.tzinfo is None:  # calendar start_time is local time without a zone
        at = at.replace(tzinfo=dt_util.get_default_time_zone())
    at = dt_util.as_local(at)
    day = days_away(at)
    if day not in ("today", "tomorrow"):
        day = f"on {at.strftime('%A')} {at.day} {at.strftime('%B')}"
    return day if all_day else f"{day} at {at.strftime('%H:%M')}"


def _offline(hass: HomeAssistant, area: str, device_class: str) -> bool:
    """The room has a sensor of this class, and it is not answering."""
    return any(
        (state := hass.states.get(e)) is not None
        and state.attributes.get("device_class") == device_class
        and state.state in ("unavailable", "unknown")
        for e in area_entities(hass, area) if e.startswith("sensor.")
    )


def house_state(hass: HomeAssistant) -> str:
    """The live house in short lines, most important first."""
    now = dt_util.now()
    lines: list[str] = [f"Live house at {now.strftime('%H:%M')}:"]

    for person in real_people(hass):
        if person.visitor and not person.home:
            continue  # not staying over now: nothing to say about them
        if person.away:
            where = "away"
        elif area := person_area(hass, person):
            where = f"home, in the {area_name(hass, area)}"
        else:
            where = "home"
        extra = []
        alarm = min((t for _, t in next_alarms(hass, person) if t > now), default=None)
        if alarm and alarm - now < timedelta(hours=24):
            extra.append(f"next alarm {_when(hass, alarm.isoformat(), False)}")
        if (leave := leave_time(hass, person)) and leave > now:
            extra.append(f"leaves home {_when(hass, leave.isoformat(), False)}")
        lines.append(f"- {person.name.capitalize()}: {where}" + (f"; {'; '.join(extra)}" if extra else ""))

    for area in ar.async_get(hass).async_list_areas():
        ctx = describe(hass, area.id)
        parts = []
        if ctx.temperature is not None:
            parts.append(f"{round(ctx.temperature)} degrees")
        if ctx.co2 is not None:
            parts.append(f"CO2 {round(ctx.co2)} parts per million")
        elif _offline(hass, area.id, "carbon_dioxide"):
            parts.append("CO2 sensor offline, so the CO2 is unknown")
        if ctx.humidity is not None:
            parts.append(f"humidity {round(ctx.humidity)} percent")
        if parts:
            lines.append(f"- {area.name}: {', '.join(parts)}")

    _, open_ = still_on(hass)
    if open_:
        lines.append(f"- Open: {', '.join(open_)}")

    weather = [s for s in hass.states.async_all("weather") if s.state not in ("unavailable", "unknown")]
    if weather:
        tagged = label_entities(hass, LABEL_GLADOS)
        w = next((s for s in weather if s.entity_id in tagged), weather[0])
        temp = w.attributes.get("temperature")
        wind = w.attributes.get("wind_speed")
        text = str(w.state).replace("partlycloudy", "partly cloudy").replace("-", " ")
        bits = [text] + ([f"{round(temp)} degrees"] if temp is not None else [])
        unit = w.attributes.get("wind_speed_unit") or "km/h"
        unit = {"km/h": "kilometres per hour", "m/s": "metres per second", "mph": "miles per hour"}.get(unit, unit)
        bits += [f"wind {round(wind)} {unit}"] if wind is not None else []
        lines.append(f"- Outside: {', '.join(bits)}")

    for cal in hass.states.async_all("calendar"):
        message = cal.attributes.get("message")
        if not message or cal.state in ("unavailable", "unknown"):
            continue
        when = _when(hass, str(cal.attributes.get("start_time") or ""),
                     bool(cal.attributes.get("all_day")))
        now_on = "happening now" if cal.state == "on" else "next"
        lines.append(f"- {cal.name} calendar, {now_on}: {message}" + (f", {when}" if when else ""))

    text = "\n".join(lines)
    while len(text) > MAX_CHARS and len(lines) > 1:
        lines.pop()  # calendars and weather go before people and rooms
        text = "\n".join(lines)
    return text
