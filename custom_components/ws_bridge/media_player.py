"""media_player 플랫폼 (1차): 재생/볼륨/소스 선택 → 클라이언트에 중계.

browse_media / play_media / grouping 등은 범위 밖 — 추후 Phase.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_MEDIA_PLAYER
from .entity import WsBridgeCompositeEntity
from .helpers import parse_bool

_STATE_MAP = {
    "off": MediaPlayerState.OFF,
    "on": MediaPlayerState.ON,
    "idle": MediaPlayerState.IDLE,
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
}

_FEATURE_MAP = {
    "pause": MediaPlayerEntityFeature.PAUSE,
    "seek": MediaPlayerEntityFeature.SEEK,
    "volume_set": MediaPlayerEntityFeature.VOLUME_SET,
    "volume_mute": MediaPlayerEntityFeature.VOLUME_MUTE,
    "previous_track": MediaPlayerEntityFeature.PREVIOUS_TRACK,
    "next_track": MediaPlayerEntityFeature.NEXT_TRACK,
    "turn_on": MediaPlayerEntityFeature.TURN_ON,
    "turn_off": MediaPlayerEntityFeature.TURN_OFF,
    "play_media": MediaPlayerEntityFeature.PLAY_MEDIA,
    "volume_step": MediaPlayerEntityFeature.VOLUME_STEP,
    "select_source": MediaPlayerEntityFeature.SELECT_SOURCE,
    "stop": MediaPlayerEntityFeature.STOP,
    "clear_playlist": MediaPlayerEntityFeature.CLEAR_PLAYLIST,
    "play": MediaPlayerEntityFeature.PLAY,
    "shuffle_set": MediaPlayerEntityFeature.SHUFFLE_SET,
    "repeat_set": MediaPlayerEntityFeature.REPEAT_SET,
}

_DEFAULT_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(
        PLATFORM_MEDIA_PLAYER, async_add_entities, WsBridgeMediaPlayer
    )


def _features(
    names: list[str] | None, *, has_sources: bool
) -> MediaPlayerEntityFeature:
    if not names:
        flags = _DEFAULT_FEATURES
    else:
        flags = MediaPlayerEntityFeature(0)
        for name in names:
            if (flag := _FEATURE_MAP.get(name)) is not None:
                flags |= flag
        flags = flags or _DEFAULT_FEATURES
    if has_sources:
        flags |= MediaPlayerEntityFeature.SELECT_SOURCE
    else:
        flags &= ~MediaPlayerEntityFeature.SELECT_SOURCE
    return flags


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class WsBridgeMediaPlayer(WsBridgeCompositeEntity, MediaPlayerEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply_state()

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")
        sources = defn.get("source_list")
        self._attr_source_list = list(sources) if sources else None
        self._attr_supported_features = _features(
            defn.get("features"), has_sources=bool(self._attr_source_list)
        )

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    @callback
    def _apply_state(self) -> None:
        raw = self._state.get("state")
        self._attr_state = (
            _STATE_MAP.get(str(raw).lower()) if raw is not None else None
        )
        vol = _as_float(self._state.get("volume_level"))
        self._attr_volume_level = (
            max(0.0, min(1.0, vol)) if vol is not None else None
        )
        muted = self._state.get("is_volume_muted")
        if muted is None:
            self._attr_is_volume_muted = None
        elif isinstance(muted, bool):
            self._attr_is_volume_muted = muted
        else:
            self._attr_is_volume_muted = parse_bool(muted)
        title = self._state.get("media_title")
        self._attr_media_title = str(title) if title is not None else None
        artist = self._state.get("media_artist")
        self._attr_media_artist = str(artist) if artist is not None else None
        new_pos = _as_int(self._state.get("media_position"))
        if new_pos != getattr(self, "_attr_media_position", None):
            self._attr_media_position = new_pos
            self._attr_media_position_updated_at = (
                dt_util.utcnow() if new_pos is not None else None
            )
        self._attr_media_duration = _as_int(self._state.get("media_duration"))
        source = self._state.get("source")
        self._attr_source = str(source) if source is not None else None
        image = self._state.get("media_image_url")
        self._attr_media_image_url = str(image) if image is not None else None

    async def async_media_play(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "media_play")
        self._state["state"] = "playing"
        self._apply_state()
        self.async_write_ha_state()

    async def async_media_pause(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "media_pause")
        self._state["state"] = "paused"
        self._apply_state()
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "media_stop")
        self._state["state"] = "idle"
        self._apply_state()
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "media_next_track")

    async def async_media_previous_track(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "media_previous_track")

    async def async_set_volume_level(self, volume: float) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "volume_set", params={"volume_level": volume}
        )
        self._state["volume_level"] = volume
        self._apply_state()
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "volume_mute", params={"is_volume_muted": mute}
        )
        self._state["is_volume_muted"] = mute
        self._apply_state()
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "volume_up")

    async def async_volume_down(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "volume_down")

    async def async_turn_on(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_on")
        self._state["state"] = "on"
        self._apply_state()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_off")
        self._state["state"] = "off"
        self._apply_state()
        self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        self._bridge.send_command(
            self._attr_unique_id, "select_source", params={"source": source}
        )
        self._state["source"] = source
        self._apply_state()
        self.async_write_ha_state()
