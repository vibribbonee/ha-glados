"""Room context: everything GLaDOS needs to know about one room.

A port of the glados_room_context script. Every field it returns is kept with
the same name, so the scripts and automations that read it keep working when
the script becomes a thin wrapper around the glados.room_context service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import area_registry as ar, entity_registry as er, label_registry as lr
from homeassistant.util import dt as dt_util

from .const import (
    BED_CLASSES,
    BED_PATTERN,
    BEDROOM_NAME_PATTERN,
    LABEL_BEDROOM,
    LABEL_COOLING,
    LABEL_GLADOS,
    LABEL_HEATING,
    LABEL_QUIET,
    MORNING_ENDS_HOUR,
    PRESENCE_CLASSES,
)
from .people import all_people, next_alarms, people_home, people_in_area, person_area
from .registry import area_entities, area_name, area_of, label_entities

_BED = re.compile(BED_PATTERN)
_BEDROOM = re.compile(BEDROOM_NAME_PATTERN, re.IGNORECASE)
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")
_QUIET_OFF = ("off", "unknown", "unavailable", "idle", "none")
_NOT_VIDEO = ("music", "podcast", "")
# assist_satellite feature flag for start_conversation (asking a question)
_FEATURE_START_CONVERSATION = 2


@dataclass
class RoomContext:
    """One room, as the proactive features see it."""

    area: str = ""
    area_name: str = ""
    people: list[str] = field(default_factory=list)
    anyone_home: bool = False
    occupied: bool = False
    occupied_minutes: int = -1
    in_bed: bool = False
    before_alarm: str = ""
    dark_bedroom: bool = False
    sleeping: bool = False
    quiet: list[str] = field(default_factory=list)
    watching: list[str] = field(default_factory=list)
    may_speak: bool = False
    temperature: float | None = None
    co2: float | None = None
    humidity: float | None = None
    windows: list[str] = field(default_factory=list)
    open_windows: list[str] = field(default_factory=list)
    outside: float | None = None
    heaters: list[str] = field(default_factory=list)
    coolers: list[str] = field(default_factory=list)
    satellite: str = ""
    ask_satellite: str = ""
    any_satellite: str = ""

    def as_dict(self) -> dict[str, Any]:
        """The context as a service response."""
        return asdict(self)


def _device_class(state: State) -> str:
    return state.attributes.get("device_class") or ""


def _is_presence(state: State, classes: tuple[str, ...]) -> bool:
    return state.state == STATE_ON and _device_class(state) in classes


def _number(state: State | None) -> float | None:
    if state is None:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _pick_room(hass: HomeAssistant) -> str:
    """Where people are; else the room whose presence sensor turned on last."""
    for person in people_home(hass):
        if area := person_area(hass, person):
            return area
    occupied = sorted(
        (
            s
            for s in hass.states.async_all("binary_sensor")
            if _is_presence(s, PRESENCE_CLASSES) and not _BED.search(s.entity_id)
        ),
        key=lambda s: s.last_changed,
        reverse=True,
    )
    for state in occupied:
        if area := area_of(hass, state.entity_id):
            return area
    return ""


# Sensors that measure a device, not the room: a CPU, a 3D printer bed, a battery.
_NOT_ROOM = re.compile(
    r"cpu|gpu|chip|processor|soc\b|core|board|nozzle|bed_temp|bed_target|hotend|extruder"
    r"|chamber|battery|printer|disk|ssd|nvme|router|inverter|charger|motor|engine|water_heater"
    r"|boiler|fridge|freezer|oven|probe|outdoor|outside",
    re.IGNORECASE,
)
# What a room can plausibly read; anything outside is a device or a broken sensor.
_ROOM_RANGE = {"temperature": (0, 40), "humidity": (1, 100), "carbon_dioxide": (250, 10000)}


def _sensor_value(
    hass: HomeAssistant, ents: list[str], device_class: str, preferred: set[str]
) -> float | None:
    """The room's own sensor of this class: glados-labelled first, never a device's insides."""
    registry = er.async_get(hass)
    low, high = _ROOM_RANGE.get(device_class, (float("-inf"), float("inf")))
    labelled, others = [], []
    for entity_id in ents:
        if not entity_id.startswith("sensor."):
            continue
        state = hass.states.get(entity_id)
        if not state or _device_class(state) != device_class or (value := _number(state)) is None:
            continue
        if entity_id in preferred:
            labelled.append(value)
            continue
        entry = registry.async_get(entity_id)
        name = f"{entity_id} {state.name}"
        if (entry and entry.entity_category) or _NOT_ROOM.search(name) or not low <= value <= high:
            continue
        others.append(value)
    hits = labelled or others
    return hits[0] if hits else None


def _before_alarm(
    hass: HomeAssistant, area: str, people: list[str], now: datetime
) -> str:
    """The earliest morning alarm still to ring today, of the room's people or clock."""
    owners = [
        p
        for p in all_people(hass)
        if (p.name in people) or (not people and not p.away)
    ]
    times: list[datetime] = [at for p in owners for _, at in next_alarms(hass, p)]
    if area:
        for state in hass.states.async_all("sensor"):
            if _NEXT_ALARM.match(state.entity_id) and area_of(hass, state.entity_id) == area:
                if at := dt_util.parse_datetime(state.state):
                    times.append(at)
    today = [
        dt_util.as_local(at)
        for at in times
        if at > now
        and dt_util.as_local(at).date() == now.date()
        and dt_util.as_local(at).hour < MORNING_ENDS_HOUR
    ]
    return min(today).strftime("%H:%M") if today else ""


