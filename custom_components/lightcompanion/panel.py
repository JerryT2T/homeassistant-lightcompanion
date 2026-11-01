"""Frontend delivery: static path, always-on card module, optional hidden panel.

Every URL carries ``?v=<VERSION>`` because the static path is served with long
cache headers. Registration is idempotent and reversible (config entry reloads).
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    CARD_JS,
    DOMAIN,
    FRONTEND_URL_BASE,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_JS,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_STATIC_FLAG = "frontend_static_registered"

CARD_MODULE_URL = f"{FRONTEND_URL_BASE}/{CARD_JS}?v={VERSION}"
PANEL_MODULE_URL = f"{FRONTEND_URL_BASE}/{PANEL_JS}?v={VERSION}"


def resolve_static_file(name: str) -> Path | None:
    """Resolve ``name`` inside the frontend dir; None if it escapes (path guard)."""
    base = _FRONTEND_DIR.resolve()
    target = (base / name).resolve()
    return target if target.is_relative_to(base) else None


async def async_register_frontend(hass: HomeAssistant, *, show_panel: bool) -> None:
    """Mount static files, load the card everywhere, optionally add the panel."""
    store = hass.data.setdefault(DOMAIN, {})

    # Static paths cannot be unregistered, so mount exactly once per process.
    if not store.get(_STATIC_FLAG):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL_BASE, str(_FRONTEND_DIR), True)]
        )
        store[_STATIC_FLAG] = True

    # Always loaded so the card shows up in the card picker.
    frontend.add_extra_js_url(hass, CARD_MODULE_URL)

    # async_register_built_in_panel raises on a duplicate path.
    if show_panel and PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT_NAME,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=PANEL_MODULE_URL,
            require_admin=False,
        )
    _LOGGER.debug("Frontend registered (panel=%s)", show_panel)


def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Remove panel and card module (the static mount stays)."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    try:
        frontend.remove_extra_js_url(hass, CARD_MODULE_URL)
    except KeyError:
        _LOGGER.debug("Card module was not registered, nothing to remove")
