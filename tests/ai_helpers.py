"""Test helpers of the AI slice: importable without Home Assistant installed.

If ``homeassistant`` is missing, a stub package ``custom_components.lightcompanion``
(without running its ``__init__``) plus minimal fake HA modules and a fake
``const``/``engine`` are registered. With real HA available nothing is faked
except the lights/settings stand-ins used for building inputs.
"""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PKG = "custom_components.lightcompanion"
ROOT = Path(__file__).resolve().parent.parent
FAKE_HA = False


def _mod(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def install() -> None:
    global FAKE_HA  # noqa: PLW0603
    if PKG in sys.modules or FAKE_HA:
        return
    sys.path.insert(0, str(ROOT))
    try:
        importlib.import_module("homeassistant.core")
        return
    except ImportError:
        pass
    FAKE_HA = True

    class HomeAssistantError(Exception):
        pass

    class ServiceNotFound(HomeAssistantError):
        pass

    _mod("homeassistant")
    _mod("homeassistant.core", callback=lambda f: f, HomeAssistant=object, CALLBACK_TYPE=object)
    _mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError, ServiceNotFound=ServiceNotFound)
    _mod("homeassistant.helpers")
    _mod("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: hass.session)
    pkg_root = types.ModuleType("custom_components")
    pkg_root.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = pkg_root
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT / "custom_components" / "lightcompanion")]
    sys.modules[PKG] = pkg
    _mod(
        f"{PKG}.const",
        DOMAIN="lightcompanion",
        DEFAULT_MODELS={"openai": "gpt-5-mini", "anthropic": "claude-haiku-4-5", "google": "gemini-2.5-flash"},
    )

    class EffectBlockedError(Exception):
        def __init__(self, entity_id: str = "") -> None:
            super().__init__(entity_id)
            self.entity_id = entity_id

    _mod(f"{PKG}.engine", EffectBlockedError=EffectBlockedError)


install()


def imp(name: str) -> Any:
    return importlib.import_module(f"{PKG}.{name}")


@dataclass(frozen=True)
class FakeLight:
    entity_id: str
    name: str = "Lamp"
    area_id: str | None = "room"
    platform: str = "hue"
    transport: str = "hue"
    color_modes: tuple[str, ...] = ("xy", "color_temp")
    supports_color: bool = True
    effect_list: tuple[str, ...] = ()
    min_kelvin: int | None = 2000
    max_kelvin: int | None = 6500
    is_group: bool = False
    excluded: bool = False


def make_settings(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "llm_provider": "ai_task",
        "ai_task_entity": None,
        "conversation_agent": None,
        "api_key": "sk-secret",
        "model": None,
        "ai_calls_per_hour": 50,
        "light_rate": 4,
        "allow_strobe": False,
        "excluded_lights": (),
        "exclude_keywords": ("aquarium",),
        "player_overrides": {},
        "default_area": None,
        "show_panel": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


@dataclass
class FakeState:
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)


class FakeStates:
    def __init__(self) -> None:
        self.data: dict[str, FakeState] = {}

    def get(self, entity_id: str) -> FakeState | None:
        return self.data.get(entity_id)


class FakeServices:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, dict, dict]] = []
        self.response = response
        self.error = error

    async def async_call(self, domain: str, service: str, data: dict, **kw: Any) -> Any:
        self.calls.append((domain, service, data, kw))
        if self.error:
            raise self.error
        return self.response


class FakeHass:
    def __init__(self) -> None:
        self.states = FakeStates()
        self.services = FakeServices()
        self.session: Any = None
        self.tasks: list[Any] = []

    def async_create_task(self, coro: Any) -> Any:
        import asyncio

        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task
