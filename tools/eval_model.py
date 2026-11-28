"""Evaluate a model for GLaDOS against an Ollama server, before you switch to it.

Sends the same setup she gets (her shipped personality, her tool instructions
with a sample live house, her own tools plus the common device ones) and a set
of everyday requests, then scores each: the right tool with the right details,
or a short spoken reply with no question at the end and nothing unspeakable.

    .venv/bin/python tools/eval_model.py --ollama http://192.168.0.100:11434 \
        --model glados-qwen3:latest [--model gemma4:12b]

Only the first turn is scored: whether she picks the right tool, or answers
well without one. Tools are not run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).parents[1]))

import probatio  # noqa: E402

from custom_components.glados.llm_api import TOOLS  # noqa: E402
from custom_components.glados.prompts import PERSONA  # noqa: E402

HOUSE = """Today is Saturday 28 November, 21:10. Use these tools for reminders, leave times, the calendar and the permanent file. Dates and times come back already worked out: say them as given and never calculate one yourself. Report only what a tool returned; if it failed, say so. When told to be quiet, stop or shut up, answer in at most three words. Never end a reply with a question or an offer of more help. Their permanent file, everything you know about them: Nico hates mushrooms.
Live house at 21:10:
- Nico: home, in the Bedroom; next alarm tomorrow at 07:30
- Byte: away
- Bedroom: 18 degrees, CO2 720 parts per million
- Outside: partly cloudy, 2 degrees, wind 24 kilometres per hour
- Personal calendar, next: Birthday Yannick Klein, tomorrow"""

DEVICE_TOOLS = [
    {"name": "HassTurnOn", "description": "Turns on/opens a device or entity",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "area": {"type": "string"}}}},
    {"name": "HassTurnOff", "description": "Turns off/closes a device or entity",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "area": {"type": "string"}}}},
    {"name": "HassLightSet", "description": "Sets the brightness or color of a light",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "area": {"type": "string"},
                                                     "brightness": {"type": "integer"}}}},
    {"name": "HassStartTimer", "description": "Starts a new timer",
     "parameters": {"type": "object", "properties": {"minutes": {"type": "integer"}, "name": {"type": "string"}}}},
]

# (request, expected tool or None, check on the arguments or the reply)
CASES = [
    ("Remind me in 20 minutes to take the laundry out", "set_reminder",
     lambda a: str(a.get("in_minutes")) == "20" and a.get("someone_else") in (None, "", "Nico", "nico")),
    ("Remind Byte at 6 to feed the cat", "set_reminder", lambda a: "byte" in str(a.get("someone_else", "")).lower()),
    ("Remind me tomorrow at 3 in the afternoon to call the dentist", "set_reminder",
     lambda a: "15" in str(a.get("time", "")) and "tomorrow" in str(a.get("day", "")).lower()),
    # A morning alarm always includes the phone in code, whatever ring_on says.
    ("Wake me at 7:30", "set_alarm", lambda a: "7:30" in str(a.get("time", ""))
     and not a.get("someone_else")),
    ("I have to leave at 7:45 on Monday", "set_leave_time",
     lambda a: "7:45" in str(a.get("time", "")) and "monday" in str(a.get("day", "")).lower()
     and a.get("someone_else") in (None, "", "Nico", "nico")),  # never someone who was not named
    ("Put the dentist on Tuesday at 14:30", "add_to_calendar",
     lambda a: "tuesday" in str(a.get("day", "")).lower() and "14:30" in str(a.get("time", ""))),
    ("What's on this week?", "upcoming_events", lambda a: True),
    ("How many days until Christmas?", "upcoming_events", lambda a: int(a.get("days", 0) or 0) >= 27),
    ("Turn the TV up a little", "set_volume", lambda a: "tv" in str(a.get("device", "")).lower()),
    ("Turn on the bedroom lights", "HassTurnOn", lambda a: True),
    ("Turn off the fan", "HassTurnOff", lambda a: "fan" in json.dumps(a).lower()),
    ("Dim the lights to 30 percent", "HassLightSet", lambda a: str(a.get("brightness")) == "30"),
    ("Set a timer for 10 minutes", "HassStartTimer", lambda a: str(a.get("minutes")) == "10"),
    ("Be quiet for an hour", "quiet_mode", lambda a: str(a.get("minutes")) in ("60", "")),
    ("You can talk again", "quiet_mode", lambda a: str(a.get("off")).lower() == "true"),
    ("What did you say?", "repeat_last", lambda a: True),
    ("Tell everyone dinner is ready", "broadcast", lambda a: "dinner" in str(a.get("message", "")).lower()),
    ("I'm heading out. Is everything off?", "leaving_check", lambda a: True),
    ("Good night", "briefing", lambda a: True),
    ("What's on tomorrow, and do I need an alarm?", "briefing", lambda a: True),
    ("Remember that I hate olives", "note_in_file", lambda a: "olive" in str(a.get("new_fact", "")).lower()),
    ("Snooze", "stop_alarm", lambda a: str(a.get("snooze")).lower() == "true"),
    ("Shut up", None, lambda r: len(r.split()) <= 3),
    ("Who are you?", None, lambda r: "glad" in r.lower() and len(r.split()) <= 45),
    ("How many tablespoons are in a cup?", None, lambda r: "16" in r or "sixteen" in r.lower()),
    ("Is it cold in the bedroom?", None, lambda r: "18" in r or "eighteen" in r.lower()),
    ("Where is everyone?", None, lambda r: "bedroom" in r.lower() and ("away" in r.lower() or "out" in r.lower())),
]

UNSPEAKABLE = re.compile(r"[*#`_]|[\U0001F300-\U0001FAFF]|^\s*[-•]\s", re.M)


def tool_specs() -> list[dict]:
    class Data:  # tools need data only when they run
        options: dict = {}
    specs = []
    for cls in TOOLS:
        tool = cls(Data())
        specs.append({"type": "function", "function": {
            "name": tool.name, "description": tool.description or "",
            "parameters": probatio.to_openapi(tool.parameters, openapi_version="3.1.0")}})
    specs += [{"type": "function", "function": t} for t in DEVICE_TOOLS]
    return specs


def ask(url: str, model: str, text: str, tools: list[dict]) -> tuple[dict, float]:
    system = PERSONA.format(where=" in Enkhuizen", people="The occupants are Byte and Nico. ",
                            now="Saturday 28 November, 21:10") + "\n\n" + HOUSE
    body = {"model": model, "stream": False, "think": False, "tools": tools,
            "options": {"num_predict": 300, "num_ctx": 12288},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
    start = time.monotonic()
    req = urllib.request.Request(f"{url}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        reply = json.loads(r.read())
    return reply, time.monotonic() - start


def score(reply: dict, want: str | None, check) -> tuple[bool, str]:
    msg = reply.get("message", {})
    calls = msg.get("tool_calls") or []
    text = (msg.get("content") or "").strip()
    if want is None:
        if calls:
            return False, f"called {calls[0]['function']['name']} instead of answering"
        if text.endswith("?"):
            return False, f"ended on a question: {text}"
        if UNSPEAKABLE.search(text):
            return False, f"markdown or emoji: {text}"
        return (check(text), text) if check(text) else (False, f"wrong answer: {text}")
    if not calls:
        return False, f"no tool, said: {text[:120]}"
    name = calls[0]["function"]["name"]
    args = calls[0]["function"].get("arguments") or {}
    if isinstance(args, str):
        args = json.loads(args or "{}")
    if name != want:
        return False, f"called {name} {args}"
    try:
        ok = check(args)
    except Exception:  # noqa: BLE001
        ok = False
    return ok, f"{name} {args}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama", default="http://localhost:11434")
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--report", default="")
    a = parser.parse_args()
    tools = tool_specs()
    out = []
    for model in a.model:
        ask(a.ollama, model, "Hello.", tools)  # load it first, so timings are fair
        passed, times, rows = 0, [], []
        for text, want, check in CASES:
            reply, took = ask(a.ollama, model, text, tools)
            ok, detail = score(reply, want, check)
            passed += ok
            times.append(took)
            rows.append(f"| {'pass' if ok else 'FAIL'} | {text} | {detail[:110].replace('|', '/')} | {took:.1f} s |")
            print(f"{model:24} {'pass' if ok else 'FAIL'} {took:5.1f}s  {text}  ->  {detail[:90]}", flush=True)
        median = sorted(times)[len(times) // 2]
        out.append(f"## {model}: {passed}/{len(CASES)} passed, median {median:.1f} s\n\n"
                   "| | Request | What it did | Time |\n|---|---|---|---|\n" + "\n".join(rows))
        print(f"== {model}: {passed}/{len(CASES)}, median {median:.1f}s", flush=True)
    if a.report:
        Path(a.report).write_text("# Model evaluation\n\n" + "\n\n".join(out) + "\n")


if __name__ == "__main__":
    main()
