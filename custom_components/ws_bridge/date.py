"""date 플랫폼: ISO 날짜 문자열 ↔ HA date 엔티티."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_DATE
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_DATE, async_add_entities, WsBridgeDate)


def _parse_date(value: Any) -> date | None:
    if is_unknown(value) or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class WsBridgeDate(WsBridgeEntity, DateEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_native_value = _parse_date(bridge.last_state(self._attr_unique_id))

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        return

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = _parse_date(value)
        safe_write_ha_state(self)

    async def async_set_value(self, value: date) -> None:
        text = value.isoformat()
        self._send_command("set_value", text)
        self._attr_native_value = value
        self.async_write_ha_state()
