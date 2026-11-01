"""LLM client protocol, error type and JSON helpers shared by all providers."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

CODE_TIMEOUT = "timeout"
CODE_REQUEST_FAILED = "request_failed"
CODE_NO_ANSWER = "no_answer"
CODE_INVALID_JSON = "invalid_json"
CODE_NOT_CONFIGURED = "not_configured"

REQUEST_TIMEOUT_S = 20

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

JSON_ONLY_SYSTEM = (
    "You are a strict JSON API. Reply with exactly one JSON object and nothing else: "
    "no prose, no markdown fences."
)


class LLMError(Exception):
    """Provider failure; ``code`` is one of the CODE_* values."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


class LLMClient(Protocol):
    """One structured generation call. Never called per beat."""

    async def async_generate(
        self, *, task_name: str, instructions: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Return the JSON object answering ``instructions`` in the shape of ``schema``.

        ``schema`` is a Home Assistant ``ai_task`` structure (field -> selector).
        """
        ...


def extract_json(text: str | None) -> dict[str, Any]:
    """Pull one JSON object out of a model answer (fences, surrounding prose)."""
    if not text or not text.strip():
        raise LLMError(CODE_NO_ANSWER)
    candidates: list[str] = [text.strip()]
    candidates.extend(m.strip() for m in _FENCE.findall(text))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise LLMError(CODE_INVALID_JSON)


def _field_schema(spec: dict[str, Any]) -> dict[str, Any]:
    selector = spec.get("selector") or {}
    out: dict[str, Any]
    if "boolean" in selector:
        out = {"type": "boolean"}
    elif "number" in selector:
        cfg = selector["number"] or {}
        out = {"type": "number"}
        if "min" in cfg:
            out["minimum"] = cfg["min"]
        if "max" in cfg:
            out["maximum"] = cfg["max"]
    elif "select" in selector:
        cfg = selector["select"] or {}
        item: dict[str, Any] = {"type": "string"}
        if cfg.get("options"):
            item["enum"] = [str(o) for o in cfg["options"]]
        out = {"type": "array", "items": item} if cfg.get("multiple") else item
    elif "object" in selector:
        out = {"type": "object"}
    else:  # text and anything unknown
        cfg = selector.get("text") or {}
        out = {"type": "string"}
        if cfg.get("multiple"):
            out = {"type": "array", "items": {"type": "string"}}
    if spec.get("description"):
        out["description"] = spec["description"]
    return out


def structure_to_json_schema(structure: dict[str, Any]) -> dict[str, Any]:
    """Convert an ``ai_task`` structure to a plain JSON Schema (for prompts)."""
    return {
        "type": "object",
        "properties": {name: _field_schema(spec) for name, spec in structure.items()},
        "required": [name for name, spec in structure.items() if spec.get("required")],
    }


def schema_hint(structure: dict[str, Any]) -> str:
    """Text block telling a free-form model which JSON to return."""
    return "Return ONLY a JSON object matching this JSON Schema:\n" + json.dumps(
        structure_to_json_schema(structure), separators=(",", ":")
    )
