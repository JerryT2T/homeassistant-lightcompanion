# Light Companion 1.0 — architecture contract

This file is the binding contract between the modules of the rebuild. Every
module owner implements exactly the interfaces below; changing an interface
means changing this file first.

## Goal

Chat or voice in a Lovelace card ("disco like the music, but dark colors")
turns into a validated **LightPlan** that a local **effect engine** plays on the
lights of one **area** (room). Music context is *read* from Music Assistant
(never controlled). One LLM call per chat command or per new track — never per
beat. Invalid LLM output never reaches a light service.

Must work for any HA installation (no apartment-specific logic). Defaults may
encode sensible conventions (e.g. auto-exclude lights whose name or area
contains "aquarium"/"terrarium").

## Package layout and owners

```
custom_components/lightcompanion/
  manifest.json            infra   version 1.0.1
  const.py                 infra   all constants + option keys + defaults
  __init__.py              infra   setup/unload, runtime_data wiring
  settings.py              infra   Settings dataclass from entry.options
  config_flow.py           infra   config + options flow
  websocket_api.py         infra   WS commands (contract below)
  panel.py                 infra   static path, card JS, hidden panel
  diagnostics.py           infra
  strings.json, translations/*.json   infra (en source; de, others)
  services.yaml            infra   (lightcompanion.chat, lightcompanion.stop)
  llm/__init__.py          ai
  llm/base.py              ai      LLMClient protocol, LLMError
  llm/ai_task.py           ai      ai_task.generate_data (+ structure)
  llm/conversation.py      ai      conversation.process fallback
  llm/http.py              ai      own-key providers: openai, anthropic, google
  llm/factory.py           ai      create_client(hass, settings)
  ai_budget.py             ai      calls-per-hour sliding window
  plan.py                  ai      LightPlan + validate_plan
  prompt.py                ai      prompt builders
  music.py                 ai      MusicService (read-only MA context)
  planner.py               ai      Planner: chat + music-follow orchestration
  lights.py                engine  area → lights, capabilities, exclusions
  ratelimit.py             engine  per-transport token buckets
  engine.py                engine  EffectEngine (patterns, restore)
  switch.py                engine  one switch per area with an active effect
  frontend/lightcompanion-card.js    frontend
  frontend/lightcompanion-panel.js   frontend
tests/                     each owner writes tests for its own modules;
                           infra owns conftest.py + pyproject/pytest config
.github/workflows/, scripts/bump_versions.py, pyproject.toml,
requirements_test.txt, hacs.json, README.md       infra
```

`addons/`, `repository.yaml` and the `ha-customapps` dependency are removed
(infra). No module imports `ha_customapps`.

## const.py (infra writes, everyone imports)

```python
DOMAIN = "lightcompanion"
VERSION = "1.0.1"            # kept in sync with manifest by scripts/bump_versions.py
PLATFORMS = [Platform.SWITCH]
FRONTEND_URL_BASE = "/lightcompanion_static"
CARD_JS = "lightcompanion-card.js"
PANEL_JS = "lightcompanion-panel.js"
PANEL_URL_PATH = "lightcompanion"
EVENT_STATUS = f"{DOMAIN}_status"   # internal dispatcher signal name

# option keys
CONF_LLM_PROVIDER = "llm_provider"      # "ai_task" | "conversation" | "openai" | "anthropic" | "google"
CONF_AI_TASK_ENTITY = "ai_task_entity"  # optional entity_id, None = default ai_task entity
CONF_CONVERSATION_AGENT = "conversation_agent"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_AI_CALLS_PER_HOUR = "ai_calls_per_hour"        # default 50, 5..200
CONF_LIGHT_RATE = "light_rate"                      # global commands/s, default 4, 1..10
CONF_ALLOW_STROBE = "allow_strobe"                  # default False
CONF_EXCLUDED_LIGHTS = "excluded_lights"            # list[entity_id], default []
CONF_EXCLUDE_KEYWORDS = "exclude_keywords"          # list[str], default ["aquarium", "terrarium"]
CONF_PLAYER_OVERRIDES = "player_overrides"          # dict[area_id, media_player entity_id]
CONF_DEFAULT_AREA = "default_area"                  # area_id | None
CONF_SHOW_PANEL = "show_panel"                      # default False

LLM_PROVIDERS = ("ai_task", "conversation", "openai", "anthropic", "google")
DEFAULT_MODELS = {"openai": "gpt-5-mini", "anthropic": "claude-haiku-4-5", "google": "gemini-2.5-flash"}
```

