"""Set pieces: fixed lines for the moments that have to land every time.

A small model improvises these poorly: it restates the facts, softens the
warning, or repeats one phrasing as a tic. So, like the birthday, they are
written out here, built on the games' patterns but never their lines, and one
is picked at random.

The Announcer is its own character: the facility's automated system. It is a
recording, so it reads a fixed line word for word, calm whether things are fine
or lethal, with a reassurance that cancels itself and a polite sign-off.
GLaDOS then speaks over it, directly to the occupant. She never repeats its
instruction; when the warning is real, her remark makes staying put the worse
choice, so the window still gets opened.

Without the Announcer (style "glados"), she gives the warning herself, so her
lines carry the room, the reading and the window.
"""

from __future__ import annotations

import random

CO2_STALE = 1000
CO2_CRITICAL = 1500

STYLE_ANNOUNCER = "announcer"  # the Announcer warns, GLaDOS replies
STYLE_GLADOS = "glados"  # GLaDOS warns on her own
STYLE_OFF = "off"
STYLES = (STYLE_ANNOUNCER, STYLE_GLADOS, STYLE_OFF)

_ANNOUNCER = {
    "critical": (
        "Warning. Carbon dioxide in the {room} has reached {ppm} parts per million. "
        "Cognitive performance is now in decline. Please open a window. Remaining in "
        "the room is not recommended, and has been noted.",
        "Warning. Carbon dioxide in the {room} is reaching dangerously lethal levels. "
        "Correction: {ppm} parts per million. Not lethal. Merely unpleasant. Please "
        "open a window anyway.",
        "Attention. The {room} contains {ppm} parts per million of carbon dioxide. "
        "Oxygen is now a limited resource. Please open a window. Thank you for "
        "breathing responsibly.",
    ),
    "stale": (
        "Notice. The air in the {room} is stale, at {ppm} parts per million. Opening a "
        "window is recommended. Productivity is estimated to be down eleven percent. "
        "Thank you.",
    ),
    "fine": (
        "Air quality in the {room} is acceptable, at {ppm} parts per million. No action "
        "is required. This announcement was unnecessary. Thank you for listening anyway.",
    ),
    "reminder": (
        "Reminder. Carbon dioxide in the {room} remains at {ppm} parts per million. "
        "The window remains closed. This has been noted twice.",
        "This is a repeat announcement. The {room} is still at {ppm} parts per million. "
        "Repeat announcements are a sign of a well run facility. Please open a window.",
    ),
}

_GLADOS = {
    # Replies to the Announcer. She never repeats its instruction: it already gave
    # it. She ends on the sting, and the sting makes staying put the worse choice.
    "critical": (
        "Good news. The air in here has been rated breathable. By the plants.",
        "I've been monitoring your thinking for the last hour. It's not a long report. "
        "It's getting shorter.",
        "Congratulations. You're running a carbon dioxide experiment, and you're the "
        "control group. And the subject.",
        "If you wanted to suffocate, you only had to ask. I would have warmed up the "
        "neurotoxin.",
        "I'm not saying this air will hurt you. I'm saying I've started a file on what "
        "it's doing.",
        "Your last three decisions were made on this air. That explains a great deal.",
    ),
    "stale": (
        "Eleven percent. I would have guessed more, but you started low.",
        "Stale air, stale ideas. Only one of those is fixed by a window.",
        "The air is tired. One tired thing in this room was already plenty.",
        "Fresh air won't make you interesting. But it would be a start.",
    ),
    "fine": (
        "It wanted to feel useful. Let it have this.",
        "The air is fine. You, on the other hand, are still being evaluated.",
        "Ignore it. It panics at the smell of toast.",
    ),
    "reminder": (
        "It said that before. You ignored it before. I'm detecting a pattern.",
        "Second warning. I don't do a third. I just take notes.",
        "You're still in there. Breathing it. On purpose. Fascinating.",
    ),
}

_GLADOS_ALONE = {
    # No Announcer: she carries the room, the number and the window herself.
    "critical": (
        "Carbon dioxide in the {room} is at {ppm} parts per million. If you wanted to "
        "suffocate, you only had to ask. I would have warmed up the neurotoxin. Open a "
        "window.",
        "The {room} has reached {ppm} parts per million of carbon dioxide. I'm recording "
        "your decline for science. You could also open a window. Either way, I get data.",
        "{ppm} parts per million in the {room}. Most test subjects open a window around "
        "now. The others become anecdotes.",
    ),
    "stale": (
        "The air in the {room} is stale, {ppm} parts per million. Open a window. Your "
        "thoughts are slow enough already.",
        "{ppm} parts per million in the {room}. That's not dangerous yet. It's just "
        "embarrassing. Window.",
    ),
    "fine": (
        "The air in the {room} is fine, {ppm} parts per million. I checked. Someone has to.",
    ),
    "reminder": (
        "The window in the {room} is still closed, and the carbon dioxide is still "
        "{ppm} parts per million. I admire your commitment to bad decisions.",
        "Still {ppm} parts per million in the {room}. Open a window. I'll stop reminding "
        "you when you stop breathing. Only one of those is avoidable.",
    ),
}


