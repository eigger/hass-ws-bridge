"""button 플랫폼: 누르면 press 의도를 클라이언트에 중계 (상태 없음)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_BUTTON
from .entity import WsBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_BUTTON, async_add_entities, WsBridgeButton)


class WsBridgeButton(WsBridgeEntity, ButtonEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_device_class = defn.get("device_class")

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._attr_device_class = defn.get("device_class")

    async def async_press(self) -> None:
        self._bridge.send_command(self._attr_unique_id, "press")
