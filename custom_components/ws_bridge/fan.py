"""fan 플랫폼: 속도/프리셋/진동/방향 → turn_on/set_* 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_FAN
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_FEATURE_MAP = {
    "set_speed": FanEntityFeature.SET_SPEED,
    "oscillate": FanEntityFeature.OSCILLATE,
    "direction": FanEntityFeature.DIRECTION,
    "preset_mode": FanEntityFeature.PRESET_MODE,
    "turn_on": FanEntityFeature.TURN_ON,
    "turn_off": FanEntityFeature.TURN_OFF,
}

_DEFAULT_FEATURES = (
    FanEntityFeature.TURN_ON
    | FanEntityFeature.TURN_OFF
    | FanEntityFeature.SET_SPEED
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_FAN, async_add_entities, WsBridgeFan)


def _features(names: list[str] | None) -> FanEntityFeature:
    if not names:
        return _DEFAULT_FEATURES
    flags = FanEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    return flags or _DEFAULT_FEATURES


def _as_percentage(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        pct = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, pct))


class WsBridgeFan(WsBridgeCompositeEntity, FanEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_speed_count = int(defn.get("speed_count") or 100)
        presets = defn.get("preset_modes")
        self._attr_preset_modes = list(presets) if presets else None
        self._attr_supported_features = _features(defn.get("features"))

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        self._attr_is_on = parse_bool(self._state.get("state"))
        self._attr_percentage = _as_percentage(self._state.get("percentage"))
        preset = self._state.get("preset_mode")
        self._attr_preset_mode = str(preset) if preset is not None else None
        oscillating = self._state.get("oscillating")
        if oscillating is None:
            self._attr_oscillating = None
        elif isinstance(oscillating, bool):
            self._attr_oscillating = oscillating
        else:
            self._attr_oscillating = parse_bool(oscillating)
        direction = self._state.get("direction")
        self._attr_current_direction = (
            str(direction) if direction is not None else None
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        params: dict[str, Any] = {}
        if percentage is not None:
            params["percentage"] = percentage
        if preset_mode is not None:
            params["preset_mode"] = preset_mode
        self._send_command(
            "turn_on", params=params or None
        )
        self._state["state"] = "on"
        if percentage is not None:
            self._state["percentage"] = percentage
        if preset_mode is not None:
            self._state["preset_mode"] = preset_mode
        self._publish_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._send_command("turn_off")
        self._state["state"] = "off"
        self._publish_state()

    async def async_set_percentage(self, percentage: int) -> None:
        self._send_command(
            "set_percentage", params={"percentage": percentage}
        )
        self._state["percentage"] = percentage
        if percentage > 0:
            self._state["state"] = "on"
        else:
            self._state["state"] = "off"
        self._publish_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._send_command(
            "set_preset_mode",
            params={"preset_mode": preset_mode},
        )
        self._state["preset_mode"] = preset_mode
        self._publish_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        self._send_command(
            "oscillate", params={"oscillating": oscillating}
        )
        self._state["oscillating"] = oscillating
        self._publish_state()

    async def async_set_direction(self, direction: str) -> None:
        self._send_command(
            "set_direction", params={"direction": direction}
        )
        self._state["direction"] = direction
        self._publish_state()
