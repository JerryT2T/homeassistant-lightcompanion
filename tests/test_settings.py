"""Settings parsing and option validation."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.lightcompanion.settings import Settings, validate_options


def test_defaults() -> None:
    s = Settings.from_options({})
    assert s.llm_provider == "ai_task"
    assert s.ai_calls_per_hour == 50
    assert s.light_rate == 4
    assert s.allow_strobe is False
    assert s.exclude_keywords == ("aquarium", "terrarium")
    assert s.excluded_lights == ()
    assert s.blocking_entities == ()
    assert s.exclude_label == "lightcompanion_exclude"
    assert s.show_panel is False
    assert s.default_area is None


def test_clamping_and_unknown_provider() -> None:
    s = Settings.from_options({"llm_provider": "nope", "ai_calls_per_hour": 9999, "light_rate": 0})
    assert s.llm_provider == "ai_task"
    assert s.ai_calls_per_hour == 200
    assert s.light_rate == 1


def test_public_dict_hides_key() -> None:
    s = Settings.from_options({"llm_provider": "openai", "api_key": "sk-secret"})
    pub = s.public_dict()
    assert "api_key" not in pub
    assert pub["has_api_key"] is True
    assert "sk-secret" not in str(pub)


def test_empty_keywords_allowed() -> None:
    assert Settings.from_options({"exclude_keywords": []}).exclude_keywords == ()


def test_validate_requires_key_for_own_key_provider() -> None:
    with pytest.raises(vol.Invalid):
        validate_options({"llm_provider": "openai"})
    assert validate_options({"llm_provider": "openai", "api_key": "k"})["api_key"] == "k"


@pytest.mark.parametrize(
    "bad",
    [
        {"ai_calls_per_hour": 1},
        {"light_rate": 11},
        {"excluded_lights": ["switch.x"]},
        {"blocking_entities": ["light.x"]},
        {"llm_provider": "other"},
    ],
)
def test_validate_rejects(bad: dict) -> None:
    with pytest.raises(vol.Invalid):
        validate_options(bad)


def test_validate_accepts_blocking() -> None:
    out = validate_options({"blocking_entities": ["input_boolean.cleaning", "switch.a"]})
    assert out["blocking_entities"] == ["input_boolean.cleaning", "switch.a"]
