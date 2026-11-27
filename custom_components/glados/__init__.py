"""GLaDOS: a sarcastic, genuinely helpful home assistant.

Phase 1 of docs/PLAN.md. For now this only provides the speech cleanup as a
service; room context, memory and the polite announcer follow.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
import homeassistant.helpers.config_validation as cv

from .const import ATTR_TEXT, DOMAIN, SERVICE_CLEAN_TEXT
from .speech import clean_for_speech

CLEAN_TEXT_SCHEMA = vol.Schema({vol.Required(ATTR_TEXT): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GLaDOS from a config entry."""

    async def _clean_text(call: ServiceCall) -> ServiceResponse:
        return {ATTR_TEXT: clean_for_speech(call.data[ATTR_TEXT])}

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_TEXT,
        _clean_text,
        schema=CLEAN_TEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    hass.services.async_remove(DOMAIN, SERVICE_CLEAN_TEXT)
    return True
