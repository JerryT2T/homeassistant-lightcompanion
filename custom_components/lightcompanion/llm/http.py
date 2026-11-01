"""Own-API-key providers (OpenAI, Anthropic, Google) over HA's shared session."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DEFAULT_MODELS
from .base import (
    CODE_INVALID_JSON,
    CODE_NO_ANSWER,
    CODE_NOT_CONFIGURED,
    CODE_REQUEST_FAILED,
    CODE_TIMEOUT,
    JSON_ONLY_SYSTEM,
    REQUEST_TIMEOUT_S,
    LLMError,
    extract_json,
    schema_hint,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ANTHROPIC_MAX_TOKENS = 1024


def build_request(
    provider: str, model: str, key: str, system: str, user: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """URL, headers and body for one provider (pure, no I/O)."""
    if provider == "openai":
        return (
            OPENAI_URL,
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    if provider == "anthropic":
        return (
            ANTHROPIC_URL,
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": ANTHROPIC_MAX_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
    if provider == "google":
        return (
            GOOGLE_URL.format(model=model),
            {"x-goog-api-key": key},  # header, not query string: keys stay out of URLs
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
    raise LLMError(CODE_NOT_CONFIGURED, f"unknown provider {provider}")


def parse_response(provider: str, data: Any) -> str | None:
    """Answer text out of a provider response body."""
    try:
        if provider == "openai":
            content = data["choices"][0]["message"]["content"]
            return content if isinstance(content, str) else None
        if provider == "anthropic":
            parts = [b.get("text", "") for b in data["content"] if isinstance(b, dict)]
            return "".join(parts) or None
        if provider == "google":
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict)) or None
    except (KeyError, IndexError, TypeError):
        return None
    return None


class HttpClient:
    """JSON-mode chat call against a vendor API with the user's own key."""

    def __init__(
        self, hass: HomeAssistant, provider: str, api_key: str | None, model: str | None
    ) -> None:
        self._hass = hass
        self._provider = provider
        self._key = api_key
        self._model = model or DEFAULT_MODELS.get(provider)

    async def async_generate(
        self, *, task_name: str, instructions: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        if not self._key or not self._model:
            raise LLMError(CODE_NOT_CONFIGURED, "API key or model missing")
        url, headers, body = build_request(
            self._provider,
            self._model,
            self._key,
            f"{JSON_ONLY_SYSTEM}\n{schema_hint(schema)}",
            instructions,
        )
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
            ) as resp:
                if resp.status != 200:  # noqa: PLR2004
                    _LOGGER.warning(
                        "%s answered HTTP %s for %s", self._provider, resp.status, task_name
                    )
                    raise LLMError(CODE_REQUEST_FAILED, f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except TimeoutError as err:
            raise LLMError(CODE_TIMEOUT) from err
        except aiohttp.ClientError as err:
            # never include request details: headers carry the key
            raise LLMError(CODE_REQUEST_FAILED, type(err).__name__) from err
        except ValueError as err:
            raise LLMError(CODE_INVALID_JSON) from err
        text = parse_response(self._provider, data)
        if text is None:
            raise LLMError(CODE_NO_ANSWER)
        return extract_json(text)
