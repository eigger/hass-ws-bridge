"""Camera entities backed by URL stills or uploaded JPEG frames."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import web
from homeassistant.components import camera
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_CAMERA
from .entity import WsBridgeCompositeEntity, safe_write_ha_state
from .helpers import parse_bool, sanitize_remote_url

_LOGGER = logging.getLogger(__name__)

_FEATURE_MAP = {
    "on_off": CameraEntityFeature.ON_OFF,
    "stream": CameraEntityFeature.STREAM,
}

_STILL_TIMEOUT = aiohttp.ClientTimeout(total=10)
_PUSH_FRAME_TIMEOUT = 15


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
        self._push_stream_queues: dict[asyncio.Queue[bytes | None], int] = {}
        self._push_stream_enabled = False
        self._push_stream_started = False
        self._push_stream_generation = 0
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
        self._push_stream_enabled = "push_stream" in (self._declared_features or ())

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        was_enabled = self._push_stream_enabled
        self._configure_from_defn(defn)
        if was_enabled and not self._push_stream_enabled:
            self._end_push_streams()

    @callback
    def _apply_state(self) -> None:
        still = self._state.get("still_image_url") or self._state.get("image_url")
        raw_still = str(still) if still is not None else None
        self._still_url = sanitize_remote_url(raw_still)
        if raw_still and self._still_url is None:
            _LOGGER.warning(
                "Ignoring unsafe still_image_url for %s", self._attr_unique_id
            )
        # A state carrying a still URL explicitly selects URL transport. It
        # must not leave viewers subscribed to an earlier pushed-frame stream.
        if (
            self._still_url
            and not self._has_live_push_media()
            and self._push_stream_queues
        ):
            self._end_push_streams()
        stream = self._state.get("stream_source")
        raw_stream = str(stream) if stream is not None else None
        # rtsp(s) for ffmpeg; http(s) for HLS-style sources
        self._stream_url = sanitize_remote_url(
            raw_stream, schemes=("http", "https", "rtsp", "rtsps")
        )
        if raw_stream and self._stream_url is None:
            _LOGGER.warning(
                "Ignoring unsafe stream_source for %s", self._attr_unique_id
            )
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
        if frame := self._bridge.latest_media_frame(self._attr_unique_id):
            return frame
        if not self._still_url:
            return None
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(self._still_url, timeout=_STILL_TIMEOUT) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "Still image fetch for %s returned HTTP %s (%s)",
                        self._attr_unique_id,
                        resp.status,
                        self._still_url,
                    )
                    return None
                return await resp.read()
        except Exception as err:  # noqa: BLE001 — 네트워크 오류는 빈 프레임 + 로그
            _LOGGER.warning(
                "Still image fetch failed for %s (%s): %s",
                self._attr_unique_id,
                self._still_url,
                err,
            )
            return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_media(self._on_media)

    @callback
    def _on_media(self) -> None:
        """Fan out one uploaded frame without retaining per-viewer history."""
        frame = self._bridge.latest_media_frame(self._attr_unique_id)
        if frame is None or not self._bridge.has_media_connection(self._attr_unique_id):
            # A cleared frame or a closed upload socket means the producer,
            # entity, or gateway went away. Wake every waiting HTTP response
            # so it can clean up.
            self._end_push_streams()
        elif self._push_stream_queues:
            for queue in self._push_stream_queues:
                self._replace_queued_frame(queue, frame)

        # Snapshot cameras still refresh their proxy state. While viewers are
        # consuming live frames, avoid one HA state/store write per video frame.
        if not self._push_stream_queues:
            safe_write_ha_state(self)

    @staticmethod
    @callback
    def _replace_queued_frame(
        queue: asyncio.Queue[bytes | None], frame: bytes | None
    ) -> None:
        """Keep only the newest frame (or terminal marker) for one viewer."""
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(frame)

    @callback
    def _end_push_streams(self) -> None:
        """End native MJPEG viewers and release the producer once."""
        ended = tuple(self._push_stream_queues)
        # Detach terminal queues before scheduling their wake-up. A new viewer
        # can then start a fresh producer generation, and an old handler's
        # finally block can never stop that newer generation.
        self._push_stream_queues.clear()
        self._push_stream_generation += 1
        for queue in ended:
            self._replace_queued_frame(queue, None)
        if self._push_stream_started:
            self._bridge.send_command(
                self._attr_unique_id, "stop_stream", params={"format": "mjpeg"}
            )
            self._push_stream_started = False

    async def _async_next_push_frame(
        self, queue: asyncio.Queue[bytes | None]
    ) -> bytes | None:
        """Wait for one latest frame, ending a stalled MJPEG response."""
        try:
            async with asyncio.timeout(_PUSH_FRAME_TIMEOUT):
                return await queue.get()
        except TimeoutError:
            _LOGGER.debug("Timed out waiting for pushed frame from %s", self.entity_id)
            return None

    @callback
    def _has_live_push_media(self) -> bool:
        """A fresh producer/frame takes precedence over historical URL state."""
        return self._bridge.latest_media_frame(
            self._attr_unique_id
        ) is not None or self._bridge.has_media_connection(self._attr_unique_id)

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve negotiated pushed JPEG frames as a bounded native MJPEG stream."""
        # URL mode and clients that did not explicitly negotiate push-stream
        # keep Home Assistant's normal camera behavior.
        if not self._push_stream_enabled or (
            self._still_url and not self._has_live_push_media()
        ):
            return await super().handle_async_mjpeg_stream(request)

        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1)
        first_viewer = not self._push_stream_queues
        generation = self._push_stream_generation
        self._push_stream_queues[queue] = generation
        if first_viewer:
            if not self._bridge.send_command(
                self._attr_unique_id, "start_stream", params={"format": "mjpeg"}
            ):
                self._push_stream_queues.pop(queue, None)
                return None
            self._push_stream_started = True

        # A frame arriving just before subscription remains useful as the first
        # MJPEG part without requiring another ESP request.
        if frame := self._bridge.latest_media_frame(self._attr_unique_id):
            self._replace_queued_frame(queue, frame)

        try:
            return await camera.async_get_still_stream(
                request,
                lambda: self._async_next_push_frame(queue),
                camera.DEFAULT_CONTENT_TYPE,
                0.0,
            )
        finally:
            # _end_push_streams() has already detached terminal queues. Do not
            # let their delayed HTTP cleanup affect a newer viewer generation.
            if self._push_stream_queues.get(queue) == generation:
                self._push_stream_queues.pop(queue, None)
                if not self._push_stream_queues and self._push_stream_started:
                    self._bridge.send_command(
                        self._attr_unique_id,
                        "stop_stream",
                        params={"format": "mjpeg"},
                    )
                    self._push_stream_started = False

    async def async_will_remove_from_hass(self) -> None:
        """Release a producer when the camera entity is removed or unloaded."""
        self._end_push_streams()
        await super().async_will_remove_from_hass()

    async def stream_source(self) -> str | None:
        return self._stream_url

    async def async_turn_on(self) -> None:
        self._send_command("turn_on")
        self._state["is_on"] = True
        self._publish_state()

    async def async_turn_off(self) -> None:
        self._send_command("turn_off")
        self._state["is_on"] = False
        self._publish_state()
