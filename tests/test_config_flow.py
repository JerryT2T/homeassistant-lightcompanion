"""Config flow and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lightcompanion.const import DOMAIN


async def _start(hass: HomeAssistant, provider: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"llm_provider": provider}
    )


async def test_ai_task_default(hass: HomeAssistant, mock_runtime) -> None:
    result = await _start(hass, "ai_task")
    assert result["step_id"] == "ai_task"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {"llm_provider": "ai_task"}


async def test_conversation(hass: HomeAssistant, mock_runtime) -> None:
    result = await _start(hass, "conversation")
    assert result["step_id"] == "conversation"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"conversation_agent": "conversation.home_assistant"}
    )
    assert result["options"]["conversation_agent"] == "conversation.home_assistant"


async def test_own_key_requires_key(hass: HomeAssistant, mock_runtime) -> None:
    result = await _start(hass, "anthropic")
    assert result["step_id"] == "api"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "  ", "model": "x"}
    )
    assert result["errors"] == {"api_key": "api_key_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "sk-1", "model": ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["api_key"] == "sk-1"
    assert result["options"]["model"] == "claude-haiku-4-5"


async def test_single_instance(hass: HomeAssistant, entry, mock_runtime) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_all_fields(hass: HomeAssistant, entry, mock_runtime) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    keys = {str(k) for k in result["data_schema"].schema}
    assert {
        "llm_provider",
        "ai_calls_per_hour",
        "light_rate",
        "allow_strobe",
        "excluded_lights",
        "exclude_keywords",
        "exclude_label",
        "blocking_entities",
        "default_area",
        "show_panel",
        "api_key",
        "model",
        "ai_task_entity",
        "conversation_agent",
    } <= keys
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "llm_provider": "ai_task",
            "ai_calls_per_hour": 80.0,
            "light_rate": 6.0,
            "allow_strobe": True,
            "excluded_lights": ["light.fish"],
            "exclude_keywords": ["tank"],
            "blocking_entities": ["input_boolean.cleaning"],
            "show_panel": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["ai_calls_per_hour"] == 80
    assert result["data"]["blocking_entities"] == ["input_boolean.cleaning"]
    assert result["data"]["show_panel"] is True


async def test_options_flow_keeps_stored_key(hass: HomeAssistant, entry, mock_runtime) -> None:
    hass.config_entries.async_update_entry(
        entry, options={"llm_provider": "openai", "api_key": "sk-old", "model": "m"}
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "llm_provider": "openai",
            "ai_calls_per_hour": 50,
            "light_rate": 4,
            "allow_strobe": False,
            "show_panel": False,
            "model": "m",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["api_key"] == "sk-old"


async def test_options_flow_missing_key_error(hass: HomeAssistant, entry, mock_runtime) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "llm_provider": "google",
            "ai_calls_per_hour": 50,
            "light_rate": 4,
            "allow_strobe": False,
            "show_panel": False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_key": "api_key_required"}
