"""Area -> lights resolution, capabilities, transport detection, exclusions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)
from homeassistant.util import color as color_util

from .ratelimit import DEFAULT_TRANSPORT, TRANSPORTS

if TYPE_CHECKING:
    from .settings import Settings

LIGHT_DOMAIN = "light"
COLOR_MODES = frozenset({"hs", "rgb", "rgbw", "rgbww", "xy"})


@dataclass(frozen=True, slots=True)
class LightInfo:
    """Static description of one light entity."""

    entity_id: str
    name: str
    area_id: str | None
    platform: str
    transport: str
    color_modes: tuple[str, ...]
    supports_color: bool
    effect_list: tuple[str, ...]
    min_kelvin: int | None
    max_kelvin: int | None
    is_group: bool
    excluded: bool


def _restrictiveness(transport: str) -> float:
    return TRANSPORTS.get(transport, TRANSPORTS[DEFAULT_TRANSPORT]).max_per_s


def _platform_transport(
    platform: str, device: dr.DeviceEntry | None = None
) -> str | None:
    """Map an entity-registry platform to a transport class (None = unknown)."""
    if platform == "hue":
        return "hue"
    if platform in ("zha", "deconz"):
        return "zigbee"
    if platform == "mqtt":
        if device is not None and any(
            str(ident[0]) == "mqtt" and "zigbee2mqtt" in str(ident[1]).lower()
            for ident in device.identifiers
        ):
            return "zigbee"
        return None
    if platform in ("wled", "lifx", "nanoleaf"):
        return platform
    if platform.startswith("govee"):
        return "wifi_slow"
    return None


def _members(hass: HomeAssistant, entity_id: str) -> list[str]:
    state = hass.states.get(entity_id)
    members = state.attributes.get("entity_id") if state else None
    if isinstance(members, str):
        return [members]
    if isinstance(members, (list, tuple)):
        return [m for m in members if isinstance(m, str)]
    return []


def detect_transport(
    hass: HomeAssistant,
    entity_id: str,
    ent_reg: er.EntityRegistry,
    dev_reg: dr.DeviceRegistry,
    _seen: frozenset[str] = frozenset(),
) -> str:
    """Return the rate-limit class of a light; groups use the most restrictive member."""
    entry = ent_reg.async_get(entity_id)
    platform = entry.platform if entry else ""
    device = dev_reg.async_get(entry.device_id) if entry and entry.device_id else None
    direct = _platform_transport(platform, device)
    members = [m for m in _members(hass, entity_id) if m not in _seen]
    if platform == "group" or (direct is None and members):
        classes = [
            detect_transport(hass, m, ent_reg, dev_reg, _seen | {entity_id})
            for m in members
        ]
        if classes:
            return min(classes, key=_restrictiveness)
    return direct or DEFAULT_TRANSPORT


def _has_exclude_label(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    dev_reg: dr.DeviceRegistry,
    settings: Settings,
) -> bool:
    """True if the entity (or its device) carries the exclusion label."""
    wanted = str(getattr(settings, "exclude_label", "lightcompanion_exclude") or "")
    wanted = wanted.strip().lower()
    if not wanted:
        return False
    label_ids = set(entry.labels)
    if entry.device_id and (device := dev_reg.async_get(entry.device_id)):
        label_ids |= set(device.labels)
    label_reg = lr.async_get(hass)
    for label_id in label_ids:
        if label_id.lower() == wanted:
            return True
        label = label_reg.async_get_label(label_id)
        if label is not None and label.name.strip().lower() == wanted:
            return True
    return False


def _is_excluded(
    settings: Settings,
    entity_id: str,
    name: str,
    area_name: str | None,
    labeled: bool = False,
) -> bool:
    if labeled or entity_id in settings.excluded_lights:
        return True
    haystack = " ".join((name, entity_id, area_name or "")).lower()
    return any(
        kw.strip().lower() in haystack
        for kw in settings.exclude_keywords
        if kw and kw.strip()
    )


def _build_info(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    area_id: str | None,
    area_name: str | None,
    settings: Settings,
    ent_reg: er.EntityRegistry,
    dev_reg: dr.DeviceRegistry,
) -> LightInfo:
    state = hass.states.get(entry.entity_id)
    attrs: dict[str, Any] = dict(state.attributes) if state else {}
    name = (
        attrs.get("friendly_name")
        or entry.name
        or entry.original_name
        or entry.entity_id
    )
    modes = tuple(str(m) for m in (attrs.get(ATTR_SUPPORTED_COLOR_MODES) or ()))
    min_k = attrs.get("min_color_temp_kelvin")
    max_k = attrs.get("max_color_temp_kelvin")
    return LightInfo(
        entity_id=entry.entity_id,
        name=str(name),
        area_id=area_id,
        platform=entry.platform,
        transport=detect_transport(hass, entry.entity_id, ent_reg, dev_reg),
        color_modes=modes,
        supports_color=bool(COLOR_MODES.intersection(modes)),
        effect_list=tuple(str(e) for e in (attrs.get("effect_list") or ())),
        min_kelvin=int(min_k) if min_k else None,
        max_kelvin=int(max_k) if max_k else None,
        is_group="entity_id" in attrs or entry.platform == "group",
        excluded=_is_excluded(
            settings,
            entry.entity_id,
            str(name),
            area_name,
            _has_exclude_label(hass, entry, dev_reg, settings),
        ),
    )


def _iter_light_entries(
    ent_reg: er.EntityRegistry,
) -> Iterable[er.RegistryEntry]:
    for entry in ent_reg.entities.values():
        if entry.domain != LIGHT_DOMAIN:
            continue
        if entry.disabled_by is not None or entry.hidden_by is not None:
            continue
        yield entry


def _resolve_area(
    entry: er.RegistryEntry, dev_reg: dr.DeviceRegistry
) -> str | None:
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        device = dev_reg.async_get(entry.device_id)
        if device:
            return device.area_id
    return None


@callback
def async_area_lights(
    hass: HomeAssistant,
    area_id: str,
    settings: Settings,
    *,
    include_excluded: bool = False,
) -> list[LightInfo]:
    """Return the lights of an area (excluded ones only when asked for)."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area = ar.async_get(hass).async_get_area(area_id)
    area_name = area.name if area else None
    result: list[LightInfo] = []
    for entry in _iter_light_entries(ent_reg):
        if _resolve_area(entry, dev_reg) != area_id:
            continue
        info = _build_info(hass, entry, area_id, area_name, settings, ent_reg, dev_reg)
        if info.excluded and not include_excluded:
            continue
        result.append(info)
    result.sort(key=lambda i: (i.name.lower(), i.entity_id))
    return result


