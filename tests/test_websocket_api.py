"""WebSocket commands, invoked directly with a fake connection."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import area_registry as ar

from custom_components.lightcompanion import websocket_api as ws
from custom_components.lightcompanion.engine import EffectBlockedError

PKG = "custom_components.lightcompanion"


@dataclass
class _Result:
    reply: str = "ok"
    applied: bool = True
    plan: dict | None = None
    error: str | None = None


def _conn(admin: bool = True) -> MagicMock:
    conn = MagicMock()
    conn.user.is_admin = admin
    conn.subscriptions = {}
    return conn


async def _loaded(hass, entry, mock_runtime) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_not_loaded(hass: HomeAssistant) -> None:
    conn = _conn()
    ws.ws_settings_get(hass, conn, {"id": 1, "type": "lightcompanion/settings/get"})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "not_loaded"


async def test_areas(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    mock_runtime.music.player_for_area.return_value = "media_player.ma"
    conn = _conn()
    with patch(f"{PKG}.websocket_api.async_list_areas", return_value=[{"area_id": "living"}]):
        ws.ws_areas(hass, conn, {"id": 1})
        await hass.async_block_till_done()
    conn.send_result.assert_called_once_with(
        1, {"areas": [{"area_id": "living", "player": "media_player.ma"}]}
    )


async def test_chat_and_unknown_area(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    area = ar.async_get(hass).async_create("Living")
    mock_runtime.planner.async_chat = AsyncMock(return_value=_Result())
    conn = _conn()
    ws.ws_chat(hass, conn, {"id": 1, "area_id": area.id, "text": "hi"})
    await hass.async_block_till_done()
    assert conn.send_result.call_args.args[1]["reply"] == "ok"
    mock_runtime.planner.async_chat.assert_awaited_once_with(area.id, "hi", None)

    conn = _conn()
    ws.ws_chat(hass, conn, {"id": 2, "area_id": "nope", "text": "hi"})
    await hass.async_block_till_done()
    assert conn.send_error.call_args.args[1] == "unknown_area"


async def test_chat_blocked(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    area = ar.async_get(hass).async_create("Living")
    mock_runtime.planner.async_chat = AsyncMock(side_effect=EffectBlockedError("input_boolean.x"))
    conn = _conn()
    ws.ws_chat(hass, conn, {"id": 1, "area_id": area.id, "text": "hi"})
    await hass.async_block_till_done()
    assert conn.send_error.call_args.args[1] == "blocked"


async def test_stop(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    area = ar.async_get(hass).async_create("Living")
    conn = _conn()
    ws.ws_stop(hass, conn, {"id": 1, "area_id": area.id})
    await hass.async_block_till_done()
    mock_runtime.engine.async_stop.assert_awaited_once_with(area.id)
    conn.send_result.assert_called_once_with(1, {})


async def test_settings_get(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    hass.states.async_set("light.lamp", "on", {"friendly_name": "Lamp"})
    conn = _conn(admin=False)
    ws.ws_settings_get(hass, conn, {"id": 1})
    payload = conn.send_result.call_args.args[1]
    assert payload["is_admin"] is False
    assert "api_key" not in payload["settings"]
    assert payload["providers"][0]["id"] == "ai_task"
    assert payload["light_candidates"] == [
        {"entity_id": "light.lamp", "name": "Lamp", "area": None}
    ]


async def test_settings_set_merges_and_keeps_key(hass: HomeAssistant, entry, mock_runtime) -> None:
    hass.config_entries.async_update_entry(
        entry,
        options={"llm_provider": "openai", "api_key": "sk-old", "model": "m", "light_rate": 4},
    )
    await _loaded(hass, entry, mock_runtime)
    conn = _conn()
    ws.ws_settings_set(hass, conn, {"id": 1, "options": {"light_rate": 7, "api_key": ""}})
    assert entry.options["light_rate"] == 7
    assert entry.options["api_key"] == "sk-old"
    assert entry.options["llm_provider"] == "openai"
    result = conn.send_result.call_args.args[1]["settings"]
    assert result["light_rate"] == 7 and "api_key" not in result


async def test_settings_set_invalid(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    conn = _conn()
    ws.ws_settings_set(hass, conn, {"id": 1, "options": {"light_rate": 99}})
    assert conn.send_error.call_args.args[1] == "invalid_options"
    conn = _conn()
    ws.ws_settings_set(hass, conn, {"id": 2, "options": {"llm_provider": "openai"}})
    assert conn.send_error.call_args.args[1] == "invalid_options"


async def test_settings_set_requires_admin(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    conn = _conn(admin=False)
    with pytest.raises(Unauthorized):
        ws.ws_settings_set(hass, conn, {"id": 1, "options": {"light_rate": 5}})
    assert entry.options.get("light_rate") != 5


async def test_subscribe(hass: HomeAssistant, entry, mock_runtime) -> None:
    await _loaded(hass, entry, mock_runtime)
    conn = _conn()
    ws.ws_subscribe(hass, conn, {"id": 5})
    conn.send_result.assert_called_once_with(5)
    assert conn.send_message.call_count == 1
    assert 5 in conn.subscriptions
    mock_runtime.engine.async_add_listener.assert_called_once()
    # engine change pushes again
    mock_runtime.engine.async_add_listener.call_args.args[0]()
    assert conn.send_message.call_count == 2
    conn.subscriptions[5]()
    mock_runtime.engine.async_add_listener.return_value.assert_called_once()


async def test_register_once(hass: HomeAssistant) -> None:
    with patch(f"{PKG}.websocket_api.websocket_api.async_register_command") as reg:
        ws.async_register_websocket_api(hass)
        ws.async_register_websocket_api(hass)
    assert reg.call_count == 6
