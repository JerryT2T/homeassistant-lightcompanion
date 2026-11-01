"""Build the one active LLM client from the settings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .ai_task import AiTaskClient
from .base import CODE_NOT_CONFIGURED, CODE_REQUEST_FAILED, LLMClient, LLMError
from .conversation import ConversationClient
from .http import HttpClient

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..settings import Settings

_LOGGER = logging.getLogger(__name__)

HTTP_PROVIDERS = ("openai", "anthropic", "google")
_FALLBACK_CODES = (CODE_NOT_CONFIGURED, CODE_REQUEST_FAILED)


class FallbackClient:
    """``ai_task`` first; ``conversation.process`` when ai_task is unusable."""

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self._primary = primary
        self._fallback = fallback

    async def async_generate(
        self, *, task_name: str, instructions: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return await self._primary.async_generate(
                task_name=task_name, instructions=instructions, schema=schema
            )
        except LLMError as err:
            if err.code not in _FALLBACK_CODES:
                raise
            _LOGGER.debug("ai_task unusable (%s), falling back to conversation", err.code)
            return await self._fallback.async_generate(
                task_name=task_name, instructions=instructions, schema=schema
            )


def create_client(hass: HomeAssistant, settings: Settings) -> LLMClient:
    """Exactly one provider is active: ``settings.llm_provider``."""
    provider = settings.llm_provider
    if provider == "ai_task":
        return FallbackClient(
            AiTaskClient(hass, settings.ai_task_entity),
            ConversationClient(hass, settings.conversation_agent),
        )
    if provider == "conversation":
        return ConversationClient(hass, settings.conversation_agent)
    if provider in HTTP_PROVIDERS:
        return HttpClient(hass, provider, settings.api_key, settings.model)
    raise LLMError(CODE_NOT_CONFIGURED, f"unknown provider {provider}")
