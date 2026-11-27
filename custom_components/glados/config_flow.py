"""Config flow for GLaDOS: pick her brain at setup, tune voices and sounds later."""

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
    CONF_ALARM_BACKUP,
    CONF_ANNOUNCER_VOICE,
    CONF_BEEP_IN,
    CONF_BEDTIME_SENSOR,
    CONF_BEEP_OUT,
    CONF_CO2_ALERTS,
    CONF_CO2_REMINDER,
    CONF_COLD_OUTSIDE,
    CONF_CHAT_AGENT,
    CONF_HOME_TOWN,
    CONF_LEAVE_HEADS_UP,
    CONF_PERSONALITY,
    CONF_REMINDERS,
    CONF_ROUTINE_MINUTES,
    CONF_SCHEDULE,
    CONF_VOICE_AGENT,
    DEFAULTS,
    DOMAIN,
)

AGENT = selector.EntitySelector(selector.EntitySelectorConfig(domain="conversation"))
TEXT = selector.TextSelector()


def _suggested(key: str, current: dict[str, Any]) -> dict[str, Any] | None:
    value = current.get(key)
    return {"suggested_value": value} if value else None


def _setup_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CHAT_AGENT, description=_suggested(CONF_CHAT_AGENT, current)): AGENT,
            vol.Required(CONF_PERSONALITY, default=bool(current[CONF_PERSONALITY])): (
                selector.BooleanSelector()
            ),
            vol.Optional(CONF_HOME_TOWN, description=_suggested(CONF_HOME_TOWN, current)): TEXT,
        }
    )


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    def opt(key: str) -> vol.Optional:
        return vol.Optional(key, description=_suggested(key, current))

    return _setup_schema(current).extend(
        {
            opt(CONF_VOICE_AGENT): AGENT,
            opt(CONF_ANNOUNCER_VOICE): TEXT,
            opt(CONF_BEEP_IN): TEXT,
            opt(CONF_BEEP_OUT): TEXT,
            opt(CONF_SCHEDULE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="schedule")
            ),
            opt(CONF_BEDTIME_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="timestamp")
            ),
            vol.Required(CONF_REMINDERS, default=bool(current[CONF_REMINDERS])): (
                selector.BooleanSelector()
            ),
            vol.Required(CONF_CO2_ALERTS, default=str(current[CONF_CO2_ALERTS])): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["announcer", "glados", "off"],
                        translation_key=CONF_CO2_ALERTS,
                    )
                )
            ),
            vol.Required(CONF_CO2_REMINDER, default=int(current[CONF_CO2_REMINDER])): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=240, step=5, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
            vol.Required(CONF_COLD_OUTSIDE, default=float(current[CONF_COLD_OUTSIDE])): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-20, max=25, step=1, unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
            vol.Required(CONF_LEAVE_HEADS_UP, default=int(current[CONF_LEAVE_HEADS_UP])): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=120, step=5, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
            vol.Required(CONF_ALARM_BACKUP, default=int(current[CONF_ALARM_BACKUP])): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=60, step=1, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
            vol.Required(CONF_ROUTINE_MINUTES, default=int(current[CONF_ROUTINE_MINUTES])): (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=180, step=5, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            ),
        }
    )


def clean_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Every option stored; a text field the form left out was cleared."""
    data = dict(DEFAULTS)
    data.update(user_input)
    data[CONF_ROUTINE_MINUTES] = int(data[CONF_ROUTINE_MINUTES])
    data[CONF_CO2_REMINDER] = int(data[CONF_CO2_REMINDER])
    data[CONF_ALARM_BACKUP] = int(data[CONF_ALARM_BACKUP])
    data[CONF_LEAVE_HEADS_UP] = int(data[CONF_LEAVE_HEADS_UP])
    return data


class GladosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up GLaDOS. There is one per Home Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the chat agent she thinks with."""
        if user_input is not None:
            return self.async_create_entry(
                title="GLaDOS", data={}, options=clean_options(user_input)
            )
        return self.async_show_form(step_id="user", data_schema=_setup_schema(dict(DEFAULTS)))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Agents, voices, sounds, schedule."""
        return GladosOptionsFlow()


class GladosOptionsFlow(OptionsFlow):
    """Change her agents, voices, sounds and speaking schedule."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """One form with every option."""
        if user_input is not None:
            return self.async_create_entry(data=clean_options(user_input))
        current = {**DEFAULTS, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_options_schema(current))
