# GLaDOS

GLaDOS from Portal as your Home Assistant voice assistant. She's sarcastic, precise and quietly menacing, and genuinely the most useful thing in your house.

She does what you'd ask any smart speaker: timers, lights, the weather with a clothing tip, the calendar, lists, music and quick answers. She does it in character: help first, then one precise remark about you.

**Early version.** The conversation agent, the personality and the services below work today. The proactive features (air quality, bedtime, morning, trains) are still being moved in from scripts. See [the plan](docs/PLAN.md).

## What you need

- **Home Assistant 2026.11** or later, with a voice assistant set up (**Settings → Voice assistants**).
- **A chat agent**, the brain. Any conversation agent that can control Home Assistant works: Ollama, OpenAI, Google Gemini, Anthropic and others. Set **Control Home Assistant** to **Assist** on it. A local Ollama model keeps everything in your house; Qwen3 8B is enough.
- **A GLaDOS voice** for text-to-speech, optional but it's half the fun. See [Voices](#voices).

## Install

1. In HACS, open the ⋮ menu → **Custom repositories**, and add `https://github.com/vibribbonee/ha-glados` as an **Integration**.
2. Download **GLaDOS** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → GLaDOS**, and pick your chat agent.
4. Open your chat agent's settings (for Ollama: **Settings → Devices & services → Ollama**, then the agent's ⚙). Under **Control Home Assistant**, tick **GLaDOS** next to **Assist**, so she gets her own tools.
5. In **Settings → Voice assistants**, open your assistant and set its **Conversation agent** to **GLaDOS**. Pick your GLaDOS voice as its text-to-speech voice.

Ask her who she is.

## Settings

At setup:

| Setting | What it does |
|---|---|
| Chat agent | The agent she thinks with. GLaDOS passes every sentence to it, with the conversation, device and room, so its tools, timers and history keep working. |
| Add her personality | Sends her persona along with every request. On by default; turn it off only if your chat agent's own prompt already is GLaDOS. |
| Home town | For her remarks and local searches. Optional. |

Under **Configure**, all optional:

| Setting | Empty means |
|---|---|
| Voice agent: a separate agent that rewrites announcements in her voice | The chat agent does it |
| Announcer voice: the facility Announcer's voice, as `engine:voice`, such as `tts.piper:announcer` | Her own voice reads the notices |
| Opening and closing beep: media ids | No beeps |
| Speaking schedule: a `schedule` entity; she only speaks up unprompted while it's on | Any time |
| Default morning routine: minutes from alarm to the door | 35 minutes |
| Air and window warnings: **Announcer, then GLaDOS**, **GLaDOS alone**, or **Off** | Off |
| CO2 reminder: minutes before she reminds you while the air stays bad | 30 minutes; 0 for no reminder |
| Cold outside below: an open window counts as heating the street | 8 degrees |

Whatever the settings, every reply is cleaned before it's spoken: no emoji, markdown or quotation marks, and units, minus signs and her name are written the way the voice should say them.

## Voices

The integration doesn't include voice models or game sounds. The GLaDOS and Announcer voices are trained on Valve's game audio, so they aren't ours to redistribute, and they're too big for an integration anyway.

- **Piper**: community-trained GLaDOS voices for Piper exist. Put the `.onnx` file and its `.onnx.json` in the Piper app's custom voices folder, restart Piper, and pick the voice in your voice assistant. Check each voice's license before you use it.
- **The facility Announcer** (optional): add a second Piper voice in the same way, then enter it under **Configure → Announcer voice**, for example `tts.piper:announcer`.
- **Beeps** (optional): put your own sound files in the media folder and enter them as `media-source://media_source/local/<file>`.

## Air and window warnings

Every room with a CO2 sensor is checked each minute. When the air goes stale (1000 ppm) or critical (1500 ppm) and someone is in the room, she warns there, once. While it stays bad she reminds you after the reminder time. When it's fresh again and cold outside, she says the window can be closed.

A window open for 20 minutes in the cold gets one reminder per opening: in the room, if someone is there and the air is fine; otherwise wherever people are, naming the window and the room nobody is in. She never warns while someone sleeps, on Do Not Disturb or during a video.

With **Announcer, then GLaDOS**, the facility Announcer reads the warning and GLaDOS remarks on it. With **GLaDOS alone**, she gives the warning herself. The lines are written out rather than improvised, so a real warning is never softened. Try them with the **Test announcement** button, or with `glados.test_announcement` and a pretend `co2` reading.

## How she finds things

Nothing is hard-coded. She works it out from your areas, labels and names:

| Label | Meaning |
|---|---|
| `glados` | Devices she always knows about |
| `glados_quiet` | Do Not Disturb: while one of these is on, she stays quiet |
| `glados_heating` / `glados_cooling` | Heaters and coolers she may offer to switch on |
| `glados_own_chime` | Satellites with their own chime, so no beeps |

She stays quiet when someone is in bed, before a morning alarm, in a dark bedroom, on Do Not Disturb, or while a video plays in that room.

For each person, optionally:

| Helper | Meaning | Without it |
|---|---|---|
| `input_datetime.leave_home_<person>` | When they leave home | No leave reminders |
| `input_number.morning_routine_<person>` | Minutes from alarm to the door | `input_number.morning_routine_minutes`, then the default |
| `todo.<person>_s_list` | Their own reminders | `todo.to_do` |

Rooms of people come from a Bermuda area sensor (`sensor.<phone>_area`) on one of their tracker devices, if you have one.

## Her tools

With **GLaDOS** ticked under the chat agent's **Control Home Assistant**, she gets these besides the usual device control. Dates are worked out in Python and handed to her spelled out, so even a small model says the right day.

| Tool | For |
|---|---|
| Set reminder | "Remind me tomorrow at 3 to call the dentist": a to-do with a due time on that person's own list |
| Set leave time | "I have to leave at 7:45 on Monday": with the time to get up |
| Add to calendar | "Put the dentist on Tuesday at 14:30", or an all-day event |
| Upcoming events | "What's on this week?", "How many days until Christmas?" |
| Note in permanent file | Anything worth keeping about someone; what's in the file goes into her prompt |
| Set volume | "Turn the TV up a little": a TV that plays through a soundbar changes the soundbar |
| Set alarm | "Wake me at 7:30": a real alarm on that person's own Android phone, through the Home Assistant app. The first time, the phone asks you to allow **Display over other apps** for the app |
| Broadcast | "Tell everyone dinner is ready": every other room with a speaker, except where someone sleeps or watches a video |
| Leaving check | "I'm heading out" or "is everything off?": what's still on among devices labelled `glados_left_on`, and which windows and doors are open |

## Services

| Service | What it does |
|---|---|
| `glados.say` | Plain facts in her voice, cleaned for speech |
| `glados.announce` | Speak up unprompted in the right room, only when polite; GLaDOS or the Announcer |
| `glados.room_context` | Everything about one room: people, sleep, quiet, climate, windows, satellites |
| `glados.who` | Which person is meant, with their room, phones, leave time and list |
| `glados.remember` / `glados.recall` | Her memory, with the time each thing was stored |
| `glados.clean_text` | Make any text safe for the voice |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

[MIT license](LICENSE). Not affiliated with Valve. Portal and GLaDOS are Valve's.
