"""Light Companion: chat/voice light control with a local effect engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .ai_budget import AiBudget
from .const import DOMAIN, PLATFORMS, SERVICE_CHAT, SERVICE_STOP
from .engine import EffectEngine
from .music import MusicService
from .panel import async_register_frontend, async_unregister_frontend
from .planner import Planner
from .settings import Settings
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CHAT_SCHEMA = vol.Schema(
    {
        vol.Required("area_id"): cv.string,
        vol.Required("text"): vol.All(cv.string, vol.Length(min=1, max=2000)),
        vol.Optional("language"): cv.string,
    }
)
STOP_SCHEMA = vol.Schema({vol.Required("area_id"): cv.string})


@dataclass
class LightCompanionData:
    """Runtime objects of a loaded entry."""

    settings: Settings
    budget: AiBudget
    engine: EffectEngine
    music: MusicService
    planner: Planner


type LightCompanionConfigEntry = ConfigEntry[LightCompanionData]


def _loaded_data(hass: HomeAssistant) -> LightCompanionData:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if getattr(entry, "runtime_data", None) is not None:
            return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="not_loaded"
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services and the WebSocket API once per Home Assistant."""
    async_register_websocket_api(hass)

    async def _chat(call: ServiceCall) -> dict:
        data = _loaded_data(hass)
        try:
            result = await data.planner.async_chat(
                call.data["area_id"], call.data["text"], call.data.get("language")
            )
        except HomeAssistantError:
            raise
        except Exception as err:  # noqa: BLE001 - surface any planner failure as HA error
            raise HomeAssistantError(f"Light Companion chat failed: {err}") from err
        return asdict(result)

    async def _stop(call: ServiceCall) -> None:
        await _loaded_data(hass).engine.async_stop(call.data["area_id"])

    hass.services.async_register(
        DOMAIN, SERVICE_CHAT, _chat, schema=CHAT_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, _stop, schema=STOP_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LightCompanionConfigEntry) -> bool:
    """Set up Light Companion from a config entry."""
    settings = Settings.from_options(entry.options)
    budget = AiBudget(settings.ai_calls_per_hour)
    engine = EffectEngine(hass, settings)
    music = MusicService(hass, settings)
    planner = Planner(hass, settings, budget, engine, music)
    await planner.async_start()
    entry.runtime_data = LightCompanionData(settings, budget, engine, music, planner)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_frontend(hass, show_panel=settings.show_panel)
    # Any options change (flow or WebSocket) reloads the entry.
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def _async_reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LightCompanionConfigEntry) -> bool:
    """Unload a config entry; restore lights that were under effect."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = entry.runtime_data
        await data.planner.async_stop()
        await data.engine.async_stop_all(restore=True)
        async_unregister_frontend(hass)
    return unloaded
