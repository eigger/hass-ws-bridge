"""lock 플랫폼: lock/unlock/open 의도를 클라이언트에 중계. code 는 로그에 남기지 않음."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_LOCK
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown, parse_locked


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_LOCK, async_add_entities, WsBridgeLock)


def _features(names: list[str] | None) -> LockEntityFeature:
    flags = LockEntityFeature(0)
    for name in names or ():
        if name == "open":
            flags |= LockEntityFeature.OPEN
    return flags


class WsBridgeLock(WsBridgeEntity, LockEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply(bridge.last_state(self._attr_unique_id))

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        self._attr_supported_features = _features(defn.get("features"))
        self._attr_code_format = defn.get("code_format")

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
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_is_jammed = False
        self._attr_is_opening = False
        self._attr_is_open = False
        if is_unknown(value):
            self._attr_is_locked = None
            return
        if isinstance(value, bool):
            self._attr_is_locked = value
            return
        if isinstance(value, str):
            state = value.lower()
            if state == "locking":
                self._attr_is_locking = True
                self._attr_is_locked = False
            elif state == "unlocking":
                self._attr_is_unlocking = True
                self._attr_is_locked = True
            elif state == "jammed":
                self._attr_is_jammed = True
                self._attr_is_locked = None
            elif state == "opening":
                self._attr_is_opening = True
                self._attr_is_locked = False
            elif state == "open":
                self._attr_is_open = True
                self._attr_is_locked = False
            elif state in ("locked", "lock"):
                self._attr_is_locked = True
            elif state == "unlocked":
                self._attr_is_locked = False
            else:
                self._attr_is_locked = parse_locked(value)
            return
        self._attr_is_locked = parse_locked(value)

    @staticmethod
    def _code_params(code: str | None) -> dict[str, Any] | None:
        if code is None:
            return None
        return {"code": code}

    async def async_lock(self, **kwargs: Any) -> None:
        self._send_command(
            "lock", params=self._code_params(kwargs.get("code"))
        )
        self._attr_is_locking = True
        self._attr_is_locked = False
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        self._send_command(
            "unlock", params=self._code_params(kwargs.get("code"))
        )
        self._attr_is_unlocking = True
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_open(self, **kwargs: Any) -> None:
        self._send_command(
            "open", params=self._code_params(kwargs.get("code"))
        )
        self._attr_is_opening = True
        self.async_write_ha_state()
