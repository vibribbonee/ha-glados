# GLaDOS integration: plan

The goal is to replace the GLaDOS scripts, automations and helpers with one integration. The integration decides what goes into her context, and it cleans every reply before it is spoken.

## Where it stands (27 November 2026)

**Everything GLaDOS does still runs as scripts, automations and helpers in Home Assistant.** Phase 1 of the integration is written and tested (41 tests), but it is not installed in HA yet.

It provides these services:

| Service | Ported from |
|---|---|
| `glados.room_context` | `glados_room_context`, same fields |
| `glados.announce` | `glados_announce`: the quiet rules, both voices, the beeps |
| `glados.say` | `glados_say`: voice rewrite plus cleanup |
| `glados.who` | The person lookup duplicated in Set leave time and Set reminder |
| `glados.remember` / `glados.recall` | The to-do-list memory, now in HA's own storage |
| `glados.clean_text` | The speech cleanup |

It also adds a **GLaDOS conversation agent**. Pick it as the pipeline's agent: it passes every sentence to the chat agent (GLaDOS Extended), with the conversation, device and satellite, and cleans the reply for speech. This is the reply cleanup from phase 2, without waiting for her own LLM API. The one cost is that the reply is no longer streamed to the voice, so a long answer starts speaking a moment later.

Its settings screen holds the chat agent, the voice agent, the Announcer voice, the beeps, the speaking schedule and the default routine length.

Next:

1. Install it, and set the GLaDOS pipeline's conversation agent to GLaDOS.
2. Turn each old script into a one-step wrapper around its service, so nothing calling it changes. Compare the results for a day.
3. Move on to phase 2: her own LLM API, so chat replies are cleaned and the tools compute dates.

The reference copies of the live setup are in `reference/current-setup/`.

### Per person

Each person has their own settings, found by name, so nobody is hard-coded:

| Helper | Meaning | Falls back to |
|---|---|---|
| `input_datetime.leave_home_<person>` | Leave time, set by voice | none |
| `input_number.morning_routine_<person>` | Minutes from alarm to the door | `input_number.morning_routine_minutes` |
| `todo.<person>_s_list` | Their own reminders | `todo.to_do` |

Adding someone means creating those helpers. The integration should create them automatically for every person with a phone.

### Found in a simulated week of voice commands

| Request | Before | Now |
|---|---|---|
| "Leave at 7:45 on Monday" | Set for tomorrow, but said Monday | Weekdays and dates understood; the reply carries the real date |
| "Remind me tomorrow at 3 to…" | Became a 03:00 leave time | `Set reminder`: a to-do with a due time, read out by the Announcer in their room |
| "Add oat milk to the shopping list" | Written into the permanent file | Lists exposed, so HA's own list intent is used |
| "What's on this week?" | Wrong dates (30 instead of 28 November) | Every event carries its weekday, date and "in N days" |
| "Put the dentist on Tuesday" | No way to do it | `Add to calendar` (default: the calendar labelled `glados`) |
| "Days until Christmas" | 27 days, from Sinterklaas | Correct from the calendar |
| "What do you know about me?" | Mixed up calendar birthdays with the user's, invented a trip | Only the permanent file counts as knowing them; a calendar event belongs to whoever it names. The 8B model still sometimes misses a birthday that is in its live list |
| "Good night" | Read the briefing word for word, no character | The briefing voices itself (two or three things that matter, one remark) and the chat model only gets that line. Automations ask for `plain: true` and keep the raw facts |
| Chat replies | "km/h", markdown lists | The integration's GLaDOS agent cleans every reply, once installed |
| Timers | "I cannot set timers" in a satellite-less test | Check on a Puck: HA's local timer intent should handle it before the LLM |

### Still missing compared with a commercial smart speaker

- **Alarms.** Phone alarms can only be read, not set. The kiosk alarms script can set them on the Lenovo.
- **Music by voice.** `Play music` exists but was not tested, to avoid playing music while someone was home.
- **Broadcast** ("tell everyone dinner is ready").
- **A routine word** ("I'm leaving": lights off and a check of what is left on; "I'm home").
- **Per-person bedtime.** `sensor.bedtime_target` still follows one person's alarm.

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
