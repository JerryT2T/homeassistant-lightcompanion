"""Effect engine: plays LightPlans on the lights of one area."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import color as color_util

from .lights import LightInfo
from .ratelimit import RateLimiter

if TYPE_CHECKING:
    from .plan import LightPlan
    from .settings import Settings

_LOGGER = logging.getLogger(__name__)

EVENT_EFFECT_STARTED = "lightcompanion_effect_started"
EVENT_EFFECT_STOPPED = "lightcompanion_effect_stopped"
EVENT_EFFECT_SKIPPED = "lightcompanion_effect_skipped"

TEMPO_INTERVAL_S: dict[str, float] = {"slow": 4.0, "medium": 2.0, "fast": 0.8}
STROBE_BURST_S = 8.0
STROBE_COOLDOWN_S = 30.0
# One flash = an "on" and an "off" frame, so the frame interval is bounded by this.
MAX_FLASHES_PER_S = 3.0
STROBE_INTERVAL_S = 0.25  # allowed (party + allow_strobe)
STROBE_SAFE_INTERVAL_S = 0.34
DYNAMIC_PATTERNS = frozenset({"breathe", "pulse", "wave", "color_cycle", "sparkle", "strobe"})
# Patterns where every light shows the same thing -> one call to a group is enough.
UNIFORM_PATTERNS = frozenset({"static", "breathe", "pulse", "color_cycle", "strobe"})
QUIET_AFTER_COMMAND_S = 2.0
RESTORE_TRANSITION_S = 1.0
MAX_OWN_CONTEXTS = 512
AL_SWITCH_PREFIX = "switch.adaptive_lighting_"
UNAVAILABLE = ("unavailable", "unknown")


class EffectBlockedError(HomeAssistantError):
    """Raised when a blocking entity (cleaning mode, sleep, ...) is on."""

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"Effect blocked by {entity_id}")
        self.entity_id = entity_id


@dataclass(frozen=True, slots=True)
class FrameCmd:
    """What one unit should show in one frame."""

    color_index: int
    brightness_pct: int
    fast: bool = False  # short transition (snappy patterns)


def effective_pattern(pattern: str, elapsed_s: float, strobe_allowed: bool) -> str:
    """Strobe policy: bursts <= 8 s, then pulse for 30 s; never when not allowed."""
    if pattern != "strobe":
        return pattern
    if not strobe_allowed:
        return "pulse"
    if elapsed_s % (STROBE_BURST_S + STROBE_COOLDOWN_S) < STROBE_BURST_S:
        return "strobe"
    return "pulse"


def frame_interval(pattern: str, tempo: str, strobe_allowed: bool) -> float:
    """Seconds between frames for the (effective) pattern."""
    if pattern == "strobe":
        base = STROBE_INTERVAL_S if strobe_allowed else STROBE_SAFE_INTERVAL_S
        return max(base, 1.0 / (2 * MAX_FLASHES_PER_S))
    return TEMPO_INTERVAL_S.get(tempo, TEMPO_INTERVAL_S["medium"])


def _depth(intensity: int) -> float:
    return min(0.9, 0.1 + 0.15 * max(1, min(5, intensity)))


def build_frame(
    pattern: str,
    step: int,
    n_units: int,
    n_colors: int,
    base_pct: int,
    intensity: int,
    rng: random.Random,
) -> list[FrameCmd]:
    """Pure frame generator (one command per unit)."""
    n_colors = max(1, n_colors)
    base = max(1, min(100, base_pct))
    low = max(1, round(base * (1 - _depth(intensity))))
    cycle, phase = divmod(step, 2)
    if pattern == "breathe":
        cmd = FrameCmd(cycle % n_colors, low if phase else base)
        return [cmd] * n_units
    if pattern == "pulse":
        cmd = FrameCmd(cycle % n_colors, low if phase else base, fast=True)
        return [cmd] * n_units
    if pattern == "strobe":
        cmd = FrameCmd(cycle % n_colors, 1 if phase else 100, fast=True)
        return [cmd] * n_units
    if pattern == "color_cycle":
        return [FrameCmd(step % n_colors, base)] * n_units
    if pattern == "wave":
        cmds = []
        for i in range(n_units):
            if n_colors > 1:
                cmds.append(FrameCmd((step + i) % n_colors, base))
            else:
                wave = 0.5 + 0.5 * math.sin(2 * math.pi * (i - step) / max(n_units, 4))
                depth = _depth(intensity)
                cmds.append(FrameCmd(0, max(1, round(base * (1 - depth * (1 - wave))))))
        return cmds
    if pattern == "sparkle":
        frac = 0.15 + 0.1 * max(1, min(5, intensity))
        dim = max(1, round(base * 0.3))
        return [
            FrameCmd(rng.randrange(n_colors), base, fast=True)
            if rng.random() < frac
            else FrameCmd(0, dim)
            for _ in range(n_units)
        ]
    return [FrameCmd(0, base)] * n_units  # static / unknown


@dataclass(eq=False)
class _Unit:
    """One thing we send commands to: a light, or a group covering members."""

    entity_id: str
    members: tuple[str, ...]
    transport: str
    supports_color: bool
    color_modes: tuple[str, ...]
    min_kelvin: int | None
    max_kelvin: int | None
    dimmable: bool
    native_effect: str | None = None
    yielded: bool = False
    last: tuple | None = None


@dataclass(eq=False)
class _Run:
    area_id: str
    plan: LightPlan
    source: str
    lights: tuple[LightInfo, ...]
    units: list[_Unit]
    started_mono: float
    since: str
    task: asyncio.Task | None = None
    snapshots: dict[str, str] = field(default_factory=dict)  # light -> scene entity
    manual_control: list[tuple[str, list[str]]] = field(default_factory=list)
    watch: dict[str, _Unit] = field(default_factory=dict)


def _dimmable(modes: Sequence[str]) -> bool:
    return any(m != "onoff" for m in modes)


class EffectEngine:
    """Plays LightPlans; at most one effect (task) per area."""

    def __init__(self, hass: HomeAssistant, settings: Settings) -> None:
        self.hass = hass
        self.settings = settings
        self._limiter = RateLimiter(settings.light_rate)
        self._runs: dict[str, _Run] = {}
        self._last: dict[str, tuple[LightPlan, tuple[LightInfo, ...], str]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[Callable[[], None]] = []
        self._own: OrderedDict[str, None] = OrderedDict()
        self._quiet_until: dict[str, float] = {}
        self._unsub_state: CALLBACK_TYPE | None = None
        self._rng = random.Random()

    # ------------------------------------------------------------------ API

    def is_active(self, area_id: str) -> bool:
        return area_id in self._runs

    def last(self, area_id: str) -> tuple[LightPlan, tuple[LightInfo, ...], str] | None:
        """Last applied plan, lights and source of an area (for switch turn_on)."""
        return self._last.get(area_id)

    def status(self) -> dict[str, dict]:
        return {
            area_id: {
                "active": True,
                "pattern": run.plan.pattern,
                "palette": [list(c) for c in run.plan.palette],
                "source": run.source,
                "since": run.since,
                "party": run.plan.party,
            }
            for area_id, run in self._runs.items()
        }

    def async_add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(cb)

        @callback
        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _remove

    async def async_apply(
        self,
        area_id: str,
        plan: LightPlan,
        lights: Sequence[LightInfo],
        *,
        source: str,
    ) -> None:
        if plan.action == "stop":
            await self.async_stop(area_id)
            return
        if plan.action != "apply":
            return
        async with self._lock(area_id):
            await self._apply_locked(area_id, plan, tuple(lights), source)

    async def async_stop(
        self, area_id: str, *, restore: bool = True, reason: str = "manual"
    ) -> None:
        async with self._lock(area_id):
            run = self._runs.pop(area_id, None)
            if run is None:
                return
            await self._teardown(run, restore=restore)
            self._after_run_removed()
            self._fire(EVENT_EFFECT_STOPPED, run, reason)
        self._notify()

    async def async_stop_all(self, *, restore: bool = True, reason: str = "unload") -> None:
        for area_id in list(self._runs):
            await self.async_stop(area_id, restore=restore, reason=reason)

    # ------------------------------------------------------------ internals

    def _lock(self, area_id: str) -> asyncio.Lock:
        return self._locks.setdefault(area_id, asyncio.Lock())

    @callback
    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Engine listener failed")

    def _fire(self, event: str, run: _Run, reason: str | None = None) -> None:
        data: dict[str, Any] = {
            "area_id": run.area_id,
            "pattern": run.plan.pattern,
            "source": run.source,
        }
        if reason is not None:
            data["reason"] = reason
        self.hass.bus.async_fire(event, data)

    def _blocking_entity(self) -> str | None:
        for entity_id in getattr(self.settings, "blocking_entities", ()) or ():
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == "on":
                return entity_id
        return None

    def _new_context(self) -> Context:
        ctx = Context()
        self._own[ctx.id] = None
        while len(self._own) > MAX_OWN_CONTEXTS:
            self._own.popitem(last=False)
        return ctx

    def _available(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in UNAVAILABLE

    # ---- unit building

    def _members(self, entity_id: str) -> list[str]:
        state = self.hass.states.get(entity_id)
        members = state.attributes.get("entity_id") if state else None
        if isinstance(members, str):
            return [members]
        if isinstance(members, (list, tuple)):
            return [m for m in members if isinstance(m, str)]
        return []

    def _unit_from_members(self, entity_id: str, infos: list[LightInfo]) -> _Unit | None:
        """Group unit from member infos; None if members differ in capability."""
        caps = {(i.supports_color, _dimmable(i.color_modes)) for i in infos}
        if len(caps) != 1:
            return None
        kelvins_min = [i.min_kelvin for i in infos if i.min_kelvin]
        kelvins_max = [i.max_kelvin for i in infos if i.max_kelvin]
        modes = tuple(sorted(set.intersection(*(set(i.color_modes) for i in infos))))
        transport = min(
            (i.transport for i in infos),
            key=lambda t: self._limiter.profile(t).max_per_s,
        )
        return _Unit(
            entity_id=entity_id,
            members=tuple(i.entity_id for i in infos),
            transport=transport,
            supports_color=infos[0].supports_color,
            color_modes=modes,
            min_kelvin=max(kelvins_min) if kelvins_min else None,
            max_kelvin=min(kelvins_max) if kelvins_max else None,
            dimmable=_dimmable(infos[0].color_modes),
        )

    @staticmethod
    def _unit_from_info(info: LightInfo) -> _Unit:
        return _Unit(
            entity_id=info.entity_id,
            members=(info.entity_id,),
            transport=info.transport,
            supports_color=info.supports_color,
            color_modes=info.color_modes,
            min_kelvin=info.min_kelvin,
            max_kelvin=info.max_kelvin,
            dimmable=_dimmable(info.color_modes),
        )

    def _build_units(self, plan: LightPlan, lights: Sequence[LightInfo]) -> list[_Unit]:
        wanted = set(plan.targets)
        cands = [
            light
            for light in lights
            if not light.excluded
            and (not wanted or light.entity_id in wanted)
            and self._available(light.entity_id)
        ]
        by_id = {light.entity_id: light for light in cands}
        uniform = plan.pattern in UNIFORM_PATTERNS and (
            plan.pattern != "static" or len(plan.palette) <= 1
        )
        native = {e: fx for e, fx in plan.native_effects.items() if e in by_id}
        units: list[_Unit] = []
        consumed: set[str] = set()

        for entity_id, effect in native.items():
            unit = self._unit_from_info(by_id[entity_id])
            unit.native_effect = effect
            units.append(unit)
            consumed.add(entity_id)
            consumed.update(self._members(entity_id))

        # Groups that are themselves candidates: group XOR members, never both.
        groups = sorted(
            (c for c in cands if c.is_group and c.entity_id not in consumed),
            key=lambda c: -len(self._members(c.entity_id)),
        )
        for group in groups:
            if group.entity_id in consumed:
                continue
            members = self._members(group.entity_id)
            if not members:
                units.append(self._unit_from_info(group))  # opaque group (e.g. Hue room)
                consumed.add(group.entity_id)
                continue
            if all(m in by_id and m not in consumed for m in members) and uniform:
                unit = self._unit_from_members(group.entity_id, [by_id[m] for m in members])
                if unit is not None:
                    units.append(unit)
                    consumed.add(group.entity_id)
                    consumed.update(members)
                    continue
            consumed.add(group.entity_id)  # drive its members individually

        rest = [c for c in cands if c.entity_id not in consumed]
        if uniform:
            units.extend(self._covering_groups(rest, consumed))
        for light in rest:
            if light.entity_id not in consumed:
                units.append(self._unit_from_info(light))
        return units

    def _covering_groups(self, rest: list[LightInfo], consumed: set[str]) -> list[_Unit]:
        """Use existing group entities whose members are all among our targets."""
        ids = {light.entity_id: light for light in rest if not light.is_group}
        found: list[tuple[str, list[str]]] = []
        for state in self.hass.states.async_all("light"):
            members = self._members(state.entity_id)
            if len(members) < 2 or state.entity_id in self.settings.excluded_lights:
                continue
            if all(m in ids for m in members):
                found.append((state.entity_id, members))
        units: list[_Unit] = []
        for group_id, members in sorted(found, key=lambda g: -len(g[1])):
            if any(m in consumed for m in members):
                continue
            unit = self._unit_from_members(group_id, [ids[m] for m in members])
            if unit is not None:
                units.append(unit)
                consumed.update(members)
        return units

    # ---- apply

    async def _apply_locked(
        self,
        area_id: str,
        plan: LightPlan,
        lights: tuple[LightInfo, ...],
        source: str,
    ) -> None:
        pattern = plan.pattern
        run_probe = _Run(area_id, plan, source, lights, [], 0.0, "")
        if (blocker := self._blocking_entity()) is not None:
            self._fire(EVENT_EFFECT_SKIPPED, run_probe, "blocked")
            raise EffectBlockedError(blocker)
        units = self._build_units(plan, lights)
        if not units:
            self._fire(EVENT_EFFECT_SKIPPED, run_probe, "no_lights")
            return

        previous = self._runs.pop(area_id, None)
        snapshots: dict[str, str] = {}
        if previous is not None:
            await self._teardown(previous, restore=False, keep_snapshots=True)
            snapshots = previous.snapshots
            self._fire(EVENT_EFFECT_STOPPED, previous, "replaced")

        run = _Run(
            area_id=area_id,
            plan=plan,
            source=source,
            lights=lights,
            units=units,
            started_mono=time.monotonic(),
            since=datetime.now(UTC).isoformat(),
            snapshots=snapshots,
        )
        for unit in units:
            run.watch[unit.entity_id] = unit
            for member in unit.members:
                run.watch[member] = unit
        self._runs[area_id] = run
        self._last[area_id] = (plan, lights, source)
        self._ensure_state_listener()

        await self._snapshot(run)
        await self._take_manual_control(run)

        palette = self._palette(plan)
        dynamic = pattern in DYNAMIC_PATTERNS
        for index, unit in enumerate(units):
            if unit.native_effect:
                data = {"entity_id": unit.entity_id, "effect": unit.native_effect}
                if unit.dimmable:
                    data["brightness_pct"] = plan.brightness_pct
                await self._send_reliable(unit, data)
            elif not dynamic or not unit.dimmable:
                # Static plans (and on/off-only lights, left as plain "on").
                idx = index % len(palette) if len(plan.palette) > 1 else 0
                data = self._light_data(
                    run,
                    unit,
                    palette[idx],
                    plan.brightness_pct,
                    max(plan.transition_s, 0.0),
                )
                await self._send_reliable(unit, data)
        if dynamic and any(u.dimmable and not u.native_effect and not u.yielded for u in units):
            run.task = self.hass.async_create_background_task(
                self._run_loop(run), f"lightcompanion_effect_{area_id}"
            )
        self._fire(EVENT_EFFECT_STARTED, run)
        self._notify()

    @staticmethod
    def _palette(plan: LightPlan) -> list[tuple[int, int, int]]:
        if plan.palette:
            return [tuple(c) for c in plan.palette]  # type: ignore[misc]
        kelvin = plan.color_temp_kelvin or 2700
        r, g, b = color_util.color_temperature_to_rgb(float(kelvin))
        return [(int(r), int(g), int(b))]

    def _light_data(
        self,
        run: _Run,
        unit: _Unit,
        rgb: tuple[int, int, int],
        brightness_pct: int,
        transition: float,
    ) -> dict[str, Any]:
        """Service data for one unit, honouring its capabilities."""
        data: dict[str, Any] = {"entity_id": unit.entity_id}
        if not unit.dimmable:
            return data  # on/off only (fans exposed as lights): never more than on
        profile = self._limiter.profile(unit.transport)
        transition = max(transition, profile.min_transition)
        data["transition"] = round(transition, 2)
        use_kelvin = not run.plan.palette and run.plan.color_temp_kelvin
        if use_kelvin and ("color_temp" in unit.color_modes or unit.supports_color):
            kelvin = int(run.plan.color_temp_kelvin or 2700)
            if unit.min_kelvin:
                kelvin = max(kelvin, unit.min_kelvin)
            if unit.max_kelvin:
                kelvin = min(kelvin, unit.max_kelvin)
            data["color_temp_kelvin"] = kelvin
            data["brightness_pct"] = max(1, min(100, brightness_pct))
        elif unit.supports_color:
            data["rgb_color"] = [int(c) for c in rgb]
            data["brightness_pct"] = max(1, min(100, brightness_pct))
        else:
            # Brightness-only / white lamp: approximate the colour by its luminance.
            scale = max(rgb) / 255 if not use_kelvin else 1.0
            data["brightness_pct"] = max(1, min(100, round(brightness_pct * scale)))
        return data

    async def _call(self, service: str, data: dict[str, Any], domain: str = "light") -> None:
        try:
            await self.hass.services.async_call(
                domain,
                service,
                data,
                blocking=False,
                context=self._new_context(),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("light.%s failed for %s: %s", service, data.get("entity_id"), err)

    def _mark_quiet(self, unit: _Unit, transition: float) -> None:
        until = time.monotonic() + transition + QUIET_AFTER_COMMAND_S
        for entity in (unit.entity_id, *unit.members):
            self._quiet_until[entity] = until

    async def _send(self, unit: _Unit, data: dict[str, Any]) -> None:
        self._mark_quiet(unit, float(data.get("transition", 0)))
        await self._call("turn_on", data)

    async def _send_reliable(self, unit: _Unit, data: dict[str, Any]) -> None:
        """Static/native commands must arrive: wait for a slot instead of dropping."""
        for _ in range(30):
            if await self._limiter.acquire(unit.transport):
                await self._send(unit, data)
                return
            await asyncio.sleep(0.2)
        _LOGGER.debug("Gave up sending to %s (rate limited)", unit.entity_id)

    # ---- frame loop

    async def _run_loop(self, run: _Run) -> None:
        plan = run.plan
        palette = self._palette(plan)
        strobe_ok = bool(getattr(self.settings, "allow_strobe", False) and plan.party)
        step = 0
        next_t = time.monotonic()
        try:
            while True:
                frame_start = time.monotonic()
                pattern = effective_pattern(plan.pattern, frame_start - run.started_mono, strobe_ok)
                interval = frame_interval(pattern, plan.tempo, strobe_ok)
                active = [
                    u for u in run.units if u.dimmable and not u.native_effect and not u.yielded
                ]
                cmds = build_frame(
                    pattern,
                    step,
                    len(active),
                    len(palette),
                    plan.brightness_pct,
                    plan.intensity,
                    self._rng,
                )
                for unit, cmd in zip(active, cmds, strict=True):
                    if time.monotonic() - frame_start > max(interval, 0.5):
                        break  # stale: drop the rest of this frame
                    if unit.yielded or not self._available(unit.entity_id):
                        continue
                    profile = self._limiter.profile(unit.transport)
                    transition = (
                        profile.min_transition
                        if cmd.fast
                        else min(
                            plan.transition_s if plan.transition_s > 0 else interval * 0.8,
                            interval,
                        )
                    )
                    data = self._light_data(
                        run,
                        unit,
                        palette[cmd.color_index % len(palette)],
                        cmd.brightness_pct,
                        transition,
                    )
                    key = tuple((k, str(v)) for k, v in sorted(data.items()) if k != "transition")
                    if key == unit.last:
                        continue
                    if not await self._limiter.acquire(unit.transport):
                        continue  # drop, never queue stale frames
                    if unit.yielded or run is not self._runs.get(run.area_id):
                        return
                    unit.last = key
                    await self._send(unit, data)
                step += 1
                next_t += interval
                delay = next_t - time.monotonic()
                if delay < 0:
                    next_t = time.monotonic()  # we are behind: skip, do not catch up
                await asyncio.sleep(max(delay, 0.0))
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Effect loop for %s crashed", run.area_id)
            self.hass.async_create_task(self.async_stop(run.area_id, restore=True, reason="error"))

    # ---- snapshot / restore / compatibility

    @staticmethod
    def _snap_scene_id(entity_id: str) -> str:
        return "lightcompanion_snap_" + entity_id.split(".", 1)[1]

    async def _snapshot(self, run: _Run) -> None:
        """Snapshot every driven light once per area (one scene per light)."""
        if not self.hass.services.has_service("scene", "create"):
            return
        entities: list[str] = []
        for unit in run.units:
            entities.extend(unit.members)
        for entity_id in dict.fromkeys(entities):
            if entity_id in run.snapshots:
                continue
            scene_id = self._snap_scene_id(entity_id)
            try:
                await self.hass.services.async_call(
                    "scene",
                    "create",
                    {"scene_id": scene_id, "snapshot_entities": [entity_id]},
                    blocking=True,
                    context=self._new_context(),
                )
                run.snapshots[entity_id] = f"scene.{scene_id}"
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Snapshot of %s failed: %s", entity_id, err)

    def _adaptive_switches(self, entity_ids: set[str]) -> list[tuple[str, list[str]]]:
        found: list[tuple[str, list[str]]] = []
        for state in self.hass.states.async_all("switch"):
            if not state.entity_id.startswith(AL_SWITCH_PREFIX):
                continue
            covered = state.attributes.get("lights")
            if not isinstance(covered, (list, tuple)):
                continue
            overlap = [e for e in covered if e in entity_ids]
            if overlap:
                found.append((state.entity_id, overlap))
        return found

    async def _set_manual_control(self, items: list[tuple[str, list[str]]], value: bool) -> None:
        for switch_id, lights in items:
            try:
                await self.hass.services.async_call(
                    "adaptive_lighting",
                    "set_manual_control",
                    {"entity_id": switch_id, "lights": lights, "manual_control": value},
                    blocking=True,
                    context=self._new_context(),
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("adaptive_lighting manual control failed: %s", err)

    async def _take_manual_control(self, run: _Run) -> None:
        """Keep Adaptive Lighting (if installed) from fighting our colours."""
        if not self.hass.services.has_service("adaptive_lighting", "set_manual_control"):
            return
        entity_ids = {m for u in run.units for m in u.members} | {u.entity_id for u in run.units}
        run.manual_control = self._adaptive_switches(entity_ids)
        await self._set_manual_control(run.manual_control, True)

    async def _teardown(self, run: _Run, *, restore: bool, keep_snapshots: bool = False) -> None:
        if run.task is not None:
            run.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run.task
            run.task = None
        if self.hass.services.has_service("adaptive_lighting", "set_manual_control"):
            await self._set_manual_control(run.manual_control, False)
        if run.snapshots and not keep_snapshots:
            await self._finish_snapshots(run, restore)

    async def _finish_snapshots(self, run: _Run, restore: bool) -> None:
        yielded = {m for u in run.units if u.yielded for m in (u.entity_id, *u.members)}
        if restore:
            scenes = [s for e, s in run.snapshots.items() if e not in yielded]
            if scenes:
                try:
                    await self.hass.services.async_call(
                        "scene",
                        "turn_on",
                        {"entity_id": scenes, "transition": RESTORE_TRANSITION_S},
                        blocking=True,
                        context=self._new_context(),
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Restore failed: %s", err)
        if self.hass.services.has_service("scene", "delete"):
            scenes = list(run.snapshots.values())
            with contextlib.suppress(Exception):
                await self.hass.services.async_call(
                    "scene",
                    "delete",
                    {"entity_id": scenes},
                    blocking=True,
                    context=self._new_context(),
                )
        run.snapshots = {}

    # ---- external changes

    def _after_run_removed(self) -> None:
        if not self._runs and self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None

    def _ensure_state_listener(self) -> None:
        if self._unsub_state is None:
            self._unsub_state = self.hass.bus.async_listen(
                EVENT_STATE_CHANGED, self._handle_state_changed
            )

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        if new is None or entity_id is None:
            return
        if entity_id in (getattr(self.settings, "blocking_entities", ()) or ()):
            if new.state == "on":
                for area_id in list(self._runs):
                    self.hass.async_create_task(
                        self.async_stop(area_id, restore=True, reason="blocked")
                    )
            return
        if old is None or new.state in UNAVAILABLE or old.state in UNAVAILABLE:
            return
        ctx = event.context
        if ctx.id in self._own:
            return
        if (
            ctx.user_id is None
            and ctx.parent_id is None
            and time.monotonic() < self._quiet_until.get(entity_id, 0.0)
        ):
            return  # device echo of our own command (e.g. Hue bridge push)
        for run in list(self._runs.values()):
            unit = run.watch.get(entity_id)
            if unit is None or unit.yielded:
                continue
            unit.yielded = True  # a user/scene/automation took over: hands off
            reason = "manual" if ctx.user_id else "external_change"
            self._fire(EVENT_EFFECT_SKIPPED, run, reason)
            if all(u.yielded for u in run.units):
                self.hass.async_create_task(
                    self.async_stop(run.area_id, restore=False, reason=reason)
                )
