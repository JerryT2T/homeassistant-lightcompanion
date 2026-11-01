"""Config flow and options flow for Light Companion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BLOCKING_DOMAINS,
    CONF_AI_CALLS_PER_HOUR,
    CONF_AI_TASK_ENTITY,
    CONF_ALLOW_STROBE,
    CONF_API_KEY,
    CONF_BLOCKING_ENTITIES,
    CONF_CONVERSATION_AGENT,
    CONF_DEFAULT_AREA,
    CONF_EXCLUDE_KEYWORDS,
    CONF_EXCLUDE_LABEL,
    CONF_EXCLUDED_LIGHTS,
    CONF_LIGHT_RATE,
    CONF_LLM_PROVIDER,
    CONF_MODEL,
    CONF_SHOW_PANEL,
    DEFAULT_AI_CALLS_PER_HOUR,
    DEFAULT_ALLOW_STROBE,
    DEFAULT_EXCLUDE_KEYWORDS,
    DEFAULT_EXCLUDE_LABEL,
    DEFAULT_LIGHT_RATE,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_MODELS,
    DEFAULT_SHOW_PANEL,
    DOMAIN,
    KEY_PROVIDERS,
    LLM_PROVIDERS,
    MAX_AI_CALLS_PER_HOUR,
    MAX_LIGHT_RATE,
    MIN_AI_CALLS_PER_HOUR,
    MIN_LIGHT_RATE,
    PROVIDER_AI_TASK,
    PROVIDER_CONVERSATION,
)
from .settings import validate_options

# Optional form fields that are removed from the options when left empty.
_CLEARABLE = (
    CONF_AI_TASK_ENTITY,
    CONF_CONVERSATION_AGENT,
    CONF_MODEL,
    CONF_DEFAULT_AREA,
)


def _number(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


def _provider_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(LLM_PROVIDERS),
            translation_key="llm_provider",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


_KEY_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
_TEXT_SELECTOR = selector.TextSelector()
_KEYWORD_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
_AGENT_SELECTOR = selector.ConversationAgentSelector(selector.ConversationAgentSelectorConfig())
_AI_TASK_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task"))


class LightCompanionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick exactly one LLM provider."""

    VERSION = 1

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the provider."""
        if user_input is not None:
            provider = user_input[CONF_LLM_PROVIDER]
            self._options = {CONF_LLM_PROVIDER: provider}
            if provider == PROVIDER_AI_TASK:
                return await self.async_step_ai_task()
            if provider == PROVIDER_CONVERSATION:
                return await self.async_step_conversation()
            return await self.async_step_api()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LLM_PROVIDER, default=DEFAULT_LLM_PROVIDER
                    ): _provider_selector()
                }
            ),
        )

    async def async_step_ai_task(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional ai_task entity (empty = default entity)."""
        if user_input is not None:
            if user_input.get(CONF_AI_TASK_ENTITY):
                self._options[CONF_AI_TASK_ENTITY] = user_input[CONF_AI_TASK_ENTITY]
            return self._create()
        return self.async_show_form(
            step_id="ai_task",
            data_schema=vol.Schema({vol.Optional(CONF_AI_TASK_ENTITY): _AI_TASK_SELECTOR}),
        )

    async def async_step_conversation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Conversation agent used as the LLM."""
        if user_input is not None:
            self._options[CONF_CONVERSATION_AGENT] = user_input[CONF_CONVERSATION_AGENT]
            return self._create()
        return self.async_show_form(
            step_id="conversation",
            data_schema=vol.Schema({vol.Required(CONF_CONVERSATION_AGENT): _AGENT_SELECTOR}),
        )

    async def async_step_api(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """API key and model for own-key providers."""
        provider = self._options[CONF_LLM_PROVIDER]
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_API_KEY) or "").strip()
            if not key:
                errors[CONF_API_KEY] = "api_key_required"
            else:
                self._options[CONF_API_KEY] = key
                self._options[CONF_MODEL] = (
                    user_input.get(CONF_MODEL) or ""
                ).strip() or DEFAULT_MODELS[provider]
                return self._create()
        return self.async_show_form(
            step_id="api",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): _KEY_SELECTOR,
                    vol.Optional(CONF_MODEL, default=DEFAULT_MODELS[provider]): _TEXT_SELECTOR,
                }
            ),
            description_placeholders={"provider": provider},
            errors=errors,
        )

    def _create(self) -> ConfigFlowResult:
        return self.async_create_entry(title="Light Companion", data={}, options=self._options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return LightCompanionOptionsFlow()


def _suggested(options: Mapping[str, Any]) -> dict[str, Any]:
    """Values shown in the options form (API key is never prefilled)."""
    return {
        CONF_LLM_PROVIDER: options.get(CONF_LLM_PROVIDER, DEFAULT_LLM_PROVIDER),
        CONF_AI_TASK_ENTITY: options.get(CONF_AI_TASK_ENTITY),
        CONF_CONVERSATION_AGENT: options.get(CONF_CONVERSATION_AGENT),
        CONF_MODEL: options.get(CONF_MODEL),
        CONF_AI_CALLS_PER_HOUR: options.get(CONF_AI_CALLS_PER_HOUR, DEFAULT_AI_CALLS_PER_HOUR),
        CONF_LIGHT_RATE: options.get(CONF_LIGHT_RATE, DEFAULT_LIGHT_RATE),
        CONF_ALLOW_STROBE: options.get(CONF_ALLOW_STROBE, DEFAULT_ALLOW_STROBE),
        CONF_EXCLUDED_LIGHTS: options.get(CONF_EXCLUDED_LIGHTS, []),
        CONF_EXCLUDE_KEYWORDS: options.get(CONF_EXCLUDE_KEYWORDS, list(DEFAULT_EXCLUDE_KEYWORDS)),
        CONF_EXCLUDE_LABEL: options.get(CONF_EXCLUDE_LABEL, DEFAULT_EXCLUDE_LABEL),
        CONF_BLOCKING_ENTITIES: options.get(CONF_BLOCKING_ENTITIES, []),
        CONF_DEFAULT_AREA: options.get(CONF_DEFAULT_AREA),
        CONF_SHOW_PANEL: options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL),
    }


def _options_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LLM_PROVIDER): _provider_selector(),
            vol.Optional(CONF_AI_TASK_ENTITY): _AI_TASK_SELECTOR,
            vol.Optional(CONF_CONVERSATION_AGENT): _AGENT_SELECTOR,
            vol.Optional(CONF_API_KEY): _KEY_SELECTOR,
            vol.Optional(CONF_MODEL): _TEXT_SELECTOR,
            vol.Required(CONF_AI_CALLS_PER_HOUR): _number(
                MIN_AI_CALLS_PER_HOUR, MAX_AI_CALLS_PER_HOUR
            ),
            vol.Required(CONF_LIGHT_RATE): _number(MIN_LIGHT_RATE, MAX_LIGHT_RATE),
            vol.Required(CONF_ALLOW_STROBE): selector.BooleanSelector(),
            vol.Optional(CONF_EXCLUDED_LIGHTS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light", multiple=True)
            ),
            vol.Optional(CONF_EXCLUDE_KEYWORDS): _KEYWORD_SELECTOR,
            vol.Optional(CONF_EXCLUDE_LABEL): _TEXT_SELECTOR,
            vol.Optional(CONF_BLOCKING_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=list(BLOCKING_DOMAINS), multiple=True)
            ),
            vol.Optional(CONF_DEFAULT_AREA): selector.AreaSelector(),
            vol.Required(CONF_SHOW_PANEL): selector.BooleanSelector(),
        }
    )


class LightCompanionOptionsFlow(OptionsFlow):
    """Expose every option in one form."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Show or save the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**self.config_entry.options, **user_input}
            for key in _CLEARABLE:
                if key not in user_input:
                    merged.pop(key, None)
            # Blank key keeps the stored one.
            if not (user_input.get(CONF_API_KEY) or "").strip():
                if self.config_entry.options.get(CONF_API_KEY):
                    merged[CONF_API_KEY] = self.config_entry.options[CONF_API_KEY]
                else:
                    merged.pop(CONF_API_KEY, None)
            # Only the active provider's settings are meaningful.
            if merged[CONF_LLM_PROVIDER] not in KEY_PROVIDERS:
                merged.pop(CONF_MODEL, None)
            try:
                cleaned = validate_options(merged)
            except vol.Invalid as err:
                if str(err.msg) == "api_key_required":
                    errors[CONF_API_KEY] = "api_key_required"
                else:
                    errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(data=cleaned)
        suggested = _suggested(user_input if user_input is not None else self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_options_schema(), suggested),
            errors=errors,
        )
