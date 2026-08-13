"""climate 플랫폼: HVAC 모드/온도/습도/팬/스윙 → set_* 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_CLIMATE
from .entity import WsBridgeCompositeEntity

_HVAC_MODE_MAP = {
    "off": HVACMode.OFF,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "heat_cool": HVACMode.HEAT_COOL,
    "auto": HVACMode.AUTO,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
}

_HVAC_ACTION_MAP = {
    "off": HVACAction.OFF,
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "drying": HVACAction.DRYING,
    "fan": HVACAction.FAN,
    "idle": HVACAction.IDLE,
    "preheating": HVACAction.PREHEATING,
    "defrosting": HVACAction.DEFROSTING,
}

_FEATURE_MAP = {
    "target_temperature": ClimateEntityFeature.TARGET_TEMPERATURE,
    "target_temperature_range": ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
    "target_humidity": ClimateEntityFeature.TARGET_HUMIDITY,
    "fan_mode": ClimateEntityFeature.FAN_MODE,
    "preset_mode": ClimateEntityFeature.PRESET_MODE,
    "swing_mode": ClimateEntityFeature.SWING_MODE,
    "turn_on": ClimateEntityFeature.TURN_ON,
    "turn_off": ClimateEntityFeature.TURN_OFF,
}

_DEFAULT_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_CLIMATE, async_add_entities, WsBridgeClimate)


def _hvac_modes(names: list[str] | None) -> list[HVACMode]:
    modes: list[HVACMode] = []
    for name in names or ():
        if (mode := _HVAC_MODE_MAP.get(str(name).lower())) is not None:
            modes.append(mode)
    return modes or [HVACMode.OFF]


def _features(names: list[str] | None) -> ClimateEntityFeature:
    if not names:
        return _DEFAULT_FEATURES
    flags = ClimateEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    return flags or _DEFAULT_FEATURES


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WsBridgeClimate(WsBridgeCompositeEntity, ClimateEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_hvac_modes = _hvac_modes(defn.get("hvac_modes"))
        self._attr_fan_modes = list(defn["fan_modes"]) if defn.get("fan_modes") else None
        self._attr_swing_modes = (
            list(defn["swing_modes"]) if defn.get("swing_modes") else None
        )
        self._attr_preset_modes = (
            list(defn["preset_modes"]) if defn.get("preset_modes") else None
        )
        if (min_temp := defn.get("min_temp")) is not None:
            self._attr_min_temp = float(min_temp)
        if (max_temp := defn.get("max_temp")) is not None:
            self._attr_max_temp = float(max_temp)
        if (step := defn.get("target_temp_step")) is not None:
            self._attr_target_temperature_step = float(step)
        if (min_hum := defn.get("min_humidity")) is not None:
            self._attr_min_humidity = float(min_hum)
        if (max_hum := defn.get("max_humidity")) is not None:
            self._attr_max_humidity = float(max_hum)
        unit = str(defn.get("temperature_unit") or "").upper()
        if unit in ("F", "°F", "FAHRENHEIT"):
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = _features(defn.get("features"))

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        mode = self._state.get("hvac_mode")
        self._attr_hvac_mode = (
            _HVAC_MODE_MAP.get(str(mode).lower()) if mode is not None else None
        )
        action = self._state.get("hvac_action")
        self._attr_hvac_action = (
            _HVAC_ACTION_MAP.get(str(action).lower()) if action is not None else None
        )
        self._attr_current_temperature = _as_float(
            self._state.get("current_temperature")
        )
        self._attr_target_temperature = _as_float(self._state.get("target_temperature"))
        self._attr_target_temperature_low = _as_float(self._state.get("target_temp_low"))
        self._attr_target_temperature_high = _as_float(
            self._state.get("target_temp_high")
        )
        self._attr_current_humidity = _as_float(self._state.get("current_humidity"))
        self._attr_target_humidity = _as_float(self._state.get("target_humidity"))
        fan = self._state.get("fan_mode")
        self._attr_fan_mode = str(fan) if fan is not None else None
        swing = self._state.get("swing_mode")
        self._attr_swing_mode = str(swing) if swing is not None else None
        preset = self._state.get("preset_mode")
        self._attr_preset_mode = str(preset) if preset is not None else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._bridge.send_command(
            self._attr_unique_id,
            "set_hvac_mode",
            params={"hvac_mode": hvac_mode},
        )
        self._state["hvac_mode"] = hvac_mode
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        params: dict[str, Any] = {}
        if "temperature" in kwargs:
            params["temperature"] = kwargs["temperature"]
        if "target_temp_low" in kwargs:
            params["target_temp_low"] = kwargs["target_temp_low"]
        if "target_temp_high" in kwargs:
            params["target_temp_high"] = kwargs["target_temp_high"]
        self._bridge.send_command(
            self._attr_unique_id, "set_temperature", params=params or None
        )
        if "temperature" in params:
            self._state["target_temperature"] = params["temperature"]
        if "target_temp_low" in params:
            self._state["target_temp_low"] = params["target_temp_low"]
        if "target_temp_high" in params:
            self._state["target_temp_high"] = params["target_temp_high"]
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "set_fan_mode", params={"fan_mode": fan_mode}
        )
        self._state["fan_mode"] = fan_mode
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "set_swing_mode", params={"swing_mode": swing_mode}
        )
        self._state["swing_mode"] = swing_mode
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._bridge.send_command(
            self._attr_unique_id,
            "set_preset_mode",
            params={"preset_mode": preset_mode},
        )
        self._state["preset_mode"] = preset_mode
        self._apply_state()
        self.async_write_ha_state()

    async def async_set_humidity(self, humidity: float) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "set_humidity", params={"humidity": humidity}
        )
        self._state["target_humidity"] = humidity
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_on")
        if self._attr_hvac_mode in (None, HVACMode.OFF) and self._attr_hvac_modes:
            for mode in self._attr_hvac_modes:
                if mode != HVACMode.OFF:
                    self._state["hvac_mode"] = mode
                    break
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_off")
        self._state["hvac_mode"] = HVACMode.OFF
        self._apply_state()
        self.async_write_ha_state()
