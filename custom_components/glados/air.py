"""Air and window warnings, room by room.

Every minute each room is checked:

- CO2 gets worse (fine, stale, critical): warn once, in that room; while it stays
  bad, remind after the reminder time, if one is set;
- CO2 is fresh again (well below stale): forget it, and when it is cold outside
  and a window is open there, say it can be closed;
- a window open in the cold for 20 minutes, in a room someone is in and where
  the air is fine: say so, once per opening;
- the same in a room nobody is in, or a window with no room: say so where
  people are, once per opening.

Nothing is said when the polite rules say no (someone in bed, before an alarm, a
dark bedroom, Do Not Disturb, a video). What could not be said is tried again
the next minute.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_ON
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .const import (
    CONF_CO2_ALERTS,
    CONF_CO2_REMINDER,
    CONF_COLD_OUTSIDE,
    CONF_SCHEDULE,
    DEFAULTS,
    VOICE_ANNOUNCER,
    VOICE_GLADOS,
)
from .people import people_home
from .registry import area_name, area_of
from .rooms import RoomContext, describe
from .setpieces import (
    CO2_STALE,
    STYLE_GLADOS,
    STYLE_OFF,
    co2_announcement,
    co2_glados_alone,
    co2_level,
    window_lines,
)

if TYPE_CHECKING:
    from . import GladosData

CHECK_EVERY = timedelta(minutes=1)
FRESH_BELOW = CO2_STALE - 150  # hysteresis: back to fine only well below stale
WINDOW_AFTER = timedelta(minutes=20)
_RANK = {"fine": 0, "stale": 1, "critical": 2}


def _request(style: str, announcer: str | None, glados: str, area: str | None,
             satellite: str | None = None) -> AnnounceRequest:
    if style == STYLE_GLADOS or announcer is None:
        return AnnounceRequest(facts=glados, voice=VOICE_GLADOS, area=area,
                               glados_line=glados, satellite=satellite)
    return AnnounceRequest(facts=announcer, voice=VOICE_ANNOUNCER, area=area,
                           glados_line=glados, satellite=satellite)


def co2_request(
    style: str, area: str | None, room: str, ppm: float, reminder: bool = False,
    satellite: str | None = None,
) -> AnnounceRequest:
    """The CO2 announcement for this room and reading, in the chosen style."""
    if style == STYLE_GLADOS:
        return _request(style, None, co2_glados_alone(room, ppm, reminder=reminder), area,
                        satellite)
    announcer, glados = co2_announcement(room, ppm, reminder=reminder)
    return _request(style, announcer, glados, area, satellite)


def _open_since(state: State) -> datetime:
    return state.last_changed


class AirWatch:
    """Checks the rooms' air and windows, and warns."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @callback
    def start(self) -> CALLBACK_TYPE:
        """Start checking; returns the stop callback."""
        return async_track_time_interval(self.hass, self.async_tick, CHECK_EVERY)

    @property
    def style(self) -> str:
        return str(self.data.options.get(CONF_CO2_ALERTS) or STYLE_OFF)

    @property
    def cold_below(self) -> float:
        return float(self.data.options.get(CONF_COLD_OUTSIDE, DEFAULTS[CONF_COLD_OUTSIDE]))

    async def async_tick(self, now: datetime | None = None) -> None:
        if self.style == STYLE_OFF:
            return
        options = self.data.options
        reminder = timedelta(minutes=int(options.get(CONF_CO2_REMINDER) or 0))
        schedule = str(options.get(CONF_SCHEDULE) or "") or None
        rooms: dict[str, RoomContext] = {}
        for area in ar.async_get(self.hass).async_list_areas():
            ctx = describe(self.hass, area.id, schedule)
            rooms[area.id] = ctx
            if ctx.co2 is not None:
                await self.async_check_room(area.id, area.name, ctx.co2, ctx.occupied,
                                            self.style, reminder, ctx)
            await self.async_check_windows_here(ctx)
        await self.async_check_loose_windows(rooms)

    # CO2 ------------------------------------------------------------------

    async def async_check_room(
        self, area: str, room: str, ppm: float, occupied: bool, style: str,
        reminder: timedelta, ctx: RoomContext | None = None,
    ) -> dict[str, Any] | None:
        """Warn, remind or forget for one room. Returns the announcement, if any."""
        memory = self.data.memory
        key = f"air {area}"
        before = memory.get(key) or "fine"
        level = co2_level(ppm)
        if level == "fine":
            if before != "fine" and ppm < FRESH_BELOW:
                memory.set(key, "fine")
                if ctx is not None and occupied:
                    return await self._fresh_again(ctx, style)
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

    async def _fresh_again(self, ctx: RoomContext, style: str) -> dict[str, Any] | None:
        """After a CO2 warning: in the cold, the open window can be closed."""
        if not self._cold(ctx.outside) or not ctx.open_windows:
            return None
        announcer, glados = window_lines(
            "fresh", style, room=area_name(self.hass, ctx.area), out=ctx.outside or 0
        )
        result = await self.data.announcer.async_announce(
            _request(style, announcer, glados, ctx.area)
        )
        if result.get("spoken"):
            for entity_id in ctx.windows:
                self._mark(entity_id)
        return result

    # Windows ----------------------------------------------------------------

    def _cold(self, outside: float | None) -> bool:
        return outside is not None and outside < self.cold_below

    def _long_open(self, entity_id: str) -> State | None:
        """The window's state when it has been open long enough and not yet mentioned."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state != STATE_ON:
            return None
        if dt_util.utcnow() - _open_since(state) < WINDOW_AFTER:
            return None
        if self.data.memory.get(f"window {entity_id}") == _open_since(state).isoformat():
            return None
        return state

    def _mark(self, entity_id: str) -> None:
        state = self.hass.states.get(entity_id)
        if state is not None and state.state == STATE_ON:
            self.data.memory.set(f"window {entity_id}", _open_since(state).isoformat())

    def _minutes(self, state: State) -> int:
        return int((dt_util.utcnow() - _open_since(state)).total_seconds() // 60)

    async def async_check_windows_here(self, ctx: RoomContext) -> dict[str, Any] | None:
        """A window open in the cold, in a room someone is in, with the air fine."""
        if not ctx.occupied or not self._cold(ctx.outside):
            return None
        if ctx.co2 is not None and ctx.co2 >= CO2_STALE:
            return None  # the window is doing its job
        for entity_id in ctx.windows:
            if (state := self._long_open(entity_id)) is None:
                continue
            announcer, glados = window_lines(
                "open", self.style, window=state.name, room=area_name(self.hass, ctx.area),
                minutes=self._minutes(state), out=ctx.outside or 0,
            )
            result = await self.data.announcer.async_announce(
                _request(self.style, announcer, glados, ctx.area)
            )
            if result.get("spoken"):
                self._mark(entity_id)
            return result
        return None

    async def async_check_loose_windows(
        self, rooms: dict[str, RoomContext]
    ) -> dict[str, Any] | None:
        """A window open in the cold where nobody is: tell whoever is home."""
        if not people_home(self.hass):
            return None
        outside = next((c.outside for c in rooms.values() if c.outside is not None), None)
        if outside is None:
            outside = describe(self.hass, None).outside
        if not self._cold(outside):
            return None
        for state in self.hass.states.async_all("binary_sensor"):
            if state.attributes.get("device_class") != "window":
                continue
            area = area_of(self.hass, state.entity_id)
            if area and rooms.get(area) and rooms[area].occupied:
                continue  # handled in the room itself
            if self._long_open(state.entity_id) is None:
                continue
            announcer, glados = window_lines(
                "empty", self.style, window=state.name,
                room=area_name(self.hass, area) if area else "",
                minutes=self._minutes(state), out=outside or 0,
            )
            result = await self.data.announcer.async_announce(
                _request(self.style, announcer, glados, None)
            )
            if result.get("spoken"):
                self._mark(state.entity_id)
            return result
        return None
