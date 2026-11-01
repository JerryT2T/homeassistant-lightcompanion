"""Typed settings parsed from config entry options."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import voluptuous as vol

from .const import (
    CONF_AI_CALLS_PER_HOUR,
    CONF_AI_TASK_ENTITY,
    CONF_ALLOW_STROBE,
    CONF_BLOCKING_ENTITIES,
    CONF_API_KEY,
    CONF_CONVERSATION_AGENT,
    CONF_DEFAULT_AREA,
    CONF_EXCLUDE_KEYWORDS,
    CONF_EXCLUDE_LABEL,
    CONF_EXCLUDED_LIGHTS,
    CONF_LIGHT_RATE,
    CONF_LLM_PROVIDER,
    CONF_MODEL,
    CONF_PLAYER_OVERRIDES,
    CONF_SHOW_PANEL,
    DEFAULT_AI_CALLS_PER_HOUR,
    DEFAULT_ALLOW_STROBE,
    DEFAULT_EXCLUDE_KEYWORDS,
    DEFAULT_EXCLUDE_LABEL,
    DEFAULT_LIGHT_RATE,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_SHOW_PANEL,
    KEY_PROVIDERS,
    LLM_PROVIDERS,
    MAX_AI_CALLS_PER_HOUR,
    MAX_LIGHT_RATE,
    MIN_AI_CALLS_PER_HOUR,
    MIN_LIGHT_RATE,
)


def _opt_str(value: Any) -> str | None:
    """Normalize empty strings to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [s for s in (str(v).strip() for v in value) if s]


_OPT_STR = vol.Any(None, vol.All(str, vol.Length(max=500)))

# Validation schema shared by the options flow and the settings/set WS command.
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_LLM_PROVIDER): vol.In(LLM_PROVIDERS),
        vol.Optional(CONF_AI_TASK_ENTITY): _OPT_STR,
        vol.Optional(CONF_CONVERSATION_AGENT): _OPT_STR,
        vol.Optional(CONF_API_KEY): _OPT_STR,
        vol.Optional(CONF_MODEL): _OPT_STR,
        vol.Optional(CONF_AI_CALLS_PER_HOUR): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_AI_CALLS_PER_HOUR, max=MAX_AI_CALLS_PER_HOUR)
        ),
        vol.Optional(CONF_LIGHT_RATE): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_LIGHT_RATE, max=MAX_LIGHT_RATE)
        ),
        vol.Optional(CONF_ALLOW_STROBE): bool,
        vol.Optional(CONF_EXCLUDED_LIGHTS): [vol.All(str, vol.Match(r"^light\.[a-z0-9_]+$"))],
        vol.Optional(CONF_EXCLUDE_KEYWORDS): [vol.All(str, vol.Length(min=1, max=100))],
        vol.Optional(CONF_PLAYER_OVERRIDES): {
            str: vol.All(str, vol.Match(r"^media_player\.[a-z0-9_]+$"))
        },
        vol.Optional(CONF_DEFAULT_AREA): _OPT_STR,
        vol.Optional(CONF_SHOW_PANEL): bool,
        vol.Optional(CONF_BLOCKING_ENTITIES): [
            vol.All(str, vol.Match(r"^(input_boolean|switch|binary_sensor)\.[a-z0-9_]+$"))
        ],
        vol.Optional(CONF_EXCLUDE_LABEL): _OPT_STR,
    },
    extra=vol.REMOVE_EXTRA,
)


