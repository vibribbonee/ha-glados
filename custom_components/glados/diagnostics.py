"""Diagnostics: what she is set to, what she did, and what went wrong."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .addon import registered_addons


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Settings, add-ons, the heartbeat, recent announcements, alarms and held reminders."""
    run = entry.runtime_data
    memory = run.memory
    def _json(key: str) -> Any:
        raw = memory.get(key)
        return json.loads(raw) if raw else []
    return {
        "options": dict(entry.options),
        "addons": [a.domain for a in registered_addons(hass)],
        "heartbeat": run.heartbeat.diagnostics() if run.heartbeat else None,
        "announcements": list(run.announcer.history),
        "alarms": _json("alarms"),
        "held_reminders": _json("held reminders"),
        "memory_keys": len(memory.as_dict()),
        "permanent_file_notes": len(memory.notes()),
    }
