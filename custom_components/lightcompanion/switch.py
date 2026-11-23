"""One switch per area that shows (and controls) a running light effect."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .engine import EffectEngine
from .lights import async_list_areas

PARALLEL_UPDATES = 0

DEVICE_NAME = "Light Companion"


def area_device_identifier(entry_id: str, area_id: str) -> tuple[str, str]:
    """Identifier of the child device that holds one area's entities."""
    return (DOMAIN, f"{entry_id}_{area_id}")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one effect switch for every area that has lights.

    Each area gets a child device of the main "Light Companion" device, placed
    in that area. With the Home Assistant 2026.11 naming model the area then
    comes from context, so the entity itself is just called "Effect".
    """
    data = entry.runtime_data
    parent = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        entry_type=DeviceEntryType.SERVICE,
        name=DEVICE_NAME,
    )
    areas = async_list_areas(hass, data.settings)
    async_add_entities(
        LightCompanionEffectSwitch(entry.entry_id, data.engine, a["area_id"], a["name"], parent.id)
        for a in areas
    )


class LightCompanionEffectSwitch(SwitchEntity):
    """On while the effect engine plays an effect in the area."""

    _attr_has_entity_name = True
    _attr_translation_key = "effect"
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        engine: EffectEngine,
        area_id: str,
        area_name: str,
        parent_device_id: str,
    ) -> None:
        self._engine = engine
        self._area_id = area_id
        # unique_id and entity_id stay as they were before the child devices,
        # so automations and dashboards keep working.
        self._attr_unique_id = f"{entry_id}_{area_id}_effect"
        self.entity_id = f"switch.lightcompanion_{area_id}_effect"
        self._attr_device_info = ChildDeviceInfo(
            identifiers={area_device_identifier(entry_id, area_id)},
            name=DEVICE_NAME,
            parent_device_id=parent_device_id,
            suggested_area=area_name,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._engine.async_add_listener(self._engine_changed))

    @callback
    def _engine_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._engine.is_active(self._area_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._engine.status().get(self._area_id)
        if not status:
            return {}
        return {
            "pattern": status["pattern"],
            "palette": status["palette"],
            "source": status["source"],
            "party": status["party"],
        }

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._engine.async_stop(self._area_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Re-apply the last plan of this area; no-op if there is none."""
        last = self._engine.last(self._area_id)
        if last is None:
            return
        plan, lights, source = last
        await self._engine.async_apply(self._area_id, plan, lights, source=source)
