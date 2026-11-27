# GLaDOS add-ons

GLaDOS works on her own: she needs a chat agent and nothing else. Anything that depends on another integration, such as train times, a vacuum or a doorbell, is an **add-on**: its own integration, in its own repository, installed through HACS next to GLaDOS. A home without trains never sees train code.

An add-on gets three things from GLaDOS, and reuses her instead of copying her:

| It can add | How |
|---|---|
| Tools she can use | `tools`: a function that returns tool objects, usually subclasses of `GladosTool` |
| Lines in her tool instructions | `prompt`: a function that returns a short paragraph |
| A background job | `start`: a function that starts it and returns its stop function. It runs while GLaDOS is loaded |

And it can use her parts:

| Part | What it does |
|---|---|
| `async_announce(hass, AnnounceRequest(...))` | Speaks in the right room, with her quiet rules, both voices and the beeps |
| `glados_data(hass)` | Her running data: settings (`options`), memory (`memory.get/set/age`) |
| `GladosTool` | A tool base class: arguments validated against `parameters`, then `run(hass, args, llm_context)` |
| `spoken_date`, `days_away`, `resolve_moment`, `parse_time` | Dates worked out in Python, ready to read aloud |
| `clean_for_speech` | Text made safe for the voice |
| `people_home`, `person_area`, `phones` | Who is home, the room they are in, their phones' notify entities |

Only what `custom_components.glados.addon` exports is the stable interface (`API_VERSION = 1`). Everything else in GLaDOS can change between versions.

## A minimal add-on

`custom_components/glados_trains/manifest.json`:

```json
{
  "domain": "glados_trains",
  "name": "GLaDOS trains",
  "config_flow": true,
  "dependencies": ["glados"],
  "version": "0.1.0"
}
```

`custom_components/glados_trains/__init__.py`:

```python
from homeassistant.helpers import llm
import probatio as p

from custom_components.glados.addon import Addon, GladosTool, async_register_addon


class NextTrain(GladosTool):
    name = "next_train"
    description = "When the next train leaves, and when to leave home for it."
    parameters = p.Schema({})

    async def run(self, hass, args, llm_context):
        return llm.ToolResult(data={"departs": "08:12", "leave_home": "07:57"})


async def async_setup_entry(hass, entry):
    entry.async_on_unload(
        async_register_addon(
            hass,
            Addon(
                domain="glados_trains",
                name="Trains",
                tools=lambda data: [NextTrain(data)],
                prompt=lambda hass: "For anything about trains, use the train tools.",
            ),
        )
    )
    return True


async def async_unload_entry(hass, entry):
    return True
```

The add-on's tools appear in her own LLM API (the **GLaDOS** option under the chat agent's **Control Home Assistant**), marked with the add-on's domain. Removing the add-on removes them.

## Rules that keep her herself

- **Return facts, not prose.** Tools return the data spelled out ("08:12", "in 3 days"); she phrases it. Never make the model calculate a date.
- **Set pieces for what must land.** A warning or a "leave now" uses fixed lines, built on the games' patterns, not improvised ones.
- **Speak through `async_announce`.** Then the quiet rules (sleep, Do Not Disturb, a video) and the speaking schedule hold for the add-on too.
- **No hard-coded entities.** Find things through settings, areas and labels.
