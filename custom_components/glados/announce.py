"""The polite announcer: say something unprompted, in the right room, only when polite.

A port of the glados_announce script, with the same rules and the same result
({spoken, reason, speech, area}):

- stay quiet outside the speaking schedule (unless told to ignore it), when
  someone is in bed, the bedroom is dark, it is before a morning alarm,
  anything labelled glados_quiet is on, a video is playing, or no voice
  satellite is free;
- the GLaDOS voice rewrites the facts; the Announcer reads them word for word
  through its own text-to-speech voice, and GLaDOS may chime in after;
- Portal-style beeps before and after, except on satellites with their own chime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from homeassistant.core import Context, HomeAssistant

from .const import (
    CONF_ANNOUNCER_VOICE,
    CONF_BEEP_IN,
    CONF_BEEP_OUT,
    CONF_SCHEDULE,
    DEFAULTS,
    LABEL_OWN_CHIME,
    VOICE_ANNOUNCER,
)
from .registry import label_entities
from .rooms import RoomContext, describe
from .speech import clean_for_speech
from .voice import async_say


@dataclass
class AnnounceRequest:
    """What to announce and how."""

    facts: str
    task: str = ""
    area: str | None = None
    ignore_schedule: bool = False
    anywhere: bool = True
    voice: str = "glados"
    glados_after: str = ""


def blocked_reason(ctx: RoomContext, ignore_schedule: bool, anywhere: bool) -> str:
    """Why she must stay quiet in this room, or '' when she may speak."""
    if not ignore_schedule and not ctx.may_speak:
        return "outside speaking hours"
    if ctx.in_bed:
        return "someone is in bed"
    if ctx.dark_bedroom:
        return "the bedroom is dark, people may be asleep"
    if ctx.before_alarm:
        return f"people may be asleep until the {ctx.before_alarm} alarm"
    if ctx.quiet:
        return "do not disturb is on"
    if ctx.watching:
        return "a video is playing"
    if not ctx.satellite and not (anywhere and ctx.any_satellite):
        return "no free voice satellite"
    return ""


def announcer_media_id(voice_setting: str, line: str) -> str:
    """A media-source URL that speaks the line in the Announcer's voice.

    voice_setting is "tts.engine:voice", such as "tts.piper_2:announcer".
    """
    engine, _, voice = voice_setting.partition(":")
    return (
        f"media-source://tts/{engine}?message={quote(line, safe='')}"
        f"&language=en_US&voice={voice or 'announcer'}"
    )


class Announcer:
    """Speaks through assist satellites, politely."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self.hass = hass
        self.options = {**DEFAULTS, **options}

    async def _play(self, satellite: str, **data: Any) -> None:
        await self.hass.services.async_call(
            "assist_satellite",
            "announce",
            {"entity_id": satellite, **data},
            blocking=True,
        )

    async def async_announce(
        self, req: AnnounceRequest, context: Context | None = None
    ) -> dict[str, Any]:
        """Announce, or explain why not."""
        ctx = describe(self.hass, req.area, str(self.options[CONF_SCHEDULE] or "") or None)
        reason = blocked_reason(ctx, req.ignore_schedule, req.anywhere)
        if reason:
            return {"spoken": False, "reason": reason, "speech": "", "area": ctx.area}

        satellite = ctx.satellite or (ctx.any_satellite if req.anywhere else "")
        own_chime = satellite in label_entities(self.hass, LABEL_OWN_CHIME)
        beep_in = str(self.options[CONF_BEEP_IN] or "")
        beep_out = str(self.options[CONF_BEEP_OUT] or "")
        chime = {"preannounce": not own_chime and bool(beep_in)}
        if chime["preannounce"]:
            chime["preannounce_media_id"] = beep_in

        if req.voice == VOICE_ANNOUNCER:
            line = clean_for_speech(req.facts)
            announcer = str(self.options[CONF_ANNOUNCER_VOICE] or "")
            if announcer:
                await self._play(
                    satellite, media_id=announcer_media_id(announcer, line), **chime
                )
            else:
                # No Announcer voice set up: the satellite's own voice reads it.
                await self._play(satellite, message=line, **chime)
            if req.glados_after:
                after = await async_say(
                    self.hass,
                    self.options,
                    req.facts,
                    task=(
                        "The facility Announcer just said this. You chime in right "
                        f"after it with one short remark of your own. {req.glados_after}"
                    ),
                    context=context,
                )
                if after:
                    await self._play(satellite, message=after, preannounce=False)
        else:
            who = (
                f"The person in the room is {ctx.people[0]}. "
                if len(ctx.people) == 1
                else ""
            )
            line = await async_say(
                self.hass,
                self.options,
                req.facts,
                task=f"Unprompted announcement. {who}{req.task}".strip(),
                context=context,
            )
            await self._play(satellite, message=line, **chime)

        if not own_chime and beep_out:
            await self._play(satellite, media_id=beep_out, preannounce=False)
        return {"spoken": True, "reason": "", "speech": line, "area": ctx.area}
