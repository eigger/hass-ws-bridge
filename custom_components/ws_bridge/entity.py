"""공통 엔티티 베이스: 클라이언트가 선언한 정의로 구성 + 디바이스 계층 + availability.

디바이스 계층: 클라이언트(게이트웨이) 디바이스 ← sub-device(via_device) ← 엔티티.
"""
from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .bridge import WsBridge, signal_avail, signal_value
from .const import DEFAULT_PLATFORM_ICONS, DOMAIN


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

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_avail(self._bridge.entry_id, self._ns_device_id),
                self._on_availability,
            )
        )

    def _on_availability(self, online: bool) -> None:
        self._attr_available = online
        self.async_write_ha_state()

    def _subscribe_state(self, cb) -> None:
        """상태 갱신(signal_value) 구독 헬퍼. 상태가 있는 플랫폼에서 호출."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_value(self._bridge.entry_id, self._attr_unique_id), cb
            )
        )
