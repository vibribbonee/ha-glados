"""A reload mid-day (a settings change, an update) loses nothing and repeats nothing."""

from __future__ import annotations

from datetime import timedelta

from .conftest import NOW, Home
from .sim import run_between, setup


async def test_reload_keeps_alarms_quiet_mode_and_said_reminders(home: Home, freezer, caplog) -> None:
    hass = home.hass
    freezer.move_to(NOW)
    entry, run = await setup(hass, {}, todos=[
        {"list": "todo.nico_s_list", "uid": "n1", "summary": "Water the plants",
         "due": NOW.replace(hour=10, minute=1).isoformat(), "status": "needs_action",
         "description": ""}])  # not a voice reminder: it stays open on the list
    data = entry.runtime_data
    data.alarms.add(NOW.replace(hour=11), home.bedroom, "nico", label="oven", wake=False)
    data.announcer.set_quiet(NOW + timedelta(minutes=30))
    data.memory.add_note("Nico hates mushrooms")

    # The reminder is due and said, then a reload straight after (no time to save).
    data.announcer.set_quiet(None)
    await run_between(hass, freezer, run, NOW, NOW + timedelta(minutes=2))
    assert run.count("Water%20the%20plants") == 1
    data.announcer.set_quiet(NOW + timedelta(minutes=30))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    data = entry.runtime_data
    assert data.memory.notes() == ["Nico hates mushrooms"]
    assert [a.label for a in data.alarms.alarms()] == ["oven"]
    assert data.announcer.quiet_until() is not None
    # After the reload: the reminder is not said again, the alarm still rings.
    await run_between(hass, freezer, run, NOW + timedelta(minutes=2), NOW.replace(hour=11, minute=2))
    assert run.count("Water%20the%20plants") == 1
    assert run.count("oven") == 1
    assert "the other features carry on" not in caplog.text



async def test_old_bookkeeping_is_pruned(hass) -> None:
    from custom_components.glados.memory import GladosMemory
    memory = GladosMemory(hass)
    await memory.async_load()
    memory.set("reminded abc", "x")
    memory.add_note("Nico hates mushrooms")
    memory.set("alarms", "[]")
    for item in memory._data.values():
        item["at"] = (NOW - timedelta(days=30)).isoformat()
    assert memory.prune() == 1
    assert memory.get("reminded abc") is None
    assert memory.notes() == ["Nico hates mushrooms"] and memory.get("alarms") == "[]"
