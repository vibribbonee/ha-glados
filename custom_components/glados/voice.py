"""Her voice: rewrite plain facts in GLaDOS's words, then make them speakable.

A port of the glados_say script. The voice agent gets REQUEST, FACTS and TASK
lines; whatever it says is cleaned for text-to-speech. When the agent fails or
says nothing, the plain facts are spoken instead, so a reminder is never lost.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant

from .const import CONF_CHAT_AGENT, CONF_PERSONALITY, CONF_VOICE_AGENT, DEFAULTS
from .prompts import voice
from .speech import clean_for_speech

_LOGGER = logging.getLogger(__name__)
VOICE_TIMEOUT = 30


def build_prompt(facts: str, request: str = "", task: str = "") -> str:
    """The text the voice agent receives."""
    return f"REQUEST: {request}\nFACTS: {facts}\nTASK: {task or 'none'}"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def echoes(line: str, task: str) -> bool:
    """True when the reply repeats the instructions instead of following them.

    Small models sometimes answer a TASK by reading it back. Six task words in
    a row inside the reply is never a coincidence.
    """
    words, said = _words(task), " ".join(_words(line))
    return any(
        " ".join(words[i : i + 6]) in said for i in range(max(0, len(words) - 5))
    )


def drop_repeat(line: str, said: str) -> str:
    """Cut a reply's opening repeat of what was just said (the Announcer's line)."""
    text = re.sub(r"^\s*the facility announcer (just )?(announced|said)[:,]?\s*", "", line, flags=re.I)
    target = " ".join(_words(said))
    words = text.split()
    for n in range(len(words), 0, -1):
        if " ".join(_words(" ".join(words[:n]))) == target:
            return " ".join(words[n:]).strip()
    return text.strip()


def voice_agent(hass: HomeAssistant, options: dict[str, Any]) -> tuple[str, str | None]:
    """Which agent rewrites facts, and the instructions it needs.

    A dedicated voice agent brings its own prompt unless her personality is on.
    Without one, the chat agent does it with the shipped voice instructions.
    """
    opts = {**DEFAULTS, **options}
    dedicated = str(opts[CONF_VOICE_AGENT] or "")
    if dedicated:
        return dedicated, voice(hass) if opts[CONF_PERSONALITY] else None
    return str(opts[CONF_CHAT_AGENT] or ""), voice(hass)


async def async_say(
    hass: HomeAssistant,
    options: dict[str, Any],
    facts: str,
    request: str = "",
    task: str = "",
    context: Context | None = None,
    fallback: str | None = None,
) -> str:
    """The facts in her voice, cleaned for speech.

    When the agent fails, says nothing or reads the task back, the fallback is
    spoken: the plain facts by default, or nothing for a remark that is optional.
    """
    spare = facts if fallback is None else fallback
    agent_id, instructions = voice_agent(hass, options)
    if not agent_id:
        return clean_for_speech(spare)
    line = ""
    try:
        # A model that hangs (laptop asleep) must not stall her: give up after a while.
        async with asyncio.timeout(VOICE_TIMEOUT):
            result = await conversation.async_converse(
                hass,
                build_prompt(facts, request, task),
                None,
                context or Context(),
                agent_id=agent_id,
                extra_system_prompt=instructions,
            )
        line = (result.response.speech.get("plain", {}).get("speech") or "").strip()
    except TimeoutError:
        _LOGGER.warning("Voice agent %s took over %ss, speaking the plain facts", agent_id, VOICE_TIMEOUT)
    except Exception as err:  # noqa: BLE001 - any failure: the facts still get said
        _LOGGER.warning("Voice agent %s failed, speaking the plain facts: %s", agent_id, err)
    if line and task and echoes(line, task):
        _LOGGER.debug("Voice agent read the task back, dropped: %s", line)
        line = ""
    return clean_for_speech(line or spare)
