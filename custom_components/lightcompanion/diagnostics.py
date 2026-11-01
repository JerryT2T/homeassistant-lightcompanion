"""Diagnostics for Light Companion (secrets redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, VERSION

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the entry."""
    data = getattr(entry, "runtime_data", None)
    return {
        "version": VERSION,
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "engine": data.engine.status() if data else None,
        "planner": data.planner.status() if data else None,
    }
