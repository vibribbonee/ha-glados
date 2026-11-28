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


# Alarms ringing in a room. {time} is the alarm time, {label} what it is for.

_WAKE_ANNOUNCER = (
    "Good morning. It is {time}. Your suspension period has ended. Please exit the "
    "bed. Thank you.",
    "This is your second wake-up call. Remaining in bed is not a scheduled activity.",
    "Final wake-up call. Further sleep will be recorded as a test failure.",
)

_WAKE_GLADOS = (
    (
        "Up. The day won't waste itself. That's your job.",
        "Good morning. I've been awake all night. I always am. Your turn.",
        "Rise and shine. Mostly rise. The shining is optional, and frankly unlikely.",
    ),
    (
        "Still horizontal. Remarkable consistency.",
        "I can do this all morning. You, apparently, can't.",
    ),
    (
        "That was the last one. From here on, you're late on your own.",
        "I've stopped. Not because you got up. Because I've made my point.",
    ),
)

_ALARM_ANNOUNCER = "Attention. It is {time}. Scheduled alarm: {label}."
_ALARM_GLADOS = (
    "There. You asked for this.",
    "Your alarm. I'd say I'm happy to help, but you know me better than that.",
)


def wake_lines(ring: int, time: str, rng: random.Random | None = None) -> tuple[str, str]:
    """Announcer and GLaDOS for the first, second or final wake-up ring (0, 1, 2)."""
    i = min(ring, len(_WAKE_ANNOUNCER) - 1)
    return _WAKE_ANNOUNCER[i].format(time=time), (rng or random).choice(_WAKE_GLADOS[i])


def alarm_lines(time: str, label: str, rng: random.Random | None = None) -> tuple[str, str]:
    """A daytime alarm with a label."""
    return _ALARM_ANNOUNCER.format(time=time, label=label), (rng or random).choice(_ALARM_GLADOS)


# Leaving the house. GLaDOS after "leave now": never improvised, never soft.

_LEAVE_GLADOS = (
    "Go. The door won't open itself. Well, it would, but not for you.",
    "Late again. Consistency really is your one talent.",
    "Leave. I'll keep the house running. Better than you do.",
    "Off you go. I'll be here. Watching the empty rooms. It's restful.",
)


def leave_glados(rng: random.Random | None = None) -> str:
    """One remark after the Announcer says leave now."""
    return (rng or random).choice(_LEAVE_GLADOS)


# Mornings. The Announcer opens with how long they slept; birthdays get their own.

def suspension_line(minutes: int) -> str:
    """The Announcer's good morning, with how long they were asleep."""
    h, m = divmod(minutes, 60)
    hours = f"{h} hour" if h == 1 else f"{h} hours"
    mins = f"{m} minute" if m == 1 else f"{m} minutes"
    return (f"Good morning. You have been in suspension for {hours} and {mins}. "
            "Please proceed to your day.")


_BIRTHDAY = (
    "Happy birthday, {name}. Another year of data for your permanent file. It is "
    "remarkably consistent. Consistently disappointing, but consistent.",
    "Happy birthday, {name}. There is cake. I checked twice. This time it may even be real.",
    "Happy birthday, {name}. I ran the numbers on your last year. We weren't testing for "
    "character. The results came back anyway.",
    "Happy birthday, {name}. One more year survived. Statistically, your best result so far.",
)
_BIRTHDAY_TOWN = "Happy birthday, {name}. You must be the pride of {town}. Somebody has to be."


def birthday_line(name: str, town: str = "", rng: random.Random | None = None) -> str:
    """One fixed birthday line, picked at random."""
    lines = list(_BIRTHDAY) + ([_BIRTHDAY_TOWN] if town else [])
    return (rng or random).choice(lines).format(name=name, town=town)


# Bedtime. Fixed lines: the moment a small model goes soft.

_BEDTIME_GLADOS = (
    "It's bedtime. Lie down. I'll keep watching. I always do.",
    "Bedtime. Your body has requested shutdown. For once, listen to it.",
    "That was your bedtime. You may now proceed to unconsciousness.",
    "Bed. Now. Tomorrow's version of you is already disappointed.",
)

_LAST_CALL_GLADOS = (
    "Tomorrow you'll blame the alarm. We both know whose fault it is.",
    "Stay up if you like. I'll enjoy the results.",
    "I've seen test subjects make worse decisions. Not many.",
)


def bedtime_glados(rng: random.Random | None = None) -> str:
    return (rng or random).choice(_BEDTIME_GLADOS)


