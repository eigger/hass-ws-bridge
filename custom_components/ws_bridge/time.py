"""time 플랫폼: ISO 시각 문자열 ↔ HA time 엔티티."""
from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_TIME
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_TIME, async_add_entities, WsBridgeTime)


def _parse_time(value: Any) -> time | None:
    if is_unknown(value) or not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


class WsBridgeTime(WsBridgeEntity, TimeEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_native_value = _parse_time(bridge.last_state(self._attr_unique_id))

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        return

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = _parse_time(value)
        safe_write_ha_state(self)

    async def async_set_value(self, value: time) -> None:
        text = value.isoformat()
        self._bridge.send_command(self._attr_unique_id, "set_value", text)
        self._attr_native_value = value
        self.async_write_ha_state()