Exactly one LLM provider is active at a time (`CONF_LLM_PROVIDER`).

## settings.py (infra)

```python
@dataclass(frozen=True, slots=True)
class Settings:
    llm_provider: str
    ai_task_entity: str | None
    conversation_agent: str | None
    api_key: str | None
    model: str | None
    ai_calls_per_hour: int
    light_rate: int
    allow_strobe: bool
    excluded_lights: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    player_overrides: Mapping[str, str]
    default_area: str | None
    show_panel: bool

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> Settings: ...
    def public_dict(self) -> dict[str, Any]: ...   # never contains api_key; adds has_api_key
```

## runtime_data (infra wires, in __init__.py)

```python
@dataclass
class LightCompanionData:
    settings: Settings
    budget: AiBudget
    engine: EffectEngine
    music: MusicService
    planner: Planner
type LightCompanionConfigEntry = ConfigEntry[LightCompanionData]
```

Setup order: `Settings.from_options` → `AiBudget(settings.ai_calls_per_hour)`
→ `EffectEngine(hass, settings)` → `MusicService(hass, settings)` →
`Planner(hass, settings, budget, engine, music)` → `await planner.async_start()`
→ forward `switch` platform → register WS commands (once per hass) → static
path + card JS (`frontend.add_extra_js_url`, URL with `?v=VERSION`) → panel
only when `settings.show_panel`. Options update → full entry reload. Unload:
`await planner.async_stop()`, `await engine.async_stop_all(restore=True)`.
Single config entry (`single_config_entry: true` in manifest).

## lights.py (engine)

```python
@dataclass(frozen=True, slots=True)
class LightInfo:
    entity_id: str
    name: str
    area_id: str | None
    platform: str                 # entity registry platform: "hue", "zha", "mqtt", "wled", "govee_light_local", ...
    transport: str                # rate-limit class, see ratelimit.TRANSPORTS
    color_modes: tuple[str, ...]  # supported_color_modes
    supports_color: bool          # hs/rgb/rgbw/rgbww/xy
    effect_list: tuple[str, ...]
    min_kelvin: int | None
    max_kelvin: int | None
    is_group: bool                # light group / attributes.entity_id present
    excluded: bool                # by settings (explicit list or keyword in name/area name)

def async_area_lights(hass, area_id: str, settings: Settings, *, include_excluded: bool = False) -> list[LightInfo]
def async_list_areas(hass, settings: Settings) -> list[dict]
    # [{"area_id", "name", "floor_id", "floor_name", "icon", "lights": [LightInfo as dict]}]
    # only areas that have >=1 light; area resolution: entity.area_id, else device.area_id;
    # skip disabled/hidden entities; skip non-"light" domains.
def async_average_color(hass, entity_ids) -> tuple[int, int, int] | None   # brightness-weighted, on lights only
```

Transport detection: platform `hue` (covers Innr/other bulbs paired to a Hue
bridge) → `hue`; `zha` → `zigbee`; `mqtt` with a Zigbee2MQTT device → `zigbee`;
`deconz` → `zigbee`; `wled` → `wled`; `lifx` → `lifx`; `nanoleaf` → `nanoleaf`;
`govee*` → `wifi_slow`; `group`/light groups → transport of the members' most
restrictive class; anything else → `generic`.

## ratelimit.py (engine)

```python
TRANSPORTS: dict[str, TransportProfile]   # per-transport defaults:
#  hue      max_per_s=8 (bridge limit ~10/s), min_transition=0.4, prefer_group=True
#  zigbee   max_per_s=2 per group/coordinator, min_transition=0.5
#  wled     max_per_s=10, native_effects_first=True
#  lifx     max_per_s=10
#  nanoleaf max_per_s=5, native_effects_first=True
#  wifi_slow max_per_s=1, min_transition=1.0
#  generic  max_per_s=2, min_transition=0.5

class RateLimiter:
    def __init__(self, global_per_s: int) -> None
    async def acquire(self, transport: str) -> bool   # waits <= frame budget; returns False => drop this frame (never queue stale frames)
    def profile(self, transport: str) -> TransportProfile
```

