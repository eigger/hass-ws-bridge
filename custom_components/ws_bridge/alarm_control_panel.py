"""alarm_control_panel 플랫폼: arm/disarm/trigger 를 클라이언트에 중계. code 는 로그 금지."""
from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import WsBridge
from .const import DOMAIN, PLATFORM_ALARM_CONTROL_PANEL
from .entity import WsBridgeEntity, safe_write_ha_state
from .helpers import is_unknown

_FEATURE_MAP = {
    "arm_home": AlarmControlPanelEntityFeature.ARM_HOME,
    "arm_away": AlarmControlPanelEntityFeature.ARM_AWAY,
    "arm_night": AlarmControlPanelEntityFeature.ARM_NIGHT,
    "arm_vacation": AlarmControlPanelEntityFeature.ARM_VACATION,
    "arm_custom_bypass": AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS,
    "trigger": AlarmControlPanelEntityFeature.TRIGGER,
}

_STATE_MAP = {
    "disarmed": AlarmControlPanelState.DISARMED,
    "armed_home": AlarmControlPanelState.ARMED_HOME,
    "armed_away": AlarmControlPanelState.ARMED_AWAY,
    "armed_night": AlarmControlPanelState.ARMED_NIGHT,
    "armed_vacation": AlarmControlPanelState.ARMED_VACATION,
    "armed_custom_bypass": AlarmControlPanelState.ARMED_CUSTOM_BYPASS,
    "arming": AlarmControlPanelState.ARMING,
    "pending": AlarmControlPanelState.PENDING,
    "triggered": AlarmControlPanelState.TRIGGERED,
}

_DEFAULT_FEATURES = (
    AlarmControlPanelEntityFeature.ARM_HOME
    | AlarmControlPanelEntityFeature.ARM_AWAY
    | AlarmControlPanelEntityFeature.TRIGGER
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: WsBridge = hass.data[DOMAIN][entry.entry_id]
    bridge.register_platform(
        PLATFORM_ALARM_CONTROL_PANEL, async_add_entities, WsBridgeAlarmControlPanel
    )


def _features(names: list[str] | None) -> AlarmControlPanelEntityFeature:
    if not names:
        return _DEFAULT_FEATURES
    flags = AlarmControlPanelEntityFeature(0)
    for name in names:
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    return flags or _DEFAULT_FEATURES


class WsBridgeAlarmControlPanel(WsBridgeEntity, AlarmControlPanelEntity):
    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._configure_from_defn(defn)
        self._apply(bridge.last_state(self._attr_unique_id))

    def _configure_from_defn(self, defn: dict[str, Any]) -> None:
        code_required = defn.get("code_arm_required")
        self._attr_code_arm_required = True if code_required is None else bool(code_required)
        fmt = defn.get("code_format")
        if fmt == "number":
            self._attr_code_format = CodeFormat.NUMBER
        elif fmt == "text":
            self._attr_code_format = CodeFormat.TEXT
        else:
            self._attr_code_format = None
        self._attr_supported_features = _features(defn.get("features"))

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
        if is_unknown(value) or value is None:
            self._attr_alarm_state = None
            return
        if isinstance(value, dict):
            value = value.get("state")
        if value is None:
            self._attr_alarm_state = None
            return
        self._attr_alarm_state = _STATE_MAP.get(str(value).lower())

    @staticmethod
    def _code_params(code: str | None) -> dict[str, Any] | None:
        if code is None:
            return None
        return {"code": code}

    def _send(self, action: str, code: str | None) -> None:
        self._send_command(action, params=self._code_params(code))

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        self._send("alarm_disarm", code)
        self._attr_alarm_state = AlarmControlPanelState.DISARMED
        self.async_write_ha_state()

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        self._send("alarm_arm_home", code)
        self._attr_alarm_state = AlarmControlPanelState.ARMED_HOME
        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        self._send("alarm_arm_away", code)
        self._attr_alarm_state = AlarmControlPanelState.ARMED_AWAY
        self.async_write_ha_state()

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        self._send("alarm_arm_night", code)
        self._attr_alarm_state = AlarmControlPanelState.ARMED_NIGHT
        self.async_write_ha_state()

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        self._send("alarm_arm_vacation", code)
        self._attr_alarm_state = AlarmControlPanelState.ARMED_VACATION
        self.async_write_ha_state()

    async def async_alarm_arm_custom_bypass(self, code: str | None = None) -> None:
        self._send("alarm_arm_custom_bypass", code)
        self._attr_alarm_state = AlarmControlPanelState.ARMED_CUSTOM_BYPASS
        self.async_write_ha_state()

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        self._send("alarm_trigger", code)
        self._attr_alarm_state = AlarmControlPanelState.TRIGGERED
        self.async_write_ha_state()
