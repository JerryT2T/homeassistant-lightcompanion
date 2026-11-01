"""Setup, unload and services."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.lightcompanion.planner import Planner  # noqa: F401 (stub or real)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.lightcompanion.const import DOMAIN, VERSION


async def test_setup_and_unload(hass: HomeAssistant, entry, mock_runtime) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    mock_runtime.planner.async_start.assert_awaited_once()
    mock_runtime.register.assert_awaited_once()
    assert mock_runtime.register.await_args.kwargs == {"show_panel": False}
    assert entry.runtime_data.settings.ai_calls_per_hour == 50

    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_runtime.planner.async_stop.assert_awaited_once()
    mock_runtime.engine.async_stop_all.assert_awaited_once_with(restore=True)
    mock_runtime.unregister.assert_called_once()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_show_panel_passed(hass: HomeAssistant, entry, mock_runtime) -> None:
    hass.config_entries.async_update_entry(entry, options={"show_panel": True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert mock_runtime.register.await_args.kwargs == {"show_panel": True}


async def test_options_update_reloads(hass: HomeAssistant, entry, mock_runtime) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={"light_rate": 6})
    await hass.async_block_till_done()
    assert mock_runtime.planner.async_start.await_count == 2
    assert entry.runtime_data.settings.light_rate == 6


async def test_services(hass: HomeAssistant, entry, mock_runtime) -> None:
    from dataclasses import dataclass

    from custom_components.lightcompanion.planner import Planner as _P  # noqa: F401

    @dataclass
    class Result:
        reply: str
        applied: bool
        plan: dict | None
        error: str | None

    mock_runtime.planner.async_chat = AsyncMock(return_value=Result("ok", True, {"a": 1}, None))
    assert await hass.config_entries.async_setup(entry.entry_id)

    resp = await hass.services.async_call(
        DOMAIN, "chat", {"area_id": "living", "text": "party"}, blocking=True, return_response=True
    )
    assert resp == {"reply": "ok", "applied": True, "plan": {"a": 1}, "error": None}
    mock_runtime.planner.async_chat.assert_awaited_once_with("living", "party", None)

    await hass.services.async_call(DOMAIN, "stop", {"area_id": "living"}, blocking=True)
    mock_runtime.engine.async_stop.assert_awaited_once_with("living")


async def test_service_not_loaded(hass: HomeAssistant, mock_runtime) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "stop", {"area_id": "x"}, blocking=True)


def test_version_matches_manifest() -> None:
    import json
    from pathlib import Path

    manifest = Path(__file__).parents[1] / "custom_components/lightcompanion/manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == VERSION
