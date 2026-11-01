"""Tests for the per-area effect switch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.lightcompanion.const import DOMAIN
from custom_components.lightcompanion.switch import (
    LightCompanionEffectSwitch,
    async_setup_entry,
)


class FakeEngine:
    def __init__(self) -> None:
        self.active = False
        self.listeners: list = []
        self.stop = AsyncMock()
        self.apply = AsyncMock()
        self._last = None

    def is_active(self, area_id: str) -> bool:
        return self.active

    def status(self) -> dict:
        if not self.active:
            return {}
        return {
            "living": {
                "active": True,
                "pattern": "wave",
                "palette": [[1, 2, 3]],
                "source": "chat",
                "since": "now",
                "party": True,
            }
        }

    def last(self, area_id: str):
        return self._last

    def async_add_listener(self, cb):
        self.listeners.append(cb)
        return lambda: self.listeners.remove(cb)

    async def async_stop(self, area_id: str, **kw) -> None:
        await self.stop(area_id, **kw)

    async def async_apply(self, *a, **kw) -> None:
        await self.apply(*a, **kw)


def make_switch(engine: FakeEngine) -> LightCompanionEffectSwitch:
    return LightCompanionEffectSwitch("entry1", engine, "living", "Living")  # type: ignore[arg-type]


def test_entity_identity() -> None:
    sw = make_switch(FakeEngine())
    assert sw.entity_id == "switch.lightcompanion_living_effect"
    assert sw.unique_id == "entry1_living_effect"
    assert sw.has_entity_name
    assert sw.translation_key == "effect"
    assert sw.translation_placeholders == {"area": "Living"}
    assert sw.device_info["identifiers"] == {(DOMAIN, "entry1")}
    assert sw.device_info["entry_type"].value == "service"


def test_state_and_attributes_follow_engine() -> None:
    eng = FakeEngine()
    sw = make_switch(eng)
    assert sw.is_on is False
    assert sw.extra_state_attributes == {}
    eng.active = True
    assert sw.is_on is True
    assert sw.extra_state_attributes == {
        "pattern": "wave",
        "palette": [[1, 2, 3]],
        "source": "chat",
        "party": True,
    }


async def test_listener_updates_state(hass: HomeAssistant) -> None:
    eng = FakeEngine()
    sw = make_switch(eng)
    sw.hass = hass
    sw.async_write_ha_state = MagicMock()
    await sw.async_added_to_hass()
    for cb in list(eng.listeners):
        cb()
    sw.async_write_ha_state.assert_called_once()


async def test_turn_off_stops_effect() -> None:
    eng = FakeEngine()
    await make_switch(eng).async_turn_off()
    eng.stop.assert_awaited_once_with("living")


async def test_turn_on_reapplies_last_plan_or_noops() -> None:
    eng = FakeEngine()
    sw = make_switch(eng)
    await sw.async_turn_on()
    eng.apply.assert_not_awaited()
    plan, lights = object(), (object(),)
    eng._last = (plan, lights, "music")
    await sw.async_turn_on()
    eng.apply.assert_awaited_once_with("living", plan, lights, source="music")


async def test_setup_creates_one_switch_per_area_with_lights(hass: HomeAssistant) -> None:
    area = ar.async_get(hass).async_create("Living").id
    ar.async_get(hass).async_create("Empty")
    reg = er.async_get(hass)
    entry = reg.async_get_or_create("light", "hue", "u1", suggested_object_id="a")
    reg.async_update_entity(entry.entity_id, area_id=area)
    hass.states.async_set(entry.entity_id, "on", {"friendly_name": "A"})
    settings = SimpleNamespace(excluded_lights=(), exclude_keywords=(), exclude_label="x")
    config_entry = SimpleNamespace(
        entry_id="e1", runtime_data=SimpleNamespace(settings=settings, engine=FakeEngine())
    )
    added: list = []
    await async_setup_entry(hass, config_entry, lambda ents: added.extend(ents))  # type: ignore[arg-type]
    assert [e.entity_id for e in added] == [f"switch.lightcompanion_{area}_effect"]
