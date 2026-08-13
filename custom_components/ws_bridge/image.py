"""image 플랫폼: 클라이언트가 제공한 URL 을 HA ImageEntity 로 노출 (바이트 전송 없음)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_IMAGE
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import as_dict, is_unknown


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_IMAGE, async_add_entities, WsBridgeImage)


class WsBridgeImage(WsBridgeEntity, ImageEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        ImageEntity.__init__(self, bridge.hass)
        WsBridgeEntity.__init__(self, bridge, defn)
        self._configure_from_defn(defn)
        self._apply(bridge.last_state(self._attr_unique_id))

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        return

    def _update_platform_defn(self, defn: dict[str, Any]) -> None:
        self._configure_from_defn(defn)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._apply(value)
        safe_write_ha_state(self)

    @callback
    def _apply(self, value: Any) -> None:
        if is_unknown(value):
            self._attr_image_url = None
            self._attr_image_last_updated = None
            self._cached_image = None
            return
        data = as_dict(value) if isinstance(value, dict) else {"image_url": value}
        url = data.get("image_url") or data.get("url") or data.get("state")
        new_url = str(url) if url is not None else None
        if new_url != self._attr_image_url:
            self._cached_image = None
        self._attr_image_url = new_url
        updated = data.get("image_last_updated")
        if isinstance(updated, str):
            try:
                parsed = datetime.fromisoformat(updated)
            except ValueError:
                parsed = dt_util.utcnow()
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            self._attr_image_last_updated = parsed
        elif new_url is not None:
            self._attr_image_last_updated = dt_util.utcnow()
        else:
            self._attr_image_last_updated = None
