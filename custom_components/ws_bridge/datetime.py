"""datetime 플랫폼: ISO datetime 문자열 ↔ HA datetime 엔티티."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_DATETIME
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_DATETIME, async_add_entities, WsBridgeDateTime)


def _parse_datetime(value: Any) -> datetime | None:
    if is_unknown(value) or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # as_local() treats naive as UTC — attach HA local tz so "07:30:00" stays 07:30 local.
        return dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt


class WsBridgeDateTime(WsBridgeEntity, DateTimeEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._attr_native_value = _parse_datetime(
            bridge.last_state(self._attr_unique_id)
        )

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        return

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._attr_native_value = _parse_datetime(value)
        safe_write_ha_state(self)

    async def async_set_value(self, value: datetime) -> None:
        text = value.isoformat()
        self._send_command("set_value", text)
        self._attr_native_value = value
        self.async_write_ha_state()
