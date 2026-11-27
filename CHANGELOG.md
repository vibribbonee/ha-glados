# Changelog

## 0.8.0 (not installed yet)

### New
- **Add-ons.** GLaDOS works on her own; anything that needs another integration becomes an add-on: its own integration and repository, with `glados` as a dependency. Add-ons register tools, lines for her instructions and background jobs through `custom_components.glados.addon`, and speak through her announcer, quiet rules and voices. See [docs/ADDONS.md](docs/ADDONS.md).
- **Leave-time reminders in the integration.** For each person with a `leave_home_<person>` helper, while they are home: a heads-up before (**Leave heads-up**, 15 minutes, with the outside temperature), then "leave now" at the time, by the Announcer in their room, with one GLaDOS remark. New: "leave now" also says what is still on (`glados_left_on`) and which windows and doors are open. Asleep or on Do Not Disturb: their phone. A minute missed during a restart is caught up, up to five minutes late.

- **Mornings in the integration.** Between 20:00 and 05:00, a phone going on a wireless charger notes when someone fell asleep. A morning alarm (a phone's next alarm, or an alarm clock's alarm-ringing sensor) fades on the lights labelled `glados_wakeup` while it's dark, sets a leave time (alarm plus their morning routine) if none is set for today, and once they're out of bed she greets them: the Announcer's "you have been in suspension for 7 hours and 33 minutes", then GLaDOS with the morning briefing. No alarm: the first time a light labelled `glados` goes on in their room. On their birthday: the **Birthday song**, then a fixed birthday line with their first commitment. Once per person per day. Settings: **Morning greeting**, **Birthday song**, **Birthday names** (such as `nico: Sjors`). `glados.greet` tests it, `pretend_birthday` too.
- **Bedtime per person.** Each person's bedtime is their next morning alarm minus the **Sleep goal** (8 hours); without an alarm, the **Usual bedtime** if set. Last call is the alarm minus the **Minimum sleep** (6 hours). In their own room: an hour before (bedtime plus the one thing that matters for tomorrow, from the briefing), at bedtime, and the Announcer's last call when the lights are still on. Never for someone in bed or in the dark. New sensors per person: **Bedtime <name>** and **Last call <name>**, for dashboards.
- **The first add-on: [GLaDOS trains](https://github.com/vibribbonee/ha-glados-trains).** Its own repository and HACS install.

### To do when installing
- Turn off `automation.glados_time_to_leave`, or it is said twice.
- Turn off `automation.glados_good_morning` and `automation.glados_notes_when_you_go_to_sleep`; set **Birthday song** to your song and **Birthday names** from `input_text.glados_birthday_names`.
- In `automation.bedroom_bedtime_nudge`, remove the "GLaDOS says the nudge in the room" step (her bedtime nudges replace it); set **Sleep goal**, **Minimum sleep** and **Usual bedtime** from `input_number.sleep_goal`, `input_number.minimum_sleep` and `input_datetime.target_bedtime`.
- After installing GLaDOS trains: turn off `automation.glados_train_reminders` and hide `script.set_train_reminder` from her.

## 0.7.0

One release instead of many small ones, so the house restarts once.

### New
- **Reminders are read out by the integration.** Every to-do with a due time on a person's own list (`todo.<person>_s_list`) or the shared To-do list is said when it comes due, by the Announcer in the room that person is in, with their name when more people are home. Away, or when it can't be said: their phone. Voice reminders are ticked off once delivered. Setting: **Read out reminders** (on).
- **Nothing is lost overnight.** A reminder that comes due while someone sleeps goes to their phone quietly *and* is kept: the first time that room is awake, the Announcer says what came due in the night, with the times.
- **A reminder missed during a restart is still said**, up to an hour late. The old automation only caught the exact minute.
- **The bedtime and morning briefing in Python.** Tomorrow at bedtime, or the rest of today in the morning: the calendar, each person's alarm and whether it's early enough (their morning routine before the first commitment, half an hour more when it has a location), leave times and when to be up, phones that won't last the night, the bedtime sensor and the weather. She picks the two or three that matter and says them. Her **Briefing** tool returns only that line; `glados.briefing` gives automations the facts (`plain: true`) or both. New setting: **Bedtime sensor** (optional).

### Better to live with
- **Settings in sections.** Configure now has five collapsible groups (Brain; Voices and sounds; Air and window warnings; Reminders, alarms and leaving; Mornings and bedtime) instead of one long form. Only Brain is open.
- **Last announcement sensor.** What she last said unprompted, or "Quiet: someone is in bed" and the like, with the last ten in its attributes. When she stays quiet, you can see why.
- **Diagnostics.** Download them from the integration page: settings, add-ons, recent announcements, alarms, held reminders and any feature errors.
- **One heartbeat.** Her background features run in turn on one timer; one that fails is logged once and the others carry on. A slow beat (a busy voice agent) is never piled up.

### Fixed
- An announcement for someone known to be awake (a bedtime nudge) is no longer silenced by the "before an alarm, people may be asleep" rule.
- **GLaDOS's chime-in no longer reads her instructions aloud.** The Announcer's line now goes to her as the fact, the extra instruction stays short, a reply that repeats the instruction is dropped (the Announcer stands alone), and a reply that opens by repeating the Announcer is trimmed.
- **Every phone alarm gets the room backup.** "On my phone, with a backup" stored no backup when the model chose "phone", and she then said there was one.

### To do when installing
- Turn off `automation.glados_reminders`, or reminders are said twice.
- Set **Bedtime sensor** to `sensor.bedtime_target`.
- Hide `script.glados_bedtime_briefing` from her (her Briefing tool replaces it) and turn that script into a wrapper around `glados.briefing`, so the bedtime nudge, Bedroom all off and the morning greeting keep working.

## 0.6.0
- **Alarms.** A morning alarm goes on the person's phone, with a backup on the room's speaker that rings only when the phone alarm failed: it never showed up on the phone, the phone is off or flat, or it wasn't dismissed within **Alarm backup after** (10 minutes). Other alarms ring on the speaker. Speaker alarms repeat three times and stop once the room looks awake, or on "stop" / "snooze".
- **Who's asking comes from the room**: the person in the speaker's room, for reminders, leave times and alarms.

## 0.5.1
- Leaving check ignores door and window sensors that are in no room and not labelled `glados`.

## 0.5.0
- **Set alarm, broadcast, leaving check** tools.
- CO2 removed from the facility notices; the air warnings cover it.

## 0.4.1
- **Window warnings**: open in the cold for 20 minutes, fresh again after a CO2 warning, and windows in empty rooms told to whoever is home. **Cold outside below** setting.

## 0.4.0
- **CO2 warnings** in the integration: Announcer then GLaDOS, GLaDOS alone, or off; a reminder while the air stays bad.

## 0.3.x
- Test announcement button and service; announce on a chosen satellite.
- CO2 set pieces: fixed Announcer and GLaDOS lines per air level.
- **Set volume** follows the sound: a TV that plays through a soundbar changes the soundbar.
- Her tool instructions: report only what a tool returned; three words when told to be quiet; never end on a question.

## 0.3.0
- Her own tools as an LLM API: reminders, leave times, add to calendar, upcoming events, permanent file. Dates worked out in Python.

## 0.2.0
- Works in any home: setup asks only for a chat agent; her personality ships with the integration.

## 0.1.0
- Core services, and the GLaDOS conversation agent that cleans every reply for speech.

## Done in Home Assistant itself (no restart)

27 November:
- `automation.tv_wake_on_turn_on`: lets HA turn the LG TV on with Wake-on-LAN. On the TV, turn on **Mobile TV On** / **Turn on via Wi-Fi**.
- Hidden from her: `script.kiosk_satellite_alarms` (set alarm replaces it), `script.get_room_climate` (her live list has the climate), `script.get_assistant_spoken_name`, the five unavailable ALPSTUGA sensors, and the Google TV remote entity.
- Hidden from her earlier: the five scripts her own tools replace (set reminder, set leave time, add to calendar, upcoming events, note in permanent file).
- `automation.glados_fresh_air_and_windows` turned off; CO2 taken out of `automation.glados_facility_notices`.