def is_bedroom(hass: HomeAssistant, area: str) -> bool:
    """A bedroom: labelled glados_bedroom (any language), or named like one."""
    entry = ar.async_get(hass).async_get_area(area)
    if entry is None:
        return False
    labels = lr.async_get(hass)
    names = {(found.name or "").lower() for label in entry.labels
             if (found := labels.async_get_label(label))}
    return LABEL_BEDROOM in names | set(entry.labels) or bool(_BEDROOM.search(entry.name))


def describe(
    hass: HomeAssistant,
    area: str | None = None,
    schedule: str | None = None,
    now: datetime | None = None,
) -> RoomContext:
    """Describe a room. With no area, the room people are in."""
    now = dt_util.as_local(now or dt_util.now())
    a = area or _pick_room(hass)
    ctx = RoomContext(area=a, area_name=area_name(hass, a) if a else "")
    ents = area_entities(hass, a) if a else []
    glados = label_entities(hass, LABEL_GLADOS)

    # People and occupancy
    ctx.people = [p.name for p in people_in_area(hass, a)] if a else []
    ctx.anyone_home = bool(people_home(hass))
    since = [
        s.last_changed
        for e in ents
        if e.startswith("binary_sensor.")
        and (s := hass.states.get(e))
        and _is_presence(s, PRESENCE_CLASSES)
        and not _BED.search(e)
    ]
    if since:
        ctx.occupied_minutes = int(round((now - min(since)).total_seconds() / 60))
    ctx.occupied = ctx.occupied_minutes >= 0 or bool(ctx.people)

    # Sleep
    ctx.in_bed = any(
        _is_presence(s, BED_CLASSES)
        and _BED.search(s.entity_id)
        and area_of(hass, s.entity_id) in (a, None)
        for s in hass.states.async_all("binary_sensor")
    )
    ctx.before_alarm = _before_alarm(hass, a, ctx.people, now)
    lights = [e for e in glados if e.startswith("light.") and e in ents]
    ctx.dark_bedroom = bool(
        a
        and is_bedroom(hass, a)
        and lights
        and not any(hass.states.is_state(e, STATE_ON) for e in lights)
    )
    ctx.sleeping = ctx.in_bed or bool(ctx.before_alarm) or ctx.dark_bedroom

    # Keep quiet
    ctx.quiet = sorted(
        e
        for e in label_entities(hass, LABEL_QUIET)
        if (s := hass.states.get(e)) and s.state not in _QUIET_OFF
    )
    ctx.watching = sorted(
        s.entity_id
        for s in hass.states.async_all("media_player")
        if s.state == "playing"
        and area_of(hass, s.entity_id) in (a, None)
        and (
            (s.attributes.get("media_content_type") or "") not in _NOT_VIDEO
            or _device_class(s) == "tv"
        )
    )
    # No schedule set up: she may speak up any time (sleep rules still apply).
    ctx.may_speak = hass.states.is_state(schedule, STATE_ON) if schedule else True

    # Climate
    ctx.temperature = _sensor_value(hass, ents, "temperature", glados)
    ctx.co2 = _sensor_value(hass, ents, "carbon_dioxide", glados)
    ctx.humidity = _sensor_value(hass, ents, "humidity", glados)
    windows = [
        e
        for e in ents
        if e.startswith("binary_sensor.")
        and (s := hass.states.get(e))
        and _device_class(s) == "window"
    ]
    ctx.windows = windows
    ctx.open_windows = [
        hass.states.get(e).name for e in windows if hass.states.is_state(e, STATE_ON)
    ]
    weather = sorted(
        (
            s
            for s in hass.states.async_all("weather")
            if s.state not in ("unknown", "unavailable")
        ),
        key=lambda s: s.entity_id not in glados,
    )
    if weather:
        try:
            ctx.outside = float(weather[0].attributes.get("temperature"))
        except (TypeError, ValueError):
            ctx.outside = None

    # Heaters and coolers: climate devices in the room, then labelled entities
    heaters: list[str] = []
    coolers: list[str] = []
    for e in ents:
        if e.startswith("climate.") and (s := hass.states.get(e)):
            modes = s.attributes.get("hvac_modes") or []
            if "heat" in modes:
                heaters.append(e)
            if "cool" in modes:
                coolers.append(e)
    for label, here in ((LABEL_HEATING, heaters), (LABEL_COOLING, coolers)):
        tagged = label_entities(hass, label)
        inside = sorted(e for e in tagged if area_of(hass, e) == a)
        nowhere = sorted(e for e in tagged if area_of(hass, e) is None)
        for e in inside:
            if e not in here:
                here.append(e)
        if not here:
            here.extend(nowhere)
    ctx.heaters, ctx.coolers = heaters, coolers

    # Voice satellites that are free
    idle_here = [
        e
        for e in ents
        if e.startswith("assist_satellite.") and hass.states.is_state(e, "idle")
    ]
    ctx.satellite = idle_here[0] if idle_here else ""
    ask = [
        e
        for e in idle_here
        if int(hass.states.get(e).attributes.get("supported_features") or 0)
        & _FEATURE_START_CONVERSATION
    ]
    ctx.ask_satellite = ask[0] if ask else ""
    idle_anywhere = sorted(
        s.entity_id for s in hass.states.async_all("assist_satellite") if s.state == "idle"
    )
    ctx.any_satellite = idle_anywhere[0] if idle_anywhere else ""
    return ctx
