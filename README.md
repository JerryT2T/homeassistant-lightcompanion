# Light Companion

Home Assistant integration that turns chat or voice ("disco like the music, but dark colors") into a
validated light plan and plays it with a local effect engine on the lights of one area (room).
It can follow the music playing in that room through Music Assistant. Music Assistant is only **read**,
never controlled. The integration controls entities in the `light` domain only.

## Installation (HACS)

1. HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Add `https://github.com/Jerry0022/homeassistant-lightcompanion` as category **Integration**.
3. Download **Light Companion** and restart Home Assistant.
4. Settings -> Devices & services -> Add integration -> **Light Companion**.

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

Services: `lightcompanion.chat` (returns the reply and the applied plan) and `lightcompanion.stop`.

## Safety

- The AI answer must be strict JSON and is validated before anything is executed; invalid output never
  reaches a light service.
- One AI call per chat command or per new track, never per beat. Default limit: 50 calls per hour.
- Light commands are rate-limited per transport (default 4 per second overall).
- Strobe is off by default and only allowed in party mode when explicitly enabled.
- Lights containing "aquarium" or "terrarium" in name or area are excluded by default.

## Coexisting with your light automations

- Every area with an active effect gets a switch (`switch.lightcompanion_<area>_effect`); turn it off to
  stop the effect and restore the lights.
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
