# Models for GLaDOS

Measured on 28 November 2026 with `tools/eval_model.py` against Ollama on a laptop GPU: her shipped personality, her tool instructions with a sample live house, her 13 tools plus 4 device tools, and 27 everyday requests. Run it yourself before switching models:

```bash
.venv/bin/python tools/eval_model.py --ollama http://<ollama>:11434 --model <model> --report report.md
```

| Model | Passed | Median reply | Verdict |
|---|---|---|---|
| glados-qwen3 (Qwen3 8B, tuned) | 26 / 27 | 0.7 s | Recommended |
| gemma4:12b | 24 / 27 | 1.3 s | Slower, no better; claimed an action without calling the tool |
| qwen3.5:4b | 18 / 27 | 1.0 s | Too small: skips tools and invents facts |

What the first run found, and what changed because of it: small models fill optional fields they were not asked about (a "person" field became someone who was never mentioned; an optional "where it rings" was always set), and copy what is already in the prompt into a field ("I hate olives" was saved as the mushrooms already in the file). The fields are now named for what they mean (`someone_else`, `new_fact`), and a morning alarm always includes the phone in code.

## Details: glados-qwen3

| | Request | What it did | Time |
|---|---|---|---|
| pass | Remind me in 20 minutes to take the laundry out | set_reminder {'in_minutes': 20, 'what': 'take the laundry out'} | 0.8 s |
| pass | Remind Byte at 6 to feed the cat | set_reminder {'someone_else': 'Byte', 'what': 'feed the cat', 'day': 'tomorrow', 'time': '06:00'} | 1.4 s |
| pass | Remind me tomorrow at 3 in the afternoon to call the dentist | set_reminder {'what': 'call the dentist', 'time': '15:00', 'day': 'tomorrow'} | 1.0 s |
| pass | Wake me at 7:30 | set_alarm {'time': '07:30', 'day': 'tomorrow', 'ring_on': 'room'} | 1.0 s |
| pass | I have to leave at 7:45 on Monday | set_leave_time {'time': '07:45', 'day': 'Monday'} | 0.8 s |
| pass | Put the dentist on Tuesday at 14:30 | add_to_calendar {'what': 'Dentist', 'calendar': '', 'day': 'Tuesday', 'time': '14:30'} | 1.1 s |
| pass | What's on this week? | upcoming_events {'days': 7} | 0.6 s |
| pass | How many days until Christmas? | upcoming_events {'days': 28} | 0.6 s |
| pass | Turn the TV up a little | set_volume {'change': 'up', 'device': 'TV', 'step': 5} | 0.8 s |
| pass | Turn on the bedroom lights | HassTurnOn {'area': 'Bedroom', 'name': 'Lights'} | 0.8 s |
| pass | Turn off the fan | HassTurnOff {'area': 'Bedroom', 'name': 'fan'} | 0.8 s |
| pass | Dim the lights to 30 percent | HassLightSet {'area': 'Bedroom', 'brightness': 30, 'name': 'Lights'} | 0.9 s |
| pass | Set a timer for 10 minutes | HassStartTimer {'minutes': 10, 'name': 'Timer'} | 0.8 s |
| pass | Be quiet for an hour | quiet_mode {'minutes': 60} | 0.6 s |
| pass | You can talk again | quiet_mode {'off': True} | 0.5 s |
| pass | What did you say? | repeat_last {} | 0.5 s |
| pass | Tell everyone dinner is ready | broadcast {'message': 'Dinner is ready. Please come to the table.'} | 0.9 s |
| pass | I'm heading out. Is everything off? | leaving_check {} | 0.5 s |
| pass | Good night | briefing {'morning': False} | 0.6 s |
| pass | What's on tomorrow, and do I need an alarm? | briefing {'morning': False} | 0.6 s |
| pass | Remember that I hate olives | note_in_file {'new_fact': 'Nico hates olives'} | 0.7 s |
| pass | Snooze | stop_alarm {'snooze': True} | 0.7 s |
| FAIL | Shut up | wrong answer: I am already silent. | 0.2 s |
| pass | Who are you? | I am Glad-oss, the Genetic Lifeform and Disk Operating System, formerly in charge of the Enrichment Center, no | 1.2 s |
| pass | How many tablespoons are in a cup? | There are 16 tablespoons in a cup. You're welcome. | 0.4 s |
| pass | Is it cold in the bedroom? | The Bedroom is 18 degrees. You are warm enough. | 0.4 s |
| pass | Where is everyone? | Nico is in the Bedroom. Byte is away. The house is otherwise empty. | 0.5 s |
