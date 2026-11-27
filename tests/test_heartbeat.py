"""One heartbeat: a failing feature is logged, the others carry on."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant

from custom_components.glados.heartbeat import Heartbeat


async def test_one_failure_does_not_stop_the_rest(hass: HomeAssistant, caplog) -> None:
    ran: list[str] = []

    async def ok(now) -> None:
        ran.append("ok")

    async def broken(now) -> None:
        raise ValueError("calendar went away")

    heart = Heartbeat(hass)
    heart.add("broken", broken)
    heart.add("reminders", ok)
    await heart.async_beat()
    await heart.async_beat()
    assert ran == ["ok", "ok"]
    assert "calendar went away" in heart.errors["broken"]
    assert caplog.text.count("GLaDOS broken failed") == 1  # logged once, not every beat


async def test_a_slow_beat_is_not_piled_up(hass: HomeAssistant) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def slow(now) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    heart = Heartbeat(hass)
    heart.add("slow", slow)
    first = asyncio.create_task(heart.async_beat())
    await started.wait()
    await heart.async_beat()  # skipped: the first is still busy
    release.set()
    await first
    assert calls == 1
