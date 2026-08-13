"""valve 플랫폼: 개폐/위치 → open/close/stop/set_valve_position 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_VALVE
from .entity import WsBridgeCompositeEntity

_FEATURE_MAP = {
    "open": ValveEntityFeature.OPEN,
    "close": ValveEntityFeature.CLOSE,
    "stop": ValveEntityFeature.STOP,
    "set_position": ValveEntityFeature.SET_POSITION,
}

_DEFAULT_FEATURES_POSITION = (
    ValveEntityFeature.OPEN
    | ValveEntityFeature.CLOSE
    | ValveEntityFeature.STOP
    | ValveEntityFeature.SET_POSITION
)
_DEFAULT_FEATURES_NO_POSITION = (
    ValveEntityFeature.OPEN
    | ValveEntityFeature.CLOSE
    | ValveEntityFeature.STOP
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_VALVE, async_add_entities, WsBridgeValve)


def _features(
    names: list[str] | None, *, reports_position: bool = True
) -> ValveEntityFeature:
    default = (
        _DEFAULT_FEATURES_POSITION if reports_position else _DEFAULT_FEATURES_NO_POSITION
    )
    if not names:
        return default
    flags = ValveEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    if not reports_position:
        flags &= ~ValveEntityFeature.SET_POSITION
    return flags or default


def _as_position(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        pos = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, pos))


class WsBridgeValve(WsBridgeCompositeEntity, ValveEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")
        reports = defn.get("reports_position")
        self._attr_reports_position = True if reports is None else bool(reports)
        self._attr_supported_features = _features(
            defn.get("features"), reports_position=self._attr_reports_position
        )

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        if self._attr_reports_position:
            self._attr_current_valve_position = _as_position(self._state.get("position"))
        else:
            self._attr_current_valve_position = None

    @property
    def is_closed(self) -> bool | None:
        if self._attr_reports_position:
            if (pos := self._attr_current_valve_position) is not None:
                return pos == 0
            return None
        state = self._state.get("state")
        if state is None:
            return None
        return str(state).lower() == "closed"

    @property
    def is_opening(self) -> bool:
        return str(self._state.get("state") or "").lower() == "opening"

    @property
    def is_closing(self) -> bool:
        return str(self._state.get("state") or "").lower() == "closing"

    async def async_open_valve(self, **kwargs: Any) -> None:
        self._send_command("open_valve")
        self._state["state"] = "opening"
        self._publish_state()

    async def async_close_valve(self, **kwargs: Any) -> None:
        self._send_command("close_valve")
        self._state["state"] = "closing"
        self._publish_state()

    async def async_stop_valve(self, **kwargs: Any) -> None:
        self._send_command("stop_valve")

    async def async_set_valve_position(self, position: int) -> None:
        self._send_command(
            "set_valve_position", params={"position": position}
        )
        self._state["position"] = position
        self._publish_state()
