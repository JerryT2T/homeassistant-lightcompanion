"""LightPlan contract and the strict validator (the safety core).

Nothing the LLM says reaches a light service unless ``validate_plan`` accepts it.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .lights import LightInfo
    from .settings import Settings

ACTIONS = ("apply", "stop", "none")
PATTERNS = ("static", "breathe", "pulse", "wave", "color_cycle", "sparkle", "strobe")
TEMPOS = ("slow", "medium", "fast")
MAX_PALETTE = 8
MIN_KELVIN = 1000
MAX_KELVIN = 10000
MAX_REPLY = 600

DEFAULT_BRIGHTNESS = 60
DEFAULT_INTENSITY = 3
DEFAULT_TRANSITION = 1.5

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


class PlanValidationError(ValueError):
    """The LLM answer is not an acceptable plan; apply nothing."""


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
    native_effects: Mapping[str, str] = field(default_factory=dict)
    strobe_capped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "action": self.action,
            "party": self.party,
            "follow_music": self.follow_music,
            "targets": list(self.targets),
            "palette": [list(c) for c in self.palette],
            "color_temp_kelvin": self.color_temp_kelvin,
            "brightness_pct": self.brightness_pct,
            "pattern": self.pattern,
            "tempo": self.tempo,
            "intensity": self.intensity,
            "transition_s": self.transition_s,
            "native_effects": dict(self.native_effects),
            "strobe_capped": self.strobe_capped,
        }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_int(value: Any, name: str) -> int:
    """Integral number (int or integral float) or error."""
    if not _is_number(value) or math.isnan(value) or value in (float("inf"), float("-inf")):
        raise PlanValidationError(f"{name} must be a number")
    if int(value) != value:
        raise PlanValidationError(f"{name} must be a whole number")
    return int(value)


def _bool(raw: Mapping[str, Any], name: str) -> bool:
    value = raw.get(name, False)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise PlanValidationError(f"{name} must be a boolean")
    return value


def _enum(raw: Mapping[str, Any], name: str, allowed: Sequence[str], default: str) -> str:
    value = raw.get(name)
    if value is None:
        return default
    if not isinstance(value, str) or value not in allowed:
        raise PlanValidationError(f"{name} must be one of {', '.join(allowed)}")
    return value


def normalize_raw_plan(raw: Any) -> Any:
    """Make provider quirks uniform before validation (no leniency on values).

    Accepts hex colors (``#ff8800``) in the palette, JSON-encoded strings for the
    list/object fields (some providers stringify them) and ``null`` placeholders.
    Anything it cannot convert is left untouched for the validator to reject.
    """
    if not isinstance(raw, Mapping):
        return raw
    out = dict(raw)
    for key in ("palette", "targets", "native_effects"):
        value = out.get(key)
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                out[key] = json.loads(value)
    palette = out.get("palette")
    if isinstance(palette, list):
        converted: list[Any] = []
        for item in palette:
            match = _HEX.match(item) if isinstance(item, str) else None
            if match:
                h = match.group(1)
                converted.append([int(h[i : i + 2], 16) for i in (0, 2, 4)])
            else:
                converted.append(item)
        out["palette"] = converted
    if out.get("native_effects") in ([], ""):
        out["native_effects"] = {}
    return out


def _palette(raw: Mapping[str, Any]) -> tuple[tuple[int, int, int], ...]:
    value = raw.get("palette")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise PlanValidationError("palette must be a list of RGB triples")
    if len(value) > MAX_PALETTE:
        raise PlanValidationError(f"palette has more than {MAX_PALETTE} colors")
    colors: list[tuple[int, int, int]] = []
    for color in value:
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            raise PlanValidationError("palette entries must be [r, g, b]")
        r, g, b = (_as_int(c, "palette channel") for c in color)
        if not all(0 <= c <= 255 for c in (r, g, b)):
            raise PlanValidationError("palette channel out of range 0..255")
        colors.append((r, g, b))
    return tuple(colors)


def validate_plan(  # noqa: PLR0912, PLR0915 - one linear rule list, kept in one place
    raw: Any, lights: Sequence[LightInfo], settings: Settings
) -> LightPlan:
    """Return a safe :class:`LightPlan` or raise :class:`PlanValidationError`."""
    if not isinstance(raw, Mapping):
        raise PlanValidationError("plan must be a JSON object")

    action = raw.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise PlanValidationError("action must be apply, stop or none")

    reply = raw.get("reply", "")
    if reply is None:
        reply = ""
    if not isinstance(reply, str):
        raise PlanValidationError("reply must be a string")
    reply = reply.strip()[:MAX_REPLY]

    party = _bool(raw, "party")
    follow_music = _bool(raw, "follow_music")

    allowed = {light.entity_id: light for light in lights if not light.excluded}

    targets_raw = raw.get("targets")
    targets: list[str] = []
    if targets_raw is not None:
        if not isinstance(targets_raw, (list, tuple)):
            raise PlanValidationError("targets must be a list of entity ids")
        for target in targets_raw:
            if not isinstance(target, str) or target not in allowed:
                raise PlanValidationError(f"unknown or excluded target: {target!r}")
            if target not in targets:
                targets.append(target)

    palette = _palette(raw)

    kelvin_raw = raw.get("color_temp_kelvin")
    kelvin: int | None = None
    if kelvin_raw is not None:
        kelvin = _as_int(kelvin_raw, "color_temp_kelvin")
        if not MIN_KELVIN <= kelvin <= MAX_KELVIN:
            raise PlanValidationError("color_temp_kelvin out of range")

    if action == "apply" and not palette and kelvin is None:
        raise PlanValidationError("apply needs a palette or color_temp_kelvin")

    brightness_raw = raw.get("brightness_pct", DEFAULT_BRIGHTNESS)
    if not _is_number(brightness_raw) or math.isnan(brightness_raw):
        raise PlanValidationError("brightness_pct must be a number")
    brightness = max(1, min(100, round(brightness_raw)))

    transition_raw = raw.get("transition_s", DEFAULT_TRANSITION)
    if not _is_number(transition_raw) or math.isnan(transition_raw):
        raise PlanValidationError("transition_s must be a number")
    transition = float(max(0.0, min(10.0, transition_raw)))

    intensity_raw = raw.get("intensity")
    intensity = DEFAULT_INTENSITY if intensity_raw is None else _as_int(intensity_raw, "intensity")
    if not 1 <= intensity <= 5:
        raise PlanValidationError("intensity must be 1..5")

    pattern = _enum(raw, "pattern", PATTERNS, "static")
    tempo = _enum(raw, "tempo", TEMPOS, "medium")

    strobe_capped = False
    if pattern == "strobe" and not (settings.allow_strobe and party):
        pattern = "pulse"
        strobe_capped = True

    effects_raw = raw.get("native_effects")
    native: dict[str, str] = {}
    if effects_raw:
        if not isinstance(effects_raw, Mapping):
            raise PlanValidationError("native_effects must be an object")
        for entity_id, effect in effects_raw.items():
            light = allowed.get(entity_id) if isinstance(entity_id, str) else None
            if light is None:
                raise PlanValidationError(f"native effect for unknown light: {entity_id!r}")
            if targets and entity_id not in targets:
                raise PlanValidationError(f"native effect for non-target light: {entity_id}")
            if not isinstance(effect, str) or effect not in light.effect_list:
                raise PlanValidationError(f"effect not supported by {entity_id}: {effect!r}")
            native[entity_id] = effect

    return LightPlan(
        reply=reply,
        action=action,  # type: ignore[arg-type]
        party=party,
        follow_music=follow_music,
        targets=tuple(targets),
        palette=palette,
        color_temp_kelvin=kelvin,
        brightness_pct=brightness,
        pattern=pattern,
        tempo=tempo,
        intensity=intensity,
        transition_s=transition,
        native_effects=native,
        strobe_capped=strobe_capped,
    )
