"""WebSocket API consumed by the Lightcompanion card and panel."""

from __future__ import annotations

import inspect
import logging
from dataclasses import asdict
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_API_KEY,
    CONF_PLAYER_OVERRIDES,
    DEFAULT_MODELS,
    DOMAIN,
    KEY_PROVIDERS,
    LLM_PROVIDERS,
)
from .lights import async_list_areas
from .settings import Settings, validate_options

_LOGGER = logging.getLogger(__name__)

_REGISTERED = "ws_registered"
SUBSCRIBE_REFRESH = timedelta(seconds=10)


def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if getattr(entry, "runtime_data", None) is not None:
            return entry
    return None


def _not_loaded(connection: websocket_api.ActiveConnection, msg_id: int) -> None:
    connection.send_error(msg_id, "not_loaded", "Light Companion is not loaded")


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _known_area(hass: HomeAssistant, area_id: str) -> bool:
    return ar.async_get(hass).async_get_area(area_id) is not None


def _light_candidates(hass: HomeAssistant) -> list[dict[str, Any]]:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    out: list[dict[str, Any]] = []
    for state in hass.states.async_all("light"):
        reg = ent_reg.async_get(state.entity_id)
        area_id = reg.area_id if reg else None
        if reg and not area_id and reg.device_id and (dev := dev_reg.async_get(reg.device_id)):
            area_id = dev.area_id
        area = area_reg.async_get_area(area_id) if area_id else None
        out.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "area": area.name if area else None,
            }
        )
    return sorted(out, key=lambda c: c["name"].casefold())


def _providers() -> list[dict[str, Any]]:
    return [
        {
            "id": provider,
            "needs_api_key": provider in KEY_PROVIDERS,
            "default_model": DEFAULT_MODELS.get(provider),
        }
        for provider in LLM_PROVIDERS
    ]


def _settings_payload(hass: HomeAssistant, settings: Settings, connection: Any) -> dict[str, Any]:
    return {
        "settings": settings.public_dict(),
        "is_admin": bool(connection.user and connection.user.is_admin),
        "providers": _providers(),
        "light_candidates": _light_candidates(hass),
    }


@websocket_api.websocket_command({vol.Required("type"): "lightcompanion/areas"})
@websocket_api.async_response
async def ws_areas(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List areas with lights, enriched with the music player."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    data = entry.runtime_data
    areas = await _maybe_await(async_list_areas(hass, data.settings))
    result = []
    for area in areas:
        area = dict(area)
        area["player"] = data.music.player_for_area(area["area_id"])
        result.append(area)
    connection.send_result(msg["id"], {"areas": result})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lightcompanion/chat",
        vol.Required("area_id"): str,
        vol.Required("text"): vol.All(str, vol.Length(min=1, max=2000)),
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_chat(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run a chat command for an area."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    if not _known_area(hass, msg["area_id"]):
        connection.send_error(msg["id"], "unknown_area", f"Unknown area {msg['area_id']}")
        return
    try:
        result = await entry.runtime_data.planner.async_chat(
            msg["area_id"], msg["text"], msg.get("language")
        )
    except Exception as err:
        if type(err).__name__ == "EffectBlockedError":
            connection.send_error(msg["id"], "blocked", str(err))
            return
        _LOGGER.exception("Chat failed")
        connection.send_error(msg["id"], "chat_failed", "Chat failed, see the log")
        return
    connection.send_result(msg["id"], asdict(result))


@websocket_api.websocket_command(
    {vol.Required("type"): "lightcompanion/stop", vol.Required("area_id"): str}
)
@websocket_api.async_response
async def ws_stop(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stop the effect of an area and restore its lights."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    if not _known_area(hass, msg["area_id"]):
        connection.send_error(msg["id"], "unknown_area", f"Unknown area {msg['area_id']}")
        return
    await entry.runtime_data.engine.async_stop(msg["area_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "lightcompanion/settings/get"})
@callback
def ws_settings_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the public settings (never the API key)."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    payload = _settings_payload(hass, entry.runtime_data.settings, connection)
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {vol.Required("type"): "lightcompanion/settings/set", vol.Required("options"): dict}
)
@websocket_api.require_admin
@callback
def ws_settings_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Merge partial options, validate, store (the entry reloads afterwards)."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    incoming = dict(msg["options"])
    incoming.pop("has_api_key", None)
    # An omitted or empty key keeps the stored one.
    if not incoming.get(CONF_API_KEY):
        incoming.pop(CONF_API_KEY, None)
    merged = {**entry.options, **incoming}
    try:
        validated = validate_options(merged)
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_options", str(err))
        return
    if CONF_PLAYER_OVERRIDES not in validated and CONF_PLAYER_OVERRIDES in merged:
        validated[CONF_PLAYER_OVERRIDES] = merged[CONF_PLAYER_OVERRIDES]
    hass.config_entries.async_update_entry(entry, options=validated)
    connection.send_result(
        msg["id"],
        {"settings": Settings.from_options(validated).public_dict()},
    )


@websocket_api.websocket_command({vol.Required("type"): "lightcompanion/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stream engine/planner status."""
    entry = _entry(hass)
    if entry is None:
        _not_loaded(connection, msg["id"])
        return
    data = entry.runtime_data
    msg_id = msg["id"]

    @callback
    def _push(*_: Any) -> None:
        connection.send_message(
            websocket_api.event_message(
                msg_id,
                {"engine": data.engine.status(), "planner": data.planner.status()},
            )
        )

    unsub_engine = data.engine.async_add_listener(_push)
    unsub_timer = async_track_time_interval(hass, _push, SUBSCRIBE_REFRESH)

    @callback
    def _unsub() -> None:
        unsub_engine()
        unsub_timer()

    connection.subscriptions[msg_id] = _unsub
    connection.send_result(msg_id)
    _push()


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all commands once per Home Assistant instance."""
    store = hass.data.setdefault(DOMAIN, {})
    if store.get(_REGISTERED):
        return
    for handler in (
        ws_areas,
        ws_chat,
        ws_stop,
        ws_settings_get,
        ws_settings_set,
        ws_subscribe,
    ):
        websocket_api.async_register_command(hass, handler)
    store[_REGISTERED] = True
