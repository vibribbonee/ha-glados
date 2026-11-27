"""People: who someone is, where they are, and their own settings.

Everything is found through the person entities and the devices of their
device trackers, so new people work without configuration:

- the room comes from a Bermuda "<device> area" sensor on a tracker device;
- alarms from "next alarm" sensors on those devices;
- phones from notify entities on those devices;
- per-person settings from helpers named after the person (see const.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import re

from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from homeassistant.util import dt as dt_util

from .const import (
    BED_PATTERN,
    LEAVE_HELPER_PREFIX,
    OWN_LIST_TEMPLATE,
    ROUTINE_DEFAULT_HELPER,
    ROUTINE_HELPER_PREFIX,
    SHARED_LIST,
)
from .registry import area_of, device_entities, device_of, resolve_area

_AREA_SENSOR = re.compile(r"^sensor\..*_area$")
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")
_BED = re.compile(BED_PATTERN)
_NOTIFY = re.compile(r"^notify\.")
# Notify targets that are not phones: headsets and watches stay quiet.
_NOT_A_PHONE = re.compile(r"quest|watch|tv|tablet", re.IGNORECASE)
_UNUSABLE = ("unknown", "unavailable", "")


@dataclass(frozen=True)
class Person:
    """A person entity, with the slug their own helpers are named after."""

    entity_id: str
    name: str
    state: str

    @property
    def slug(self) -> str:
        """The object id, such as "nico" for person.nico."""
        return self.entity_id.split(".", 1)[1]

    @property
    def home(self) -> bool:
        """True when the person is at home."""
        return self.state == STATE_HOME

    @property
    def away(self) -> bool:
        """True when the person is known to be away."""
        return self.state == STATE_NOT_HOME


def _person(state: State) -> Person:
    return Person(state.entity_id, state.name, state.state)


def all_people(hass: HomeAssistant) -> list[Person]:
    """Every person entity."""
    return [_person(s) for s in hass.states.async_all("person")]


def real_people(hass: HomeAssistant) -> list[Person]:
    """People who live here: with a device tracker or a Home Assistant login.

    A person entity made for a wall tablet or "Guest" has neither, and is not an
    occupant: no bedtime, no leave time, not named in her personality.
    """
    found = []
    for state in hass.states.async_all("person"):
        if state.attributes.get("device_trackers") or state.attributes.get("user_id"):
            found.append(_person(state))
    return found


def people_home(hass: HomeAssistant) -> list[Person]:
    """Everyone at home."""
    return [p for p in all_people(hass) if p.home]


def tracker_devices(hass: HomeAssistant, person: Person | str) -> list[str]:
    """Device ids of a person's device trackers."""
    entity_id = person.entity_id if isinstance(person, Person) else person
    state = hass.states.get(entity_id)
    trackers = state.attributes.get("device_trackers", []) if state else []
    devices: list[str] = []
    for tracker in trackers or []:
        if (device := device_of(hass, tracker)) and device not in devices:
            devices.append(device)
    return devices


def _device_matches(hass: HomeAssistant, person: Person, pattern: re.Pattern) -> list[str]:
    found: list[str] = []
    for device in tracker_devices(hass, person):
        found.extend(e for e in device_entities(hass, device) if pattern.match(e))
    return found


def person_area(hass: HomeAssistant, person: Person | str) -> str | None:
    """The area a person is in, from a Bermuda area sensor on one of their devices."""
    if isinstance(person, str):
        state = hass.states.get(person)
        if state is None:
            return None
        person = _person(state)
    for sensor in _device_matches(hass, person, _AREA_SENSOR):
        state = hass.states.get(sensor)
        if state and (area := resolve_area(hass, state.state)):
            return area
    # No room tracking (such as Bermuda): when they are the only one home and
    # exactly one room shows presence, that is where they are.
    if not person.home or [p.entity_id for p in people_home(hass)] != [person.entity_id]:
        return None
    occupied = _occupied_rooms(hass)
    return occupied[0] if len(occupied) == 1 else None


def _occupied_rooms(hass: HomeAssistant) -> list[str]:
    rooms = set()
    for state in hass.states.async_all("binary_sensor"):
        if (state.state == "on"
                and state.attributes.get("device_class") in ("occupancy", "presence", "motion")
                and not _BED.search(state.entity_id)
                and (area := area_of(hass, state.entity_id))):
            rooms.add(area)
    return sorted(rooms)


def people_in_area(hass: HomeAssistant, area_id: str) -> list[Person]:
    """People at home whose devices put them in this area."""
    return [p for p in people_home(hass) if person_area(hass, p) == area_id]


def phones(hass: HomeAssistant, person: Person) -> list[str]:
    """Notify entities of a person's phones (not their headset or watch)."""
    return sorted(
        {
            e
            for e in _device_matches(hass, person, _NOTIFY)
            if not _NOT_A_PHONE.search(e)
        }
    )


def android_phones(hass: HomeAssistant, person: Person) -> list[str]:
    """notify actions (mobile_app_<device>) of a person's Android phones.

    These take companion-app commands, such as opening the alarm clock app.
    """
    return [service for service, _ in android_phone_alarms(hass, person)]


