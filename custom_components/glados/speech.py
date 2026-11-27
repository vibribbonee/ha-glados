"""Make text safe for the GLaDOS text-to-speech voice.

The voice reads every character aloud, so anything that is not a plain spoken
word has to go or be spelled out. This module has no Home Assistant imports so
it can be tested on its own.
"""

from __future__ import annotations

import re

# Spoken name. The voice mispronounces "GLaDOS"; "Glad-oss" comes out right.
SPOKEN_NAME = "Glad-oss"

_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, symbols, flags
    "\u2600-\u27bf"  # miscellaneous symbols and dingbats
    "\u2b00-\u2bff"  # arrows and stars used as emoji
    "\ufe0f\u200d"  # variation selector and zero-width joiner
    "]"
)
_QUOTES = re.compile("[\"\u201c\u201d\u201e\u00ab\u00bb]")
_MARKDOWN = re.compile(r"[*_#`~>|]")
_LIST_MARKER = re.compile(r"(?m)^\s*(?:[-+•]|\d+[.)])\s+")
_DASH = re.compile("\\s*[\u2014\u2013]\\s*")
_NEGATIVE = re.compile(r"(?<![\w.])-(?=\d)")
_SPACES = re.compile(r"\s+")

# Order matters: longer units before the shorter ones they contain.
_UNITS = (
    ("CO\u2082", "CO2"),
    ("\u00b0C", " degrees"),
    ("\u00b0", " degrees"),
    ("km/h", " kilometres per hour"),
    ("\u00b5g/m\u00b3", " micrograms per cubic metre"),
    ("\u03bcg/m\u00b3", " micrograms per cubic metre"),
    ("%", " percent"),
)
_PPM = re.compile(r"\s?ppm\b")


def clean_for_speech(text: str) -> str:
    """Return ``text`` as one line of plain spoken words."""
    if not text:
        return ""
    out = _EMOJI.sub("", text)
    out = _LIST_MARKER.sub("", out)
    out = _QUOTES.sub("", out)
    out = _MARKDOWN.sub(" ", out)
    for old, new in _UNITS:
        out = out.replace(old, new)
    out = _PPM.sub(" parts per million", out)
    out = _DASH.sub(", ", out)
    out = _NEGATIVE.sub("minus ", out)
    out = out.replace("GLaDOS", SPOKEN_NAME)
    out = _SPACES.sub(" ", out).strip()
    # Tidy what the removals can leave behind.
    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    out = re.sub(r",\s*,", ",", out)
    return out