def validate_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Validate full options; raises ``vol.Invalid``.

    Own-key providers must end up with an API key.
    """
    cleaned: dict[str, Any] = OPTIONS_SCHEMA(dict(options))
    provider = cleaned.get(CONF_LLM_PROVIDER, DEFAULT_LLM_PROVIDER)
    if provider in KEY_PROVIDERS and not _opt_str(cleaned.get(CONF_API_KEY)):
        raise vol.Invalid("api_key_required", path=[CONF_API_KEY])
    return cleaned


@dataclass(frozen=True, slots=True)
class Settings:
    """Effective integration settings."""

    llm_provider: str
    ai_task_entity: str | None
    conversation_agent: str | None
    api_key: str | None
    model: str | None
    ai_calls_per_hour: int
    light_rate: int
    allow_strobe: bool
    excluded_lights: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    player_overrides: Mapping[str, str]
    default_area: str | None
    show_panel: bool
    blocking_entities: tuple[str, ...]
    exclude_label: str

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> Settings:
        """Build settings from raw options, applying defaults and clamping."""
        provider = options.get(CONF_LLM_PROVIDER, DEFAULT_LLM_PROVIDER)
        if provider not in LLM_PROVIDERS:
            provider = DEFAULT_LLM_PROVIDER

        def _int(key: str, default: int, lo: int, hi: int) -> int:
            try:
                return max(lo, min(hi, int(options.get(key, default))))
            except (TypeError, ValueError):
                return default

        keywords = (
            _str_list(options[CONF_EXCLUDE_KEYWORDS])
            if CONF_EXCLUDE_KEYWORDS in options
            else list(DEFAULT_EXCLUDE_KEYWORDS)
        )
        overrides = options.get(CONF_PLAYER_OVERRIDES) or {}
        return cls(
            llm_provider=provider,
            ai_task_entity=_opt_str(options.get(CONF_AI_TASK_ENTITY)),
            conversation_agent=_opt_str(options.get(CONF_CONVERSATION_AGENT)),
            api_key=_opt_str(options.get(CONF_API_KEY)),
            model=_opt_str(options.get(CONF_MODEL)),
            ai_calls_per_hour=_int(
                CONF_AI_CALLS_PER_HOUR,
                DEFAULT_AI_CALLS_PER_HOUR,
                MIN_AI_CALLS_PER_HOUR,
                MAX_AI_CALLS_PER_HOUR,
            ),
            light_rate=_int(CONF_LIGHT_RATE, DEFAULT_LIGHT_RATE, MIN_LIGHT_RATE, MAX_LIGHT_RATE),
            allow_strobe=bool(options.get(CONF_ALLOW_STROBE, DEFAULT_ALLOW_STROBE)),
            excluded_lights=tuple(_str_list(options.get(CONF_EXCLUDED_LIGHTS))),
            exclude_keywords=tuple(keywords),
            player_overrides=MappingProxyType(
                {str(k): str(v) for k, v in overrides.items() if k and v}
            ),
            default_area=_opt_str(options.get(CONF_DEFAULT_AREA)),
            show_panel=bool(options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL)),
            blocking_entities=tuple(_str_list(options.get(CONF_BLOCKING_ENTITIES))),
            exclude_label=_opt_str(options.get(CONF_EXCLUDE_LABEL)) or DEFAULT_EXCLUDE_LABEL,
        )

    def public_dict(self) -> dict[str, Any]:
        """Settings safe to send to the browser (never the API key)."""
        return {
            CONF_LLM_PROVIDER: self.llm_provider,
            CONF_AI_TASK_ENTITY: self.ai_task_entity,
            CONF_CONVERSATION_AGENT: self.conversation_agent,
            CONF_MODEL: self.model,
            "has_api_key": bool(self.api_key),
            CONF_AI_CALLS_PER_HOUR: self.ai_calls_per_hour,
            CONF_LIGHT_RATE: self.light_rate,
            CONF_ALLOW_STROBE: self.allow_strobe,
            CONF_EXCLUDED_LIGHTS: list(self.excluded_lights),
            CONF_EXCLUDE_KEYWORDS: list(self.exclude_keywords),
            CONF_PLAYER_OVERRIDES: dict(self.player_overrides),
            CONF_DEFAULT_AREA: self.default_area,
            CONF_SHOW_PANEL: self.show_panel,
            CONF_BLOCKING_ENTITIES: list(self.blocking_entities),
            CONF_EXCLUDE_LABEL: self.exclude_label,
        }
