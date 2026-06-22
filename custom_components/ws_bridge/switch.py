"""switch 플랫폼: 토글 → command 의도를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_SWITCH
from .entity import WsBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SWITCH, async_add_entities, WsBridgeSwitch)


class WsBridgeSwitch(WsBridgeEntity, SwitchEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        last = bridge.last_state(self._attr_unique_id)
        self._attr_is_on = bool(last) if last is not None else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_is_on = bool(value)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._bridge.send_command(self._attr_unique_id, "turn_off")
        self._attr_is_on = False
        self.async_write_ha_state()
