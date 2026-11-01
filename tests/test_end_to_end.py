"""End-to-end: chat → LLM → validation → engine → light services, with real modules."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.lightcompanion import websocket_api as wsapi
from custom_components.lightcompanion.const import DOMAIN

PLAN = {
    "reply": "Cozy!",
    "action": "apply",
    "palette": [[255, 120, 0]],
    "pattern": "static",
    "tempo": "slow",
    "intensity": 2,
    "brightness_pct": 40,
}


async def _setup(hass: HomeAssistant, speech: list[str]) -> tuple[Any, list[Any], MockConfigEntry]:
    """Area with two colour lights, a fake conversation agent answering `speech[0]`."""
    area = ar.async_get(hass).async_create("Living")
    reg = er.async_get(hass)
    for i in (1, 2):
        entry = reg.async_get_or_create("light", "test", f"u{i}", suggested_object_id=f"l{i}")
        reg.async_update_entity(entry.entity_id, area_id=area.id)
        hass.states.async_set(
            entry.entity_id,
            "on",
            {
                "supported_color_modes": ["rgb"],
                "color_mode": "rgb",
                "brightness": 200,
                "rgb_color": [10, 10, 10],
                "supported_features": 0,
                "friendly_name": f"L{i}",
            },
        )
    calls = async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")

    async def process(call: Any) -> dict[str, Any]:
        return {"response": {"speech": {"plain": {"speech": speech[0]}}}}

    hass.services.async_register(
        "conversation", "process", process, supports_response=SupportsResponse.ONLY
    )
    config_entry = MockConfigEntry(domain=DOMAIN, options={"llm_provider": "conversation"})
    config_entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.setup._async_process_dependencies",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("custom_components.lightcompanion.async_register_frontend", new_callable=AsyncMock),
        patch("custom_components.lightcompanion.async_unregister_frontend"),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return area, calls, config_entry


async def _ws(hass: HomeAssistant, handler: Any, msg: dict[str, Any]) -> MagicMock:
    conn = MagicMock()
    handler(hass, conn, msg)
    for _ in range(200):
        if conn.send_result.called or conn.send_error.called:
            break
        await asyncio.sleep(0.02)
    await hass.async_block_till_done()
    return conn


def _chat(area_id: str, text: str) -> dict[str, Any]:
    return {"id": 1, "type": "lightcompanion/chat", "area_id": area_id, "text": text}


async def test_chat_applies_valid_plan_and_never_executes_invalid_ones(
    hass: HomeAssistant,
) -> None:
    speech = [json.dumps(PLAN)]
    area, calls, entry = await _setup(hass, speech)

    conn = await _ws(hass, wsapi.ws_chat, _chat(area.id, "warm"))
    result = conn.send_result.call_args[0][1]
    assert result["applied"] is True
    assert result["error"] is None
    assert calls, "valid plan must reach light.turn_on"
    assert hass.states.get(f"switch.lightcompanion_{area.id}_effect") is not None

    conn = await _ws(hass, wsapi.ws_areas, {"id": 2, "type": "lightcompanion/areas"})
    areas = conn.send_result.call_args[0][1]["areas"]
    assert [len(a["lights"]) for a in areas if a["area_id"] == area.id] == [2]

    await entry.runtime_data.engine.async_stop(area.id)
    calls.clear()

    speech[0] = "this is not json {"
    conn = await _ws(hass, wsapi.ws_chat, _chat(area.id, "again"))
    assert conn.send_result.call_args[0][1]["error"] == "invalid_json"
    assert not calls

    speech[0] = json.dumps({**PLAN, "palette": [[999, 1, 1]], "pattern": "evil"})
    conn = await _ws(hass, wsapi.ws_chat, _chat(area.id, "bad"))
    assert conn.send_result.call_args[0][1]["error"] == "invalid_plan"
    assert not calls

    speech[0] = json.dumps(PLAN)
    response = await hass.services.async_call(
        DOMAIN, "chat", {"area_id": area.id, "text": "x"}, blocking=True, return_response=True
    )
    assert response["applied"] is True
    assert calls

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
