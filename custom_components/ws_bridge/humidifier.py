"""humidifier 플랫폼: on/off·습도·모드 → turn_on/set_* 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_HUMIDIFIER
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_ACTION_MAP = {
    "humidifying": HumidifierAction.HUMIDIFYING,
    "drying": HumidifierAction.DRYING,
    "idle": HumidifierAction.IDLE,
    "off": HumidifierAction.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_HUMIDIFIER, async_add_entities, WsBridgeHumidifier)


def _features(
    names: list[str] | None, *, has_modes: bool
) -> HumidifierEntityFeature:
    flags = HumidifierEntityFeature(0)
    for name in names or ():
        if name == "modes":
            flags |= HumidifierEntityFeature.MODES
    if has_modes:
        flags |= HumidifierEntityFeature.MODES
    else:
        flags &= ~HumidifierEntityFeature.MODES
    return flags


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WsBridgeHumidifier(WsBridgeCompositeEntity, HumidifierEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")
        if (min_hum := defn.get("min_humidity")) is not None:
            self._attr_min_humidity = float(min_hum)
        if (max_hum := defn.get("max_humidity")) is not None:
            self._attr_max_humidity = float(max_hum)
        modes = defn.get("available_modes")
        self._attr_available_modes = list(modes) if modes else None
        self._attr_supported_features = _features(
            defn.get("features"), has_modes=bool(self._attr_available_modes)
        )

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        self._attr_is_on = parse_bool(self._state.get("state"))
        self._attr_current_humidity = _as_float(self._state.get("current_humidity"))
        self._attr_target_humidity = _as_float(self._state.get("target_humidity"))
        mode = self._state.get("mode")
        self._attr_mode = str(mode) if mode is not None else None
        action = self._state.get("action")
        self._attr_action = (
            _ACTION_MAP.get(str(action).lower()) if action is not None else None
        )
    async def async_turn_on(self, **kwargs: Any) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_on")
        self._state["state"] = "on"
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_off")
        self._state["state"] = "off"
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_humidity(self, humidity: int) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "set_humidity", params={"humidity": humidity}
        )
        self._state["target_humidity"] = humidity
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_mode(self, mode: str) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "set_mode", params={"mode": mode}
        )
        self._state["mode"] = mode
        self._apply_state()
        self.async_write_ha_state()
