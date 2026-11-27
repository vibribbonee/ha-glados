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
import re

from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .const import (
    LEAVE_HELPER_PREFIX,
    OWN_LIST_TEMPLATE,
    ROUTINE_DEFAULT_HELPER,
    ROUTINE_HELPER_PREFIX,
    SHARED_LIST,
)
from .registry import device_entities, device_of, resolve_area

_AREA_SENSOR = re.compile(r"^sensor\..*_area$")
_NEXT_ALARM = re.compile(r"^sensor\..*next_alarm$")
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
    return None


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


def leave_helper(person: Person) -> str:
    """The person's leave-time helper (it may not exist)."""
    return f"{LEAVE_HELPER_PREFIX}{person.slug}"


def has_leave_helper(hass: HomeAssistant, person: Person) -> bool:
    """True when the person has a leave-time helper."""
    return hass.states.get(leave_helper(person)) is not None


def leave_time(hass: HomeAssistant, person: Person) -> datetime | None:
    """The person's leave time, or None when it is cleared (the year 2000) or unset."""
    state = hass.states.get(leave_helper(person))
    if state is None or state.state in _UNUSABLE:
        return None
    at = dt_util.parse_datetime(state.state)
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt_util.get_default_time_zone())
    return None if at.year <= 2000 else at


def routine_minutes(hass: HomeAssistant, person: Person, default: int = 35) -> int:
    """Minutes from alarm to the door: the person's own, the house default, or default."""
    for entity_id in (f"{ROUTINE_HELPER_PREFIX}{person.slug}", ROUTINE_DEFAULT_HELPER):
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
