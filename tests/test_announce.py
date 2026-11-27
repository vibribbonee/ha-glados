"""The polite announcer."""

from __future__ import annotations

import re

from unittest.mock import AsyncMock, patch

from custom_components.glados.announce import (
    AnnounceRequest,
    Announcer,
    announcer_media_id,
)

from pytest_homeassistant_custom_component.common import async_mock_service

from .conftest import Home


FULL = {
    "chat_agent": "conversation.chat",
    "voice_agent": "conversation.voice",
    "announcer_voice": "tts.piper_2:announcer",
    "beep_in": "media-source://media_source/local/beep-in.mp3",
    "beep_out": "media-source://media_source/local/beep-out.mp3",
    "speaking_schedule": "schedule.glados_may_speak_up",
}


def _announcer(home: Home, options: dict | None = None) -> tuple[Announcer, list]:
    calls = async_mock_service(home.hass, "assist_satellite", "announce")
    return Announcer(home.hass, FULL if options is None else options), calls


async def test_media_id_for_the_announcer_voice() -> None:
    assert announcer_media_id("tts.piper_2:announcer", "Departure time. Leave now.") == (
        "media-source://tts/tts.piper_2?message=Departure%20time.%20Leave%20now."
        "&language=en_US&voice=announcer"
    )


async def test_announcer_reads_facts_with_beeps(home: Home) -> None:
    announcer, calls = _announcer(home)
    result = await announcer.async_announce(
        AnnounceRequest(facts="Departure in fifteen minutes.", voice="announcer")
    )
    assert result == {"spoken": True, "reason": "", "speech": "Departure in fifteen minutes.",
                      "after": "", "area": home.bedroom}
    first, last = calls[0].data, calls[-1].data
    assert first["entity_id"] == "assist_satellite.puck_3"
    assert first["media_id"].startswith("media-source://tts/tts.piper_2?message=Departure")
    assert first["preannounce"] is True
    assert first["preannounce_media_id"] == FULL["beep_in"]
    assert last == {"entity_id": "assist_satellite.puck_3",
                    "media_id": FULL["beep_out"], "preannounce": False}


async def test_own_chime_gets_no_beeps(home: Home) -> None:
    home.entity("assist_satellite.puck_3", "idle", area=home.bedroom,
                labels={"glados_own_chime"}, supported_features=3)
    announcer, calls = _announcer(home)
    await announcer.async_announce(AnnounceRequest(facts="Hello.", voice="announcer"))
    assert len(calls) == 1
    assert calls[0].data["preannounce"] is False


async def test_glados_voice_rewrites_and_chimes_in(home: Home) -> None:
    announcer, calls = _announcer(home)
    with patch(
        "custom_components.glados.announce.async_say",
        AsyncMock(side_effect=["Oh. You're here.", "How thrilling."]),
    ) as say:
        result = await announcer.async_announce(AnnounceRequest(facts="Nico is home."))
        assert result["speech"] == "Oh. You're here."
        assert "The person in the room is nico." in say.call_args.kwargs["task"]
        await announcer.async_announce(
            AnnounceRequest(facts="Warning.", voice="announcer", glados_after="Agree.")
        )
    spoken = [c.data.get("message") for c in calls if c.data.get("message")]
    assert spoken == ["Oh. You're here.", "How thrilling."]


async def test_quiet_rules(home: Home) -> None:
    hass = home.hass
    announcer, calls = _announcer(home)

    hass.states.async_set("schedule.glados_may_speak_up", "off")
    result = await announcer.async_announce(AnnounceRequest(facts="x", voice="announcer"))
    assert result["reason"] == "outside speaking hours"
    result = await announcer.async_announce(
        AnnounceRequest(facts="x", voice="announcer", ignore_schedule=True)
    )
    assert result["spoken"]

    # A dark bedroom stays quiet even when the schedule is ignored.
    hass.states.async_set("light.bedroom_main", "off")
    result = await announcer.async_announce(
        AnnounceRequest(facts="x", voice="announcer", ignore_schedule=True)
    )
    assert result == {"spoken": False, "reason": "the bedroom is dark, people may be asleep",
                      "speech": "", "after": "", "area": home.bedroom}


async def test_no_free_satellite(home: Home) -> None:
    hass = home.hass
    hass.states.async_set("assist_satellite.puck_3", "responding")
    hass.states.async_set("assist_satellite.office_puck", "listening")
    announcer, calls = _announcer(home)
    result = await announcer.async_announce(AnnounceRequest(facts="x", voice="announcer"))
    assert result["reason"] == "no free voice satellite"
    assert calls == []


async def test_uses_another_room_only_when_allowed(home: Home) -> None:
    home.hass.states.async_set("assist_satellite.puck_3", "responding")
    announcer, calls = _announcer(home)
    result = await announcer.async_announce(
        AnnounceRequest(facts="x", voice="announcer", anywhere=False)
    )
    assert result["reason"] == "no free voice satellite"
    result = await announcer.async_announce(AnnounceRequest(facts="x", voice="announcer"))
    assert result["spoken"]
    assert calls[0].data["entity_id"] == "assist_satellite.office_puck"


async def test_bare_install_uses_her_own_voice_and_no_beeps(home: Home) -> None:
    # No Announcer voice, no beeps, no schedule: the satellite reads the notice.
    home.hass.states.async_set("schedule.glados_may_speak_up", "off")
    announcer, calls = _announcer(home, {})
    result = await announcer.async_announce(
        AnnounceRequest(facts="Departure in fifteen minutes.", voice="announcer")
    )
    assert result["spoken"]
    assert [c.data for c in calls] == [
        {"entity_id": "assist_satellite.puck_3",
         "message": "Departure in fifteen minutes.", "preannounce": False}
    ]


async def test_the_test_announcement(home: Home) -> None:
    # A fixed set piece: the Announcer, then GLaDOS, on the chosen satellite.
    announcer, calls = _announcer(home)
    result = await announcer.async_test("assist_satellite.puck_3", co2=1500)
    assert result["spoken"]
    assert "1500%20parts%20per%20million" in calls[0].data["media_id"]
    assert "Please%20open%20a%20window" in calls[0].data["media_id"]
    assert calls[1].data["message"] == result["after"] and result["after"]
    assert {c.data["entity_id"] for c in calls} == {"assist_satellite.puck_3"}
    # Without a pretend reading, the bedroom's real 1240 is stale air.
    announcer, calls = _announcer(home)
    await announcer.async_test("assist_satellite.puck_3")
    assert "stale%2C%20at%201240" in calls[0].data["media_id"]


def test_glados_backs_up_a_real_warning() -> None:
    from custom_components.glados.setpieces import _GLADOS, co2_announcement, co2_level
    assert [co2_level(x) for x in (700, 1200, 1500)] == ["fine", "stale", "critical"]
    # When the warning is real, she never talks them out of it, and she leaves
    # the instruction to the Announcer.
    for level in ("critical", "stale"):
        for line in _GLADOS[level]:
            assert not re.search(r"ignore|nothing to worry|you're fine|open the", line.lower()), line
    announcer, _ = co2_announcement("Bedroom", 1499.6)
    assert "1500 parts per million" in announcer
