"""binary_sensor 플랫폼: 불리언 상태(켜짐/꺼짐, 감지/접촉 등)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_BINARY_SENSOR
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_BINARY_SENSOR, async_add_entities, WsBridgeBinarySensor)


def _truthy(value: Any) -> bool | None:
    if value is None or (isinstance(value, str) and value.lower() == "unknown"):
        return None
    if isinstance(value, str):
        return value.lower() in ("1", "true", "on", "yes")
    return bool(value)


class WsBridgeBinarySensor(WsBridgeEntity, BinarySensorEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = defn.get("device_class")
        last = bridge.last_state(self._attr_unique_id)
        self._attr_is_on = _truthy(last)

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")

    async def async_added_to_hass(self) -> None:

        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_is_on = _truthy(value)
        safe_write_ha_state(self)
