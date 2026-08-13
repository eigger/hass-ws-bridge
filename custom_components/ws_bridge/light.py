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

# HA: ONOFF/BRIGHTNESS 는 다른 색상 모드와 함께 쓸 수 없다.
_STANDALONE_MODES = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}

# color_mode 생략 시 상태 키로 추론 (우선순위: 더 구체적인 색 모드 먼저)
_INFER_COLOR_MODE = (
    ("rgbww_color", ColorMode.RGBWW),
    ("rgbw_color", ColorMode.RGBW),
    ("rgb_color", ColorMode.RGB),
    ("hs_color", ColorMode.HS),
    ("color_temp_kelvin", ColorMode.COLOR_TEMP),
    ("white", ColorMode.WHITE),
    ("brightness", ColorMode.BRIGHTNESS),
)

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


def _as_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    """형제 플랫폼의 _as_position / _coerce_float 과 동일 — 파싱 실패 시 None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _color_modes(names: list[str] | None) -> set[ColorMode]:
    modes: set[ColorMode] = set()
    for name in names or ():
        if (mode := _COLOR_MODE_MAP.get(name)) is not None:
            modes.add(mode)
    if not modes:
        return {ColorMode.ONOFF}
    # 색상 모드가 하나라도 있으면 ONOFF/BRIGHTNESS 를 제거 (HA 배타 규칙)
    if modes - _STANDALONE_MODES:
        modes -= _STANDALONE_MODES
    elif ColorMode.ONOFF in modes and ColorMode.BRIGHTNESS in modes:
        modes = {ColorMode.BRIGHTNESS}
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


def _infer_color_mode(state: dict[str, Any], supported: set[ColorMode] | None) -> ColorMode | None:
    supported = supported or set()
    for key, mode in _INFER_COLOR_MODE:
        if state.get(key) is not None and mode in supported:
            return mode
    if len(supported) == 1:
        return next(iter(supported))
    return None


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
        if (v := _as_int(defn.get("min_color_temp_kelvin"))) is not None:
            self._attr_min_color_temp_kelvin = v
        if (v := _as_int(defn.get("max_color_temp_kelvin"))) is not None:
            self._attr_max_color_temp_kelvin = v

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        self._attr_is_on = parse_bool(self._state.get("state"))
        self._attr_brightness = _as_int(
            self._state.get("brightness"), minimum=0, maximum=255
        )
        color_mode = self._state.get("color_mode")
        if isinstance(color_mode, str) and color_mode in _COLOR_MODE_MAP:
            mapped = _COLOR_MODE_MAP[color_mode]
            supported = self._attr_supported_color_modes or set()
            self._attr_color_mode = mapped if mapped in supported else None
        else:
            self._attr_color_mode = _infer_color_mode(
                self._state, self._attr_supported_color_modes
            )
        self._attr_color_temp_kelvin = _as_int(self._state.get("color_temp_kelvin"))
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
        self._send_command(
            "turn_on", params=params or None
        )
        self._state["state"] = "on"
        for key, val in params.items():
            if key not in ("transition", "flash"):
                self._state[key] = val
        self._publish_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        params = {}
        if (transition := kwargs.get("transition")) is not None:
            params["transition"] = transition
        self._send_command(
            "turn_off", params=params or None
        )
        self._state["state"] = "off"
        self._publish_state()