The global limit (`settings.light_rate`, default 4/s) caps the sum; each
transport additionally caps its own share.

## plan.py (ai) — the LightPlan contract

LLM output (JSON object) — the `structure` handed to `ai_task` mirrors it:

```json
{
  "reply": "short answer to the user, in the user's language",
  "action": "apply" | "stop" | "none",
  "party": false,
  "follow_music": false,
  "targets": ["light.x"],                 // [] = all non-excluded lights of the area
  "palette": [[r,g,b], ...],              // 1..8 colors, 0..255
  "color_temp_kelvin": null,              // only for white static scenes
  "brightness_pct": 60,                   // 1..100
  "pattern": "static|breathe|pulse|wave|color_cycle|sparkle|strobe",
  "tempo": "slow|medium|fast",
  "intensity": 3,                         // 1..5
  "transition_s": 1.5,                    // 0..10
  "native_effects": {"light.wled": "Rainbow"}  // optional, each must be in that light's effect_list
}
```

```python
class PlanValidationError(ValueError): ...

@dataclass(frozen=True, slots=True)
class LightPlan:
    reply: str
    action: Literal["apply", "stop", "none"]
    party: bool
    follow_music: bool
    targets: tuple[str, ...]
    palette: tuple[tuple[int, int, int], ...]
    color_temp_kelvin: int | None
    brightness_pct: int
    pattern: str
    tempo: str
    intensity: int
    transition_s: float
    native_effects: Mapping[str, str]
    strobe_capped: bool = False       # set by validation when strobe was downgraded

def validate_plan(raw: Any, lights: Sequence[LightInfo], settings: Settings) -> LightPlan
```

Validation rules (all enforced, unit-tested): object type; `action` enum;
targets ⊆ given non-excluded lights (unknown → error, not silently dropped);
palette 1..8 RGB triples in range (required when `action=="apply"` and no
`color_temp_kelvin`); enums for pattern/tempo; numeric ranges clamped only
where documented (brightness, transition) else error; native effect must be in
that light's `effect_list`; **strobe policy**: `pattern=="strobe"` is allowed
only if `settings.allow_strobe and party`; otherwise downgraded to `pulse` with
`strobe_capped=True`. Any `PlanValidationError` ⇒ no service call at all.

## ai_budget.py (ai)

```python
class AiBudget:
    def __init__(self, calls_per_hour: int) -> None
    def try_spend(self) -> bool          # sliding 60-min window
    @property
    def used_last_hour(self) -> int
    @property
    def limit(self) -> int
```

## llm/ (ai)

```python
class LLMError(Exception): code: str   # "timeout" | "request_failed" | "no_answer" | "invalid_json" | "not_configured"
class LLMClient(Protocol):
    async def async_generate(self, *, task_name: str, instructions: str, schema: dict[str, Any]) -> dict[str, Any]
def create_client(hass, settings) -> LLMClient
```

`ai_task`: `hass.services.async_call("ai_task", "generate_data", {...,
"structure": <HA selector structure>}, blocking=True, return_response=True)`.
`conversation`: `conversation.process`, then strict JSON extraction (fences,
first `{` … last `}`). Own-key HTTP providers use `async_get_clientsession`,
20 s timeout, JSON mode where the API offers it. Keys never logged.

## music.py (ai) — read-only Music Assistant context

```python
@dataclass(frozen=True, slots=True)
class TrackInfo:
    player_entity_id: str
    uri: str | None            # media_content_id
    title: str | None
    artist: str | None
    album: str | None
    duration_s: float | None
    position_s: float | None
    image_url: str | None      # entity_picture (via HA proxy)
    is_playing: bool

@dataclass(frozen=True, slots=True)
class MusicProfile:            # LLM-estimated per track, cached by uri (LRU ~500)
    genre: str
    mood: str
    energy: int                # 1..5
    tempo_class: str           # slow|medium|fast
    bpm: float | None          # only from a measured source, never LLM-guessed
    bpm_source: str | None     # e.g. "music_assistant", "deezer"
    cover_palette: tuple[tuple[int, int, int], ...]   # 0..5 colors
    estimated: bool = True

class MusicService:
    def __init__(self, hass, settings) -> None
    def player_for_area(self, area_id: str) -> str | None    # override > MA media_player in area (playing first) > None
    def track(self, area_id: str) -> TrackInfo | None
    async def async_cover_palette(self, track: TrackInfo) -> tuple[tuple[int,int,int], ...]
    async def async_energy_envelope(self, track: TrackInfo) -> list[float] | None   # MA audio_analysis/wave_form, best effort
    async def async_bpm(self, track: TrackInfo) -> tuple[float, str] | None        # pluggable sources, best effort
    def async_track_listener(self, area_id: str, cb: Callable[[TrackInfo | None], None]) -> CALLBACK_TYPE
```

