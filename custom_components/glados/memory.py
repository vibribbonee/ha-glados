"""What GLaDOS remembers: one value and the time it was stored, per key.

Replaces the to-do list the scripts use as memory. Keys look like
"air bedroom", "comfort bedroom" or "greeted person.nico".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

STORAGE_VERSION = 1
SAVE_DELAY = 5
NOTE_PREFIX = "note "
PRUNE_AFTER = timedelta(days=14)
# Bookkeeping that only matters for a while: what was said, when, per item.
TRANSIENT = ("reminded ", "heads_up ", "leave ", "bedtime ", "window ", "greeted ",
             "asleep ", "docked ", "presence ", "comfort ", "air ")


class GladosMemory:
    """A small persistent key-value memory."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.memory"
        )
        self._data: dict[str, dict[str, str]] = {}

    async def async_load(self) -> None:
        """Read the memory from storage, dropping old bookkeeping."""
        self._data = (await self._store.async_load()) or {}
        self.prune()

    def prune(self, older_than: timedelta = PRUNE_AFTER) -> int:
        """Forget old "already done" notes; never the permanent file or alarms."""
        cutoff = dt_util.now() - older_than
        old = [
            key for key, item in self._data.items()
            if key.startswith(TRANSIENT) and (at := dt_util.parse_datetime(item.get("at", "")))
            and at < cutoff
        ]
        for key in old:
            self._data.pop(key)
        if old:
            self._store.async_delay_save(lambda: self._data, SAVE_DELAY)
        return len(old)

    async def async_flush(self) -> None:
        """Write now: a reload must not lose the last seconds (an alarm just set)."""
        await self._store.async_save(self._data)

    def get(self, key: str) -> str | None:
        """The stored value, or None."""
        item = self._data.get(key)
        return item["value"] if item else None

    def stored_at(self, key: str) -> datetime | None:
        """When the value was stored, or None."""
        item = self._data.get(key)
        return dt_util.parse_datetime(item["at"]) if item else None

    def age(self, key: str) -> timedelta | None:
        """How long ago the value was stored, or None."""
        at = self.stored_at(key)
        return dt_util.now() - at if at else None

    def stored_today(self, key: str) -> bool:
        """True when the value was stored today (local time)."""
        at = self.stored_at(key)
        return at is not None and dt_util.as_local(at).date() == dt_util.now().date()

    def set(self, key: str, value: str) -> None:
        """Store a value now; written to disk a few seconds later."""
        self._data[key] = {"value": value, "at": dt_util.now().isoformat()}
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY)

    def forget(self, key: str) -> None:
        """Remove a key."""
        if self._data.pop(key, None) is not None:
            self._store.async_delay_save(lambda: self._data, SAVE_DELAY)

    # The permanent file: short facts about people, kept as "note <time>" keys.

    def add_note(self, note: str) -> None:
        """Write one fact into the permanent file."""
        self.set(f"{NOTE_PREFIX}{dt_util.now().isoformat()}", note)

    def notes(self) -> list[str]:
        """Every fact in the permanent file, newest first."""
        keys = sorted((k for k in self._data if k.startswith(NOTE_PREFIX)), reverse=True)
        return [self._data[k]["value"] for k in keys]

    def as_dict(self) -> dict[str, dict[str, str]]:
        """Everything, for diagnostics."""
        return dict(self._data)
