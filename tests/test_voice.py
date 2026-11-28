"""Her voice: rewrite, clean, and never lose the facts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.glados.voice import async_say, build_prompt, voice_agent


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
        assert await async_say(hass, {"voice_agent": "conversation.glados_voice", "personality": False}, "It is -3°C") == (
            "It is minus 3 degrees. Lovely."
        )
    assert converse.call_args.kwargs["agent_id"] == "conversation.glados_voice"
    assert converse.call_args.kwargs["extra_system_prompt"] is None


async def test_falls_back_to_the_facts(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(side_effect=HomeAssistantError("agent gone")),
    ):
        assert await async_say(hass, {"chat_agent": "conversation.x"}, "Reminder: call the dentist.") == (
            "Reminder: call the dentist."
        )
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(return_value=_reply("   ")),
    ):
        assert await async_say(hass, {"chat_agent": "conversation.x"}, "Leave now.") == "Leave now."


async def test_which_agent_rewrites(hass: HomeAssistant) -> None:
    # Without a voice agent, the chat agent rewrites with the shipped instructions.
    agent, instructions = voice_agent(hass, {"chat_agent": "conversation.chat"})
    assert agent == "conversation.chat" and "FACTS" in instructions
    # A dedicated voice agent brings its own prompt when the personality is off.
    assert voice_agent(hass, {"voice_agent": "conversation.v", "personality": False}) == (
        "conversation.v", None
    )
    # No agent at all: the plain facts are spoken, cleaned.
    assert await async_say(hass, {}, "It is 3°C.") == "It is 3 degrees."


async def test_a_task_read_back_is_dropped(hass: HomeAssistant) -> None:
    from custom_components.glados.voice import echoes
    task = "Reply to the Announcer in one short remark. Be surprised and shocked."
    echo = "The Announcer in one short remark. Be surprised and shocked."
    assert echoes(echo, task) and not echoes("Oh. How brave of you.", task)
    with patch(
        "custom_components.glados.voice.conversation.async_converse",
        AsyncMock(return_value=_reply(echo)),
    ):
        # An optional remark falls back to nothing; a real message to the facts.
        assert await async_say(hass, {"chat_agent": "conversation.x"}, "x", task=task, fallback="") == ""
        assert await async_say(hass, {"chat_agent": "conversation.x"}, "Leave now.", task=task) == "Leave now."


def test_drop_the_announcers_line() -> None:
    from custom_components.glados.voice import drop_repeat
    said = "I like kissing boys."
    reply = "The facility Announcer announced: I like kissing boys. How... unexpected."
    assert drop_repeat(reply, said) == "How... unexpected."
    assert drop_repeat("How brave.", said) == "How brave."


async def test_a_hung_model_gives_up(hass: HomeAssistant) -> None:
    import asyncio

    async def hang(*args, **kwargs):
        await asyncio.sleep(10)

    with patch("custom_components.glados.voice.VOICE_TIMEOUT", 0.05), patch(
        "custom_components.glados.voice.conversation.async_converse", side_effect=hang
    ):
        assert await async_say(hass, {"chat_agent": "conversation.x"}, "Leave now.") == "Leave now."


async def test_announcements_take_turns(hass: HomeAssistant) -> None:
    import asyncio
    from custom_components.glados.announce import Announcer, AnnounceRequest
    order: list[str] = []
    announcer = Announcer(hass, {})

    async def slow(req, context=None):
        order.append(f"start {req.facts}")
        await asyncio.sleep(0.01)
        order.append(f"end {req.facts}")
        return {"spoken": True}

    announcer._announce = slow
    await asyncio.gather(announcer.async_announce(AnnounceRequest(facts="a")),
                         announcer.async_announce(AnnounceRequest(facts="b")))
    assert order in (["start a", "end a", "start b", "end b"], ["start b", "end b", "start a", "end a"])
