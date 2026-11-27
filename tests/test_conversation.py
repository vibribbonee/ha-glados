"""The GLaDOS agent: passes the sentence on and cleans the reply."""

from __future__ import annotations

from typing import Literal

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component

from custom_components.glados.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


class FakeChat(conversation.AbstractConversationAgent):
    """Replies like the 8B model on a bad day, and keeps what it was given."""

    def __init__(self) -> None:
        self.seen: list[conversation.ConversationInput] = []

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return "*"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        self.seen.append(user_input)
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech("**Wind:** 12 km/h, it is -3°C 🙂")
        return conversation.ConversationResult(
            response, conversation_id="abc", continue_conversation=True
        )


async def _setup(hass: HomeAssistant, chat: str | None, **options) -> FakeChat:
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    fake = FakeChat()
    chat_entry = MockConfigEntry(domain="fake_chat")
    chat_entry.add_to_hass(hass)
    conversation.async_set_agent(hass, chat_entry, fake)
    options = {"chat_agent": chat or chat_entry.entry_id, **options}
    entry = MockConfigEntry(domain=DOMAIN, title="GLaDOS", options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return fake


async def test_reply_is_cleaned(hass: HomeAssistant) -> None:
    fake = await _setup(hass, None)
    assert hass.states.get("conversation.glados") is not None

    result = await conversation.async_converse(
        hass,
        "how cold is it",
        "abc",
        Context(),
        agent_id="conversation.glados",
        device_id="puck",
        satellite_id="assist_satellite.puck_3",
    )
    speech = result.response.speech["plain"]["speech"]
    assert "km/h" not in speech and "°" not in speech and "**" not in speech
    assert "minus 3 degrees" in speech
    assert result.conversation_id == "abc" and result.continue_conversation

    sent = fake.seen[0]
    assert sent.text == "how cold is it" and sent.conversation_id == "abc"
    assert sent.device_id == "puck" and sent.satellite_id == "assist_satellite.puck_3"


async def test_personality_travels_along(hass: HomeAssistant) -> None:
    hass.states.async_set("person.ada", "home", {"friendly_name": "ada"})
    fake = await _setup(hass, None, home_town="Delft")
    await conversation.async_converse(
        hass, "who are you", None, Context(), agent_id="conversation.glados"
    )
    prompt = fake.seen[0].extra_system_prompt
    assert "Glad-oss" in prompt and "in Delft" in prompt and "occupant is Ada" in prompt


async def test_personality_off(hass: HomeAssistant) -> None:
    fake = await _setup(hass, None, personality=False)
    await conversation.async_converse(
        hass, "hello", None, Context(), agent_id="conversation.glados"
    )
    assert fake.seen[0].extra_system_prompt is None


async def test_never_calls_itself(hass: HomeAssistant) -> None:
    fake = await _setup(hass, "conversation.glados")
    result = await conversation.async_converse(
        hass, "hello", None, Context(), agent_id="conversation.glados"
    )
    assert result.response.response_type == intent.IntentResponseType.ERROR
    assert not fake.seen
