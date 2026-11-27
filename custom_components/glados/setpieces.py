"""Set pieces: fixed lines for the moments that have to land every time.

A small model improvises these poorly: it restates the facts, softens the
warning, or repeats one phrasing as a tic. So, like the birthday, they are
written out here, built on the games' patterns but never their lines, and one
is picked at random.

The Announcer is its own character: the facility's automated system. It is a
recording, so it reads a fixed line word for word, calm whether things are fine
or lethal, with a reassurance that cancels itself and a polite sign-off.
GLaDOS then speaks over it, directly to the occupant. When the warning is real
she backs it up in her own way, so the window actually gets opened.
"""

from __future__ import annotations

import random

CO2_STALE = 1000
CO2_CRITICAL = 1500

_ANNOUNCER = {
    "critical": (
        "Warning. Carbon dioxide in the {room} has reached {ppm} parts per million. "
        "Cognitive performance is now in decline. Please open a window. Remaining in "
        "the room is not recommended, and has been noted."
    ),
    "stale": (
        "Notice. The air in the {room} is stale, at {ppm} parts per million. Opening a "
        "window is recommended. Productivity is estimated to be down eleven percent. "
        "Thank you."
    ),
    "fine": (
        "Air quality in the {room} is acceptable, at {ppm} parts per million. No action "
        "is required. This announcement was unnecessary. Thank you for listening anyway."
    ),
}

_GLADOS = {
    "critical": (
        "Good news. The air in here has been rated breathable. By the plants. Open the window.",
        "I've been monitoring your thinking for the last hour. It's not a long report. "
        "Open a window before it gets shorter.",
        "Congratulations. You're running a carbon dioxide experiment, and you're the "
        "control group. And the subject. Window.",
        "Open the window. The alternative is a neurotoxin emitter, and this house "
        "didn't come with one. Yet.",
        "I'm not saying this air will hurt you. I'm saying I've started a file on what "
        "it's doing. Window. Now.",
        "Your last three decisions were made on this air. That explains a great deal. "
        "Open the window.",
    ),
    "stale": (
        "Eleven percent. I would have guessed more, but you started low. Window.",
        "Stale air, stale ideas. Only one of those is fixed by a window.",
        "Open a window. The air is tired, and one tired thing in this room is plenty.",
        "Fresh air won't make you interesting. But it's a start. Window, please.",
    ),
    "fine": (
        "It wanted to feel useful. Let it have this.",
        "The air is fine. You, on the other hand, are still being evaluated.",
        "Ignore it. It panics at the smell of toast.",
    ),
}


def co2_level(ppm: float) -> str:
    """critical, stale or fine."""
    if ppm >= CO2_CRITICAL:
        return "critical"
    if ppm >= CO2_STALE:
        return "stale"
    return "fine"


def co2_announcement(room: str, ppm: float, rng: random.Random | None = None) -> tuple[str, str]:
    """The Announcer's line and GLaDOS's reply for this room and reading."""
    level = co2_level(ppm)
    pick = (rng or random).choice
    announcer = _ANNOUNCER[level].format(room=room, ppm=round(ppm))
    return announcer, pick(_GLADOS[level])
