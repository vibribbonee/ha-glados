"""One heartbeat for everything she does on her own.

Air and windows, alarms, reminders, leave times, mornings and bedtime each have
an async_tick. The heartbeat runs them in turn every half minute. A feature that
fails is logged and skipped for that beat; the others carry on, and the failing
one is tried again on the next beat. The last error per feature is kept for the
diagnostics.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

BEAT = timedelta(seconds=30)

Tick = Callable[[datetime | None], Awaitable[Any]]


class Heartbeat:
    """Runs every feature's tick, each on its own."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.features: dict[str, Tick] = {}
        self.errors: dict[str, str] = {}
        self._running = False

    def add(self, name: str, tick: Tick) -> None:
        self.features[name] = tick

    @callback
    def start(self) -> CALLBACK_TYPE:
        return async_track_time_interval(self.hass, self.async_beat, BEAT)

    async def async_beat(self, now: datetime | None = None) -> None:
        if self._running:
            return  # the last beat is still busy (a slow voice agent): skip, don't pile up
        self._running = True
        try:
            for name, tick in self.features.items():
                try:
                    await tick(now)
                    self.errors.pop(name, None)
                except Exception as err:  # noqa: BLE001 - one feature must not stop the rest
                    if self.errors.get(name) != repr(err):
                        _LOGGER.exception("GLaDOS %s failed; the other features carry on", name)
                    self.errors[name] = repr(err)
        finally:
            self._running = False

    def diagnostics(self) -> dict[str, Any]:
        return {"features": list(self.features), "errors": dict(self.errors),
                "checked": dt_util.now().isoformat()}