@callback
def async_list_areas(hass: HomeAssistant, settings: Settings) -> list[dict[str, Any]]:
    """List areas that have at least one light (excluded lights flagged)."""
    area_reg = ar.async_get(hass)
    floor_reg = fr.async_get(hass)
    area_ids = {
        a
        for entry in _iter_light_entries(er.async_get(hass))
        if (a := _resolve_area(entry, dr.async_get(hass)))
    }
    areas: list[dict[str, Any]] = []
    for area_id in area_ids:
        area = area_reg.async_get_area(area_id)
        if area is None:
            continue
        lights = async_area_lights(hass, area_id, settings, include_excluded=True)
        if not lights:
            continue
        floor = floor_reg.async_get_floor(area.floor_id) if area.floor_id else None
        areas.append(
            {
                "area_id": area_id,
                "name": area.name,
                "floor_id": area.floor_id,
                "floor_name": floor.name if floor else None,
                "icon": area.icon,
                "lights": [asdict(light) for light in lights],
            }
        )
    areas.sort(key=lambda a: a["name"].lower())
    return areas


def _state_rgb(attrs: dict[str, Any]) -> tuple[int, int, int] | None:
    rgb = attrs.get("rgb_color")
    if rgb:
        return int(rgb[0]), int(rgb[1]), int(rgb[2])
    hs = attrs.get("hs_color")
    if hs:
        r, g, b = color_util.color_hs_to_RGB(float(hs[0]), float(hs[1]))
        return r, g, b
    xy = attrs.get("xy_color")
    if xy:
        r, g, b = color_util.color_xy_to_RGB(float(xy[0]), float(xy[1]))
        return r, g, b
    kelvin = attrs.get("color_temp_kelvin")
    if kelvin:
        r, g, b = color_util.color_temperature_to_rgb(float(kelvin))
        return int(r), int(g), int(b)
    return None


@callback
def async_average_color(
    hass: HomeAssistant, entity_ids: Iterable[str]
) -> tuple[int, int, int] | None:
    """Brightness-weighted RGB average of the lights that are on."""
    total = 0.0
    acc = [0.0, 0.0, 0.0]
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None or state.state != "on":
            continue
        rgb = _state_rgb(dict(state.attributes))
        if rgb is None:
            # On, but no colour information (dimmer only): treat as warm white.
            rgb = (255, 244, 229)
        weight = float(state.attributes.get("brightness") or 255)
        total += weight
        for i in range(3):
            acc[i] += rgb[i] * weight
    if total <= 0:
        return None
    return (round(acc[0] / total), round(acc[1] / total), round(acc[2] / total))
