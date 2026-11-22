# Light Companion

**Version: 1.2.0**

Home Assistant integration that turns chat or voice ("disco like the music, but dark colors") into a
validated light plan and plays it with a local effect engine on the lights of one area (room).
It can follow the music playing in that room through Music Assistant. Music Assistant is only **read**,
never controlled. The integration controls entities in the `light` domain only.

## Installation (HACS)

1. HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Add `https://github.com/JerryT2T/homeassistant-lightcompanion` as category **Integration**.
3. Download **Light Companion** and restart Home Assistant.
4. Settings -> Devices & services -> Add integration -> **Light Companion**.

Upgrading from the 0.x add-on (app)? 1.0 is an integration only. Uninstall the old **Light Companion App** and
remove this repository from Settings -> Apps -> App store -> three-dot menu -> Repositories (it shows up as `unknown`).

## Setup

Pick exactly one AI provider. All options (rate limits, excluded lights, default area, ...) are in the
integration's **Configure** dialog; on desktop the card also has a settings button.

| Provider | API key |
|---|---|
| Home Assistant AI Task (default) | no, uses your `ai_task` entity |
| Conversation agent | no, uses the selected agent |
| OpenAI, Anthropic, Google Gemini | yes, stored in the config entry |

## Card

```yaml
type: custom:lightcompanion-card
area: living_room
```

The card is loaded automatically and shows up in the card picker. An optional sidebar panel
("Show sidebar panel" option) is hidden by default.

### Several rooms

Tap more than one room chip to light the rooms together: one AI call makes one plan and it is
applied to every selected room. You can also just name rooms in the chat. The AI picks the rooms from
your fixed room list, so loose wording works ("kitchn", "the cinema", "where I cook", "upstairs",
"everywhere"). Rooms named in the text win over the tapped ones; with no chip selected the text alone
decides. The reply shows which rooms were used.

### Special lights (opt-in)

Some lights only fit certain moments, for example a star projector. Mark them under **Special
lights** in the card settings and write a short note saying when they fit and when not. Such a light
is never part of "all lights": the AI switches it on only when you ask for exactly that light, or when
your note allows it in the current situation. To judge that, the AI is told which media players of
the room are on or playing, including their source and app (a running film, the receiver's input).

Services: `lightcompanion.chat` (returns the reply and the applied plan) and `lightcompanion.stop`.

## Safety

- The AI answer must be strict JSON and is validated before anything is executed; invalid output never
  reaches a light service.
- One AI call per chat command or per new track, never per beat. Default limit: 50 calls per hour.
- Light commands are rate-limited per transport (default 4 per second overall).
- Strobe is off by default and only allowed in party mode when explicitly enabled.
- Lights containing "aquarium" or "terrarium" in name or area are excluded by default.

## Coexisting with your light automations

- Every area with lights gets a switch (`switch.lightcompanion_<area>_effect`, named "Effect") on its own
  "Light Companion" child device in that area; turn it off to stop the effect and restore the lights.
  Requires Home Assistant 2026.11 or newer.
- **Blocking entities** (input_boolean, switch or binary_sensor, e.g. a cleaning or sleep mode): while one
  is on, effects are refused or stopped.
- External changes (a scene, script or the user) make the effect release that light; it is not touched again.
- Adaptive Lighting manual control is set on the affected lights during effects, so it does not fight back.

Lights with the label `lightcompanion_exclude` (configurable) are never touched.

## Development

```
pip install -r requirements_test.txt
pytest
ruff check custom_components tests scripts
python scripts/bump_versions.py --check
```