def android_phone_alarms(hass: HomeAssistant, person: Person) -> list[tuple[str, str]]:
    """(notify action, next-alarm sensor or "") for a person's Android phones."""
    reg = dr.async_get(hass)
    found: list[tuple[str, str]] = []
    for device_id in tracker_devices(hass, person):
        device = reg.async_get(device_id)
        if device is None or not any(d == "mobile_app" for d, _ in device.identifiers):
            continue
        if (device.manufacturer or "").lower() == "apple" or _NOT_A_PHONE.search(device.name or ""):
            continue
        service = f"mobile_app_{slugify(device.name or '')}"
        if hass.services.has_service("notify", service) and service not in [f for f, _ in found]:
            sensor = next((e for e in device_entities(hass, device_id) if _NEXT_ALARM.match(e)), "")
            found.append((service, sensor))
    return found


def next_alarms(hass: HomeAssistant, person: Person) -> list[tuple[str, datetime]]:
    """(sensor, time) for every next-alarm sensor on a person's devices that is set."""
    alarms: list[tuple[str, datetime]] = []
    for sensor in _device_matches(hass, person, _NEXT_ALARM):
        state = hass.states.get(sensor)
        if state and (at := dt_util.parse_datetime(state.state)):
            alarms.append((sensor, at))
    return alarms


def resolve_person(
    hass: HomeAssistant,
    name: str | None = None,
    user_id: str | None = None,
    among: list[Person] | None = None,
) -> Person | None:
    """Work out who is meant.

    In order: the name given (person name, object id or entity id); the person
    linked to the user who asked; the only one of them at home; the only one.
    With a name that matches nobody, the answer is None rather than a guess.
    """
    people = among if among is not None else all_people(hass)
    wanted = (name or "").strip().lower()
    if wanted:
        for p in people:
            if wanted in (p.entity_id, p.slug, p.name.lower()):
                return p
        return None
    if user_id:
        for p in people:
            state = hass.states.get(p.entity_id)
            if state and state.attributes.get("user_id") == user_id:
                return p
    home = [p for p in people if p.home]
    if len(home) == 1:
        return home[0]
    if len(people) == 1:
        return people[0]
    return None


# Per-person settings -------------------------------------------------------


LEAVE_UNIQUE = "leave_home_{}"  # GLaDOS's own entity per person
ROUTINE_UNIQUE = "morning_routine_{}"
CLEARED = "2000-01-01 00:00:00"


def _own_entity(hass: HomeAssistant, domain: str, unique: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, "glados", unique)


def leave_helper(hass: HomeAssistant, person: Person) -> str:
    """Where the person's leave time lives.

    Their own input_datetime.leave_home_<person> if there is one, else the
    "Leave home <name>" entity GLaDOS makes for everyone.
    """
    own = f"{LEAVE_HELPER_PREFIX}{person.slug}"
    if hass.states.get(own) is not None:
        return own
    return _own_entity(hass, "datetime", LEAVE_UNIQUE.format(person.entity_id)) or own


def has_leave_helper(hass: HomeAssistant, person: Person) -> bool:
    """True when the person has somewhere to keep a leave time."""
    return hass.states.get(leave_helper(hass, person)) is not None


def leave_time(hass: HomeAssistant, person: Person) -> datetime | None:
    """The person's leave time, or None when it is cleared (the year 2000) or unset."""
    state = hass.states.get(leave_helper(hass, person))
    if state is None or state.state in _UNUSABLE:
        return None
    at = dt_util.parse_datetime(state.state)
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt_util.get_default_time_zone())
    return None if at.year <= 2000 else dt_util.as_local(at)


async def async_set_leave(hass: HomeAssistant, person: Person, value: datetime | None,
                          context: Any = None) -> None:
    """Set (or with None, clear) the person's leave time, wherever it lives."""
    helper = leave_helper(hass, person)
    text = value.strftime("%Y-%m-%d %H:%M:%S") if value else CLEARED
    if helper.startswith("datetime."):
        at = value or datetime(2000, 1, 1, tzinfo=dt_util.get_default_time_zone())
        await hass.services.async_call(
            "datetime", "set_value", {"entity_id": helper, "datetime": at},
            blocking=True, context=context)
    else:
        await hass.services.async_call(
            "input_datetime", "set_datetime", {"entity_id": helper, "datetime": text},
            blocking=True, context=context)


def routine_minutes(hass: HomeAssistant, person: Person, default: int = 35) -> int:
    """Minutes from alarm to the door.

    Their own input_number.morning_routine_<person>, else GLaDOS's "Morning
    routine <name>", else the house's input_number.morning_routine_minutes,
    else the default from the settings.
    """
    candidates = [
        f"{ROUTINE_HELPER_PREFIX}{person.slug}",
        _own_entity(hass, "number", ROUTINE_UNIQUE.format(person.entity_id)),
        ROUTINE_DEFAULT_HELPER,
    ]
    for entity_id in filter(None, candidates):
        state = hass.states.get(entity_id)
        if state and state.state not in _UNUSABLE:
            try:
                return int(float(state.state))
            except ValueError:
                continue
    return default


def own_list(hass: HomeAssistant, person: Person | None) -> str:
    """The person's own to-do list, or the shared one."""
    if person is not None:
        own = OWN_LIST_TEMPLATE.format(slug=person.slug)
        state = hass.states.get(own)
        if state is not None and state.state not in ("unknown", "unavailable"):
            return own
    return SHARED_LIST
