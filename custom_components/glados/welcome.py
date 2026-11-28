"""Welcome home: what you missed while you were out.

When someone comes home after being away for at least an hour, she waits until
they are in a room (or two minutes), then the Announcer says how long they were
gone, the reminders that came due while they were out (they went to their phone
then), and what is still on or open. One GLaDOS remark after. A quick trip
outside gets nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .briefing import deliveries_today
from .const import CONF_WELCOME, VOICE_ANNOUNCER
from .departures import still_on
from .people import Person, person_area, real_people
from .setpieces import welcome_glados

if TYPE_CHECKING:
    from . import GladosData

AWAY_AT_LEAST = timedelta(hours=1)
SETTLE = timedelta(minutes=2)
GIVE_UP = timedelta(minutes=15)


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _duration(away: timedelta) -> str:
    if away >= timedelta(days=2):
        return f"{away.days} days"
    hours = int(away.total_seconds() // 3600)
    minutes = int(away.total_seconds() % 3600 // 60)
    if hours == 0:
        return f"{minutes} minutes"
    return f"{hours} hour{'s' if hours != 1 else ''}" + (f" and {minutes} minutes" if minutes else "")


class Welcome:
    """Notices people coming home, and tells them what they missed."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        if not self.data.options.get(CONF_WELCOME, True):
            return []
        now = dt_util.now()
        memory = self.data.memory
        said = []
        for person in real_people(self.hass):
            key = f"presence {person.entity_id}"
            before = memory.get(key)
            state = "home" if person.home else "away"
            if before != state:
                if before == "away" and state == "home":
                    left = memory.stored_at(key)
                    if left and now - left >= AWAY_AT_LEAST:
                        memory.set(f"arrived {person.entity_id}",
                                   json.dumps({"at": now.isoformat(), "left": left.isoformat()}))
                memory.set(key, state)
            if (result := await self._maybe_greet(person, now)) is not None:
                said.append(result)
        return said

    async def _maybe_greet(self, person: Person, now: datetime) -> dict[str, Any] | None:
        memory = self.data.memory
        raw = memory.get(f"arrived {person.entity_id}")
        if not raw:
            return None
        info = json.loads(raw)
        arrived = dt_util.parse_datetime(info["at"])
        area = person_area(self.hass, person)
        if now - arrived > GIVE_UP or not person.home:
            memory.forget(f"arrived {person.entity_id}")
            return None
        if now - arrived < SETTLE or (area is None and now - arrived < SETTLE * 2):
            return None
        away = arrived - dt_util.parse_datetime(info["left"])
        if person.visitor:  # back for a stay, not back from the shops
            line = f"Welcome back, {person.name.capitalize()}. The facility has kept your room. Barely."
        else:
            line = f"Welcome back, {person.name.capitalize()}. You were away for {_duration(away)}."
        missed = json.loads(memory.get(f"missed {person.entity_id}") or "[]")
        if missed:
            items = [f"{m['what']} at {dt_util.as_local(dt_util.parse_datetime(m['at'])).strftime('%H:%M')}"
                     for m in missed]
            line += f" While you were out: {_join(items)}."
        if parcels := await deliveries_today(self.hass):
            line += f" A delivery is due today: {_join(parcels)}."
        on, open_ = still_on(self.hass)
        if on:
            line += f" Still on: {_join(on)}."
        if open_:
            line += f" Still open: {_join(open_)}."
        result = await self.data.announcer.async_announce(AnnounceRequest(
            facts=line, voice=VOICE_ANNOUNCER, area=area, glados_line=welcome_glados()))
        if result.get("spoken"):
            memory.forget(f"arrived {person.entity_id}")
            memory.forget(f"missed {person.entity_id}")
        return result
