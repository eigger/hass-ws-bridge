"""HA WebSocket API 위의 커스텀 명령 (PROTOCOL.md). 클라이언트 인식, 범용.

인증된 어떤 클라이언트든 표준 HA auth(토큰) 후 사용.
 - ws_bridge/connect      : gateway_id로 구독 등록. command를 이 connection으로 push
 - ws_bridge/entity       : 엔티티 선언(생성/메타)
 - ws_bridge/state        : 상태 갱신(배치)
 - ws_bridge/availability : sub-device 연결 상태
 - ws_bridge/remove       : 엔티티·장치·게이트웨이 삭제
 - ws_bridge/sync         : 선언 전체 목록과 대조해 사라진 엔티티 정리

제어 플랫폼: switch, number, select, button, update.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .bridge import WsBridge
from .const import (
    ALL_PLATFORMS,
    CONF_KEEP_LAST_STATE_ON_DISCONNECT,
    DEFAULT_KEEP_LAST_STATE_ON_DISCONNECT,
    DOMAIN,
    REMOVE_MODES,
    WS_AVAILABILITY,
    WS_CONNECT,
    WS_ENTITY,
    WS_REMOVE,
    WS_STATE,
    WS_SYNC,
)


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_connect)
    websocket_api.async_register_command(hass, ws_entity)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_availability)
    websocket_api.async_register_command(hass, ws_remove)
    websocket_api.async_register_command(hass, ws_sync)


def _bridges(hass: HomeAssistant) -> list[WsBridge]:
    return [b for b in hass.data.get(DOMAIN, {}).values() if isinstance(b, WsBridge)]


@websocket_api.websocket_command({
    vol.Required("type"): WS_CONNECT,
    vol.Required("gateway_id"): str,
    vol.Optional("name"): vol.Any(str, None),
    vol.Optional("app_version"): vol.Any(str, None),
    vol.Optional(
        CONF_KEEP_LAST_STATE_ON_DISCONNECT, default=DEFAULT_KEEP_LAST_STATE_ON_DISCONNECT
    ): bool,
})
@websocket_api.async_response
async def ws_connect(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                     msg: dict[str, Any]) -> None:
    @callback
    def _send_event(event: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], event))

    gateway_id = msg["gateway_id"]
    name = msg.get("name") or ""
    unsubs = []
    for b in _bridges(hass):
        subentry_id = await b.async_ensure_gateway_subentry(gateway_id, name)
        unsubs.append(
            b.connect_client(
                connection,
                gateway_id,
                name,
                _send_event,
                msg.get("app_version"),
                subentry_id,
                keep_last_state_on_disconnect=msg[CONF_KEEP_LAST_STATE_ON_DISCONNECT],
            )
        )
    connection.subscriptions[msg["id"]] = lambda: [u() for u in unsubs]
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): WS_ENTITY,
    vol.Required("unique_id"): str,
    vol.Required("platform"): vol.In(ALL_PLATFORMS),
    vol.Required("name"): str,
    vol.Optional("device"): vol.Any(
        vol.Schema({
            vol.Required("id"): str,
            vol.Optional("name"): vol.Any(str, None),
        }),
        None,
    ),
    vol.Optional("device_class"): vol.Any(str, None),
    vol.Optional("unit_of_measurement"): vol.Any(str, None),
    vol.Optional("state_class"): vol.Any(str, None),
    vol.Optional("suggested_display_precision"): vol.Any(vol.Coerce(int), None),
    vol.Optional("icon"): vol.Any(str, None),
    vol.Optional("entity_category"): vol.Any(vol.In(["config", "diagnostic"]), None),
    vol.Optional("options"): vol.Any([str], None),          # select
    vol.Optional("min"): vol.Any(vol.Coerce(float), None),  # number / text(length)
    vol.Optional("max"): vol.Any(vol.Coerce(float), None),
    vol.Optional("step"): vol.Any(vol.Coerce(float), None),
    vol.Optional("features"): vol.Any([str], None),
    vol.Optional("supported_color_modes"): vol.Any([str], None),  # light
    vol.Optional("effect_list"): vol.Any([str], None),            # light
    vol.Optional("min_color_temp_kelvin"): vol.Any(vol.Coerce(int), None),  # light
    vol.Optional("max_color_temp_kelvin"): vol.Any(vol.Coerce(int), None),  # light
    vol.Optional("speed_count"): vol.Any(vol.Coerce(int), None),  # fan
    vol.Optional("preset_modes"): vol.Any([str], None),           # fan
    vol.Optional("pattern"): vol.Any(str, None),                  # text
    vol.Optional("mode"): vol.Any(str, None),                     # text
    vol.Optional("code_format"): vol.Any(str, None),              # lock
    vol.Optional("event_types"): vol.Any([str], None),            # event
    vol.Optional("reports_position"): vol.Any(bool, None),        # valve
})
@callback
def ws_entity(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
              msg: dict[str, Any]) -> None:
    defn = {k: v for k, v in msg.items() if k != "id"}
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is not None:
            b.handle_entity(gid, defn)
    connection.send_result(msg["id"])


# `value` accepts an object as well as a scalar: platforms whose state is not a
# single number/string (device_tracker needs latitude+longitude together) carry
# it as a dict. Scalar senders are unaffected.
@websocket_api.websocket_command({
    vol.Required("type"): WS_STATE,
    vol.Required("states"): [{
        vol.Required("unique_id"): str,
        vol.Required("value"): vol.Any(int, float, str, bool, dict, None),
    }],
    vol.Optional("ts"): vol.Any(int, float),
})
@callback
def ws_state(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
             msg: dict[str, Any]) -> None:
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        for item in msg["states"]:
            b.handle_state(gid, item["unique_id"], item["value"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): WS_AVAILABILITY,
    vol.Required("device_id"): str,
    vol.Required("online"): bool,
})
@callback
def ws_availability(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                    msg: dict[str, Any]) -> None:
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is not None:
            b.handle_availability(gid, msg["device_id"], msg["online"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): WS_REMOVE,
    vol.Optional("unique_id"): str,
    vol.Optional("device_id"): str,
    vol.Optional("mode"): vol.In(REMOVE_MODES),
})
@websocket_api.async_response
async def ws_remove(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                    msg: dict[str, Any]) -> None:
    """엔티티·sub-device·게이트웨이(전체) 삭제. 대상 미지정 시 연결된 게이트웨이 전체."""
    mode = msg.get("mode", "exact")
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        if unique_id := msg.get("unique_id"):
            await b.async_remove_entity(gid, unique_id, mode)
        elif device_id := msg.get("device_id"):
            await b.async_remove_device(gid, device_id, mode)
        else:
            await b.async_remove_gateway(gid)
        connection.send_result(msg["id"])
        return
    connection.send_error(msg["id"], "not_connected", "No ws_bridge session for this connection")


# 빈 목록은 스키마에서 거부한다 — 설정을 못 읽었거나 부분 부팅한 클라이언트가
# 실수로 전체를 날리는 사고를 막기 위해서다. 전체 삭제는 ws_bridge/remove(대상 생략).
@websocket_api.websocket_command({
    vol.Required("type"): WS_SYNC,
    vol.Required("unique_ids"): vol.All([str], vol.Length(min=1)),
})
@websocket_api.async_response
async def ws_sync(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                  msg: dict[str, Any]) -> None:
    """선언 전체 목록과 대조해, 이제는 없는 엔티티만 제거한다 (PROTOCOL.md §3.5)."""
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        removed = await b.async_sync_entities(gid, msg["unique_ids"])
        connection.send_result(msg["id"], {"removed": removed})
        return
    connection.send_error(msg["id"], "not_connected", "No ws_bridge session for this connection")
