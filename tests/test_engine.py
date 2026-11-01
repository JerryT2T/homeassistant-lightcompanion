"""Tests for the effect engine (mocked light/scene services)."""

from __future__ import annotations

import asyncio
import random
import time
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.core import Context, HomeAssistant, ServiceCall

from custom_components.lightcompanion import engine as engine_mod
from custom_components.lightcompanion.engine import (
    EVENT_EFFECT_SKIPPED,
    EVENT_EFFECT_STARTED,
    EVENT_EFFECT_STOPPED,
    EffectBlockedError,
    EffectEngine,
    build_frame,
    effective_pattern,
    frame_interval,
)
from custom_components.lightcompanion.lights import LightInfo

RED = (255, 0, 0)
BLUE = (0, 0, 255)


def make_settings(**kw: Any) -> SimpleNamespace:
    base = {
        "light_rate": 100,
        "allow_strobe": False,
        "excluded_lights": (),
        "exclude_keywords": (),
        "blocking_entities": (),
    }
    base.update(kw)
    return SimpleNamespace(**base)


def make_plan(**kw: Any) -> SimpleNamespace:
    base = {
        "reply": "",
        "action": "apply",
        "party": False,
        "follow_music": False,
        "targets": (),
        "palette": (RED, BLUE),
        "color_temp_kelvin": None,
        "brightness_pct": 60,
        "pattern": "static",
        "tempo": "fast",
        "intensity": 3,
        "transition_s": 0.0,
        "native_effects": {},
        "strobe_capped": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def make_light(
    entity_id: str,
    *,
    transport: str = "lifx",
    modes: tuple[str, ...] = ("xy", "color_temp"),
    is_group: bool = False,
    excluded: bool = False,
    effects: tuple[str, ...] = (),
) -> LightInfo:
    return LightInfo(
        entity_id=entity_id,
        name=entity_id,
        area_id="living",
        platform="x",
        transport=transport,
        color_modes=modes,
        supports_color=any(m in ("xy", "rgb", "hs") for m in modes),
        effect_list=effects,
        min_kelvin=2000,
        max_kelvin=6500,
        is_group=is_group,
        excluded=excluded,
    )


class Env:
    """Registers fake services on a real hass and records the calls."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[tuple[str, str, dict[str, Any], Context]] = []
        for domain, service in (
            ("light", "turn_on"),
            ("light", "turn_off"),
            ("scene", "create"),
            ("scene", "turn_on"),
            ("scene", "delete"),
        ):
            hass.services.async_register(domain, service, self._handler)

    async def _handler(self, call: ServiceCall) -> None:
        self.calls.append((call.domain, call.service, dict(call.data), call.context))

    def of(self, domain: str, service: str) -> list[dict[str, Any]]:
        return [d for dom, svc, d, _ in self.calls if (dom, svc) == (domain, service)]

    def light_targets(self) -> list[str]:
        return [d["entity_id"] for d in self.of("light", "turn_on")]


def set_on(hass: HomeAssistant, *entity_ids: str, **attrs: Any) -> None:
    for entity_id in entity_ids:
        hass.states.async_set(entity_id, "on", attrs)


@pytest.fixture
def env(hass: HomeAssistant) -> Env:
    return Env(hass)


@pytest.fixture(autouse=True)
def fast_tempo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_mod, "TEMPO_INTERVAL_S", {"slow": 0.2, "medium": 0.1, "fast": 0.05})


# ---------------------------------------------------------------- pure logic


def test_frame_intervals_follow_tempo() -> None:
    assert frame_interval("wave", "slow", False) == 0.2
    assert frame_interval("wave", "bogus", False) == 0.1


def test_strobe_never_exceeds_three_flashes_per_second() -> None:
    for allowed in (True, False):
        interval = frame_interval("strobe", "fast", allowed)
        assert 1 / (2 * interval) <= engine_mod.MAX_FLASHES_PER_S


def test_strobe_is_downgraded_unless_allowed() -> None:
    assert effective_pattern("strobe", 0.0, False) == "pulse"
    assert effective_pattern("strobe", 1.0, True) == "strobe"


def test_strobe_bursts_at_most_eight_seconds_then_thirty_second_fallback() -> None:
    assert effective_pattern("strobe", 7.9, True) == "strobe"
    assert effective_pattern("strobe", 8.1, True) == "pulse"
    assert effective_pattern("strobe", 37.9, True) == "pulse"
    assert effective_pattern("strobe", 38.1, True) == "strobe"
    assert effective_pattern("wave", 100, True) == "wave"


def test_frames_wave_rotates_colors() -> None:
    rng = random.Random(1)
    first = [c.color_index for c in build_frame("wave", 0, 3, 3, 50, 3, rng)]
    second = [c.color_index for c in build_frame("wave", 1, 3, 3, 50, 3, rng)]
    assert first == [0, 1, 2]
    assert second == [1, 2, 0]


def test_frames_single_color_wave_modulates_brightness() -> None:
    cmds = build_frame("wave", 0, 6, 1, 80, 5, random.Random(1))
    assert len({c.brightness_pct for c in cmds}) > 1
    assert all(1 <= c.brightness_pct <= 80 for c in cmds)


def test_frames_breathe_and_pulse_alternate() -> None:
    rng = random.Random(1)
    for pattern in ("breathe", "pulse"):
        hi = build_frame(pattern, 0, 2, 2, 60, 3, rng)[0]
        lo = build_frame(pattern, 1, 2, 2, 60, 3, rng)[0]
        assert hi.brightness_pct == 60
        assert lo.brightness_pct < 60
        assert build_frame(pattern, 2, 2, 2, 60, 3, rng)[0].color_index == 1
    assert build_frame("pulse", 0, 1, 1, 60, 3, rng)[0].fast
    assert not build_frame("breathe", 0, 1, 1, 60, 3, rng)[0].fast


def test_frames_color_cycle_and_sparkle() -> None:
    assert [
        build_frame("color_cycle", s, 2, 3, 50, 3, random.Random())[0].color_index for s in range(4)
    ] == [0, 1, 2, 0]
    sparks = build_frame("sparkle", 0, 200, 4, 60, 5, random.Random(7))
    bright = [c for c in sparks if c.brightness_pct == 60]
    assert 0 < len(bright) < 200
    assert all(c.fast for c in bright)


# --------------------------------------------------------------- engine runs


async def test_static_is_one_call_per_light_and_restores(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    eng = EffectEngine(hass, make_settings())
    lights = [make_light("light.a"), make_light("light.b")]
    await eng.async_apply("living", make_plan(), lights, source="chat")
    await hass.async_block_till_done()

    calls = env.of("light", "turn_on")
    assert sorted(c["entity_id"] for c in calls) == ["light.a", "light.b"]
    # palette distributed over lights
    assert {tuple(c["rgb_color"]) for c in calls} == {RED, BLUE}
    assert len(env.of("scene", "create")) == 2  # snapshot per light
    assert eng.is_active("living")
    assert eng.status()["living"]["pattern"] == "static"

    await eng.async_stop("living")
    assert not eng.is_active("living")
    (restore,) = env.of("scene", "turn_on")
    assert sorted(restore["entity_id"]) == [
        "scene.lightcompanion_snap_a",
        "scene.lightcompanion_snap_b",
    ]
    assert len(env.of("scene", "delete")) == 1
    await asyncio.sleep(0.05)
    assert len(env.of("light", "turn_on")) == 2  # nothing after stop


async def test_stop_without_restore(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    await eng.async_stop("living", restore=False)
    assert env.of("scene", "turn_on") == []


async def test_transition_respects_transport_minimum(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.hue", "light.lifx")
    eng = EffectEngine(hass, make_settings())
    lights = [make_light("light.hue", transport="hue"), make_light("light.lifx")]
    await eng.async_apply(
        "living", make_plan(palette=(RED,), transition_s=0.0), lights, source="chat"
    )
    await hass.async_block_till_done()
    by_id = {c["entity_id"]: c for c in env.of("light", "turn_on")}
    assert by_id["light.hue"]["transition"] >= 0.4
    assert by_id["light.lifx"]["transition"] >= 0.0
    await eng.async_stop("living")


async def test_dynamic_frames_are_paced_and_dropped_not_queued(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a", "light.b")
    eng = EffectEngine(hass, make_settings(light_rate=100))
    lights = [make_light("light.a"), make_light("light.b")]
    await eng.async_apply("living", make_plan(pattern="color_cycle"), lights, source="chat")
    await asyncio.sleep(0.42)
    await eng.async_stop("living", restore=False)
    sent = len(env.of("light", "turn_on"))
    # 0.05 s frames over 0.42 s, 2 lights: ~8 frames, bounded; never a backlog
    assert 4 <= sent <= 2 * 10
    await asyncio.sleep(0.2)
    assert len(env.of("light", "turn_on")) == sent
    assert eng._runs == {}


async def test_slow_transport_frames_are_dropped(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.slow")
    eng = EffectEngine(hass, make_settings(light_rate=100))
    await eng.async_apply(
        "living",
        make_plan(pattern="color_cycle"),
        [make_light("light.slow", transport="wifi_slow")],
        source="chat",
    )
    await asyncio.sleep(0.45)
    await eng.async_stop("living", restore=False)
    # wifi_slow allows 1/s: only the first frame (static reliable send not used for dynamic)
    assert len(env.of("light", "turn_on")) <= 2


async def test_unchanged_frames_are_not_resent(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply(
        "living",
        make_plan(pattern="color_cycle", palette=(RED,)),
        [make_light("light.a")],
        source="chat",
    )
    await asyncio.sleep(0.3)
    await eng.async_stop("living", restore=False)
    assert len(env.of("light", "turn_on")) == 1


async def test_one_effect_per_area_replace_keeps_original_snapshot(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    lights = [make_light("light.a")]
    await eng.async_apply("living", make_plan(pattern="color_cycle"), lights, source="chat")
    task = eng._runs["living"].task
    await eng.async_apply("living", make_plan(pattern="breathe"), lights, source="music")
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()
    assert len(env.of("scene", "create")) == 1
    assert eng.status()["living"]["pattern"] == "breathe"
    await eng.async_stop("living")
    assert len(env.of("scene", "turn_on")) == 1


async def test_native_effect_is_used_and_not_animated(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.wled", "light.b")
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.wled", transport="wled", effects=("Rainbow",)),
        make_light("light.b"),
    ]
    plan = make_plan(pattern="color_cycle", native_effects={"light.wled": "Rainbow"})
    await eng.async_apply("living", plan, lights, source="chat")
    await asyncio.sleep(0.25)
    await eng.async_stop("living", restore=False)
    wled = [c for c in env.of("light", "turn_on") if c["entity_id"] == "light.wled"]
    assert len(wled) == 1
    assert wled[0]["effect"] == "Rainbow"


async def test_excluded_and_unavailable_lights_are_never_touched(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a", "light.fish")
    hass.states.async_set("light.gone", "unavailable")
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.a"),
        make_light("light.fish", excluded=True),
        make_light("light.gone"),
    ]
    await eng.async_apply("living", make_plan(), lights, source="chat")
    assert env.light_targets() == ["light.a"]
    await eng.async_stop("living", restore=False)


async def test_targets_limit_the_lights(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    eng = EffectEngine(hass, make_settings())
    lights = [make_light("light.a"), make_light("light.b")]
    await eng.async_apply("living", make_plan(targets=("light.b",)), lights, source="chat")
    assert env.light_targets() == ["light.b"]
    await eng.async_stop("living", restore=False)


async def test_on_off_lights_are_never_animated(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.fan")
    eng = EffectEngine(hass, make_settings())
    fan = make_light("light.fan", modes=("onoff",))
    await eng.async_apply("living", make_plan(pattern="pulse"), [fan], source="chat")
    await asyncio.sleep(0.3)
    await eng.async_stop("living", restore=False)
    calls = env.of("light", "turn_on")
    assert calls == [{"entity_id": "light.fan"}]


async def test_color_temp_plan_for_white_lamps(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.w", "light.dim")
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.w", modes=("color_temp",)),
        make_light("light.dim", modes=("brightness",)),
    ]
    plan = make_plan(palette=(), color_temp_kelvin=1000, brightness_pct=40)
    await eng.async_apply("living", plan, lights, source="chat")
    by_id = {c["entity_id"]: c for c in env.of("light", "turn_on")}
    assert by_id["light.w"]["color_temp_kelvin"] == 2000  # clamped to the lamp range
    assert by_id["light.dim"]["brightness_pct"] == 40
    assert "color_temp_kelvin" not in by_id["light.dim"]
    await eng.async_stop("living", restore=False)


async def test_stop_action_stops(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    await eng.async_apply("living", make_plan(action="stop"), [], source="chat")
    assert not eng.is_active("living")
    await eng.async_apply("living", make_plan(action="none"), [], source="chat")
    assert not eng.is_active("living")


async def test_listeners_and_last_plan(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    hits: list[int] = []
    remove = eng.async_add_listener(lambda: hits.append(1))
    plan = make_plan()
    await eng.async_apply("living", plan, [make_light("light.a")], source="chat")
    await eng.async_stop("living")
    assert len(hits) == 2
    assert eng.last("living")[0] is plan
    remove()
    await eng.async_apply("living", plan, [make_light("light.a")], source="chat")
    assert len(hits) == 2
    await eng.async_stop_all()
    assert not eng.is_active("living")


async def test_bus_events(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    events: list[tuple[str, dict]] = []
    for name in (EVENT_EFFECT_STARTED, EVENT_EFFECT_STOPPED, EVENT_EFFECT_SKIPPED):
        hass.bus.async_listen(name, lambda e: events.append((e.event_type, dict(e.data))))
    eng = EffectEngine(hass, make_settings())
    light = [make_light("light.a")]
    await eng.async_apply("living", make_plan(), light, source="chat")
    await eng.async_apply("living", make_plan(pattern="pulse"), light, source="music")
    await eng.async_stop_all()
    await hass.async_block_till_done()
    names = [(n, d.get("reason")) for n, d in events]
    assert names == [
        (EVENT_EFFECT_STARTED, None),
        (EVENT_EFFECT_STOPPED, "replaced"),
        (EVENT_EFFECT_STARTED, None),
        (EVENT_EFFECT_STOPPED, "unload"),
    ]
    assert events[2][1] == {"area_id": "living", "pattern": "pulse", "source": "music"}


# ------------------------------------------------- external change policy (1)


async def test_external_change_makes_engine_yield_that_light(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    eng = EffectEngine(hass, make_settings())
    lights = [make_light("light.a"), make_light("light.b")]
    await eng.async_apply("living", make_plan(pattern="color_cycle"), lights, source="chat")
    await asyncio.sleep(0.15)
    assert "light.a" in env.light_targets()

    # a scene/user takes over light.a (foreign context with a user)
    hass.states.async_set("light.a", "on", {"x": 1}, context=Context(user_id="u1"))
    await hass.async_block_till_done()
    env.calls.clear()
    await asyncio.sleep(0.25)
    targets = env.light_targets()
    assert "light.a" not in targets
    assert "light.b" in targets
    assert eng.is_active("living")

    # restore must not clobber the light that was taken over
    await eng.async_stop("living")
    (restore,) = env.of("scene", "turn_on")
    assert restore["entity_id"] == ["scene.lightcompanion_snap_b"]


async def test_own_context_and_device_echo_do_not_count_as_external(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply(
        "living", make_plan(pattern="color_cycle"), [make_light("light.a")], source="chat"
    )
    await asyncio.sleep(0.12)
    own = env.calls[-1][3]
    hass.states.async_set("light.a", "on", {"x": 1}, context=own)
    # bare context right after our command: device echo (e.g. Hue bridge push)
    hass.states.async_set("light.a", "on", {"x": 2}, context=Context())
    await hass.async_block_till_done()
    assert not eng._runs["living"].units[0].yielded

    # a bare context long after our last command is a real external change
    eng._quiet_until.clear()
    hass.states.async_set("light.a", "off", context=Context())
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert not eng.is_active("living")  # all lights yielded -> effect ends
    assert env.of("scene", "turn_on") == []  # and nothing is restored over the takeover


async def test_unavailable_light_does_not_end_the_effect(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply(
        "living", make_plan(pattern="color_cycle"), [make_light("light.a")], source="chat"
    )
    hass.states.async_set("light.a", "unavailable", context=Context(user_id="u"))
    await hass.async_block_till_done()
    assert eng.is_active("living")
    await eng.async_stop("living", restore=False)


# ------------------------------------------------------ blocking entities (2)


async def test_blocking_entity_refuses_apply(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    hass.states.async_set("input_boolean.sleep", "on")
    events: list[dict] = []
    hass.bus.async_listen(EVENT_EFFECT_SKIPPED, lambda e: events.append(dict(e.data)))
    eng = EffectEngine(hass, make_settings(blocking_entities=("input_boolean.sleep",)))
    with pytest.raises(EffectBlockedError) as err:
        await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    assert err.value.entity_id == "input_boolean.sleep"
    assert env.calls == []
    assert not eng.is_active("living")
    await hass.async_block_till_done()
    assert events[0]["reason"] == "blocked"


async def test_blocking_entity_off_allows_apply(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    hass.states.async_set("input_boolean.sleep", "off")
    eng = EffectEngine(hass, make_settings(blocking_entities=("input_boolean.sleep",)))
    await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    assert eng.is_active("living")
    await eng.async_stop("living", restore=False)


async def test_running_effect_stops_with_restore_when_blocker_turns_on(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a")
    hass.states.async_set("switch.cleaning", "off")
    events: list[dict] = []
    hass.bus.async_listen(EVENT_EFFECT_STOPPED, lambda e: events.append(dict(e.data)))
    eng = EffectEngine(hass, make_settings(blocking_entities=("switch.cleaning",)))
    await eng.async_apply(
        "living", make_plan(pattern="color_cycle"), [make_light("light.a")], source="chat"
    )
    hass.states.async_set("switch.cleaning", "on")
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert not eng.is_active("living")
    assert len(env.of("scene", "turn_on")) == 1
    await hass.async_block_till_done()
    assert events[-1]["reason"] == "blocked"


# ------------------------------------------------------- group handling (4)


def group_state(hass: HomeAssistant, group: str, members: list[str]) -> None:
    hass.states.async_set(group, "on", {"entity_id": members})


async def test_group_with_all_members_is_driven_as_one_call(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    group_state(hass, "light.grp", ["light.a", "light.b"])
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.a"),
        make_light("light.b"),
        make_light("light.grp", is_group=True),
    ]
    await eng.async_apply("living", make_plan(pattern="pulse"), lights, source="chat")
    await asyncio.sleep(0.4)
    await eng.async_stop("living", restore=False)
    targets = set(env.light_targets())
    assert targets == {"light.grp"}  # never group AND members


async def test_per_bulb_patterns_drive_members_not_the_group(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    group_state(hass, "light.grp", ["light.a", "light.b"])
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.a"),
        make_light("light.b"),
        make_light("light.grp", is_group=True),
    ]
    await eng.async_apply("living", make_plan(pattern="wave"), lights, source="chat")
    await asyncio.sleep(0.4)
    await eng.async_stop("living", restore=False)
    assert set(env.light_targets()) == {"light.a", "light.b"}


async def test_group_with_foreign_members_is_never_used(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b", "light.outside")
    group_state(hass, "light.grp", ["light.a", "light.b", "light.outside"])
    eng = EffectEngine(hass, make_settings())
    lights = [
        make_light("light.a"),
        make_light("light.b"),
        make_light("light.grp", is_group=True),
    ]
    await eng.async_apply("living", make_plan(pattern="pulse"), lights, source="chat")
    await asyncio.sleep(0.4)
    await eng.async_stop("living", restore=False)
    assert set(env.light_targets()) == {"light.a", "light.b"}


async def test_existing_group_covering_the_targets_is_preferred(
    hass: HomeAssistant, env: Env
) -> None:
    set_on(hass, "light.a", "light.b", "light.c")
    group_state(hass, "light.ab", ["light.a", "light.b"])
    eng = EffectEngine(hass, make_settings())
    lights = [make_light(e) for e in ("light.a", "light.b", "light.c")]
    await eng.async_apply("living", make_plan(pattern="breathe"), lights, source="chat")
    await asyncio.sleep(0.4)
    await eng.async_stop("living", restore=False)
    assert set(env.light_targets()) == {"light.ab", "light.c"}


async def test_excluded_group_entity_is_not_used_as_shortcut(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a", "light.b")
    group_state(hass, "light.ab", ["light.a", "light.b"])
    eng = EffectEngine(hass, make_settings(excluded_lights=("light.ab",)))
    lights = [make_light("light.a"), make_light("light.b")]
    await eng.async_apply("living", make_plan(), lights, source="chat")
    assert set(env.light_targets()) == {"light.a", "light.b"}
    await eng.async_stop("living", restore=False)


# ------------------------------------------------- Adaptive Lighting handoff


async def test_adaptive_lighting_manual_control_is_taken_and_released(
    hass: HomeAssistant, env: Env
) -> None:
    al_calls: list[dict] = []

    async def _al(call: ServiceCall) -> None:
        al_calls.append(dict(call.data))

    hass.services.async_register("adaptive_lighting", "set_manual_control", _al)
    set_on(hass, "light.a", "light.other")
    hass.states.async_set(
        "switch.adaptive_lighting_living", "on", {"lights": ["light.a", "light.other"]}
    )
    hass.states.async_set("switch.adaptive_lighting_sleep_mode_living", "on", {})
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    assert al_calls == [
        {
            "entity_id": "switch.adaptive_lighting_living",
            "lights": ["light.a"],
            "manual_control": True,
        }
    ]
    await eng.async_stop("living", restore=False)
    assert al_calls[-1]["manual_control"] is False
    assert len(al_calls) == 2


async def test_no_adaptive_lighting_service_is_fine(hass: HomeAssistant, env: Env) -> None:
    set_on(hass, "light.a")
    hass.states.async_set("switch.adaptive_lighting_living", "on", {"lights": ["light.a"]})
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply("living", make_plan(), [make_light("light.a")], source="chat")
    await eng.async_stop("living")


async def test_no_lights_is_a_noop(hass: HomeAssistant, env: Env) -> None:
    eng = EffectEngine(hass, make_settings())
    await eng.async_apply("living", make_plan(), [], source="chat")
    assert not eng.is_active("living")
    assert env.calls == []
    assert time.monotonic() > 0
