"""sensor 플랫폼: 클라이언트가 선언하면 동적 생성 + 통합 진단 센서."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge, signal_clients
from .const import CONNECTED_CLIENTS_UNIQUE_ID, DOMAIN, ICON_CONNECTED_CLIENTS, PLATFORM_SENSOR
from .entity import WsBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SENSOR, async_add_entities, WsBridgeSensor)
    async_add_entities([WsBridgeConnectedClientsSensor(bridge, entry)])


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


class WsBridgeConnectedClientsSensor(SensorEntity):
    """현재 WebSocket으로 연결된 클라이언트(gateway_id) 수."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = CONNECTED_CLIENTS_UNIQUE_ID
    _attr_icon = ICON_CONNECTED_CLIENTS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, bridge: WsBridge, entry: ConfigEntry) -> None:
        self._bridge = bridge
        self._attr_unique_id = f"{entry.entry_id}_{CONNECTED_CLIENTS_UNIQUE_ID}"
        self._attr_native_value = bridge.connected_client_count
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="WebSocket Bridge",
            manufacturer="ws_bridge",
            model="Bridge",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_clients(self._bridge.entry_id),
                self._on_count_changed,
            )
        )

    @callback
    def _on_count_changed(self, count: int) -> None:
        self._attr_native_value = count
        self.async_write_ha_state()
