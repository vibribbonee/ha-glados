"""Her voice: rewrite plain facts in GLaDOS's words, then make them speakable.

A port of the glados_say script. The voice agent gets REQUEST, FACTS and TASK
lines; whatever it says is cleaned for text-to-speech. When the agent fails or
says nothing, the plain facts are spoken instead, so a reminder is never lost.
"""

from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .speech import clean_for_speech

_LOGGER = logging.getLogger(__name__)


def build_prompt(facts: str, request: str = "", task: str = "") -> str:
    """The text the voice agent receives."""
    return f"REQUEST: {request}\nFACTS: {facts}\nTASK: {task or 'none'}"


async def async_say(
    hass: HomeAssistant,
    agent_id: str,
    facts: str,
    request: str = "",
    task: str = "",
    context: Context | None = None,
) -> str:
    """The facts in her voice, cleaned for speech."""
    line = ""
    try:
        result = await conversation.async_converse(
            hass,
            build_prompt(facts, request, task),
            None,
            context or Context(),
            agent_id=agent_id,
        )
        line = (result.response.speech.get("plain", {}).get("speech") or "").strip()
    except (HomeAssistantError, ValueError) as err:
        _LOGGER.warning("Voice agent %s failed, speaking the plain facts: %s", agent_id, err)
    return clean_for_speech(line or facts)
