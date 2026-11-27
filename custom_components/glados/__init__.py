"""GLaDOS: a sarcastic, genuinely helpful home assistant.

Phase 1 of docs/PLAN.md: the core, as services. Nothing runs on its own yet;
the existing scripts can call these instead of their own Jinja:

- glados.clean_text: make text safe for the text-to-speech voice
- glados.say: plain facts in her voice, cleaned
- glados.room_context: everything about one room (same fields as the script)
- glados.announce: the polite announcer, GLaDOS or the facility Announcer
- glados.who: work out which person is meant, with their own settings
- glados.remember / glados.recall: her memory, in HA's own storage

It also adds the GLaDOS conversation agent, which cleans every chat reply, and
her own LLM API with tools for reminders, leave times, the calendar and her
permanent file (see llm_api.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import llm

from .addon import async_start_addons
from .air import AirWatch
from .alarms import AlarmClock
from .departures import Departures
from .reminders import Reminders
from .announce import AnnounceRequest, Announcer
from .briefing import async_briefing, async_facts
from .const import (
    ATTR_ANYWHERE,
    ATTR_AREA,
    ATTR_CO2,
    ATTR_MORNING,
    ATTR_PLAIN,
    ATTR_REMINDER,
    ATTR_STYLE,
    ATTR_FACTS,
    ATTR_GLADOS_AFTER,
    ATTR_IGNORE_SCHEDULE,
    ATTR_KEY,
    ATTR_PERSON,
    ATTR_REQUEST,
    ATTR_SATELLITE,
    ATTR_TASK,
    ATTR_TEXT,
    ATTR_VALUE,
    ATTR_VOICE,
    CONF_ROUTINE_MINUTES,
    CONF_SCHEDULE,
    DEFAULTS,
    DOMAIN,
    SERVICE_ANNOUNCE,
    SERVICE_BRIEFING,
    SERVICE_CLEAN_TEXT,
    SERVICE_RECALL,
    SERVICE_REMEMBER,
    SERVICE_ROOM_CONTEXT,
    SERVICE_SAY,
    SERVICE_TEST_ANNOUNCEMENT,
    SERVICE_WHO,
    VOICE_ANNOUNCER,
    VOICE_GLADOS,
)
from .llm_api import GladosAPI
from .memory import GladosMemory
from .people import (
    has_leave_helper,
    leave_helper,
    leave_time,
    own_list,
    person_area,
    phones,
    resolve_person,
    routine_minutes,
)
from .rooms import describe
from .setpieces import STYLE_ANNOUNCER, STYLE_GLADOS
from .speech import clean_for_speech
from .voice import async_say

PLATFORMS = [Platform.BUTTON, Platform.CONVERSATION]

SERVICES = (
    SERVICE_CLEAN_TEXT,
    SERVICE_SAY,
    SERVICE_ROOM_CONTEXT,
    SERVICE_ANNOUNCE,
    SERVICE_WHO,
    SERVICE_REMEMBER,
    SERVICE_RECALL,
    SERVICE_TEST_ANNOUNCEMENT,
    SERVICE_BRIEFING,
)

CLEAN_TEXT_SCHEMA = vol.Schema({vol.Required(ATTR_TEXT): cv.string})
SAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FACTS): cv.string,
        vol.Optional(ATTR_REQUEST, default=""): cv.string,
        vol.Optional(ATTR_TASK, default=""): cv.string,
    }
)
ROOM_SCHEMA = vol.Schema({vol.Optional(ATTR_AREA, default=""): cv.string})
ANNOUNCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FACTS): cv.string,
        vol.Optional(ATTR_TASK, default=""): cv.string,
        vol.Optional(ATTR_AREA, default=""): cv.string,
        vol.Optional(ATTR_IGNORE_SCHEDULE, default=False): cv.boolean,
        vol.Optional(ATTR_ANYWHERE, default=True): cv.boolean,
        vol.Optional(ATTR_VOICE, default=VOICE_GLADOS): vol.In(
            [VOICE_GLADOS, VOICE_ANNOUNCER]
        ),
        vol.Optional(ATTR_GLADOS_AFTER, default=""): cv.string,
        vol.Optional(ATTR_SATELLITE): cv.entity_id,
    }
)
BRIEFING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_MORNING, default=False): cv.boolean,
        vol.Optional(ATTR_AREA, default=""): cv.string,
        vol.Optional(ATTR_PLAIN, default=False): cv.boolean,
    }
)
TEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_SATELLITE): cv.entity_id,
        vol.Optional(ATTR_CO2): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
        vol.Optional(ATTR_STYLE, default=STYLE_ANNOUNCER): vol.In([STYLE_ANNOUNCER, STYLE_GLADOS]),
        vol.Optional(ATTR_REMINDER, default=False): cv.boolean,
    }
)
WHO_SCHEMA = vol.Schema({vol.Optional(ATTR_PERSON, default=""): cv.string})
REMEMBER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_KEY): cv.string, vol.Required(ATTR_VALUE): cv.string}
)
RECALL_SCHEMA = vol.Schema({vol.Required(ATTR_KEY): cv.string})


@dataclass
class GladosData:
    """What the entry keeps while it runs."""

    memory: GladosMemory
    announcer: Announcer
    options: dict[str, Any]
    alarms: AlarmClock | None = None


type GladosConfigEntry = ConfigEntry[GladosData]


def _options(entry: ConfigEntry) -> dict[str, Any]:
    return {**DEFAULTS, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: GladosConfigEntry) -> bool:
    """Set up GLaDOS from a config entry."""
    memory = GladosMemory(hass)
    await memory.async_load()
    options = _options(entry)
    entry.runtime_data = GladosData(memory, Announcer(hass, options), options)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(llm.async_register_api(hass, GladosAPI(hass, entry.runtime_data)))
    entry.async_on_unload(AirWatch(hass, entry.runtime_data).start())
    entry.runtime_data.alarms = AlarmClock(hass, entry.runtime_data)
    entry.async_on_unload(entry.runtime_data.alarms.start())
    entry.async_on_unload(Reminders(hass, entry.runtime_data).start())
    entry.async_on_unload(Departures(hass, entry.runtime_data).start())
    entry.async_on_unload(async_start_addons(hass, entry.runtime_data))

    def data() -> GladosData:
        return entry.runtime_data

    async def _clean_text(call: ServiceCall) -> ServiceResponse:
        return {ATTR_TEXT: clean_for_speech(call.data[ATTR_TEXT])}

    async def _say(call: ServiceCall) -> ServiceResponse:
        speech = await async_say(
            hass,
            data().options,
            call.data[ATTR_FACTS],
            call.data[ATTR_REQUEST],
            call.data[ATTR_TASK],
            context=call.context,
        )
        return {"speech": speech}

    async def _room_context(call: ServiceCall) -> ServiceResponse:
        ctx = describe(hass, call.data[ATTR_AREA] or None, str(data().options[CONF_SCHEDULE] or "") or None)
        return ctx.as_dict()

    async def _announce(call: ServiceCall) -> ServiceResponse:
        req = AnnounceRequest(
            facts=call.data[ATTR_FACTS],
            task=call.data[ATTR_TASK],
            area=call.data[ATTR_AREA] or None,
            ignore_schedule=call.data[ATTR_IGNORE_SCHEDULE],
            anywhere=call.data[ATTR_ANYWHERE],
            voice=call.data[ATTR_VOICE],
            glados_after=call.data[ATTR_GLADOS_AFTER],
            satellite=call.data.get(ATTR_SATELLITE),
        )
        return await data().announcer.async_announce(req, call.context)

    async def _briefing(call: ServiceCall) -> ServiceResponse:
        area = call.data[ATTR_AREA] or None
        if call.data[ATTR_PLAIN]:
            return {"facts": await async_facts(hass, data().options, call.data[ATTR_MORNING], area)}
        return await async_briefing(
            hass, data().options, call.data[ATTR_MORNING], area, call.context
        )

    async def _test(call: ServiceCall) -> ServiceResponse:
        return await data().announcer.async_test(
            call.data.get(ATTR_SATELLITE),
            call.context,
            call.data.get(ATTR_CO2),
            call.data[ATTR_STYLE],
            call.data[ATTR_REMINDER],
        )

    async def _who(call: ServiceCall) -> ServiceResponse:
        person = resolve_person(hass, call.data[ATTR_PERSON], call.context.user_id)
        if person is None:
            return {"found": False}
        leave = leave_time(hass, person)
        return {
            "found": True,
            "person": person.entity_id,
            "name": person.name,
            "home": person.home,
            "area": person_area(hass, person) or "",
            "phones": phones(hass, person),
            "leave_helper": leave_helper(person) if has_leave_helper(hass, person) else "",
            "leave": leave.isoformat() if leave else "",
            "routine_minutes": routine_minutes(
                hass, person, int(data().options[CONF_ROUTINE_MINUTES])
            ),
            "list": own_list(hass, person),
        }

    async def _remember(call: ServiceCall) -> None:
        data().memory.set(call.data[ATTR_KEY], call.data[ATTR_VALUE])

    async def _recall(call: ServiceCall) -> ServiceResponse:
        key = call.data[ATTR_KEY]
        at = data().memory.stored_at(key)
        return {
            "key": key,
            "value": data().memory.get(key) or "",
            "stored_at": at.isoformat() if at else "",
            "today": data().memory.stored_today(key),
        }

    register = hass.services.async_register
    register(DOMAIN, SERVICE_CLEAN_TEXT, _clean_text, CLEAN_TEXT_SCHEMA, SupportsResponse.ONLY)
    register(DOMAIN, SERVICE_SAY, _say, SAY_SCHEMA, SupportsResponse.ONLY)
    register(DOMAIN, SERVICE_ROOM_CONTEXT, _room_context, ROOM_SCHEMA, SupportsResponse.ONLY)
    register(DOMAIN, SERVICE_ANNOUNCE, _announce, ANNOUNCE_SCHEMA, SupportsResponse.OPTIONAL)
    register(DOMAIN, SERVICE_BRIEFING, _briefing, BRIEFING_SCHEMA, SupportsResponse.ONLY)
    register(DOMAIN, SERVICE_TEST_ANNOUNCEMENT, _test, TEST_SCHEMA, SupportsResponse.OPTIONAL)
    register(DOMAIN, SERVICE_WHO, _who, WHO_SCHEMA, SupportsResponse.ONLY)
    register(DOMAIN, SERVICE_REMEMBER, _remember, REMEMBER_SCHEMA)
    register(DOMAIN, SERVICE_RECALL, _recall, RECALL_SCHEMA, SupportsResponse.ONLY)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply new options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GladosConfigEntry) -> bool:
    """Unload the config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    for service in SERVICES:
        hass.services.async_remove(DOMAIN, service)
    return True
