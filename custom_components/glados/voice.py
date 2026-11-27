"""Her voice: rewrite plain facts in GLaDOS's words, then make them speakable.

A port of the glados_say script. The voice agent gets REQUEST, FACTS and TASK
lines; whatever it says is cleaned for text-to-speech. When the agent fails or
says nothing, the plain facts are spoken instead, so a reminder is never lost.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_CHAT_AGENT, CONF_PERSONALITY, CONF_VOICE_AGENT, DEFAULTS
from .prompts import voice
from .speech import clean_for_speech

_LOGGER = logging.getLogger(__name__)


def build_prompt(facts: str, request: str = "", task: str = "") -> str:
    """The text the voice agent receives."""
    return f"REQUEST: {request}\nFACTS: {facts}\nTASK: {task or 'none'}"


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
) -> str:
    """The facts in her voice, cleaned for speech."""
    agent_id, instructions = voice_agent(hass, options)
    if not agent_id:
        return clean_for_speech(facts)
    line = ""
    try:
        result = await conversation.async_converse(
            hass,
            build_prompt(facts, request, task),
            None,
            context or Context(),
            agent_id=agent_id,
            extra_system_prompt=instructions,
        )
        line = (result.response.speech.get("plain", {}).get("speech") or "").strip()
    except (HomeAssistantError, ValueError) as err:
        _LOGGER.warning("Voice agent %s failed, speaking the plain facts: %s", agent_id, err)
    return clean_for_speech(line or facts)
