"""light 플랫폼: 밝기/색상 등 복합 상태 → turn_on/turn_off 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_LIGHT
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_COLOR_MODE_MAP = {
    "onoff": ColorMode.ONOFF,
    "brightness": ColorMode.BRIGHTNESS,
    "color_temp": ColorMode.COLOR_TEMP,
    "hs": ColorMode.HS,
    "rgb": ColorMode.RGB,
    "rgbw": ColorMode.RGBW,
    "rgbww": ColorMode.RGBWW,
    "white": ColorMode.WHITE,
}

_FEATURE_MAP = {
    "transition": LightEntityFeature.TRANSITION,
    "flash": LightEntityFeature.FLASH,
    "effect": LightEntityFeature.EFFECT,
}

# HA turn_on kwargs 키 → 프로토콜 params 키 (동일 이름). tuple 은 list 로 변환.
_TURN_ON_KEYS = (
    "brightness",
    "color_temp_kelvin",
    "hs_color",
    "rgb_color",
    "rgbw_color",
    "rgbww_color",
    "white",
    "effect",
    "transition",
    "flash",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_LIGHT, async_add_entities, WsBridgeLight)


def _color_modes(names: list[str] | None) -> set[ColorMode]:
    modes: set[ColorMode] = set()
    for name in names or ():
        if (mode := _COLOR_MODE_MAP.get(name)) is not None:
            modes.add(mode)
    return modes or {ColorMode.ONOFF}


def _features(names: list[str] | None, *, has_effects: bool) -> LightEntityFeature:
    flags = LightEntityFeature(0)
    for name in names or ():
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    if has_effects:
        flags |= LightEntityFeature.EFFECT
    return flags


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    return value


class WsBridgeLight(WsBridgeCompositeEntity, LightEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        effects = defn.get("effect_list") or None
        self._attr_effect_list = list(effects) if effects else None
        self._attr_supported_color_modes = _color_modes(defn.get("supported_color_modes"))
        self._attr_supported_features = _features(
            defn.get("features"), has_effects=bool(self._attr_effect_list)
        )
        if (v := defn.get("min_color_temp_kelvin")) is not None:
            self._attr_min_color_temp_kelvin = int(v)
        if (v := defn.get("max_color_temp_kelvin")) is not None:
            self._attr_max_color_temp_kelvin = int(v)

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        self._attr_is_on = parse_bool(self._state.get("state"))
        brightness = self._state.get("brightness")
        self._attr_brightness = int(brightness) if brightness is not None else None
        color_mode = self._state.get("color_mode")
        if isinstance(color_mode, str) and color_mode in _COLOR_MODE_MAP:
            self._attr_color_mode = _COLOR_MODE_MAP[color_mode]
        elif len(self._attr_supported_color_modes or ()) == 1:
            self._attr_color_mode = next(iter(self._attr_supported_color_modes))
        else:
            self._attr_color_mode = None
        kelvin = self._state.get("color_temp_kelvin")
        self._attr_color_temp_kelvin = int(kelvin) if kelvin is not None else None
        self._attr_hs_color = self._tuple_or_none(self._state.get("hs_color"), 2)
        self._attr_rgb_color = self._tuple_or_none(self._state.get("rgb_color"), 3)
        self._attr_rgbw_color = self._tuple_or_none(self._state.get("rgbw_color"), 4)
        self._attr_rgbww_color = self._tuple_or_none(self._state.get("rgbww_color"), 5)
        effect = self._state.get("effect")
        self._attr_effect = str(effect) if effect is not None else None

    @staticmethod
    def _tuple_or_none(value: Any, size: int) -> tuple | None:
        if not isinstance(value, (list, tuple)) or len(value) != size:
            return None
        try:
            return tuple(float(v) if size == 2 else int(v) for v in value)
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        params = {
            key: _jsonable(kwargs[key])
            for key in _TURN_ON_KEYS
            if key in kwargs and kwargs[key] is not None
        }
        self._bridge.send_command(
            self._attr_unique_id, "turn_on", params=params or None
        )
        self._state["state"] = "on"
        for key, val in params.items():
            if key not in ("transition", "flash"):
                self._state[key] = val
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        params = {}
        if (transition := kwargs.get("transition")) is not None:
            params["transition"] = transition
        self._bridge.send_command(
            self._attr_unique_id, "turn_off", params=params or None
        )
        self._state["state"] = "off"
        self._apply_state()
        self.async_write_ha_state()
