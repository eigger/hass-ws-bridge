"""camera 플랫폼: still/stream URL 기반 (바이트·base64 전송 없음)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_CAMERA
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_FEATURE_MAP = {
    "on_off": CameraEntityFeature.ON_OFF,
    "stream": CameraEntityFeature.STREAM,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_CAMERA, async_add_entities, WsBridgeCamera)


def _features(names: list[str] | None, *, has_stream: bool) -> CameraEntityFeature:
    flags = CameraEntityFeature(0)
    for name in names or ():
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    if has_stream:
        flags |= CameraEntityFeature.STREAM
    else:
        flags &= ~CameraEntityFeature.STREAM
    return flags


class WsBridgeCamera(WsBridgeCompositeEntity, Camera):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        Camera.__init__(self)
        WsBridgeCompositeEntity.__init__(self, bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_brand = defn.get("brand")
        self._attr_model = defn.get("model")
        # stream URL may arrive later via state — features re-evaluated in _apply_state
        self._attr_supported_features = _features(
            defn.get("features"),
            has_stream=bool(self._state.get("stream_source")),
        )
        self._declared_features = defn.get("features")

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        still = self._state.get("still_image_url") or self._state.get("image_url")
        self._still_url = str(still) if still is not None else None
        stream = self._state.get("stream_source")
        self._stream_url = str(stream) if stream is not None else None
        self._attr_supported_features = _features(
            self._declared_features, has_stream=bool(self._stream_url)
        )
        is_on = self._state.get("is_on")
        if is_on is None:
            self._attr_is_on = True
        elif isinstance(is_on, bool):
            self._attr_is_on = is_on
        else:
            parsed = parse_bool(is_on)
            self._attr_is_on = True if parsed is None else parsed
        streaming = self._state.get("is_streaming")
        if streaming is None:
            self._attr_is_streaming = bool(self._stream_url)
        elif isinstance(streaming, bool):
            self._attr_is_streaming = streaming
        else:
            self._attr_is_streaming = bool(parse_bool(streaming))

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        if not self._still_url:
            return None
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(self._still_url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:  # noqa: BLE001 — 네트워크/세션 오류는 빈 프레임으로
            return None

    async def stream_source(self) -> str | None:
        return self._stream_url

    async def async_turn_on(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_on")
        self._state["is_on"] = True
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_off")
        self._state["is_on"] = False
        self._apply_state()
        self.async_write_ha_state()
