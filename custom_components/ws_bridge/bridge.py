"""브릿지 / 동적 엔티티 팩토리 (클라이언트 인식, 범용).

연결된 클라이언트(gateway_id로 식별)별로:
 - HA에 클라이언트 디바이스를 만들고
 - 그 클라이언트가 선언한 (sub)디바이스/엔티티를 via_device로 묶고
 - gateway_id로 unique_id를 네임스페이스해 충돌을 막고
 - 명령(command)을 그 클라이언트에만 라우팅한다.
형식(BLE 등) 지식 없음 — 프로토콜만 안다. config entry 당 1개.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import Entity

from .const import CONNECTED_CLIENTS_UNIQUE_ID, DOMAIN, SUBENTRY_TYPE_GATEWAY

_LOGGER = logging.getLogger(__name__)


def signal_value(entry_id: str, unique_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_state_{unique_id}"


def signal_avail(entry_id: str, ns_device_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_avail_{ns_device_id}"


def signal_clients(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_clients"


@dataclass
class _Client:
    gateway_id: str
    name: str
    send_event: Callable[[dict[str, Any]], None]
    sw_version: str | None = None
    device_ids: set[str] = field(default_factory=set)   # 네임스페이스된 sub-device id


class _PlatformReg:
    def __init__(self, add_entities: Callable, factory: Callable[..., Any]) -> None:
        self.add_entities = add_entities
        self.factory = factory


class WsBridge:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._platforms: dict[str, _PlatformReg] = {}
        self._pending: dict[str, list[dict[str, Any]]] = {}
        self._created: set[str] = set()                 # 네임스페이스된 unique_id
        self._states: dict[str, Any] = {}
        self._clients: dict[str, _Client] = {}          # gateway_id → ctx
        self._conn_client: dict[Any, str] = {}          # connection → gateway_id
        self._entity_client: dict[str, str] = {}        # ns unique_id → gateway_id
        self._entities: dict[str, Entity] = {}          # ns unique_id → live entity
        self._connections: set[Any] = set()            # active connections

    # ── 플랫폼 등록 ──────────────────────────────────────────────────────────
    @callback
    def register_platform(self, platform: str, add_entities: Callable,
                          factory: Callable[..., Any]) -> None:
        self._platforms[platform] = _PlatformReg(add_entities, factory)
        for defn in self._pending.pop(platform, []):
            self._create(defn)

    def _subentry_id_for_gateway(self, gateway_id: str) -> str | None:
        config_entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if config_entry is None:
            return None
        for subentry in config_entry.subentries.values():
            if subentry.data.get("gateway_id") == gateway_id:
                return subentry.subentry_id
        return None

    async def async_ensure_gateway_subentry(
        self, gateway_id: str, name: str
    ) -> str | None:
        """connect 시 게이트웨이 Subentry가 없으면 자동 생성한다."""
        config_entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if config_entry is None:
            return None

        display_name = (name or gateway_id).strip() or gateway_id

        for subentry in config_entry.subentries.values():
            if subentry.data.get("gateway_id") != gateway_id:
                continue
            if (
                subentry.title != display_name
                or subentry.data.get("name") != display_name
            ):
                self.hass.config_entries.async_update_subentry(
                    config_entry,
                    subentry,
                    data={"gateway_id": gateway_id, "name": display_name},
                    title=display_name,
                )
            return subentry.subentry_id

        subentry = ConfigSubentry(
            data={"gateway_id": gateway_id, "name": display_name},
            subentry_type=SUBENTRY_TYPE_GATEWAY,
            unique_id=gateway_id,
            title=display_name,
        )
        self.hass.config_entries.async_add_subentry(config_entry, subentry)
        _LOGGER.info(
            "Auto-created gateway subentry: %s (%s)", display_name, gateway_id
        )
        return subentry.subentry_id

    # ── 클라이언트 연결 ──────────────────────────────────────────────────────
    @callback
    def connect_client(
        self,
        connection: Any,
        gateway_id: str,
        name: str,
        send_event: Callable[[dict[str, Any]], None],
        sw_version: str | None = None,
        subentry_id: str | None = None,
    ) -> Callable[[], None]:
        client = self._clients.get(gateway_id)
        if client is None:
            client = self._clients[gateway_id] = _Client(gateway_id, name or gateway_id, send_event, sw_version)
        else:
            client.name = name or client.name
            client.send_event = send_event
            if sw_version:
                client.sw_version = sw_version
        self._connections.add(connection)
        self._conn_client[connection] = gateway_id
        self._notify_clients_changed()

        # 게이트웨이를 독립 디바이스로 등록 — WebSocket Bridge 서비스 디바이스와 병렬
        dev_reg = dr.async_get(self.hass)

        if subentry_id is None:
            subentry_id = self._subentry_id_for_gateway(gateway_id)

        # 중복 기기 정리 (같은 name을 가졌지만 다른 gateway_id인 디바이스가 있는 경우 삭제)
        existing_devices = dr.async_entries_for_config_entry(dev_reg, self.entry_id)
        gids_to_remove = set()
        for d_entry in existing_devices:
            if d_entry.name == (name or gateway_id):
                for identifier in d_entry.identifiers:
                    if identifier[0] == DOMAIN:
                        gid = identifier[1]
                        if ":" not in gid and gid != gateway_id and gid not in self._conn_client.values():
                            gids_to_remove.add(gid)

        if gids_to_remove:
            for d_entry in list(existing_devices):
                should_remove = False
                for identifier in d_entry.identifiers:
                    if identifier[0] == DOMAIN:
                        val = identifier[1]
                        if val in gids_to_remove or any(val.startswith(f"{rgid}:") for rgid in gids_to_remove):
                            should_remove = True
                            break
                if should_remove:
                    _LOGGER.info("Removing duplicate/offline device: %s (%s)", d_entry.name, d_entry.identifiers)
                    dev_reg.async_remove_device(d_entry.id)

        gw_entry = dev_reg.async_get_or_create(
            config_entry_id=self.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, gateway_id)},
            name=client.name,
            manufacturer="ws_bridge",
            model="Gateway",
            sw_version=client.sw_version,
        )
        # via_device가 남아 있으면 제거, sw_version도 갱신
        if gw_entry.via_device_id is not None or (
            client.sw_version and gw_entry.sw_version != client.sw_version
        ):
            dev_reg.async_update_device(
                gw_entry.id,
                via_device_id=None,
                sw_version=client.sw_version,
            )
        for ns_dev in client.device_ids:   # 재연결 → 온라인 복귀
            async_dispatcher_send(self.hass, signal_avail(self.entry_id, ns_dev), True)

        @callback
        def _disconnect() -> None:
            self._connections.discard(connection)
            self._conn_client.pop(connection, None)
            if gateway_id not in self._conn_client.values():
                for ns_dev in client.device_ids:   # 끊김 → 해당 클라이언트 엔티티 unavailable
                    async_dispatcher_send(self.hass, signal_avail(self.entry_id, ns_dev), False)
            self._notify_clients_changed()

        return _disconnect

    @callback
    def unload(self) -> None:
        """Close all client connections when integration unloads."""
        for conn in list(self._connections):
            try:
                conn.close()
            except Exception as e:
                _LOGGER.warning("Error closing client connection: %s", e)

    @callback
    def client_for(self, connection: Any) -> str | None:
        return self._conn_client.get(connection)

    @property
    def connected_client_count(self) -> int:
        return len(set(self._conn_client.values()))

    @callback
    def _notify_clients_changed(self) -> None:
        async_dispatcher_send(
            self.hass, signal_clients(self.entry_id), self.connected_client_count
        )

    # ── 클라이언트 → HA ──────────────────────────────────────────────────────
    @callback
    def handle_entity(self, gateway_id: str, defn: dict[str, Any]) -> None:
        client = self._clients.get(gateway_id)
        if client is None:
            return
        ns = dict(defn)
        ns["unique_id"] = self._ns_uid(gateway_id, defn["unique_id"])
        device = defn.get("device")
        if device is None or device["id"] == gateway_id:
            ns_device_id = gateway_id
            ns["_device"] = {
                "ns_id": ns_device_id,
                "name": client.name,
                "gateway_id": gateway_id,
                "is_gateway": True,
            }
        else:
            ns_device_id = self._ns_dev(gateway_id, device["id"])
            ns["_device"] = {
                "ns_id": ns_device_id,
                "name": device.get("name"),
                "gateway_id": gateway_id,
                "is_gateway": False,
            }
        client.device_ids.add(ns_device_id)
        self._entity_client[ns["unique_id"]] = gateway_id

        ns["_subentry_id"] = self._subentry_id_for_gateway(gateway_id)

        platform = ns.get("platform")
        if platform not in self._platforms:
            self._pending.setdefault(platform, []).append(ns)
            return
        self._create(ns)

    @callback
    def _create(self, defn: dict[str, Any]) -> None:
        uid = defn["unique_id"]
        if uid in self._created:
            return
        self._created.add(uid)
        reg = self._platforms[defn["platform"]]

        kwargs = {}
        if subentry_id := defn.get("_subentry_id"):
            kwargs["config_subentry_id"] = subentry_id

        entity = reg.factory(self, defn)
        self._entities[uid] = entity
        reg.add_entities([entity], **kwargs)

    # ── 삭제 (subentry / ws_bridge/remove) ───────────────────────────────────
    async def async_remove_entity(self, gateway_id: str, unique_id: str) -> None:
        await self._remove_entity_ns(self._ns_uid(gateway_id, unique_id))

    async def async_remove_device(self, gateway_id: str, device_id: str) -> None:
        ns_dev = gateway_id if device_id == gateway_id else self._ns_dev(gateway_id, device_id)
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device({(DOMAIN, ns_dev)})
        if device is None:
            return

        entity_reg = er.async_get(self.hass)
        for entity_entry in list(er.async_entries_for_device(entity_reg, device.id)):
            if entity_entry.config_entry_id == self.entry_id and entity_entry.unique_id:
                await self._remove_entity_ns(entity_entry.unique_id)

        dev_reg.async_remove_device(device.id)
        if client := self._clients.get(gateway_id):
            client.device_ids.discard(ns_dev)

    async def async_remove_gateway(self, gateway_id: str) -> None:
        """게이트웨이·하위 장치·엔티티를 HA 레지스트리와 내부 상태에서 제거."""
        prefix = f"{gateway_id}__"
        entity_reg = er.async_get(self.hass)

        for entity_entry in list(er.async_entries_for_config_entry(entity_reg, self.entry_id)):
            uid = entity_entry.unique_id
            if not uid or uid.endswith(f"_{CONNECTED_CLIENTS_UNIQUE_ID}"):
                continue
            if uid.startswith(prefix):
                await self._remove_entity_ns(uid)

        dev_reg = dr.async_get(self.hass)
        for device in list(dr.async_entries_for_config_entry(dev_reg, self.entry_id)):
            for identifier in device.identifiers:
                if identifier[0] != DOMAIN:
                    continue
                val = identifier[1]
                if val == gateway_id or val.startswith(f"{gateway_id}:"):
                    dev_reg.async_remove_device(device.id)
                    break

        self._purge_gateway_state(gateway_id)

        config_entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if config_entry:
            for subentry in list(config_entry.subentries.values()):
                if subentry.data.get("gateway_id") == gateway_id:
                    self.hass.config_entries.async_remove_subentry(
                        config_entry, subentry.subentry_id
                    )
                    break

        _LOGGER.info("Removed gateway and associated devices/entities: %s", gateway_id)

    async def _remove_entity_ns(self, ns_uid: str) -> None:
        entity = self._entities.pop(ns_uid, None)
        if entity is not None:
            await entity.async_remove()
        else:
            entity_reg = er.async_get(self.hass)
            for entity_entry in er.async_entries_for_config_entry(entity_reg, self.entry_id):
                if entity_entry.unique_id == ns_uid:
                    entity_reg.async_remove(entity_entry.entity_id)
                    break

        self._created.discard(ns_uid)
        self._states.pop(ns_uid, None)
        self._entity_client.pop(ns_uid, None)

    def _purge_gateway_state(self, gateway_id: str) -> None:
        prefix = f"{gateway_id}__"
        self._clients.pop(gateway_id, None)
        for uid in list(self._created):
            if uid.startswith(prefix):
                self._created.discard(uid)
        for uid in list(self._states):
            if uid.startswith(prefix):
                self._states.pop(uid, None)
        for uid in list(self._entity_client):
            if uid.startswith(prefix):
                self._entity_client.pop(uid, None)
        for uid in list(self._entities):
            if uid.startswith(prefix):
                self._entities.pop(uid, None)
        for platform, pending in self._pending.items():
            self._pending[platform] = [
                d for d in pending if not d.get("unique_id", "").startswith(prefix)
            ]

    @callback
    def handle_state(self, gateway_id: str, unique_id: str, value: Any) -> None:
        ns_uid = self._ns_uid(gateway_id, unique_id)
        self._states[ns_uid] = value
        async_dispatcher_send(self.hass, signal_value(self.entry_id, ns_uid), value)

    @callback
    def handle_availability(self, gateway_id: str, device_id: str, online: bool) -> None:
        ns_dev = gateway_id if device_id == gateway_id else self._ns_dev(gateway_id, device_id)
        async_dispatcher_send(
            self.hass, signal_avail(self.entry_id, ns_dev), online
        )

    @callback
    def last_state(self, unique_id: str) -> Any:
        return self._states.get(unique_id)

    # ── HA → 클라이언트 (해당 클라이언트로만 라우팅) ─────────────────────────
    @callback
    def send_command(self, unique_id: str, action: str, value: Any = None) -> None:
        gateway_id = self._entity_client.get(unique_id)
        client = self._clients.get(gateway_id) if gateway_id else None
        if client is None:
            return
        event: dict[str, Any] = {
            "kind": "command",
            "unique_id": self._strip(gateway_id, unique_id),   # 원래 unique_id로 복원
            "action": action,
        }
        if value is not None:
            event["value"] = value
        client.send_event(event)

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _ns_uid(gateway_id: str, unique_id: str) -> str:
        return f"{gateway_id}__{unique_id}"

    @staticmethod
    def _ns_dev(gateway_id: str, device_id: str) -> str:
        return f"{gateway_id}:{device_id}"

    @staticmethod
    def _strip(gateway_id: str, ns_uid: str) -> str:
        prefix = f"{gateway_id}__"
        return ns_uid[len(prefix):] if ns_uid.startswith(prefix) else ns_uid
