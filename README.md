# GLaDOS

GLaDOS from Portal as your Home Assistant voice assistant. She's sarcastic, precise and quietly menacing, and genuinely the most useful thing in your house.

She does what you'd ask any smart speaker: timers, lights, the weather with a clothing tip, the calendar, lists, music and quick answers. She does it in character: help first, then one precise remark about you.

**Early version.** The conversation agent, the personality and the services below work today. The proactive features (air quality, bedtime, morning, trains) are still being moved in from scripts. See [the plan](docs/PLAN.md).

## What you need

- **Home Assistant 2026.11** or later, with a voice assistant set up (**Settings → Voice assistants**).
- **A chat agent**, the brain. Any conversation agent that can control Home Assistant works: Ollama, OpenAI, Google Gemini, Anthropic and others. Set **Control Home Assistant** to **Assist** on it. A local Ollama model keeps everything in your house; Qwen3 8B is enough.
- **A GLaDOS voice** for text-to-speech, optional but it's half the fun. See [Voices](#voices).

## Install

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vibribbonee&repository=ha-glados&category=integration)
[![Add the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=glados)

The first button opens this repository in HACS, in your own Home Assistant, ready to download. After the restart, the second starts the setup.

1. Open this repository in HACS (first button), or add `https://github.com/vibribbonee/ha-glados` under ⋮ → **Custom repositories** as an **Integration**.
2. Download **GLaDOS** and restart Home Assistant.
3. Add the integration (second button, or **Settings → Devices & services → Add integration → GLaDOS**), and pick your chat agent.
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

## Alarms, timers and reminders

| | Means | Rings on |
|---|---|---|
| Timer | "In 10 minutes": a countdown | The speaker you asked, through Home Assistant's own timers |
| Reminder | "At 3, remind me to call the dentist" | The room you are in at that time, else your phone |
| Alarm | "Wake me at 7:30", "alarm at 4 for the oven" | Morning: your phone, with a backup on the speaker. Otherwise the speaker |

The backup rings only when the phone alarm failed: it never showed up as the phone's next alarm, the phone is off or flat, or it was not dismissed within **Alarm backup after** (10 minutes). A speaker alarm repeats three times, three minutes apart, and stops as soon as the room looks awake (out of bed with the light on), or when you say stop. Alarms are the one thing allowed past the sleep rules.

For the phone part, the Home Assistant app needs **Display over other apps**: on the phone, **Settings → Apps → Home Assistant → Display over other apps → Allow**. Who the alarm is for comes from the room: the person in the speaker's room, as Bermuda sees it.

## How she finds things

Nothing is hard-coded. She works it out from your areas, labels and names:

| Label | Meaning |
|---|---|
| `glados` | Devices she always knows about |
| `glados_quiet` | Do Not Disturb: while one of these is on, she stays quiet |
| `glados_heating` / `glados_cooling` | Heaters and coolers she may offer to switch on |
| `glados_own_chime` | Satellites with their own chime, so no beeps |

She stays quiet when someone is in bed, before a morning alarm, in a dark bedroom, on Do Not Disturb, or while a video plays in that room.

Add `glados_bedroom` to an area to mark it as a bedroom in any language. Rooms named like one ("bedroom", "slaapkamer") count anyway.

**Everyone gets their own**, with no helpers to make: GLaDOS creates, for each person with a phone or a Home Assistant login,

| Entity | Meaning |
|---|---|
| Leave home \<name\> | When they leave home, set by voice or on a dashboard |
| Morning routine \<name\> | Minutes from alarm to the door |
| Bedtime \<name\>, Last call \<name\> | From their own morning alarm and the sleep settings |

Someone who moves in gets theirs straight away. Existing helpers keep working and win: `input_datetime.leave_home_<person>`, `input_number.morning_routine_<person>`. Their own reminders go to `todo.<person>_s_list` when that list exists, otherwise to the shared To-do list. Person entities without a phone or login (a wall tablet, "Guest") are not occupants.

**Which room someone is in** comes from a Bermuda area sensor on one of their devices. Without one: when only one person is home and only one room shows presence, that's theirs; otherwise she speaks where people are.

## Services

| Service | What it does |
|---|---|
| `glados.say` | Plain facts in her voice, cleaned for speech |
| `glados.announce` | Speak up unprompted in the right room, only when polite; GLaDOS or the Announcer |
| `glados.room_context` | Everything about one room: people, sleep, quiet, climate, windows, satellites |
| `glados.who` | Which person is meant, with their room, phones, leave time and list |
| `glados.remember` / `glados.recall` | Her memory, with the time each thing was stored |
| `glados.clean_text` | Make any text safe for the voice |

## Add-ons

GLaDOS needs only a chat agent. Features that depend on another integration are separate add-ons you install next to her:

| Add-on | Needs | Adds |
|---|---|---|
| [GLaDOS trains](https://github.com/vibribbonee/ha-glados-trains) [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vibribbonee&repository=ha-glados-trains&category=integration) | Train departure sensors (NS works best) | Which train to catch, a heads-up, and when to leave, with live delays |

Writing one: [docs/ADDONS.md](docs/ADDONS.md).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

[MIT license](LICENSE). Not affiliated with Valve. Portal and GLaDOS are Valve's.
