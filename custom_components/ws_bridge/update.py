"""update 플랫폼: 펌웨어 업데이트. install/check 의도를 클라이언트에 중계.

상태 값이 단일 스칼라가 아니라 객체다 (`device_tracker`와 같은 패턴):

    {
        "installed_version": "1.0.0",
        "latest_version": "1.0.1",
        "in_progress": false,
        "progress": 45,
        "title": "Living Room",
        "summary": "Bug fixes",
        "release_url": "https://..."
    }

실제 다운로드/플래시는 클라이언트가 한다 (ESPHome이면 `update: platform: http_request`).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_UPDATE
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_UPDATE, async_add_entities, WsBridgeUpdate)


def _as_str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return False


def _as_progress(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        progress = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, progress))


def _parse_update_state(value: Any) -> dict[str, Any]:
    """상태 값 → UpdateEntity 속성 dict.

    dict가 아니거나 `"unknown"`이면 버전 정보를 비운다.
    """
    empty: dict[str, Any] = {
        "installed_version": None,
        "latest_version": None,
        "in_progress": False,
        "progress": None,
        "title": None,
        "summary": None,
        "release_url": None,
    }
    if not isinstance(value, dict):
        return empty

    in_progress = _as_bool(value.get("in_progress"))
    progress = _as_progress(value.get("progress")) if in_progress else None

    return {
        "installed_version": _as_str(value.get("installed_version")),
        "latest_version": _as_str(value.get("latest_version")),
        "in_progress": in_progress,
        "progress": progress,
        "title": _as_str(value.get("title")),
        "summary": _as_str(value.get("summary")),
        "release_url": _as_str(value.get("release_url")),
    }


class WsBridgeUpdate(WsBridgeEntity, UpdateEntity):
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = (
            try_parse_enum(UpdateDeviceClass, defn.get("device_class"))
            or UpdateDeviceClass.FIRMWARE
        )
        self._apply(bridge.last_state(self._attr_unique_id))

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = (
            try_parse_enum(UpdateDeviceClass, defn.get("device_class"))
            or UpdateDeviceClass.FIRMWARE
        )

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """ESPHome project 버전은 `2025.11.5_c51f7548`처럼 빌드 접미사가 붙을 수 있다."""
        return super().version_is_newer(
            latest_version.partition("_")[0], installed_version.partition("_")[0]
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._apply(value)
        safe_write_ha_state(self)

    @callback
    def _apply(self, value: Any) -> None:
        parsed = _parse_update_state(value)
        self._attr_installed_version = parsed["installed_version"]
        self._attr_latest_version = parsed["latest_version"]
        self._attr_in_progress = parsed["in_progress"]
        self._attr_update_percentage = parsed["progress"]
        self._attr_title = parsed["title"]
        self._attr_release_summary = parsed["summary"]
        self._attr_release_url = parsed["release_url"]

    async def async_release_notes(self) -> str | None:
        return self._attr_release_summary

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        self._bridge.send_command(self._attr_unique_id, "install")
        self._attr_in_progress = True
        self.async_write_ha_state()

    async def async_update(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "check")