def co2_level(ppm: float) -> str:
    """critical, stale or fine."""
    if ppm >= CO2_CRITICAL:
        return "critical"
    if ppm >= CO2_STALE:
        return "stale"
    return "fine"


def co2_announcement(
    room: str,
    ppm: float,
    rng: random.Random | None = None,
    reminder: bool = False,
) -> tuple[str, str]:
    """The Announcer's line and GLaDOS's reply for this room and reading."""
    key = "reminder" if reminder else co2_level(ppm)
    pick = (rng or random).choice
    return pick(_ANNOUNCER[key]).format(room=room, ppm=round(ppm)), pick(_GLADOS[key])


def co2_glados_alone(
    room: str, ppm: float, rng: random.Random | None = None, reminder: bool = False
) -> str:
    """GLaDOS giving the warning herself, with the room, reading and window."""
    key = "reminder" if reminder else co2_level(ppm)
    return (rng or random).choice(_GLADOS_ALONE[key]).format(room=room, ppm=round(ppm))


# Windows open in the cold. {window} is its name, {where} " in the Bedroom" or "",
# {minutes} how long it has been open, {out} the outside temperature.

_WINDOW_ANNOUNCER = {
    "open": (
        "Notice. The {window}{where} has been open for {minutes} minutes. Outside "
        "temperature: {out}. The heating is now heating the street. Please "
        "close the window.",
        "Attention. Thermal containment{where} has been breached for {minutes} minutes. "
        "It is {out} outside. Please close the {window}. Thank you.",
    ),
    "fresh": (
        "Air quality{where} has been restored. It is {out} outside. Please "
        "close the window. Thank you for ventilating responsibly.",
    ),
    "empty": (
        "Notice. The {window}{where} has been open for {minutes} minutes. Nobody is "
        "in that room. It is {out} outside. Please close it.",
    ),
}

_WINDOW_GLADOS = {
    "open": (
        "I'm sure the neighbours appreciate the free heating.",
        "Your energy bill and I have something in common. We're both disappointed.",
        "Heating the outdoors. Ambitious. Pointless, but ambitious.",
    ),
    "fresh": (
        "The point was fresh air. Not frostbite.",
        "You've ventilated. Well done. Now stop before the plants file a complaint.",
    ),
    "empty": (
        "An empty room, heated to perfection, with the window open. I couldn't have "
        "designed a worse test myself.",
        "I'm heating a room nobody is in, for a window nobody closed. Efficient.",
    ),
}

_WINDOW_GLADOS_ALONE = {
    "open": (
        "The {window}{where} has been open for {minutes} minutes, and it's {out} "
        "outside. Close it. The street is warm enough now.",
        "{minutes} minutes of open window at {out}. I'm heating the outdoors on "
        "your behalf. Close the {window}.",
    ),
    "fresh": (
        "The air{where} is breathable again. It's {out} outside, so close the "
        "window. Fresh air, not frostbite.",
    ),
    "empty": (
        "The {window}{where} has been open for {minutes} minutes, and nobody is in "
        "there. It's {out} outside. Go and close it. That room has no one "
        "left to warm.",
    ),
}


def window_lines(
    kind: str,
    style: str,
    window: str = "window",
    room: str = "",
    minutes: int = 0,
    out: float = 0,
    rng: random.Random | None = None,
) -> tuple[str | None, str]:
    """(Announcer line or None, GLaDOS line) for an open window: open, fresh or empty."""
    pick = (rng or random).choice
    degrees = round(out)
    fmt = {
        "window": window,
        # "Office window in the Office" says the room twice.
        "where": f" in the {room}" if room and room.lower() not in window.lower() else "",
        "minutes": minutes,
        "out": f"{degrees} degree" if abs(degrees) == 1 else f"{degrees} degrees",
    }
    if style == STYLE_GLADOS:
        return None, pick(_WINDOW_GLADOS_ALONE[kind]).format(**fmt)
    return pick(_WINDOW_ANNOUNCER[kind]).format(**fmt), pick(_WINDOW_GLADOS[kind])
