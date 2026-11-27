"""Tests for the text-to-speech cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Load speech.py directly so these tests need no Home Assistant install.
_PATH = Path(__file__).parents[1] / "custom_components" / "glados" / "speech.py"
_SPEC = importlib.util.spec_from_file_location("glados_speech", _PATH)
speech = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(speech)
clean = speech.clean_for_speech


def test_removes_emoji_quotes_and_markdown() -> None:
    assert clean('Oh "wonderful" \U0001f382\U0001f389 *cake* ✨') == "Oh wonderful cake"


def test_spells_out_units() -> None:
    assert clean("CO₂ is 431 ppm and it is 18°C, 60%") == (
        "CO2 is 431 parts per million and it is 18 degrees, 60 percent"
    )


def test_wind_speed() -> None:
    assert clean("wind 30 km/h") == "wind 30 kilometres per hour"


def test_negative_numbers_become_minus_but_ranges_stay() -> None:
    assert clean("from -1 to 2, room 2-3") == "from minus 1 to 2, room 2-3"
    assert clean("-3 degrees") == "minus 3 degrees"


def test_dashes_become_pauses() -> None:
    assert clean("Cake — or not") == "Cake, or not"


def test_lists_and_newlines_become_one_line() -> None:
    text = "Today:\n- Dentist at 9\n- Papa's birthday\n\n1. Water the plants"
    assert clean(text) == "Today: Dentist at 9 Papa's birthday Water the plants"


def test_her_name_is_spelled_for_the_voice() -> None:
    assert clean("I am GLaDOS.") == "I am Glad-oss."


def test_keeps_ordinary_punctuation_and_apostrophes() -> None:
    assert clean("Don't. Really? Fine...") == "Don't. Really? Fine..."


def test_empty() -> None:
    assert clean("") == ""
