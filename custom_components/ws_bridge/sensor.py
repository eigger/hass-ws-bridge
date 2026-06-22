"""sensor 플랫폼: 클라이언트가 선언하면 동적 생성."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_SENSOR
from .entity import WsBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SENSOR, async_add_entities, WsBridgeSensor)


class WsBridgeSensor(WsBridgeEntity, SensorEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_native_unit_of_measurement = defn.get("unit_of_measurement")
        self._attr_device_class = defn.get("device_class")
        self._attr_state_class = defn.get("state_class")
        self._attr_native_value = bridge.last_state(self._attr_unique_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
