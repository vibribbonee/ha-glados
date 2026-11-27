# GLaDOS integration: plan

The goal is to replace the GLaDOS scripts, automations and helpers with one integration. The integration decides what goes into her context, and it cleans every reply before it is spoken.

## Why an integration

| Today (scripts and automations) | With the integration |
|---|---|
| HA's Assist API sends every exposed device plus every tool. At 8192 tokens that silently pushed her persona out. | Her own LLM API decides what she sees: a compact live list, a curated set of tools and a size budget. |
| Only her own announcements are cleaned; chat replies can still contain "CO₂", emoji or markdown. | Every reply is cleaned before it reaches text-to-speech, conversation included. |
| About 10 scripts, 10 automations, 20 helpers, 5 labels, and a to-do list used as memory. | One integration with a settings screen, and memory in HA's own storage. |
| Logic lives in long Jinja templates and polls every 5 minutes. | Readable, tested Python that reacts to state changes. |

## Two voices

The integration keeps the split from Portal 2:

- **GLaDOS** is the assistant: conversation, opinions, her own unprompted remarks. She speaks through the GLaDOS voice agent and Piper voice.
- **The Announcer** is the facility system: it reads fixed text word for word, in short clipped sentences, through its own Piper voice. It handles:
  - the morning "you have been in suspension for…" line (sleep start is taken from when the phone goes on the night charger);
  - safety alarms;
  - "leave now" for a train;
  - the bedtime last call;
  - rare facility notices built from something real (stale air, sitting still for hours, the cold).
- **GLaDOS can chime in** with one remark right after the Announcer.

## Settings screen

The entry setup asks for:

- the conversation agent (and the voice-rewriter agent) to use;
- the home town;
- the people's birthday names;
- the news regions.

The options cover the rest:

- **Thresholds:** cold below, warm above, CO2 stale and fresh, cold outside, settled-after minutes, morning-routine minutes, walk to the station.
- **Speaking schedule:** a `schedule` entity.
- **Sounds:** the beep-in, beep-out and birthday song.
- **Features:** a switch for each, so features can be turned on one by one during the migration.

Labels stay the way you tag devices, so it keeps working however your rooms and devices change:

| Label | Meaning |
|---|---|
| `glados` | In her live list; counts as a real light |
| `glados_quiet` | Do Not Disturb |
| `glados_heating` / `glados_cooling` | Heaters and coolers |
| `glados_wakeup` | Lights that fade on at a morning alarm |
| `glados_own_chime` | Satellites with their own chime, so no beeps |

## Structure

```
custom_components/glados/
  __init__.py        set up the entry, start the features, register the services and the LLM API
  config_flow.py     setup and options
  const.py
  speech.py          clean text for text-to-speech (emoji, quotes, markdown, units, minus, name)
  memory.py          per-key memory with timestamps (homeassistant.helpers.storage.Store)
  rooms.py           room context: people (Bermuda), occupancy, sleep, quiet, movie, climate,
                     windows, heaters/coolers, satellites
  announce.py        polite announcer: picks the room and satellite, gates on sleep and quiet,
                     beep in, voice, beep out
  voice.py           FACTS/TASK rewrite through the voice agent, then speech.clean
  llm_api.py         her own LLM API: compact live list, curated tools, size budget
  features/
    air.py           stale air, fresh again, window reminders (hysteresis per room)
    comfort.py       offer heating or cooling, remember the answer
    trains.py        heads-up and leave-now reminders, live NS delay check
    bedtime.py       bedtime nudges, goodnight briefing
    morning.py       wake-up routine and birthday (hum, fixed canon-pattern lines)
  sensor.py          last announcement, why she stayed quiet
  switch.py          one master "GLaDOS may speak up" switch, plus one per feature
  services.yaml, translations/en.json, brand/icon.png
tests/               pytest-homeassistant-custom-component
```

The services keep today's names where scripts call them, so dashboards and voice keep working: `glados.announce`, `glados.say`, `glados.remember`, `glados.room_context`, `glados.set_train_reminder` and `glados.bedtime_briefing`.

## Phases

Every phase ends with the old part removed in HA, so nothing runs twice.

1. **Core.** Speech cleanup, memory, room context and the announcer, with tests. Services only, nothing runs on its own yet. The old scripts become thin wrappers that call the services.
2. **Conversation.** Her own LLM API and prompt builder, then a test in a separate "GLaDOS (integration)" pipeline before it replaces the current one. This is the change that fixes the context and the output cleaning for real.
3. **Proactive features, one at a time:**
   1. air;
   2. comfort;
   3. trains;
   4. bedtime;
   5. morning and birthday.

   Each one turns its old automation off, then the old automation is deleted after a day of working correctly.
4. **Cleanup and release.** Delete the old helpers and the to-do memory, write the README, add the HACS button and tag v0.1.0.

## Rules carried over from what went wrong

- **No quoted example lines in prompts.** The 8B model repeats them as tics, so prompts describe techniques. Set pieces like the birthday use fixed lines built on the games' own patterns.
- **Measure the context.** Count the tokens and refuse to send more than the window, which is 12288 today; trim the live list first.
- **Stay quiet when people may be asleep:**
  - someone is in bed in that room;
  - it is before a morning alarm;
  - a bedroom is dark;
  - Do Not Disturb is on;
  - a video is playing in that room.
- **No hard-coded entities.** Everything is found through areas and labels.

## Open questions

- Each conversation agent has its own context window. Should the integration provide its own Ollama agent, or keep using the Ollama integration's agent and only supply the LLM API? The second is less code; the first gives full control of the context.
