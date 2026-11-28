"""Her own initiative: comfort offers, facility notices, the idle remark.

- Comfort: someone has settled in a room (10 minutes) that is too cold or too
  warm, and a heater or cooler for it is off. She asks out loud whether to switch
  it on and listens for yes or no, on a satellite that can listen. No heat while
  a window there is open. She remembers the answer: a no holds for the rest of
  the day, a yes for three hours, no answer for an hour.
- Facility notices: rare and true, by the Announcer: a reminder to move after
  three hours in one room, a coat in the cold. At most one every three days,
  at a random moment. And once a night, an hour past someone's bedtime with the
  lights still on: testing hours have ended.
- The idle remark: once a day at a random moment, one unprompted remark about
  something real in the room, with one technique picked at random. This one is
  improvised on purpose, so it stays fresh.

All of it only during the speaking schedule (the late notice aside), never while
someone sleeps, on Do Not Disturb or during a video.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import random
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util

from .announce import AnnounceRequest
from .bedtime import bedtime_for
from .const import (
    CONF_COLD_BELOW,
    CONF_COMFORT,
    CONF_IDLE,
    CONF_NOTICES,
    CONF_SCHEDULE,
    CONF_SETTLED,
    CONF_WARM_ABOVE,
    LABEL_GLADOS,
    LABEL_OWN_CHIME,
    VOICE_ANNOUNCER,
    VOICE_GLADOS,
)
from .people import people_home, person_area
from .registry import area_of, label_entities
from .rooms import RoomContext, describe
from .setpieces import (
    COMFORT_NO_WORDS,
    COMFORT_YES_WORDS,
    LATE_NOTICE,
    comfort_lines,
    notice_lines,
)
from .voice import async_say

if TYPE_CHECKING:
    from . import GladosData

NOTICE_EVERY = timedelta(days=3)
# Odds per heartbeat (every 30 s): a notice lands on average after ~8 hours of
# chances, an idle remark after ~1.5 hours, so neither comes at a predictable time.
NOTICE_ODDS = 960
IDLE_ODDS = 180
_HEAT_ON = ("on", "heat", "heat_cool", "auto")
_COOL_ON = ("on", "cool", "heat_cool", "auto", "dry")
TECHNIQUES = (
    "a fake Enrichment Center announcement in a cheerful corporate voice, about something "
    "real in this room right now",
    "an interesting scientific fact that is really an insult, about what they are doing or "
    "the time of day",
    "a note you are adding to their permanent file about their behaviour today",
    "a needling rhetorical question about how they are spending their time",
    "a short, almost sincere remark that you undercut immediately",
    "a petty callback to something in their permanent file",
)


def _names(hass: HomeAssistant, entity_ids: list[str]) -> str:
    names = [s.name for e in entity_ids if (s := hass.states.get(e))]
    return " and ".join(names) or "heater"


class Character:
    """What she does on her own initiative."""

    def __init__(self, hass: HomeAssistant, data: GladosData) -> None:
        self.hass = hass
        self.data = data

    @property
    def options(self) -> dict[str, Any]:
        return self.data.options

    def _quiet(self, ctx: RoomContext) -> bool:
        return ctx.sleeping or bool(ctx.quiet) or bool(ctx.watching) or not ctx.satellite

    async def async_tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = dt_util.now()
        said: list[dict[str, Any]] = []
        schedule = str(self.options.get(CONF_SCHEDULE) or "") or None
        rooms = [describe(self.hass, a.id, schedule) for a in ar.async_get(self.hass).async_list_areas()]
        if self.options.get(CONF_COMFORT, True):
            for ctx in rooms:
                if result := await self.async_comfort(ctx, now):
                    said.append(result)
        if self.options.get(CONF_NOTICES, True):
            # The late notice when it is due; otherwise, now and then, a daytime one.
            result = await self.async_late_notice(now)
            if result is None and random.randrange(NOTICE_ODDS) == 0:
                result = await self.async_notice(rooms, now)
            if result:
                said.append(result)
        if self.options.get(CONF_IDLE, True) and random.randrange(IDLE_ODDS) == 0:
            if result := await self.async_idle(rooms, now):
                said.append(result)
        return said

    # Comfort --------------------------------------------------------------------

    def _recent_answer(self, key: str, kind: str, now: datetime) -> bool:
        raw = self.data.memory.get(key)
        at = self.data.memory.stored_at(key)
        if not raw or at is None or not raw.startswith(f"{kind}:"):
            return False
        answer = raw.split(":", 1)[1]
        age = now - at
        if answer == "no":
            return dt_util.as_local(at).date() == now.date()
        return age < (timedelta(hours=3) if answer == "yes" else timedelta(hours=1))

    async def async_comfort(self, ctx: RoomContext, now: datetime) -> dict[str, Any] | None:
        """Offer heat or cool in one room, and act on the answer."""
        t = ctx.temperature
        if t is None or not ctx.may_speak or self._quiet(ctx) or not ctx.ask_satellite:
            return None
        if ctx.occupied_minutes < float(self.options.get(CONF_SETTLED, 10)):
            return None
        heat_on = any(self.hass.states.is_state(e, s) for e in ctx.heaters for s in _HEAT_ON)
        cool_on = any(self.hass.states.is_state(e, s) for e in ctx.coolers for s in _COOL_ON)
        if t < float(self.options.get(CONF_COLD_BELOW, 16)) and ctx.heaters and not heat_on \
                and not ctx.open_windows:
            kind, devices = "heat", ctx.heaters
        elif t > float(self.options.get(CONF_WARM_ABOVE, 25)) and ctx.coolers and not cool_on:
            kind, devices = "cool", ctx.coolers
        else:
            return None
        key = f"comfort {ctx.area}"
        if self._recent_answer(key, kind, now):
            return None
        device = _names(self.hass, devices)
        question, yes_line, no_line = comfort_lines(kind, t, ctx.area_name, device)
        own_chime = ctx.ask_satellite in label_entities(self.hass, LABEL_OWN_CHIME)
        beep = str(self.options.get("beep_in") or "")
        data: dict[str, Any] = {
            "entity_id": ctx.ask_satellite, "question": question,
            "preannounce": bool(beep) and not own_chime,
            "answers": [{"id": "yes", "sentences": COMFORT_YES_WORDS},
                        {"id": "no", "sentences": COMFORT_NO_WORDS}],
        }
        if data["preannounce"]:
            data["preannounce_media_id"] = beep
        try:
            reply = await self.hass.services.async_call(
                "assist_satellite", "ask_question", data, blocking=True, return_response=True)
        except Exception:
            reply = None
        answer = (reply or {}).get("id") or "none"
        if answer == "yes":
            climates = [e for e in devices if e.startswith("climate.")]
            others = [e for e in devices if not e.startswith("climate.")]
            if climates:
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {"entity_id": climates, "hvac_mode": kind},
                    blocking=True)
            if others:
                await self.hass.services.async_call(
                    "homeassistant", "turn_on", {"entity_id": others}, blocking=True)
        if answer in ("yes", "no"):
            await self.hass.services.async_call(
                "assist_satellite", "announce",
                {"entity_id": ctx.ask_satellite, "message": yes_line if answer == "yes" else no_line,
                 "preannounce": False}, blocking=True)
        self.data.memory.set(key, f"{kind}:{answer}")
        return {"kind": kind, "answer": answer, "question": question, "area": ctx.area}

    # Facility notices --------------------------------------------------------------

    async def async_late_notice(self, now: datetime) -> dict[str, Any] | None:
        """Once a night, an hour past someone's bedtime, lights still on."""
        if (at := self.data.memory.stored_at("late notice")) and now - at < timedelta(hours=12):
            return None
        for person in people_home(self.hass):
            bt = bedtime_for(self.hass, self.options, person, now).bedtime
            if bt is None or not (bt + timedelta(hours=1) <= now < bt + timedelta(hours=5)):
                continue
            area = person_area(self.hass, person)
            ctx = describe(self.hass, area, None)
            lights_on = any(e.startswith("light.") and area_of(self.hass, e) == ctx.area
                            and self.hass.states.is_state(e, "on")
                            for e in label_entities(self.hass, LABEL_GLADOS))
            if not lights_on or ctx.in_bed or ctx.quiet or ctx.watching:
                continue
            result = await self.data.announcer.async_announce(AnnounceRequest(
                facts=LATE_NOTICE, voice=VOICE_ANNOUNCER, area=ctx.area, ignore_schedule=True,
                awake=True))
            if result.get("spoken"):
                self.data.memory.set("late notice", now.isoformat())
                return result
        return None

    async def async_notice(self, rooms: list[RoomContext], now: datetime) -> dict[str, Any] | None:
        """A rare, true facility notice where someone is."""
        if (age := self.data.memory.age("facility notice")) is not None and age < NOTICE_EVERY:
            return None
        for ctx in rooms:
            if not ctx.people or not ctx.may_speak or self._quiet(ctx):
                continue
            lines = notice_lines(ctx.area_name, ctx.occupied_minutes // 60, ctx.outside)
            if not lines:
                continue
            result = await self.data.announcer.async_announce(AnnounceRequest(
                facts=random.choice(lines), voice=VOICE_ANNOUNCER, area=ctx.area))
            if result.get("spoken"):
                self.data.memory.set("facility notice", now.isoformat())
                return result
        return None

    # The idle remark ------------------------------------------------------------------

    async def async_idle(self, rooms: list[RoomContext], now: datetime) -> dict[str, Any] | None:
        """Once a day: one unprompted remark to fill the silence."""
        if self.data.memory.stored_today("idle remark"):
            return None
        for ctx in rooms:
            if not ctx.people or ctx.occupied_minutes < 20 or not ctx.may_speak or self._quiet(ctx):
                continue
            playing = next((s.attributes.get("media_title") for s in self.hass.states.async_all("media_player")
                            if s.state == "playing" and s.attributes.get("media_title")
                            and area_of(self.hass, s.entity_id) in (ctx.area, None)), "")
            notes = self.data.memory.notes()[:3]
            facts = (f"It is {now.strftime('%A %H:%M')}. They have been in the {ctx.area_name} for "
                     f"{ctx.occupied_minutes} minutes.")
            if ctx.temperature is not None:
                facts += f" It is {round(ctx.temperature)} degrees in here."
            if playing:
                facts += f" {playing} is playing."
            if notes:
                facts += " Their permanent file says: " + "; ".join(notes) + "."
            line = await async_say(
                self.hass, self.options, facts,
                task=("Nobody asked. One unprompted remark to fill the silence, using this "
                      f"technique: {random.choice(TECHNIQUES)}. One or two short sentences."),
                fallback="")
            if not line:
                return None
            result = await self.data.announcer.async_announce(AnnounceRequest(
                facts=line, voice=VOICE_GLADOS, area=ctx.area, glados_line=line))
            if result.get("spoken"):
                self.data.memory.set("idle remark", now.isoformat())
                return result
        return None
