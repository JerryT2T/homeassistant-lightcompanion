"""Constants for Light Companion."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "lightcompanion"
VERSION = "1.0.1"
PLATFORMS = [Platform.SWITCH]
FRONTEND_URL_BASE = "/lightcompanion_static"
CARD_JS = "lightcompanion-card.js"
PANEL_JS = "lightcompanion-panel.js"
PANEL_URL_PATH = "lightcompanion"
PANEL_COMPONENT_NAME = "lightcompanion-panel"
PANEL_TITLE = "Light Companion"
PANEL_ICON = "mdi:lightbulb-auto"
EVENT_STATUS = f"{DOMAIN}_status"

# Option keys
CONF_LLM_PROVIDER = "llm_provider"
CONF_AI_TASK_ENTITY = "ai_task_entity"
CONF_CONVERSATION_AGENT = "conversation_agent"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_AI_CALLS_PER_HOUR = "ai_calls_per_hour"
CONF_LIGHT_RATE = "light_rate"
CONF_ALLOW_STROBE = "allow_strobe"
CONF_EXCLUDED_LIGHTS = "excluded_lights"
CONF_EXCLUDE_KEYWORDS = "exclude_keywords"
CONF_PLAYER_OVERRIDES = "player_overrides"
CONF_DEFAULT_AREA = "default_area"
CONF_SHOW_PANEL = "show_panel"
CONF_BLOCKING_ENTITIES = "blocking_entities"
CONF_EXCLUDE_LABEL = "exclude_label"

PROVIDER_AI_TASK = "ai_task"
PROVIDER_CONVERSATION = "conversation"
LLM_PROVIDERS = ("ai_task", "conversation", "openai", "anthropic", "google")
KEY_PROVIDERS = ("openai", "anthropic", "google")
DEFAULT_MODELS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-haiku-4-5",
    "google": "gemini-2.5-flash",
}

# Defaults and ranges
DEFAULT_LLM_PROVIDER = PROVIDER_AI_TASK
DEFAULT_AI_CALLS_PER_HOUR = 50
MIN_AI_CALLS_PER_HOUR = 5
MAX_AI_CALLS_PER_HOUR = 200
DEFAULT_LIGHT_RATE = 4
MIN_LIGHT_RATE = 1
MAX_LIGHT_RATE = 10
DEFAULT_ALLOW_STROBE = False
DEFAULT_EXCLUDE_KEYWORDS = ("aquarium", "terrarium")
DEFAULT_SHOW_PANEL = False
DEFAULT_EXCLUDE_LABEL = "lightcompanion_exclude"
BLOCKING_DOMAINS = ("input_boolean", "switch", "binary_sensor")

# Service names
SERVICE_CHAT = "chat"
SERVICE_STOP = "stop"