Never calls any media_player / music_assistant *control* service.

## planner.py (ai)

```python
@dataclass(frozen=True, slots=True)
class ChatResult:
    reply: str
    applied: bool
    plan: dict[str, Any] | None   # validated plan as dict
    error: str | None             # "rate_limited" | "invalid_plan" | LLMError.code | "no_lights" | None

class Planner:
    def __init__(self, hass, settings, budget, engine, music) -> None
    async def async_start(self) -> None
    async def async_stop(self) -> None
    async def async_chat(self, area_id: str, text: str, language: str | None) -> ChatResult
    def status(self) -> dict    # {"ai": {"used": n, "limit": m}, "follow": {area_id: {...track...}}}
```

Music follow: when a plan has `follow_music`, the planner subscribes to the
area's track listener; on a *new* track it builds a music profile (cached per
uri; one LLM call max) and re-plans by asking the LLM once, combining the
user's last chat instruction (e.g. "dark colors") with the profile. Budget
exhausted ⇒ keep the current plan running, status says `rate_limited`.
Party detection is the LLM's job (`party` field), default false.

## engine.py (engine)

```python
class EffectEngine:
    def __init__(self, hass, settings) -> None
    async def async_apply(self, area_id: str, plan: LightPlan, lights: Sequence[LightInfo], *, source: str) -> None
        # source: "chat" | "music"; stops a previous effect in that area first;
        # static pattern: one call per target (group-aware) and done;
        # dynamic patterns: one asyncio task per area, frames paced by RateLimiter,
        # tempo → frame interval (slow≈4 s, medium≈2 s, fast≈0.8 s), transition >= profile.min_transition;
        # native effects used for lights that have one in plan.native_effects;
        # strobe: only bursts of <= 8 s, then fall back to pulse for >= 30 s;
        # snapshot previous light states (scene.create with snapshot_entities) on first start per area.
    async def async_stop(self, area_id: str, *, restore: bool = True) -> None
    async def async_stop_all(self, *, restore: bool = True) -> None
    def is_active(self, area_id: str) -> bool
    def status(self) -> dict[str, dict]   # area_id -> {"active", "pattern", "palette", "source", "since", "party"}
    def async_add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE
    def update_plan_palette(...)  # not required
```

User manual changes: if a light leaves the effect (turned off by the user),
the engine stops touching it.

## switch.py (engine)

One `SwitchEntity` per area that has lights:
`switch.lightcompanion_<area_id>_effect`, name "<Area> effect",
`is_on = engine.is_active(area)`, attributes pattern/palette/source/party;
`turn_off` → `engine.async_stop(area)`; `turn_on` → re-applies the last plan
of that area if one exists (else no-op). Entities update via
`engine.async_add_listener`. Has entity name translation keys.

## Services (infra registers, planner/engine do the work)

`lightcompanion.chat` (area_id, text; response: ChatResult) and
`lightcompanion.stop` (area_id).

## WebSocket API (infra implements, frontend consumes)

All commands require auth; `settings/set` additionally `@websocket_api.require_admin`.

| type | request | result |
|---|---|---|
| `lightcompanion/areas` | – | `{"areas": [area dict from lights.async_list_areas + "player": entity_id\|null]}` |
| `lightcompanion/chat` | `area_id: str, text: str, language?: str` | ChatResult as dict |
| `lightcompanion/stop` | `area_id: str` | `{}` |
| `lightcompanion/settings/get` | – | `{"settings": Settings.public_dict(), "is_admin": bool, "providers": [...], "light_candidates": [{"entity_id","name","area"}]}` |
| `lightcompanion/settings/set` | `options: dict` (partial) | `{"settings": ...}` — validated with the same schema as the options flow, then `hass.config_entries.async_update_entry(entry, options=merged)` (reload follows) |
| `lightcompanion/subscribe` | – | subscription; sends `{"engine": engine.status(), "planner": planner.status()}` immediately and on every change |

