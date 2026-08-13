"""water_heater 플랫폼: 온도/운전모드/외출 → set_* 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_WATER_HEATER
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_FEATURE_MAP = {
    "target_temperature": WaterHeaterEntityFeature.TARGET_TEMPERATURE,
    "operation_mode": WaterHeaterEntityFeature.OPERATION_MODE,
    "away_mode": WaterHeaterEntityFeature.AWAY_MODE,
    "on_off": WaterHeaterEntityFeature.ON_OFF,
}

_DEFAULT_BASE = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.ON_OFF
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(
        PLATFORM_WATER_HEATER, async_add_entities, WsBridgeWaterHeater
    )


def _features(
    names: list[str] | None, *, has_operation_list: bool
) -> WaterHeaterEntityFeature:
    if not names:
        flags = _DEFAULT_BASE
        if has_operation_list:
            flags |= WaterHeaterEntityFeature.OPERATION_MODE
        return flags
    flags = WaterHeaterEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    if has_operation_list:
        flags |= WaterHeaterEntityFeature.OPERATION_MODE
    else:
        flags &= ~WaterHeaterEntityFeature.OPERATION_MODE
    return flags or (
        _DEFAULT_BASE
        | (
            WaterHeaterEntityFeature.OPERATION_MODE
            if has_operation_list
            else WaterHeaterEntityFeature(0)
        )
    )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WsBridgeWaterHeater(WsBridgeCompositeEntity, WaterHeaterEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        ops = defn.get("operation_list")
        self._attr_operation_list = list(ops) if ops else None
        if (min_temp := defn.get("min_temp")) is not None:
            self._attr_min_temp = float(min_temp)
        if (max_temp := defn.get("max_temp")) is not None:
            self._attr_max_temp = float(max_temp)
        unit = str(defn.get("temperature_unit") or "").upper()
        if unit in ("F", "°F", "FAHRENHEIT"):
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = _features(
            defn.get("features"),
            has_operation_list=bool(self._attr_operation_list),
        )
    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        state = self._state.get("state")
        self._attr_current_operation = str(state) if state is not None else None
        self._attr_current_temperature = _as_float(
            self._state.get("current_temperature")
        )
        self._attr_target_temperature = _as_float(self._state.get("target_temperature"))
        away = self._state.get("away_mode")
        if away is None:
            self._attr_is_away_mode_on = None
        elif isinstance(away, bool):
            self._attr_is_away_mode_on = away
        else:
            self._attr_is_away_mode_on = parse_bool(away)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        params = {"temperature": temperature} if temperature is not None else None
        self._send_command(
            "set_temperature", params=params
        )
        if temperature is not None:
            self._state["target_temperature"] = temperature
        self._publish_state()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        self._send_command(
            "set_operation_mode",
            params={"operation_mode": operation_mode},
        )
        self._state["state"] = operation_mode
        self._publish_state()

    async def async_turn_away_mode_on(self) -> None:
        self._send_command(
            "set_away_mode", params={"away_mode": True}
        )
        self._state["away_mode"] = True
        self._publish_state()

    async def async_turn_away_mode_off(self) -> None:
        self._send_command(
            "set_away_mode", params={"away_mode": False}
        )
        self._state["away_mode"] = False
        self._publish_state()

    async def async_turn_on(self) -> None:
        self._send_command("turn_on")

    async def async_turn_off(self) -> None:
        self._send_command("turn_off")
