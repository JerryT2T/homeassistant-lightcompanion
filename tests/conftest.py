"""Shared fixtures for Light Companion tests.

* Windows / pytest-socket: let the event-loop self-pipe (socket.socketpair)
  through the socket guard (Linux CI is unaffected).
* Sibling modules owned by other slices (planner, engine, ...) are replaced by
  tiny stubs when their file does not exist yet, so the infra tests pass on
  their own; tests patch the classes on ``custom_components.lightcompanion``.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

PKG = "custom_components.lightcompanion"
PKG_DIR = Path(__file__).parent.parent / "custom_components" / "lightcompanion"


def _stub(module: str, **attrs: object) -> None:
    if (PKG_DIR / f"{module}.py").exists() or (PKG_DIR / module).is_dir():
        return
    mod = types.ModuleType(f"{PKG}.{module}")
    for name, value in attrs.items():
        setattr(mod, name, value)
    sys.modules[f"{PKG}.{module}"] = mod


class _Dummy:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


_stub("ai_budget", AiBudget=type("AiBudget", (_Dummy,), {}))
_stub("engine", EffectEngine=type("EffectEngine", (_Dummy,), {}))
_stub("music", MusicService=type("MusicService", (_Dummy,), {}))
_stub("planner", Planner=type("Planner", (_Dummy,), {}))
_stub("lights", async_list_areas=lambda hass, settings: [])


def _allow_loop_socketpair_on_windows() -> None:
    if sys.platform != "win32":
        return
    import socket

    real = socket.socketpair

    def _socketpair(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            import pytest_socket as _ps
        except ImportError:
            return real(*args, **kwargs)
        _ps.enable_socket()
        try:
            return real(*args, **kwargs)
        finally:
            _ps.disable_socket(allow_unix_socket=True)

    socket.socketpair = _socketpair  # type: ignore[assignment]


def _legacy_asyncio_stack() -> bool:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return int(version("pytest-asyncio").split(".")[0]) < 1
    except (PackageNotFoundError, ValueError):
        return False


def pytest_configure(config: pytest.Config) -> None:
    """Fix the event loop policy on Windows."""
    if not _legacy_asyncio_stack():
        _allow_loop_socketpair_on_windows()
        return
    import asyncio.events as _ev

    asyncio.set_event_loop_policy = _ev.set_event_loop_policy  # type: ignore[assignment]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    else:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # type: ignore[no-untyped-def]
    """Allow loading this custom integration."""
    return


@pytest.fixture
def mock_runtime():  # type: ignore[no-untyped-def]
    """Patch the runtime classes, the frontend and platform forwarding."""
    engine = MagicMock()
    engine.status.return_value = {"living": {"active": True}}
    engine.async_add_listener.return_value = MagicMock()
    engine.async_stop = AsyncMock()
    engine.async_stop_all = AsyncMock()
    planner = MagicMock()
    planner.async_start = AsyncMock()
    planner.async_stop = AsyncMock()
    planner.status.return_value = {"ai": {"used": 1, "limit": 50}, "follow": {}}
    music = MagicMock()
    music.player_for_area.return_value = None
    with (
        patch(f"{PKG}.AiBudget"),
        patch(f"{PKG}.EffectEngine", return_value=engine),
        patch(f"{PKG}.MusicService", return_value=music),
        patch(f"{PKG}.Planner", return_value=planner),
        patch(f"{PKG}.async_register_frontend", new_callable=AsyncMock) as reg,
        patch(f"{PKG}.async_unregister_frontend") as unreg,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new_callable=AsyncMock,
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ),
        # Real http/frontend are not needed (and not installable in every CI image).
        patch(
            "homeassistant.setup._async_process_dependencies",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        yield types.SimpleNamespace(
            engine=engine, planner=planner, music=music, register=reg, unregister=unreg
        )


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry with default options (ai_task)."""
    e = MockConfigEntry(
        domain="lightcompanion",
        title="Light Companion",
        data={},
        options={"llm_provider": "ai_task"},
    )
    e.add_to_hass(hass)
    return e
