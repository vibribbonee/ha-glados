"""Config flow for GLaDOS: one entry, with the voices and sounds as options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ANNOUNCER_VOICE,
    CONF_CHAT_AGENT,
    CONF_BEEP_IN,
    CONF_BEEP_OUT,
    CONF_ROUTINE_MINUTES,
    CONF_SCHEDULE,
    CONF_VOICE_AGENT,
    DEFAULTS,
    DOMAIN,
)


def _schema(values: dict[str, Any]) -> vol.Schema:
    current = {**DEFAULTS, **values}
    return vol.Schema(
        {
            vol.Required(CONF_CHAT_AGENT, default=current[CONF_CHAT_AGENT]): (
                selector.EntitySelector(selector.EntitySelectorConfig(domain="conversation"))
            ),
            vol.Required(CONF_VOICE_AGENT, default=current[CONF_VOICE_AGENT]): (
                selector.EntitySelector(selector.EntitySelectorConfig(domain="conversation"))
            ),
            vol.Required(CONF_ANNOUNCER_VOICE, default=current[CONF_ANNOUNCER_VOICE]): (
                selector.TextSelector()
            ),
            vol.Optional(CONF_BEEP_IN, default=current[CONF_BEEP_IN]): selector.TextSelector(),
            vol.Optional(CONF_BEEP_OUT, default=current[CONF_BEEP_OUT]): selector.TextSelector(),
            vol.Required(CONF_SCHEDULE, default=current[CONF_SCHEDULE]): (
                selector.EntitySelector(selector.EntitySelectorConfig(domain="schedule"))
            ),
            vol.Required(CONF_ROUTINE_MINUTES, default=current[CONF_ROUTINE_MINUTES]): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=180, step=5, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
        }
    )


class GladosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up GLaDOS. There is one per Home Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry with the defaults; change them under Configure."""
        if user_input is not None:
            return self.async_create_entry(title="GLaDOS", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Voices, sounds, schedule."""
        return GladosOptionsFlow()


class GladosOptionsFlow(OptionsFlow):
    """Change voices, sounds and the speaking schedule."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """One form with every option."""
        if user_input is not None:
            user_input[CONF_ROUTINE_MINUTES] = int(user_input[CONF_ROUTINE_MINUTES])
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=_schema(dict(self.config_entry.options))
        )
