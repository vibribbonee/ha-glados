"""Which speaker you actually hear.

A TV that sends its sound to a soundbar (ARC, optical, Bluetooth) ignores its own
volume. HA knows this from the TV's sound output attribute, so a volume request
for the TV goes to the speaker in the same room that is playing instead.
"""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .registry import area_of

_EXTERNAL = ("external", "arc", "optical", "bt_soundbar", "bluetooth", "headphone", "lineout")
_LIVE = ("playing", "paused", "on", "idle", "buffering")


def _can_set_volume(state: State) -> bool:
    features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0)
    return bool(features & MediaPlayerEntityFeature.VOLUME_SET)


def sends_sound_elsewhere(state: State) -> bool:
    """True when this player's sound comes out of another device."""
    output = str(state.attributes.get("sound_output") or "").lower()
    return any(word in output for word in _EXTERNAL)


def find_player(hass: HomeAssistant, name: str, area: str | None = None) -> str | None:
    """A media player by name, alias or entity id; empty name: the one playing."""
    wanted = name.strip().lower()
    reg = er.async_get(hass)
    players = hass.states.async_all("media_player")
    if wanted:
        for s in players:
            entry = reg.async_get(s.entity_id)
            aliases = {a.lower() for a in (entry.aliases if entry else ()) if isinstance(a, str)}
            if wanted in (s.entity_id, s.object_id, s.name.lower()) or wanted in aliases:
                return s.entity_id
        return None
    playing = [s for s in players if s.state == "playing" and _can_set_volume(s)]
    in_area = [s for s in playing if area and area_of(hass, s.entity_id) == area]
    return (in_area or playing)[0].entity_id if (in_area or playing) else None


def audible_player(hass: HomeAssistant, entity_id: str) -> str:
    """The player whose volume you actually hear for this one."""
    state = hass.states.get(entity_id)
    if state is None or not sends_sound_elsewhere(state):
        return entity_id
    area = area_of(hass, entity_id)
    candidates = [
        s
        for s in hass.states.async_all("media_player")
        if s.entity_id != entity_id
        and s.state in _LIVE
        and _can_set_volume(s)
        and s.attributes.get("device_class") != "tv"
        and area_of(hass, s.entity_id) == area
    ]
    candidates.sort(key=lambda s: s.state != "playing")
    return candidates[0].entity_id if candidates else entity_id
