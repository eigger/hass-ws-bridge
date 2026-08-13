"""text 플랫폼: 쓰기 가능 문자열 (text_sensor 와 별개 — HA text 도메인)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_TEXT
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_TEXT, async_add_entities, WsBridgeText)


def _as_length(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


class WsBridgeText(WsBridgeEntity, TextEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._attr_native_value = self._parse(bridge.last_state(self._attr_unique_id))

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        # number 의 min/max 는 값 범위, text 에서는 문자열 길이
        self._attr_native_min = _as_length(defn.get("min"), 0)
        self._attr_native_max = _as_length(defn.get("max"), 255)
        self._attr_pattern = defn.get("pattern")
        mode = (defn.get("mode") or "text").lower()
        self._attr_mode = TextMode.PASSWORD if mode == "password" else TextMode.TEXT

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = self._parse(value)
        safe_write_ha_state(self)

    @staticmethod
    def _parse(value: Any) -> str | None:
        if is_unknown(value):
            return None
        return str(value)

    async def async_set_value(self, value: str) -> None:
        self._send_command("set_value", value)
        self._attr_native_value = value
        self.async_write_ha_state()
