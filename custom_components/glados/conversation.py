"""GLaDOS as a conversation agent: any chat agent, in her character, cleaned for speech.

Pick "GLaDOS" as the pipeline's conversation agent. Every sentence goes to the
chat agent set in the options (any LLM agent: Ollama, OpenAI, Google, Anthropic),
with its conversation id, device and satellite, so tools, history and timers
keep working. With "Add her personality" on, her persona travels along as the
extra system prompt. The spoken reply goes through the same cleanup as her
announcements: emoji, markdown, quotes, units and minus signs.
"""

from __future__ import annotations

from typing import Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHAT_AGENT, CONF_HOME_TOWN, CONF_PERSONALITY, DEFAULTS, DOMAIN
from .prompts import persona
from .speech import clean_for_speech


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the GLaDOS conversation agent."""
    async_add_entities([GladosAgent(entry)])


def clean_result(result: ConversationResult) -> ConversationResult:
    """Clean the spoken part of a reply in place."""
    speech = result.response.speech.get("plain", {}).get("speech")
    if speech:
        result.response.async_set_speech(clean_for_speech(speech))
    return result


class GladosAgent(conversation.ConversationEntity):
    """Passes each sentence to the chat agent and cleans the reply."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "GLaDOS",
            "manufacturer": "Aperture Science",
            "model": "Genetic Lifeform and Disk Operating System",
            "entry_type": "service",
        }

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Whatever the chat agent speaks."""
        return "*"

    @property
    def options(self) -> dict:
        return {**DEFAULTS, **self._entry.options}

    def _error(self, user_input: ConversationInput, text: str) -> ConversationResult:
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, text)
        return ConversationResult(response, user_input.conversation_id)

    def _instructions(self, user_input: ConversationInput) -> str | None:
        opts = self.options
        parts = [
            persona(self.hass, str(opts[CONF_HOME_TOWN] or "")) if opts[CONF_PERSONALITY] else "",
            user_input.extra_system_prompt or "",
        ]
        return "\n\n".join(p for p in parts if p) or None

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Ask the chat agent, then clean what she says."""
        agent = str(self.options[CONF_CHAT_AGENT] or "")
        if not agent:
            return self._error(
                user_input, "I have no brain. Pick a chat agent under Configure."
            )
        if agent == self.entity_id:
            return self._error(
                user_input,
                "My chat agent is set to myself. Pick another one under Configure.",
            )
        result = await conversation.async_converse(
            self.hass,
            user_input.text,
            user_input.conversation_id,
            user_input.context,
            language=user_input.language,
            agent_id=agent,
            device_id=user_input.device_id,
            satellite_id=user_input.satellite_id,
            extra_system_prompt=self._instructions(user_input),
        )
        return clean_result(result)
