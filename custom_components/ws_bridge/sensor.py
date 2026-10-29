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
from homeassistant.util import dt as dt_util

from .bridge import WsBridge, signal_clients
from .const import (
    CONNECTED_CLIENTS_UNIQUE_ID,
    DOMAIN,
    ICON_CONNECTED_CLIENTS,
    PLATFORM_SENSOR,
    PLATFORM_TEXT_SENSOR,
)
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SENSOR, async_add_entities, WsBridgeSensor)
    # HA has no separate "text_sensor" domain — string-state entities are just
    # sensor entities too, so route them through the same sensor platform setup.
    bridge.register_platform(
        PLATFORM_TEXT_SENSOR, async_add_entities, WsBridgeTextSensor
    )
    async_add_entities([WsBridgeConnectedClientsSensor(bridge, entry)])


_DATETIME_CLASSES = ("timestamp", "uptime")


def _parse_sensor_value(device_class: str | None, value: Any) -> Any:
    """Coerce a client value into what HA requires for this device class."""
    if value is None or (isinstance(value, str) and value.lower() == "unknown"):
        return None
    if device_class in _DATETIME_CLASSES:
        # HA raises (and the entity fails to add/write) for anything but an
        # aware datetime, so never pass through an unparsed value.
        if isinstance(value, bool):
            return None
        if isinstance(value, str):
            text = value.strip()
            # ISO forms first ("20261029" is a date, not an epoch); only a
            # string that is not a datetime falls back to a numeric epoch.
            if dt := dt_util.parse_datetime(text):
                return dt_util.as_local(dt) if dt.tzinfo is None else dt
            try:
                value = float(text)
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            try:
                # Epoch seconds, or milliseconds for clearly larger values.
                seconds = value / 1000 if abs(value) > 1e11 else value
                return dt_util.utc_from_timestamp(seconds)
            except (OverflowError, OSError, ValueError):
                return None
        return None
    if device_class == "date":
        if isinstance(value, str) and (d := dt_util.parse_date(value)) is not None:
            return d
        return None
    return value


class WsBridgeSensor(WsBridgeEntity, SensorEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_native_unit_of_measurement = defn.get("unit_of_measurement")
        self._attr_device_class = defn.get("device_class")
        self._attr_state_class = defn.get("state_class")
        self._attr_suggested_display_precision = defn.get("suggested_display_precision")
        last = bridge.last_state(self._attr_unique_id)
        self._attr_native_value = self._parse_value(last)

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_native_unit_of_measurement = defn.get("unit_of_measurement")
        self._attr_device_class = defn.get("device_class")
        self._attr_state_class = defn.get("state_class")
        self._attr_suggested_display_precision = defn.get("suggested_display_precision")
        # A new device class changes what the stored value must look like.
        self._attr_native_value = self._parse_value(
            self._bridge.last_state(self._attr_unique_id)
        )

    def _parse_value(self, value: Any) -> Any:
        return _parse_sensor_value(self._attr_device_class, value)

    async def async_added_to_hass(self) -> None:

        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = self._parse_value(value)
        safe_write_ha_state(self)


class WsBridgeTextSensor(WsBridgeEntity, SensorEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = defn.get("device_class")
        last = bridge.last_state(self._attr_unique_id)
        self._attr_native_value = self._parse_value(last)

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")
        self._attr_native_value = self._parse_value(
            self._bridge.last_state(self._attr_unique_id)
        )

    def _parse_value(self, value: Any) -> Any:
        return _parse_sensor_value(self._attr_device_class, value)

    async def async_added_to_hass(self) -> None:

        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = self._parse_value(value)
        safe_write_ha_state(self)


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
        safe_write_ha_state(self)
