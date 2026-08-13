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

객체 상태는 bridge 에서 **얕은 병합**된다. 키를 생략하면 이전 값이 유지되고,
지우려면 JSON `null` 을 보낸다 (예: 설치 시작 시
`{"in_progress": true, "progress": null}`, 설치 완료 후 노트 제거 시
`"release_url": null` / `"summary": null`).

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_UPDATE
from .entity import WsBridgeCompositeEntity


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
    if isinstance(value, (int, float)):
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


def _strip_build_suffix(version: str) -> str:
    """Drop an ESPHome project build suffix (`2025.11.5_c51f7548` → `2025.11.5`).

    AwesomeVersion cannot parse the suffix; HA only calls version_is_newer when
    the raw strings differ, so this matters exactly when they differ only by it.
    """
    return version.partition("_")[0]


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


class WsBridgeUpdate(WsBridgeCompositeEntity, UpdateEntity):
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = (
            try_parse_enum(UpdateDeviceClass, defn.get("device_class"))
            or UpdateDeviceClass.FIRMWARE
        )
        self._apply_state()

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = (
            try_parse_enum(UpdateDeviceClass, defn.get("device_class"))
            or UpdateDeviceClass.FIRMWARE
        )

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        return super().version_is_newer(
            _strip_build_suffix(latest_version),
            _strip_build_suffix(installed_version),
        )

    @callback
    def _apply_state(self) -> None:
        parsed = _parse_update_state(self._state)
        self._attr_installed_version = parsed["installed_version"]
        self._attr_latest_version = parsed["latest_version"]
        self._attr_in_progress = parsed["in_progress"]
        self._attr_update_percentage = parsed["progress"]
        self._attr_title = parsed["title"]
        self._attr_release_summary = parsed["summary"]
        self._attr_release_url = parsed["release_url"]

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        if not self._bridge.send_command(self._attr_unique_id, "install"):
            raise HomeAssistantError("Gateway is not connected")
        self._attr_in_progress = True
        self.async_write_ha_state()

    async def async_update(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "check")
