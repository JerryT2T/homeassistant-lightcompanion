"""Fallback provider: ``conversation.process`` plus strict JSON extraction."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .base import (
    CODE_NO_ANSWER,
    CODE_REQUEST_FAILED,
    CODE_TIMEOUT,
    JSON_ONLY_SYSTEM,
    LLMError,
    extract_json,
    schema_hint,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CALL_TIMEOUT_S = 45


def _speech(result: Any) -> str | None:
    """Plain speech text of a ``conversation.process`` response."""
    try:
        speech = result["response"]["speech"]["plain"]["speech"]
    except (KeyError, TypeError):
        return None
    return speech if isinstance(speech, str) else None


class ConversationClient:
    """Asks a conversation agent to answer with JSON only."""

    def __init__(self, hass: HomeAssistant, agent_id: str | None = None) -> None:
        self._hass = hass
        self._agent_id = agent_id

    async def async_generate(
        self, *, task_name: str, instructions: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        from homeassistant.exceptions import HomeAssistantError

        data: dict[str, Any] = {
            "text": f"{JSON_ONLY_SYSTEM}\n\n{instructions}\n\n{schema_hint(schema)}",
        }
        if self._agent_id:
            data["agent_id"] = self._agent_id
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                result = await self._hass.services.async_call(
                    "conversation",
                    "process",
                    data,
                    blocking=True,
                    return_response=True,
                )
        except TimeoutError as err:
            raise LLMError(CODE_TIMEOUT) from err
        except HomeAssistantError as err:
            _LOGGER.warning("conversation.process failed: %s", err)
            raise LLMError(CODE_REQUEST_FAILED, str(err)) from err
        speech = _speech(result)
        if speech is None:
            raise LLMError(CODE_NO_ANSWER)
        return extract_json(speech)
