"""Her voice: rewrite, clean, and never lose the facts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.glados.voice import async_say, build_prompt


def _reply(text: str) -> SimpleNamespace:
    return SimpleNamespace(response=SimpleNamespace(speech={"plain": {"speech": text}}))


async def test_prompt_format() -> None:
    assert build_prompt("It is 3°C.", "weather?") == (
        "REQUEST: weather?\nFACTS: It is 3°C.\nTASK: none"
    )


async def test_rewrite_is_cleaned(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(return_value=_reply('It is -3°C. "Lovely." 🎂')),
    ) as converse:
        assert await async_say(hass, "conversation.glados_voice", "It is -3°C") == (
            "It is minus 3 degrees. Lovely."
        )
    assert converse.call_args.kwargs["agent_id"] == "conversation.glados_voice"


async def test_falls_back_to_the_facts(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(side_effect=HomeAssistantError("agent gone")),
    ):
        assert await async_say(hass, "conversation.x", "Reminder: call the dentist.") == (
            "Reminder: call the dentist."
        )
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(return_value=_reply("   ")),
    ):
        assert await async_say(hass, "conversation.x", "Leave now.") == "Leave now."