Errors use `connection.send_error(msg_id, code, message)` with codes
`not_loaded`, `unknown_area`, `invalid_options`.

## Frontend (frontend)

* `lightcompanion-card.js` — custom element `lightcompanion-card`, registered in
  `window.customCards`, `getStubConfig()` → `{area: <first area>}`, config
  editor (area picker), sections `getGridOptions`. Plain ES module Web
  Component, no build step, no Lit dependency from CDN.
  * Header: room chips (from `lightcompanion/areas`, current area highlighted),
    switching rooms is allowed before, after or during a chat.
  * Live average color: a glow/orb computed client-side from `hass.states`
    of the area lights (brightness-weighted RGB of lights that are on; color
    temperature converted to RGB), plus small per-light dots.
  * Chat: message list (user / companion bubbles; companion reply = `reply`),
    text input, send button, mic button (Assist STT via
    `assist_pipeline/run` start/end stage `stt`, 16-bit mono PCM through an
    AudioWorklet; fallback to Web Speech API when no STT pipeline/insecure
    context), stop button when an effect runs.
  * Status line from `lightcompanion/subscribe`: pattern, source (chat/music +
    track title), AI budget `used/limit`, "rate limited" note.
  * Settings button (gear) **only on desktop** (`matchMedia("(min-width: 870px) and (hover: hover)")`
    and not narrow): opens an `ha-dialog`-style popup (own modal is fine)
    with AI provider/model/API key (password field, key never echoed),
    AI calls/hour, light commands/s, allow strobe, excluded lights (multi
    select, opt-out), exclude keywords, player override per area, default
    area, show panel. Saves via `lightcompanion/settings/set`; non-admins see
    read-only. Mobile: no gear (the options flow remains the fallback).
  * Uses HA theme CSS variables; works in light and dark themes; no
    `innerHTML` with unescaped user/LLM text (use textContent).
* `lightcompanion-panel.js` — custom element `lightcompanion-panel`; renders
  one `lightcompanion-card` full height, passes `hass`/`narrow`.
```

## Addendum A — coexisting with existing light logic

Derived from an inventory of a real installation (scenes, cinema scripts,
cleaning mode, presence sensors, Hue groups, aquarium lights); all generic.

* Options: `blocking_entities` (input_boolean/switch/binary_sensor, default
  `[]`) — while one is on, `EffectEngine.async_apply` raises
  `EffectBlockedError(entity_id)` and running effects stop with restore;
  `exclude_label` (default `lightcompanion_exclude`) — labelled lights are
  excluded like keyword/list matches.
* External changes: a light changed under a foreign `Context` (user, scene,
  script, automation) is released by the engine (`yield_light`).
* Unavailable lights are skipped; a group and its members are never driven
  both; on/off-only devices are never blinked by dynamic patterns.
* Adaptive Lighting: `adaptive_lighting.set_manual_control` during effects,
  released on stop (only if the service exists).
* Bus events: `lightcompanion_effect_started|stopped|skipped`
  (`area_id`, `pattern`, `source`, `reason`).
* Planner maps `EffectBlockedError` to `ChatResult.error == "blocked"`.

## Addendum B — pinned after wave 1

* `Planner.async_add_listener(cb) -> CALLBACK_TYPE` exists; `lightcompanion/subscribe`
  uses it (plus a 10 s refresh fallback).
* `Planner.status()` → `{"ai": {"used", "limit"}, "follow": {area_id: {"track":
  {"title","artist","album","uri","image_url","is_playing"} | null, "profile":
  {"genre","mood","energy","tempo_class","bpm","bpm_source"} | null, "error": str | null}}}`.
* `plan.normalize_raw_plan(raw)` runs before `validate_plan` (hex palette →
  RGB, JSON-stringified lists); `validate_plan` itself stays strict.
* BPM chain in `music.py`: Music Assistant `music/tracks/get` →
  `audio_metadata.bpm` (re-polled while missing) → ReccoBeats by ISRC →
  Deezer `track/isrc:`; never LLM-guessed.
