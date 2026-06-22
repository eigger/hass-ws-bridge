"""select 플랫폼: 옵션 선택 → select_option 의도를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_SELECT
from .entity import WsBridgeEntity, safe_write_ha_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SELECT, async_add_entities, WsBridgeSelect)


class WsBridgeSelect(WsBridgeEntity, SelectEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_options = list(defn.get("options") or [])
        last = bridge.last_state(self._attr_unique_id)
        self._attr_current_option = str(last) if last is not None else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_current_option = str(value)
        safe_write_ha_state(self)

    async def async_select_option(self, option: str) -> None:
        self._bridge.send_command(self._attr_unique_id, "select_option", option)
        self._attr_current_option = option
        self.async_write_ha_state()
