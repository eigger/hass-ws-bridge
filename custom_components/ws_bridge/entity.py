"""공통 엔티티 베이스: 클라이언트가 선언한 정의로 구성 + 디바이스 계층 + availability.

디바이스 계층: 클라이언트(게이트웨이) 디바이스 ← sub-device(via_device) ← 엔티티.
"""
from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .bridge import WsBridge, signal_avail, signal_value
from .const import DEFAULT_PLATFORM_ICONS, DOMAIN
from .helpers import as_dict


def safe_write_ha_state(entity: Entity) -> None:
    """dispatcher 리스너 등 이벤트 루프 밖에서도 안전하게 상태 반영."""
    entity.hass.loop.call_soon_threadsafe(entity.async_write_ha_state)


class WsBridgeEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        self._bridge = bridge
        self._defn = defn
        self._attr_unique_id = defn["unique_id"]      # 이미 클라이언트 네임스페이스됨
        self._attr_name = defn.get("name")
        if icon := defn.get("icon"):
            self._attr_icon = icon
        elif not defn.get("device_class"):
            if platform_icon := DEFAULT_PLATFORM_ICONS.get(defn.get("platform", "")):
                self._attr_icon = platform_icon
        if (cat := defn.get("entity_category")) in (EntityCategory.CONFIG, EntityCategory.DIAGNOSTIC):
            self._attr_entity_category = EntityCategory(cat)
        else:
            # Explicit None so a platform class default (e.g. UpdateEntity's
            # CONFIG) is not kept on first create then cleared on redeclare.
            self._attr_entity_category = None

        dev = defn["_device"]                          # bridge가 주입
        self._ns_device_id = dev["ns_id"]
        if dev.get("is_gateway"):
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, dev["ns_id"])},
                name=dev.get("name"),
                manufacturer="ws_bridge",
                model="Gateway",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, dev["ns_id"])},
                name=dev.get("name"),
                via_device=(DOMAIN, dev["gateway_id"]),    # 클라이언트(게이트웨이) 아래로 묶임
            )
        self._attr_available = True

    def _send_command(
        self,
        action: str,
        value: Any = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """클라이언트로 명령을 보낸다. 미연결이면 낙관적 상태 전에 실패한다."""
        kwargs: dict[str, Any] = {}
        if value is not None:
            kwargs["value"] = value
        if params is not None:
            kwargs["params"] = params
        if not self._bridge.send_command(self._attr_unique_id, action, **kwargs):
            raise HomeAssistantError("Gateway is not connected")

    @callback
    def async_update_defn(self, defn: dict[str, Any]) -> None:
        """클라이언트가 엔티티 정의를 다시 보냈을 때(재연결/설정 갱신 등) 동적으로 메타데이터 업데이트."""
        self._defn = defn
        self._attr_name = defn.get("name")
        
        # 아이콘 업데이트
        if icon := defn.get("icon"):
            self._attr_icon = icon
        elif not defn.get("device_class"):
            if platform_icon := DEFAULT_PLATFORM_ICONS.get(defn.get("platform", "")):
                self._attr_icon = platform_icon
        else:
            self._attr_icon = None

        if (cat := defn.get("entity_category")) in (EntityCategory.CONFIG, EntityCategory.DIAGNOSTIC):
            self._attr_entity_category = EntityCategory(cat)
        else:
            self._attr_entity_category = None

        # 플랫폼별 개별 속성 업데이트 위임
        if hasattr(self, "_update_platform_defn"):
            self._update_platform_defn(defn)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_avail(self._bridge.entry_id, self._ns_device_id),
                self._on_availability,
            )
        )

    @callback
    def _on_availability(self, online: bool) -> None:
        self._attr_available = online
        safe_write_ha_state(self)

    def _subscribe_state(self, cb) -> None:
        """상태 갱신(signal_value) 구독 헬퍼. 상태가 있는 플랫폼에서 호출."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_value(self._bridge.entry_id, self._attr_unique_id), cb
            )
        )


class WsBridgeCompositeEntity(WsBridgeEntity):
    """상태가 여러 속성으로 구성되는 플랫폼(light/cover/climate 등)의 베이스.

    `__init__` 에서는 `_state` 만 준비하고 `_apply_state` 는 호출하지 않는다 —
    서브클래스가 자기 필드를 대입한 뒤 직접 호출하거나, `async_added_to_hass` 에서
    반영한다.
    """

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._state: dict[str, Any] = as_dict(bridge.last_state(self._attr_unique_id))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._apply_state()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._state = as_dict(value)
        self._apply_state()
        safe_write_ha_state(self)

    def _publish_state(self) -> None:
        """낙관적 _state 를 bridge 에 반영한 뒤 HA 에 기록.

        bridge._states 에 안 넣으면 이후 부분 state 푸시가 stale 값과 병합되어
        낙관적 설정이 되돌아간다.
        """
        self._bridge.set_local_state(self._attr_unique_id, self._state)
        self._apply_state()
        self.async_write_ha_state()

    def _apply_state(self) -> None:
        """서브클래스에서 self._state → self._attr_* 로 반영."""
        raise NotImplementedError
