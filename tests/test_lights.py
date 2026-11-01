"""Tests for area -> lights resolution, transport detection, exclusions."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lightcompanion.lights import (
    async_area_lights,
    async_average_color,
    async_list_areas,
)


def make_settings(**kw):
    base = {
        "excluded_lights": (),
        "exclude_keywords": ("aquarium", "terrarium"),
        "exclude_label": "lightcompanion_exclude",
        "light_rate": 4,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def add_light(
    hass: HomeAssistant,
    object_id: str,
    platform: str = "hue",
    *,
    area_id: str | None = "living",
    name: str | None = None,
    state: str = "on",
    attrs: dict | None = None,
    device_id: str | None = None,
    config_entry=None,
) -> str:
    reg = er.async_get(hass)
    entry = reg.async_get_or_create(
        "light",
        platform,
        object_id,
        suggested_object_id=object_id,
        device_id=device_id,
        config_entry=config_entry,
    )
    if area_id and device_id is None:
        reg.async_update_entity(entry.entity_id, area_id=area_id)
    attributes = {"supported_color_modes": ["xy", "color_temp"], "friendly_name": name or object_id}
    attributes.update(attrs or {})
    hass.states.async_set(entry.entity_id, state, attributes)
    return entry.entity_id


@pytest.fixture
def living(hass: HomeAssistant) -> str:
    return ar.async_get(hass).async_create("Living").id


@pytest.mark.parametrize(
    ("platform", "transport"),
    [
        ("hue", "hue"),
        ("zha", "zigbee"),
        ("deconz", "zigbee"),
        ("wled", "wled"),
        ("lifx", "lifx"),
        ("nanoleaf", "nanoleaf"),
        ("govee_light_local", "wifi_slow"),
        ("govee", "wifi_slow"),
        ("tuya", "generic"),
    ],
)
async def test_transport_by_platform(
    hass: HomeAssistant, living: str, platform: str, transport: str
) -> None:
    add_light(hass, "lamp", platform, area_id=living)
    (info,) = async_area_lights(hass, living, make_settings())
    assert info.transport == transport
    assert info.platform == platform


async def test_zigbee2mqtt_device_is_zigbee(hass: HomeAssistant, living: str) -> None:
    entry = MockConfigEntry(domain="mqtt")
    entry.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mqtt", "zigbee2mqtt_0xabc")},
        area_id=living,
    )
    add_light(hass, "z2m", "mqtt", area_id=None, device_id=dev.id, config_entry=entry)
    plain = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mqtt", "something")}, area_id=living
    )
    add_light(hass, "plain_mqtt", "mqtt", area_id=None, device_id=plain.id, config_entry=entry)
    infos = {i.entity_id: i for i in async_area_lights(hass, living, make_settings())}
    assert infos["light.z2m"].transport == "zigbee"
    assert infos["light.plain_mqtt"].transport == "generic"


async def test_group_uses_most_restrictive_member(hass: HomeAssistant, living: str) -> None:
    add_light(hass, "bulb_hue", "hue", area_id=None)
    add_light(hass, "bulb_govee", "govee_light_local", area_id=None)
    add_light(
        hass,
        "grp",
        "group",
        area_id=living,
        attrs={"entity_id": ["light.bulb_hue", "light.bulb_govee"]},
    )
    (info,) = async_area_lights(hass, living, make_settings())
    assert info.is_group
    assert info.transport == "wifi_slow"


async def test_capabilities(hass: HomeAssistant, living: str) -> None:
    add_light(
        hass,
        "wled",
        "wled",
        area_id=living,
        attrs={
            "supported_color_modes": ["rgb"],
            "effect_list": ["Rainbow", "Fire"],
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
        },
    )
    add_light(hass, "white", "hue", area_id=living, attrs={"supported_color_modes": ["brightness"]})
    infos = {i.entity_id: i for i in async_area_lights(hass, living, make_settings())}
    assert infos["light.wled"].supports_color
    assert infos["light.wled"].effect_list == ("Rainbow", "Fire")
    assert infos["light.wled"].min_kelvin == 2000
    assert not infos["light.white"].supports_color


async def test_exclusions(hass: HomeAssistant, living: str) -> None:
    aq_area = ar.async_get(hass).async_create("Aquarium Room").id
    add_light(hass, "normal", area_id=living)
    add_light(hass, "fish_tank", area_id=living, name="Aquarium light")
    add_light(hass, "listed", area_id=living)
    add_light(hass, "labeled", area_id=living)
    add_light(hass, "in_aq_room", area_id=aq_area)
    lr.async_get(hass).async_create("lightcompanion_exclude")
    er.async_get(hass).async_update_entity("light.labeled", labels={"lightcompanion_exclude"})

    settings = make_settings(excluded_lights=("light.listed",))
    visible = {i.entity_id for i in async_area_lights(hass, living, settings)}
    assert visible == {"light.normal"}
    everything = {
        i.entity_id: i.excluded
        for i in async_area_lights(hass, living, settings, include_excluded=True)
    }
    assert everything == {
        "light.normal": False,
        "light.fish_tank": True,
        "light.listed": True,
        "light.labeled": True,
    }
    # keyword in the area name excludes too (case-insensitive)
    assert async_area_lights(hass, aq_area, settings) == []
    (flagged,) = async_area_lights(hass, aq_area, settings, include_excluded=True)
    assert flagged.excluded


async def test_keywords_are_configurable(hass: HomeAssistant, living: str) -> None:
    add_light(hass, "fish_tank", area_id=living, name="Aquarium light")
    settings = make_settings(exclude_keywords=())
    assert len(async_area_lights(hass, living, settings)) == 1


async def test_list_areas(hass: HomeAssistant, living: str) -> None:
    ent_reg = er.async_get(hass)
    add_light(hass, "a", area_id=living)
    add_light(hass, "disabled", area_id=living)
    ent_reg.async_update_entity("light.disabled", disabled_by=er.RegistryEntryDisabler.USER)
    add_light(hass, "hidden", area_id=living)
    ent_reg.async_update_entity("light.hidden", hidden_by=er.RegistryEntryHider.USER)
    ar.async_get(hass).async_create("Empty room")
    hass.states.async_set("switch.not_a_light", "on")
    areas = async_list_areas(hass, make_settings())
    assert [a["name"] for a in areas] == ["Living"]
    assert [light["entity_id"] for light in areas[0]["lights"]] == ["light.a"]
    assert set(areas[0]) == {"area_id", "name", "floor_id", "floor_name", "icon", "lights"}


async def test_area_via_device(hass: HomeAssistant, living: str) -> None:
    entry = MockConfigEntry(domain="hue")
    entry.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("hue", "d1")}, area_id=living
    )
    add_light(hass, "viadev", area_id=None, device_id=dev.id, config_entry=entry)
    assert [i.entity_id for i in async_area_lights(hass, living, make_settings())] == [
        "light.viadev"
    ]


async def test_average_color(hass: HomeAssistant) -> None:
    hass.states.async_set("light.red", "on", {"rgb_color": (255, 0, 0), "brightness": 255})
    hass.states.async_set("light.blue", "on", {"rgb_color": (0, 0, 255), "brightness": 85})
    hass.states.async_set("light.off", "off", {"rgb_color": (0, 255, 0), "brightness": 255})
    # weights 255 : 85 -> red 191, blue 64
    assert async_average_color(hass, ["light.red", "light.blue", "light.off"]) == (191, 0, 64)
    assert async_average_color(hass, ["light.off", "light.missing"]) is None


async def test_average_color_temp_and_hs(hass: HomeAssistant) -> None:
    hass.states.async_set("light.warm", "on", {"color_temp_kelvin": 2700, "brightness": 200})
    r, g, b = async_average_color(hass, ["light.warm"])
    assert r > b  # warm white is reddish
    hass.states.async_set("light.hs", "on", {"hs_color": (0, 100), "brightness": 100})
    assert async_average_color(hass, ["light.hs"]) == (255, 0, 0)
