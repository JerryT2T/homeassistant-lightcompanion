"""Default provider: Home Assistant ``ai_task.generate_data`` with a structure."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .base import (
    CODE_NO_ANSWER,
    CODE_NOT_CONFIGURED,
    CODE_REQUEST_FAILED,
    CODE_TIMEOUT,
    LLMError,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CALL_TIMEOUT_S = 45


class AiTaskClient:
    """Calls the user's configured AI Task entity (any HA LLM integration)."""

    def __init__(self, hass: HomeAssistant, entity_id: str | None = None) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def async_generate(
        self, *, task_name: str, instructions: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

        data: dict[str, Any] = {
            "task_name": task_name,
            "instructions": instructions,
            "structure": schema,
        }
        if self._entity_id:
            data["entity_id"] = self._entity_id
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                result = await self._hass.services.async_call(
                    "ai_task",
                    "generate_data",
                    data,
                    blocking=True,
                    return_response=True,
                )
        except TimeoutError as err:
            raise LLMError(CODE_TIMEOUT) from err
        except ServiceNotFound as err:
            raise LLMError(CODE_NOT_CONFIGURED, "ai_task is not available") from err
        except HomeAssistantError as err:
            _LOGGER.warning("ai_task.generate_data failed: %s", err)
            raise LLMError(CODE_REQUEST_FAILED, str(err)) from err
        payload = result.get("data") if isinstance(result, dict) else None
        if isinstance(payload, dict):
            return payload
        raise LLMError(CODE_NO_ANSWER)
