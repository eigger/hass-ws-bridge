"""cover 플랫폼: 개폐/위치/틸트 → open/close/stop/set_* 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_COVER
from .entity import WsBridgeCompositeEntity

_FEATURE_MAP = {
    "open": CoverEntityFeature.OPEN,
    "close": CoverEntityFeature.CLOSE,
    "stop": CoverEntityFeature.STOP,
    "set_position": CoverEntityFeature.SET_POSITION,
    "open_tilt": CoverEntityFeature.OPEN_TILT,
    "close_tilt": CoverEntityFeature.CLOSE_TILT,
    "stop_tilt": CoverEntityFeature.STOP_TILT,
    "set_tilt_position": CoverEntityFeature.SET_TILT_POSITION,
}

_DEFAULT_FEATURES = (
    CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_COVER, async_add_entities, WsBridgeCover)


def _features(names: list[str] | None) -> CoverEntityFeature:
    if not names:
        return _DEFAULT_FEATURES
    flags = CoverEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    return flags or _DEFAULT_FEATURES


def _as_position(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        pos = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, pos))


class WsBridgeCover(WsBridgeCompositeEntity, CoverEntity):
    # opening/closing 은 낙관적 표시일 뿐 — 클라이언트 확인 없이 영속화하면
    # 재시작 후 "Opening" 으로 고착된다.
    _transient_state_keys = frozenset({"state"})

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = defn.get("device_class")
        self._attr_supported_features = _features(defn.get("features"))
        self._apply_state()

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")
        self._attr_supported_features = _features(defn.get("features"))

    @callback
    def _apply_state(self) -> None:
        self._attr_current_cover_position = _as_position(self._state.get("position"))
        self._attr_current_cover_tilt_position = _as_position(
            self._state.get("tilt_position")
        )

    @property
    def is_closed(self) -> bool | None:
        """position 우선, 없으면 state==closed. 둘 다 없으면 None(unknown)."""
        if (pos := self._attr_current_cover_position) is not None:
            return pos == 0
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

    async def async_open_cover(self, **kwargs: Any) -> None:
        self._send_command("open_cover")
        self._state["state"] = "opening"
        self._publish_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        self._send_command("close_cover")
        self._state["state"] = "closing"
        self._publish_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        self._send_command("stop_cover")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position")
        self._send_command(
            "set_cover_position", params={"position": position}
        )
        self._state["position"] = position
        self._publish_state()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        self._send_command("open_cover_tilt")

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        self._send_command("close_cover_tilt")

    async def async_stop_cover_tilt(self, **kwargs: Any) -> None:
        self._send_command("stop_cover_tilt")

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        tilt = kwargs.get("tilt_position")
        self._send_command(
            "set_cover_tilt_position",
            params={"tilt_position": tilt},
        )
        self._state["tilt_position"] = tilt
        self._publish_state()
