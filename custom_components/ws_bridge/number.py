"""number 플랫폼: 값 설정 → set_value 의도를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_NUMBER
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_NUMBER, async_add_entities, WsBridgeNumber)


class WsBridgeNumber(WsBridgeEntity, NumberEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        if (v := defn.get("min")) is not None:
            self._attr_native_min_value = v
        if (v := defn.get("max")) is not None:
            self._attr_native_max_value = v
        if (v := defn.get("step")) is not None:
            self._attr_native_step = v
        self._attr_native_unit_of_measurement = defn.get("unit_of_measurement")
        last = bridge.last_state(self._attr_unique_id)
        self._attr_native_value = last if not (isinstance(last, str) and last.lower() == "unknown") else None

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        if (v := defn.get("min")) is not None:
            self._attr_native_min_value = v
        if (v := defn.get("max")) is not None:
            self._attr_native_max_value = v
        if (v := defn.get("step")) is not None:
            self._attr_native_step = v
        self._attr_native_unit_of_measurement = defn.get("unit_of_measurement")

    async def async_added_to_hass(self) -> None:

        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = value if not (isinstance(value, str) and value.lower() == "unknown") else None
        safe_write_ha_state(self)

    async def async_set_native_value(self, value: float) -> None:
        self._bridge.send_command(self._attr_unique_id, "set_value", value)
        self._attr_native_value = value
        self.async_write_ha_state()