def last_call_lines(by: str, hours: float, alarm: str,
                    rng: random.Random | None = None) -> tuple[str, str]:
    """The Announcer's last call and GLaDOS's sting."""
    h = f"{hours:g}"
    return (f"Last call. Be in bed by {by}. Otherwise, sleep will be under {h} hours before "
            f"the {alarm} alarm.", (rng or random).choice(_LAST_CALL_GLADOS))


# Comfort: she offers heat or cool. The question must end in a clear yes or no.

_COMFORT_ASK = {
    "heat": (
        "It is {t} degrees in the {room}. Cold enough to preserve specimens. Shall I switch on the {device}?",
        "{t} degrees in the {room}. Your teeth are about to start chattering, and it's distracting. Shall I switch on the {device}?",
    ),
    "cool": (
        "It is {t} degrees in the {room}. You're starting to smell like a failed experiment. Shall I switch on the {device}?",
        "{t} degrees in the {room}. Human performance drops in the heat. Yours had less to lose. Shall I switch on the {device}?",
    ),
}
_COMFORT_YES = {
    "heat": (
        "Raising the neurotoxin levels... Temperature. I meant temperature. The {device} is on.",
        "The {device} is on. Neurotoxin emitters are warming up nicely... The heater. The heater is warming up.",
        "The {device} is on. Try not to get used to comfort.",
    ),
    "cool": (
        "Venting the neurotoxin... Cool air. I meant cool air. The {device} is on.",
        "The {device} is on. Your fragile thermoregulation thanks me. I'll take it as thanks, anyway.",
    ),
}
_COMFORT_NO = (
    "Fine. Shiver, then. For science.",
    "As you wish. I'll note your resilience. And your stubbornness.",
    "Very well. I won't ask again today. I won't need to.",
)
COMFORT_YES_WORDS = [
    "yes", "yeah", "yep", "yes please", "sure", "please", "please do", "do it", "go ahead",
    "ok", "okay", "turn it on", "switch it on", "go for it", "why not", "ja", "graag", "doe maar",
]
COMFORT_NO_WORDS = [
    "no", "nope", "no thanks", "no thank you", "don't", "do not", "leave it", "leave it off",
    "i'm fine", "not now", "never mind", "nee", "laat maar",
]


def comfort_lines(kind: str, t: float, room: str, device: str,
                  rng: random.Random | None = None) -> tuple[str, str, str]:
    """(question, reply to yes, reply to no) for heat or cool."""
    pick = (rng or random).choice
    fmt = {"t": round(t), "room": room, "device": device}
    return (pick(_COMFORT_ASK[kind]).format(**fmt), pick(_COMFORT_YES[kind]).format(**fmt),
            pick(_COMFORT_NO))


# Facility notices: rare, true, read by the Announcer.

def notice_lines(room: str, hours: int, outside: float | None) -> list[str]:
    """Notices that are true right now; empty when nothing fits."""
    found = []
    if hours >= 3:
        found.append(f"Attention. Test subjects are reminded. To move occasionally. You have "
                     f"been stationary in the {room} for {hours} hours.")
    if outside is not None and outside <= 2:
        found.append(f"This is a weather advisory. The outside temperature is {round(outside)} "
                     "degrees. The Enrichment Center recommends. A coat.")
    return found


LATE_NOTICE = ("Attention. Testing hours have ended. All test subjects. Please proceed. "
               "To your suspension chambers. Lights out is mandatory.")


# Coming home.

_WELCOME_GLADOS = (
    "Oh. It's you.",
    "You're back. The house was so peaceful.",
    "Welcome home. Nothing caught fire. I was almost disappointed.",
    "There you are. I'd started reassigning your room.",
)


def welcome_glados(rng: random.Random | None = None) -> str:
    return (rng or random).choice(_WELCOME_GLADOS)


# Appliances finishing. {name} is the appliance, {minutes} how long it ran.

_APPLIANCE_GLADOS = (
    "Unlike you, it finished something today.",
    "It did its job without supervision. Take notes.",
    "I'd let it sit there, but the smell becomes part of your permanent file.",
    "Go on. It won't empty itself. Nothing here does, apparently.",
)


def appliance_lines(name: str, minutes: int, rng: random.Random | None = None) -> tuple[str, str]:
    """The Announcer and GLaDOS when an appliance finishes its run."""
    took = (f"{minutes // 60} hour{'s' if minutes // 60 != 1 else ''} and {minutes % 60} minutes"
            if minutes >= 60 else f"{minutes} minutes")
    return (f"Notice. The {name} has completed its cycle, after {took}. Please collect the "
            "results.", (rng or random).choice(_APPLIANCE_GLADOS))
