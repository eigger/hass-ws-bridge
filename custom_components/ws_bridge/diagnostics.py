"""Diagnostics support for WebSocket Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ALLOWED_USER_IDS, DOMAIN

TO_REDACT = {CONF_ALLOWED_USER_IDS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    bridge = hass.data[DOMAIN][entry.entry_id]
    options = dict(entry.options)
    allowed = options.get(CONF_ALLOWED_USER_IDS) or []
    return {
        "options": async_redact_data(options, TO_REDACT),
        "allowed_user_count": len(allowed),
        "bridge": bridge.diagnostics(),
    }
