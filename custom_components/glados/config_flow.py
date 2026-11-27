"""Config flow for GLaDOS: pick her brain at setup, the rest under Configure.

The options are grouped into sections, so nobody has to scroll past bedtime
settings to change a voice:

- brain: the chat agent, her personality, the home town, the voice agent;
- voices: the Announcer, the beeps, the speaking schedule;
- warnings: CO2 and windows;
- initiative: comfort offers, facility notices, the idle remark;
- days: reminders, alarms, leave times, the morning routine;
- nights: the morning greeting, birthdays, bedtime.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_ALARM_BACKUP,
    CONF_ANNOUNCER_VOICE,
    CONF_BEDTIME,
    CONF_BEDTIME_SENSOR,
    CONF_BEEP_IN,
    CONF_BEEP_OUT,
    CONF_BIRTHDAY_NAMES,
    CONF_BIRTHDAY_SONG,
    CONF_CHAT_AGENT,
    CONF_CO2_ALERTS,
    CONF_COLD_BELOW,
    CONF_COMFORT,
    CONF_CO2_REMINDER,
    CONF_COLD_OUTSIDE,
    CONF_HOME_TOWN,
    CONF_IDLE,
    CONF_LEAVE_HEADS_UP,
    CONF_MIN_SLEEP,
    CONF_MORNING,
    CONF_NOTICES,
    CONF_PERSONALITY,
    CONF_REMINDERS,
    CONF_ROUTINE_MINUTES,
    CONF_SCHEDULE,
    CONF_SETTLED,
    CONF_SLEEP_GOAL,
    CONF_USUAL_BEDTIME,
    CONF_VOICE_AGENT,
    CONF_WARM_ABOVE,
    DEFAULTS,
    DOMAIN,
)

AGENT = selector.EntitySelector(selector.EntitySelectorConfig(domain="conversation"))
TEXT = selector.TextSelector()
SWITCH = selector.BooleanSelector()


def _number(low: float, high: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=low, max=high, step=step, unit_of_measurement=unit,
        mode=selector.NumberSelectorMode.BOX))


# Each field: (key, required, selector, how to store it).
Field = tuple[str, bool, Any, Callable[[Any], Any]]

SECTIONS: dict[str, list[Field]] = {
    "brain": [
        (CONF_CHAT_AGENT, True, AGENT, str),
        (CONF_PERSONALITY, True, SWITCH, bool),
        (CONF_HOME_TOWN, False, TEXT, str),
        (CONF_VOICE_AGENT, False, AGENT, str),
    ],
    "voices": [
        (CONF_ANNOUNCER_VOICE, False, TEXT, str),
        (CONF_BEEP_IN, False, TEXT, str),
        (CONF_BEEP_OUT, False, TEXT, str),
        (CONF_SCHEDULE, False, selector.EntitySelector(
            selector.EntitySelectorConfig(domain="schedule")), str),
    ],
    "warnings": [
        (CONF_CO2_ALERTS, True, selector.SelectSelector(selector.SelectSelectorConfig(
            options=["announcer", "glados", "off"], translation_key=CONF_CO2_ALERTS)), str),
        (CONF_CO2_REMINDER, True, _number(0, 240, 5, "min"), int),
        (CONF_COLD_OUTSIDE, True, _number(-20, 25, 1, "°C"), float),
    ],
    "initiative": [
        (CONF_COMFORT, True, SWITCH, bool),
        (CONF_COLD_BELOW, True, _number(5, 25, 0.5, "°C"), float),
        (CONF_WARM_ABOVE, True, _number(18, 35, 0.5, "°C"), float),
        (CONF_SETTLED, True, _number(1, 60, 1, "min"), int),
        (CONF_NOTICES, True, SWITCH, bool),
        (CONF_IDLE, True, SWITCH, bool),
    ],
    "days": [
        (CONF_REMINDERS, True, SWITCH, bool),
        (CONF_LEAVE_HEADS_UP, True, _number(0, 120, 5, "min"), int),
        (CONF_ROUTINE_MINUTES, True, _number(5, 180, 5, "min"), int),
        (CONF_ALARM_BACKUP, True, _number(1, 60, 1, "min"), int),
    ],
    "nights": [
        (CONF_MORNING, True, SWITCH, bool),
        (CONF_BIRTHDAY_SONG, False, TEXT, str),
        (CONF_BIRTHDAY_NAMES, False, TEXT, str),
        (CONF_BEDTIME, True, SWITCH, bool),
        (CONF_SLEEP_GOAL, True, _number(4, 12, 0.5, "h"), float),
        (CONF_MIN_SLEEP, True, _number(3, 10, 0.5, "h"), float),
        (CONF_USUAL_BEDTIME, False, selector.TimeSelector(), str),
        (CONF_BEDTIME_SENSOR, False, selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="timestamp")), str),
    ],
}
_STORE = {key: store for fields in SECTIONS.values() for key, _, _, store in fields}


def _marker(key: str, required: bool, current: dict[str, Any]) -> vol.Marker:
    value = current.get(key)
    if required and value not in (None, ""):
        return vol.Required(key, default=value)
    hint = {"suggested_value": value} if value not in (None, "") else None
    return (vol.Required if required else vol.Optional)(key, description=hint)


def _fields(fields: list[Field], current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({_marker(k, req, current): sel for k, req, sel, _ in fields})


def _setup_schema(current: dict[str, Any]) -> vol.Schema:
    return _fields(SECTIONS["brain"][:3], current)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        # Optional: a section left out keeps its defaults instead of failing the form.
        (vol.Required(name) if name == "brain" else vol.Optional(name, default={})): section(
            _fields(fields, current), {"collapsed": name != "brain"})
        for name, fields in SECTIONS.items()
    })


def clean_options(
    user_input: dict[str, Any], current: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Every option stored flat.

    In a section that was sent, a text field left out was cleared. A section
    that was not sent at all keeps the current values.
    """
    data = {**DEFAULTS, **(current or {})}
    for key, value in user_input.items():
        if key in SECTIONS and isinstance(value, dict):
            if value:
                for field, required, _, store in SECTIONS[key]:
                    if not required and field not in value:
                        data[field] = ""
            data.update(value)
        else:
            data[key] = value
    for key, store in _STORE.items():
        if data.get(key) is not None:
            data[key] = store(data[key])
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
        """Everything else, in sections."""
        return GladosOptionsFlow()


class GladosOptionsFlow(OptionsFlow):
    """Her settings, grouped."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """One form, five sections."""
        current = {**DEFAULTS, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(data=clean_options(user_input, current))
        return self.async_show_form(step_id="init", data_schema=_options_schema(current))
