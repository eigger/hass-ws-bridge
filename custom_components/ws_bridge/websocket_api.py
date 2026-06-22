"""HA WebSocket API 위의 커스텀 명령 (PROTOCOL.md). 클라이언트 인식, 범용.

인증된 어떤 클라이언트든 표준 HA auth(토큰) 후 사용.
 - ws_bridge/connect      : gateway_id로 구독 등록. command를 이 connection으로 push
 - ws_bridge/entity       : 엔티티 선언(생성/메타)
 - ws_bridge/state        : 상태 갱신(배치)
 - ws_bridge/availability : sub-device 연결 상태
 - ws_bridge/remove       : 엔티티·장치·게이트웨이 삭제
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .bridge import WsBridge
from .const import (
    ALL_PLATFORMS,
    DOMAIN,
    WS_AVAILABILITY,
    WS_CONNECT,
    WS_ENTITY,
    WS_REMOVE,
    WS_STATE,
)


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_connect)
    websocket_api.async_register_command(hass, ws_entity)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_availability)
    websocket_api.async_register_command(hass, ws_remove)


def _bridges(hass: HomeAssistant) -> list[WsBridge]:
    return [b for b in hass.data.get(DOMAIN, {}).values() if isinstance(b, WsBridge)]


@websocket_api.websocket_command({
    vol.Required("type"): WS_CONNECT,
    vol.Required("gateway_id"): str,
    vol.Optional("name"): vol.Any(str, None),
    vol.Optional("app_version"): vol.Any(str, None),
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
    vol.Optional("icon"): vol.Any(str, None),
    vol.Optional("entity_category"): vol.Any(vol.In(["config", "diagnostic"]), None),
    vol.Optional("options"): vol.Any([str], None),          # select
    vol.Optional("min"): vol.Any(vol.Coerce(float), None),  # number
    vol.Optional("max"): vol.Any(vol.Coerce(float), None),
    vol.Optional("step"): vol.Any(vol.Coerce(float), None),
})
@callback
def ws_entity(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
              msg: dict[str, Any]) -> None:
    defn = {k: v for k, v in msg.items() if k != "id"}
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is not None:
            b.handle_entity(gid, defn)
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): WS_STATE,
    vol.Required("states"): [{
        vol.Required("unique_id"): str,
        vol.Required("value"): vol.Any(int, float, str, bool, None),
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
})
@websocket_api.async_response
async def ws_remove(hass: HomeAssistant, connection: websocket_api.ActiveConnection,
                    msg: dict[str, Any]) -> None:
    """엔티티·sub-device·게이트웨이(전체) 삭제. 대상 미지정 시 연결된 게이트웨이 전체."""
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        if unique_id := msg.get("unique_id"):
            await b.async_remove_entity(gid, unique_id)
        elif device_id := msg.get("device_id"):
            await b.async_remove_device(gid, device_id)
        else:
            await b.async_remove_gateway(gid)
        connection.send_result(msg["id"])
        return
    connection.send_error(msg["id"], "not_connected", "No ws_bridge session for this connection")
