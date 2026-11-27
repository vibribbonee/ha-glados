"""CO2 warnings, room by room, with an optional reminder.

Every minute each room with a CO2 sensor is checked:

- the air gets worse (fine, stale, critical): warn once, in that room;
- it stays bad: remind after the reminder time, if one is set;
- it is fresh again (well below stale): forget it, quietly.

Nothing is said in an empty room or when the polite rules say no (someone in
bed, before an alarm, a dark bedroom, Do Not Disturb, a video). A warning that
could not be said is tried again the next minute.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.event import async_track_time_interval

from .announce import AnnounceRequest
from .const import CONF_CO2_ALERTS, CONF_CO2_REMINDER, CONF_SCHEDULE, VOICE_ANNOUNCER, VOICE_GLADOS
from .rooms import describe
from .setpieces import CO2_STALE, STYLE_GLADOS, STYLE_OFF, co2_announcement, co2_glados_alone, co2_level

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(minutes=1)
FRESH_BELOW = CO2_STALE - 150  # hysteresis: back to fine only well below stale
_RANK = {"fine": 0, "stale": 1, "critical": 2}


def co2_request(
    style: str, area: str, room: str, ppm: float, reminder: bool = False, satellite: str | None = None
) -> AnnounceRequest:
    """The announcement for this room and reading, in the chosen style."""
    if style == STYLE_GLADOS:
        line = co2_glados_alone(room, ppm, reminder=reminder)
        return AnnounceRequest(facts=line, voice=VOICE_GLADOS, area=area, glados_line=line,
                               satellite=satellite)
    announcer, glados = co2_announcement(room, ppm, reminder=reminder)
    return AnnounceRequest(facts=announcer, voice=VOICE_ANNOUNCER, area=area,
                           glados_line=glados, satellite=satellite)


class AirWatch:
    """Checks the rooms' CO2 and warns."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @callback
    def start(self) -> CALLBACK_TYPE:
        """Start checking; returns the stop callback."""
        return async_track_time_interval(self.hass, self._async_check, CHECK_EVERY)

    async def _async_check(self, now: datetime | None = None) -> None:
        options = self.data.options
        style = str(options.get(CONF_CO2_ALERTS) or STYLE_OFF)
        if style == STYLE_OFF:
            return
        reminder = timedelta(minutes=int(options.get(CONF_CO2_REMINDER) or 0))
        schedule = str(options.get(CONF_SCHEDULE) or "") or None
        for area in ar.async_get(self.hass).async_list_areas():
            ctx = describe(self.hass, area.id, schedule)
            if ctx.co2 is not None:
                await self.async_check_room(area.id, area.name, ctx.co2, ctx.occupied,
                                            style, reminder)

    async def async_check_room(
        self, area: str, room: str, ppm: float, occupied: bool, style: str, reminder: timedelta
    ) -> dict[str, Any] | None:
        """Warn, remind or forget for one room. Returns the announcement, if any."""
        memory = self.data.memory
        key = f"air {area}"
        before = memory.get(key) or "fine"
        level = co2_level(ppm)
        if level == "fine":
            if before != "fine" and ppm < FRESH_BELOW:
                memory.set(key, "fine")
            return None
        if not occupied:
            return None
        if _RANK[level] > _RANK.get(before, 0):
            is_reminder = False
        elif reminder and (age := memory.age(key)) is not None and age >= reminder:
            is_reminder = True
        else:
            return None
        result = await self.data.announcer.async_announce(
            co2_request(style, area, room, ppm, reminder=is_reminder)
        )
        if result.get("spoken"):
            memory.set(key, level)
        return result
