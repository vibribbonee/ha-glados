# GLaDOS

GLaDOS from Portal as your Home Assistant voice assistant. She's sarcastic, precise and quietly menacing, and genuinely the most useful thing in your house.

**Work in progress.** This integration is replacing a set of GLaDOS scripts and automations, step by step. See [the plan](docs/PLAN.md). Today it only provides the speech cleanup.

## What it will do

- **Know the house, room by room.** Who is in which room, the air quality, open windows, heaters and coolers. Rooms and devices are found through areas and labels, never hard-coded.
- **Speak up only when it's polite.** She stays quiet when someone is in bed, before a morning alarm, in a dark bedroom, on Do Not Disturb or during a movie.
- **Sound like the games.** An opening beep, her voice, a closing beep. On birthdays, she hums.
- **Stay in character.** She controls what goes into the model's context, so her persona is never pushed out, and she cleans every reply before it's spoken.

## Install

Not released yet. When it is, you'll add this repository to Marketplace as a custom repository, install GLaDOS and restart Home Assistant. Then go to **Settings → Devices & services → Add integration → GLaDOS**.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

A local, untracked `reference/current-setup/` folder holds copies of the live prompt, scripts and automations this integration replaces.

[MIT license](LICENSE).
