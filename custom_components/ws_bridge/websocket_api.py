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

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .bridge import WsBridge
from .const import (
    ALL_PLATFORMS,
    CONF_ALLOWED_USER_IDS,
    CONF_KEEP_LAST_STATE_ON_DISCONNECT,
    DEFAULT_KEEP_LAST_STATE_ON_DISCONNECT,
    DOMAIN,
    REMOVE_MODES,
    WS_AVAILABILITY,
    WS_CONNECT,
    WS_ENTITY,
    WS_MEDIA_CONNECT,
    WS_MEDIA_OPEN,
    WS_REMOVE,
    WS_STATE,
    WS_SYNC,
)

_LOGGER = logging.getLogger(__name__)


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_connect)
    websocket_api.async_register_command(hass, ws_entity)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_availability)
    websocket_api.async_register_command(hass, ws_remove)
    websocket_api.async_register_command(hass, ws_sync)
    websocket_api.async_register_command(hass, ws_media_open)
    websocket_api.async_register_command(hass, ws_media_connect)


def _bridges(hass: HomeAssistant) -> list[WsBridge]:
    return [b for b in hass.data.get(DOMAIN, {}).values() if isinstance(b, WsBridge)]


_warned_users: set[str] = set()


def allowed_user_ids(hass: HomeAssistant) -> list[str]:
    """Explicitly allowed token owners; empty means admins only."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        return list(entry.options.get(CONF_ALLOWED_USER_IDS) or [])
    return []


def user_allowed(hass: HomeAssistant, user: Any) -> bool:
    """Whether `user` (a token owner) may use ws_bridge commands."""
    if user is None or not user.is_active:
        return False
    allowed = allowed_user_ids(hass)
    return user.is_admin if not allowed else user.id in allowed


def _reject_if_not_allowed(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> bool:
    """Send `not_allowed` and return True when the token owner may not use ws_bridge."""
    if user_allowed(hass, connection.user):
        return False
    user = connection.user
    if user is not None and user.id not in _warned_users:
        _warned_users.add(user.id)
        _LOGGER.warning(
            "Rejected ws_bridge command from user %s (%s): not allowed. Select "
            "allowed users in the integration options, or use an administrator token",
            user.name,
            user.id,
        )
    connection.send_error(
        msg["id"], "not_allowed", "Token owner is not allowed for ws_bridge"
    )
    # Permission lost outside the options flow (admin revoked, user deactivated):
    # drop the already-registered subscription once the error has been flushed.
    for bridge in _bridges(hass):
        if bridge.client_for(connection) is not None:

            @callback
            def _close(_now: Any, b: WsBridge = bridge) -> None:
                b.close_connections(lambda c: c is connection)

            async_call_later(hass, 1, _close)
    return True


def resolve_connect_sw_version(msg: dict[str, Any]) -> str | None:
    """게이트웨이 sw_version. `sw_version` 우선, 없으면 deprecated `app_version`."""
    for key in ("sw_version", "app_version"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_CONNECT,
        vol.Required("gateway_id"): str,
        vol.Optional("name"): vol.Any(str, None),
        vol.Optional("sw_version"): vol.Any(str, None),
        vol.Optional("app_version"): vol.Any(
            str, None
        ),  # deprecated alias of sw_version
        vol.Optional("manufacturer"): vol.Any(str, None),
        vol.Optional("model"): vol.Any(str, None),
        vol.Optional("hw_version"): vol.Any(str, None),
        vol.Optional(
            CONF_KEEP_LAST_STATE_ON_DISCONNECT,
            default=DEFAULT_KEEP_LAST_STATE_ON_DISCONNECT,
        ): bool,
    }
)
@websocket_api.async_response
async def ws_connect(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _reject_if_not_allowed(hass, connection, msg):
        return
    if any(bridge.is_media_connection(connection) for bridge in _bridges(hass)):
        connection.send_error(
            msg["id"],
            "media_connection",
            "A media upload socket cannot become a ws_bridge control connection",
        )
        return

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
                resolve_connect_sw_version(msg),
                subentry_id,
                keep_last_state_on_disconnect=msg[CONF_KEEP_LAST_STATE_ON_DISCONNECT],
                manufacturer=msg.get("manufacturer"),
                model=msg.get("model"),
                hw_version=msg.get("hw_version"),
            )
        )
    connection.subscriptions[msg["id"]] = lambda: [u() for u in unsubs]
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_ENTITY,
        vol.Required("unique_id"): str,
        vol.Required("platform"): vol.In(ALL_PLATFORMS),
        vol.Required("name"): str,
        vol.Optional("device"): vol.Any(
            vol.Schema(
                {
                    vol.Required("id"): str,
                    vol.Optional("name"): vol.Any(str, None),
                }
            ),
            None,
        ),
        vol.Optional("device_class"): vol.Any(str, None),
        vol.Optional("unit_of_measurement"): vol.Any(str, None),
        vol.Optional("state_class"): vol.Any(str, None),
        vol.Optional("suggested_display_precision"): vol.Any(vol.Coerce(int), None),
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("entity_category"): vol.Any(
            vol.In(["config", "diagnostic"]), None
        ),
        vol.Optional("options"): vol.Any([str], None),  # select
        vol.Optional("min"): vol.Any(vol.Coerce(float), None),  # number / text(length)
        vol.Optional("max"): vol.Any(vol.Coerce(float), None),
        vol.Optional("step"): vol.Any(vol.Coerce(float), None),
        vol.Optional("features"): vol.Any([str], None),
        vol.Optional("supported_color_modes"): vol.Any([str], None),  # light
        vol.Optional("effect_list"): vol.Any([str], None),  # light
        vol.Optional("min_color_temp_kelvin"): vol.Any(vol.Coerce(int), None),  # light
        vol.Optional("max_color_temp_kelvin"): vol.Any(vol.Coerce(int), None),  # light
        vol.Optional("speed_count"): vol.Any(vol.Coerce(int), None),  # fan
        vol.Optional("preset_modes"): vol.Any([str], None),  # fan
        vol.Optional("pattern"): vol.Any(str, None),  # text
        vol.Optional("mode"): vol.Any(str, None),  # text
        vol.Optional("code_format"): vol.Any(str, None),  # lock (regex)
        vol.Optional("event_types"): vol.Any(
            [str], None
        ),  # event (required when platform=event)
        vol.Optional("reports_position"): vol.Any(bool, None),  # valve
        vol.Optional("hvac_modes"): vol.Any([str], None),  # climate (required)
        vol.Optional("fan_modes"): vol.Any([str], None),  # climate
        vol.Optional("swing_modes"): vol.Any([str], None),  # climate
        vol.Optional("min_temp"): vol.Any(
            vol.Coerce(float), None
        ),  # climate / water_heater
        vol.Optional("max_temp"): vol.Any(vol.Coerce(float), None),
        vol.Optional("target_temp_step"): vol.Any(vol.Coerce(float), None),  # climate
        vol.Optional("min_humidity"): vol.Any(
            vol.Coerce(float), None
        ),  # climate / humidifier
        vol.Optional("max_humidity"): vol.Any(vol.Coerce(float), None),
        vol.Optional("temperature_unit"): vol.Any(str, None),  # climate
        vol.Optional("available_modes"): vol.Any([str], None),  # humidifier
        vol.Optional("operation_list"): vol.Any([str], None),  # water_heater
        vol.Optional("available_tones"): vol.Any([str], None),  # siren
        vol.Optional("code_arm_required"): vol.Any(bool, None),  # alarm_control_panel
        vol.Optional("source_list"): vol.Any([str], None),  # media_player
        vol.Optional("brand"): vol.Any(str, None),  # camera
        vol.Optional("model"): vol.Any(str, None),  # camera
    }
)
@callback
def ws_entity(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _reject_if_not_allowed(hass, connection, msg):
        return
    if msg.get("platform") == "event":
        types = msg.get("event_types")
        if not isinstance(types, list) or not types:
            connection.send_error(
                msg["id"],
                "invalid_format",
                "event_types is required for platform=event (non-empty list)",
            )
            return
    if msg.get("platform") == "climate":
        modes = msg.get("hvac_modes")
        if not isinstance(modes, list) or not modes:
            connection.send_error(
                msg["id"],
                "invalid_format",
                "hvac_modes is required for platform=climate (non-empty list)",
            )
            return
    defn = {k: v for k, v in msg.items() if k != "id"}
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is not None:
            b.handle_entity(gid, defn)
    connection.send_result(msg["id"])


# `value` accepts an object as well as a scalar: platforms whose state is not a
# single number/string (device_tracker needs latitude+longitude together) carry
# it as a dict. Scalar senders are unaffected.
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_STATE,
        vol.Required("states"): [
            {
                vol.Required("unique_id"): str,
                vol.Required("value"): vol.Any(int, float, str, bool, dict, None),
            }
        ],
        vol.Optional("ts"): vol.Any(int, float),
    }
)
@callback
def ws_state(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _reject_if_not_allowed(hass, connection, msg):
        return
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        for item in msg["states"]:
            b.handle_state(gid, item["unique_id"], item["value"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_AVAILABILITY,
        vol.Required("device_id"): str,
        vol.Required("online"): bool,
    }
)
@callback
def ws_availability(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _reject_if_not_allowed(hass, connection, msg):
        return
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is not None:
            b.handle_availability(gid, msg["device_id"], msg["online"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_REMOVE,
        vol.Optional("unique_id"): str,
        vol.Optional("device_id"): str,
        vol.Optional("mode"): vol.In(REMOVE_MODES),
    }
)
@websocket_api.async_response
async def ws_remove(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """엔티티·sub-device·게이트웨이(전체) 삭제. 대상 미지정 시 연결된 게이트웨이 전체."""
    if _reject_if_not_allowed(hass, connection, msg):
        return
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
    connection.send_error(
        msg["id"], "not_connected", "No ws_bridge session for this connection"
    )


# 빈 목록은 스키마에서 거부한다 — 설정을 못 읽었거나 부분 부팅한 클라이언트가
# 실수로 전체를 날리는 사고를 막기 위해서다. 전체 삭제는 ws_bridge/remove(대상 생략).
@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SYNC,
        vol.Required("unique_ids"): vol.All([str], vol.Length(min=1)),
    }
)
@websocket_api.async_response
async def ws_sync(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """선언 전체 목록과 대조해, 이제는 없는 엔티티만 제거한다 (PROTOCOL.md §3.5)."""
    if _reject_if_not_allowed(hass, connection, msg):
        return
    for b in _bridges(hass):
        if (gid := b.client_for(connection)) is None:
            continue
        removed = await b.async_sync_entities(gid, msg["unique_ids"])
        connection.send_result(msg["id"], {"removed": removed})
        return
    connection.send_error(
        msg["id"], "not_connected", "No ws_bridge session for this connection"
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_MEDIA_OPEN,
        vol.Required("unique_id"): str,
    }
)
@callback
def ws_media_open(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Reserve a short-lived, entity-bound binary upload connection.

    The returned session id is not a credential: media_connect still requires a
    separate standard HA-authenticated socket owned by the same token/user.
    """
    if _reject_if_not_allowed(hass, connection, msg):
        return
    gateway_id = next(
        (
            bridge.client_for(connection)
            for bridge in _bridges(hass)
            if bridge.client_for(connection)
        ),
        None,
    )
    if gateway_id is None or connection.user is None:
        connection.send_error(
            msg["id"],
            "not_connected",
            "No ws_bridge control session for this connection",
        )
        return
    for bridge in _bridges(hass):
        if bridge.client_for(connection) != gateway_id:
            continue
        if session_id := bridge.open_media_session(
            connection, gateway_id, msg["unique_id"], connection.user.id
        ):
            connection.send_result(
                msg["id"], {"session_id": session_id, "expires_in": 30}
            )
            return
        connection.send_error(
            msg["id"], "invalid_media_entity", "Entity is not an owned image or camera"
        )
        return
    connection.send_error(msg["id"], "not_connected", "No ws_bridge control session")


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_MEDIA_CONNECT,
        vol.Required("session_id"): str,
    }
)
@callback
def ws_media_connect(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Bind a separately authenticated socket to one pending media session."""
    if _reject_if_not_allowed(hass, connection, msg):
        return
    if connection.user is None:
        connection.send_error(msg["id"], "not_allowed", "Authenticated user required")
        return
    for bridge in _bridges(hass):
        if connected := bridge.connect_media_session(
            connection, msg["session_id"], connection.user.id
        ):
            handler_id, unique_id = connected
            connection.send_result(
                msg["id"], {"handler_id": handler_id, "unique_id": unique_id}
            )
            return
    connection.send_error(
        msg["id"], "invalid_media_session", "Media session is expired or not owned"
    )
