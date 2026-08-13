"""siren 플랫폼: turn_on/turn_off(+tone/duration/volume) 를 클라이언트에 중계."""
from __future__ import annotations

from typing import Any

from homeassistant.components.siren import SirenEntity, SirenEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_SIREN
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown, parse_bool

_FEATURE_MAP = {
    "turn_on": SirenEntityFeature.TURN_ON,
    "turn_off": SirenEntityFeature.TURN_OFF,
    "tones": SirenEntityFeature.TONES,
    "duration": SirenEntityFeature.DURATION,
    "volume_set": SirenEntityFeature.VOLUME_SET,
}

_DEFAULT_FEATURES = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(PLATFORM_SIREN, async_add_entities, WsBridgeSiren)


def _features(
    names: list[str] | None, *, has_tones: bool
) -> SirenEntityFeature:
    if not names:
        flags = _DEFAULT_FEATURES
    else:
        flags = SirenEntityFeature(0)
        for name in names:
            if (flag := _FEATURE_MAP.get(name)) is not None:
                flags |= flag
        flags = flags or _DEFAULT_FEATURES
    if has_tones:
        flags |= SirenEntityFeature.TONES
    else:
        flags &= ~SirenEntityFeature.TONES
    return flags


class WsBridgeSiren(WsBridgeEntity, SirenEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply(bridge.last_state(self._attr_unique_id))

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        tones = defn.get("available_tones")
        self._attr_available_tones = list(tones) if tones else None
        self._attr_supported_features = _features(
            defn.get("features"), has_tones=bool(self._attr_available_tones)
        )
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
            self._attr_is_on = None
            return
        if isinstance(value, dict):
            self._attr_is_on = parse_bool(value.get("state"))
            return
        self._attr_is_on = parse_bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        params: dict[str, Any] = {}
        for key in ("tone", "duration", "volume_level"):
            if key in kwargs and kwargs[key] is not None:
                params[key] = kwargs[key]
        self._send_command(
            "turn_on", params=params or None
        )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._send_command("turn_off")
        self._attr_is_on = False
        self.async_write_ha_state()
