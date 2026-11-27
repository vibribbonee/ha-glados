"""The add-on interface: how other integrations extend GLaDOS.

GLaDOS works on her own. Anything that needs another integration (train times,
a vacuum, a doorbell) is an add-on: its own integration, its own repository,
with "glados" in its manifest's dependencies. An add-on registers once, when it
is set up, and gets:

- tools: added to her own LLM API next to the built-in ones;
- prompt: a few lines added to her tool instructions;
- start: a background job (such as a check every minute), started while GLaDOS
  is loaded and stopped when either side unloads.

It reuses her parts instead of copying them: AnnounceRequest and announce()
(the room, the quiet rules, both voices, the beeps), her memory, the date
helpers, and GladosTool (validated arguments, her data).

Only what this module exports is the stable interface. Everything else in the
glados package can change between versions.

    from custom_components.glados.addon import Addon, GladosTool, async_register_addon

    async def async_setup_entry(hass, entry):
        entry.async_on_unload(async_register_addon(hass, Addon(
            domain="glados_trains", name="Trains", tools=lambda data: [SetTrain(data)],
        )))
        return True
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.util.hass_dict import HassKey

from .announce import AnnounceRequest
from .const import DOMAIN, VOICE_ANNOUNCER, VOICE_GLADOS
from .dates import days_away, parse_time, resolve_date, resolve_moment, spoken_date
from .speech import clean_for_speech

if TYPE_CHECKING:
    from . import GladosData

API_VERSION = 1

__all__ = [
    "API_VERSION",
    "Addon",
    "AnnounceRequest",
    "GladosTool",
    "VOICE_ANNOUNCER",
    "VOICE_GLADOS",
    "async_announce",
    "async_register_addon",
    "clean_for_speech",
    "days_away",
    "glados_data",
    "parse_time",
    "registered_addons",
    "resolve_date",
    "resolve_moment",
    "spoken_date",
]


@dataclass(frozen=True)
class Addon:
    """What an add-on brings to GLaDOS."""

    domain: str  # the add-on integration's own domain
    name: str
    tools: Callable[[GladosData], Iterable[llm.Tool]] = field(default=lambda data: ())
    prompt: Callable[[HomeAssistant], str] | None = None
    start: Callable[[HomeAssistant, GladosData], CALLBACK_TYPE] | None = None


@dataclass
class _Registered:
    addon: Addon
    stop: CALLBACK_TYPE | None = None


_ADDONS: HassKey[dict[str, _Registered]] = HassKey(f"{DOMAIN}_addons")


def _registry(hass: HomeAssistant) -> dict[str, _Registered]:
    return hass.data.setdefault(_ADDONS, {})


@callback
def glados_data(hass: HomeAssistant) -> GladosData | None:
    """GLaDOS's running data, or None while she is not loaded."""
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data
    return None


@callback
def registered_addons(hass: HomeAssistant) -> list[Addon]:
    """Every add-on registered right now."""
    return [r.addon for r in _registry(hass).values()]


@callback
def _start(hass: HomeAssistant, reg: _Registered, data: GladosData) -> None:
    if reg.addon.start is not None and reg.stop is None:
        reg.stop = reg.addon.start(hass, data)


@callback
def _stop(reg: _Registered) -> None:
    if reg.stop is not None:
        reg.stop()
        reg.stop = None


@callback
def async_register_addon(hass: HomeAssistant, addon: Addon) -> CALLBACK_TYPE:
    """Register an add-on. Call the returned function to remove it again."""
    registry = _registry(hass)
    if addon.domain in registry:
        _stop(registry[addon.domain])
    reg = registry[addon.domain] = _Registered(addon)
    if (data := glados_data(hass)) is not None:
        _start(hass, reg, data)

    @callback
    def unregister() -> None:
        if registry.get(addon.domain) is reg:
            _stop(reg)
            registry.pop(addon.domain)

    return unregister


@callback
def async_start_addons(hass: HomeAssistant, data: GladosData) -> CALLBACK_TYPE:
    """GLaDOS loaded: start the add-ons' jobs. Returns the stop for her unload."""
    for reg in _registry(hass).values():
        _start(hass, reg, data)

    @callback
    def stop_all() -> None:
        for reg in _registry(hass).values():
            _stop(reg)

    return stop_all


def addon_tools(hass: HomeAssistant, data: GladosData) -> list[llm.Tool]:
    """The tools of every add-on, each marked with the add-on's own domain."""
    tools: list[llm.Tool] = []
    for addon in registered_addons(hass):
        for tool in addon.tools(data):
            tool.integration = addon.domain
            tools.append(tool)
    return tools


def addon_prompts(hass: HomeAssistant) -> str:
    """The add-ons' extra instructions, one paragraph each."""
    parts = [addon.prompt(hass) for addon in registered_addons(hass) if addon.prompt]
    return " ".join(p.strip() for p in parts if p and p.strip())


async def async_announce(
    hass: HomeAssistant, request: AnnounceRequest, context: Context | None = None
) -> dict[str, Any]:
    """Announce through GLaDOS: her room choice, quiet rules, voices and beeps."""
    if (data := glados_data(hass)) is None:
        return {"spoken": False, "reason": "GLaDOS is not loaded", "speech": "", "after": ""}
    return await data.announcer.async_announce(request, context)


def __getattr__(name: str) -> Any:
    # GladosTool lives in llm_api, which imports this module's neighbours; load it lazily.
    if name == "GladosTool":
        from .llm_api import GladosTool

        return GladosTool
    raise AttributeError(name)
