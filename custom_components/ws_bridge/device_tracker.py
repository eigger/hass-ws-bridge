"""device_tracker 플랫폼: 클라이언트가 보낸 위경도로 GPS 트래커 엔티티 생성.

상태 값이 단일 스칼라가 아닌 유일한 플랫폼 — 위도와 경도가 항상 함께 있어야
의미가 있으므로 `ws_bridge/state`의 `value`를 객체로 받는다:

    {"latitude": 37.5665, "longitude": 126.9780, "gps_accuracy": 8}

배터리는 여기에 넣지 않는다. HA가 device_tracker의 battery_level을 폐기(deprecate)
했고, 별도 `sensor` + `device_class: battery` 엔티티로 선언하는 쪽을 권장한다.

상태 문자열(home/not_home/존 이름)을 직접 지정하는 것도 지원하지 않는다 —
TrackerEntity.location_name이 HA 2027.7에서 제거 예정인 deprecated 프로퍼티라서,
좌표로부터 자동 계산되는 상태만 쓴다.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_DEVICE_TRACKER
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(
        PLATFORM_DEVICE_TRACKER, async_add_entities, WsBridgeDeviceTracker
    )


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_location(value: Any) -> tuple[float | None, float | None, int]:
    """상태 값 → (latitude, longitude, gps_accuracy).

    위도/경도 중 하나라도 없거나 숫자가 아니면 둘 다 None으로 돌린다 — 반쪽짜리
    좌표는 HA에서 엉뚱한 위치로 잡히므로 '위치 모름'이 맞다. dict가 아닌 값
    (None, "unknown", 잘못 보낸 스칼라)도 마찬가지.
    """
    if not isinstance(value, dict):
        return None, None, 0

    latitude = _coerce_float(value.get("latitude"))
    longitude = _coerce_float(value.get("longitude"))
    if latitude is None or longitude is None:
        latitude = longitude = None

    accuracy = _coerce_float(value.get("gps_accuracy"))

    return latitude, longitude, int(accuracy) if accuracy is not None else 0


class WsBridgeDeviceTracker(WsBridgeEntity, TrackerEntity):
    """GPS 소스 트래커. 상태(home/not_home/존 이름)는 TrackerEntity가 위경도로 계산한다."""

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._apply(bridge.last_state(self._attr_unique_id))

    # HA 버전에 따라 _attr_latitude 등의 shadow 속성 유무가 달라서, 프로퍼티를
    # 직접 오버라이드해 버전 간 동작을 고정한다.
    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self._latitude

    @property
    def longitude(self) -> float | None:
        return self._longitude

    @property
    def location_accuracy(self) -> int:
        return self._location_accuracy

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._apply(value)
        safe_write_ha_state(self)

    @callback
    def _apply(self, value: Any) -> None:
        self._latitude, self._longitude, self._location_accuracy = _parse_location(value)
