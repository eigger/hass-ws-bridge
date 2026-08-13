"""event 플랫폼: 읽기 전용 이벤트 발화. last_state 로 복원하지 않음(유령 이벤트 방지)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_EVENT
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_EVENT, async_add_entities, WsBridgeEvent)


class WsBridgeEvent(WsBridgeEntity, EventEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        # last_state 복원 금지 — 재시작마다 유령 이벤트가 발화된다.

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        types = defn.get("event_types") or []
        self._attr_event_types = [str(t) for t in types]
        self._attr_device_class = defn.get("device_class")

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        if is_unknown(value):
            return
        event_type: str | None = None
        attributes: dict[str, Any] = {}
        if isinstance(value, str):
            event_type = value
        elif isinstance(value, dict):
            raw = value.get("event_type")
            if raw is not None:
                event_type = str(raw)
            attrs = value.get("attributes")
            if isinstance(attrs, dict):
                attributes = attrs
        if event_type is None:
            return
        if event_type not in self._attr_event_types:
            _LOGGER.warning(
                "Ignoring undeclared event_type %r for %s (allowed: %s)",
                event_type,
                self._attr_unique_id,
                self._attr_event_types,
            )
            return
        self._trigger_event(event_type, attributes)
        safe_write_ha_state(self)
