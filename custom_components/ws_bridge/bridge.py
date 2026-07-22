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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    CONNECTED_CLIENTS_UNIQUE_ID,
    DOMAIN,
    REMOVE_MODE_PREFIX,
    SUBENTRY_TYPE_GATEWAY,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 10


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
    keep_last_state_on_disconnect: bool = False  # 클라이언트가 connect 시 선언
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
        self._defns: dict[str, dict[str, Any]] = {}      # ns unique_id → 마지막 엔티티 정의
        self._keep_last: dict[str, bool] = {}            # gateway_id → keep_last_state_on_disconnect
        self._clients: dict[str, _Client] = {}          # gateway_id → ctx
        self._conn_client: dict[Any, str] = {}          # connection → gateway_id
        self._entity_client: dict[str, str] = {}        # ns unique_id → gateway_id
        self._entities: dict[str, Entity] = {}          # ns unique_id → live entity
        self._connections: set[Any] = set()            # active connections
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.states")
        self._save_unsub: Callable[[], None] | None = None

    async def async_load(self) -> None:
        """디스크에서 마지막 state/엔티티 정의를 복원하고 entity registry에 없는 고아 항목을 정리."""
        data = await self._store.async_load() or {}
        self._states = data.get("states", {})
        self._defns = data.get("entities", {})
        self._keep_last = data.get("keep_last", {})
        if self._prune_orphan_states():
            await self.async_save()
        self._seed_restorable_entities()

    async def async_save(self) -> None:
        await self._store.async_save({
            "states": self._states,
            "entities": self._defns,
            "keep_last": self._keep_last,
        })

    async def async_flush_save(self) -> None:
        """대기 중인 debounce를 취소하고 즉시 저장."""
        if self._save_unsub is not None:
            self._save_unsub()
            self._save_unsub = None
        await self.async_save()

    def _prune_orphan_states(self) -> bool:
        entity_reg = er.async_get(self.hass)
        known_uids = {
            entry.unique_id
            for entry in er.async_entries_for_config_entry(entity_reg, self.entry_id)
            if entry.unique_id
            and not entry.unique_id.endswith(f"_{CONNECTED_CLIENTS_UNIQUE_ID}")
        }
        orphan_states = [uid for uid in self._states if uid not in known_uids]
        for uid in orphan_states:
            self._states.pop(uid, None)
        orphan_defns = [uid for uid in self._defns if uid not in known_uids]
        for uid in orphan_defns:
            self._defns.pop(uid, None)
        if orphan_states or orphan_defns:
            _LOGGER.debug(
                "Pruned %d orphaned state(s), %d orphaned entity defn(s) from store",
                len(orphan_states), len(orphan_defns),
            )
        return bool(orphan_states) or bool(orphan_defns)

    @callback
    def _seed_restorable_entities(self) -> None:
        """HA 재시작 직후, keep_last_state_on_disconnect였던 게이트웨이의 엔티티를
        클라이언트 재연결 없이도 마지막 정의·상태로 즉시 복원되도록 pending 큐에 예약한다.
        register_platform()의 기존 flush 로직이 각 플랫폼 준비 시점에 실제로 생성한다."""
        for uid, defn in self._defns.items():
            gateway_id = defn.get("_device", {}).get("gateway_id")
            if gateway_id is None or not self._keep_last.get(gateway_id):
                continue
            platform = defn.get("platform")
            if platform is None:
                continue
            self._entity_client[uid] = gateway_id
            self._pending.setdefault(platform, []).append(defn)

    @callback
    def _schedule_save(self) -> None:
        if self._save_unsub is not None:
            self._save_unsub()
        self._save_unsub = async_call_later(self.hass, SAVE_DELAY, self._debounced_save)

    @callback
    def _debounced_save(self, _now) -> None:
        self._save_unsub = None
        self.hass.async_create_task(self.async_save())

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
        keep_last_state_on_disconnect: bool = False,
    ) -> Callable[[], None]:
        client = self._clients.get(gateway_id)
        if client is None:
            client = self._clients[gateway_id] = _Client(
                gateway_id, name or gateway_id, send_event, sw_version,
                keep_last_state_on_disconnect,
            )
        else:
            client.name = name or client.name
            client.send_event = send_event
            if sw_version:
                client.sw_version = sw_version
            client.keep_last_state_on_disconnect = keep_last_state_on_disconnect
        if self._keep_last.get(gateway_id) != keep_last_state_on_disconnect:
            self._keep_last[gateway_id] = keep_last_state_on_disconnect
            if not keep_last_state_on_disconnect:
                # 옵션을 껐다면 더 이상 필요 없는 저장된 엔티티 정의를 즉시 비워
                # 스토리지가 계속 불어나지 않게 한다 (state는 그대로 유지).
                ns_prefix = f"{gateway_id}__"
                for uid in list(self._defns):
                    if uid.startswith(ns_prefix):
                        self._defns.pop(uid, None)
            self._schedule_save()
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
            if gateway_id not in self._conn_client.values() and not client.keep_last_state_on_disconnect:
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
            dev_name = device.get("name") or device["id"]
            gw_prefix = client.name

            # Avoid double-prefixing
            dev_name_lower = dev_name.lower()
            gw_prefix_lower = gw_prefix.lower()
            gateway_id_lower = gateway_id.lower()

            if (
                not dev_name_lower.startswith(gw_prefix_lower)
                and not dev_name_lower.startswith(gateway_id_lower)
            ):
                full_device_name = f"{gw_prefix} {dev_name}"
            else:
                full_device_name = dev_name

            ns["_device"] = {
                "ns_id": ns_device_id,
                "name": full_device_name,
                "gateway_id": gateway_id,
                "is_gateway": False,
            }
        client.device_ids.add(ns_device_id)
        self._entity_client[ns["unique_id"]] = gateway_id

        ns["_subentry_id"] = self._subentry_id_for_gateway(gateway_id)

        # 엔티티 정의는 keep_last_state_on_disconnect 게이트웨이만 저장한다 — 그래야
        # 이 옵션을 안 쓰는(기본값) 대다수 사용자의 스토리지 크기가 이전과 동일하게 유지된다.
        if self._keep_last.get(gateway_id):
            self._defns[ns["unique_id"]] = ns
            self._schedule_save()
        elif self._defns.pop(ns["unique_id"], None) is not None:
            self._schedule_save()

        platform = ns.get("platform")
        if platform not in self._platforms:
            self._pending.setdefault(platform, []).append(ns)
            return

        if ns["unique_id"] in self._entities:
            self._entities[ns["unique_id"]].async_update_defn(ns)
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
    async def async_remove_entity(
        self, gateway_id: str, unique_id: str, mode: str = "exact"
    ) -> None:
        use_prefix = mode == REMOVE_MODE_PREFIX
        if not use_prefix:
            await self._remove_entity_ns(self._ns_uid(gateway_id, unique_id))
            return

        entity_reg = er.async_get(self.hass)
        to_remove: set[str] = set()
        for entity_entry in er.async_entries_for_config_entry(entity_reg, self.entry_id):
            uid = entity_entry.unique_id
            if not uid:
                continue
            stripped = self._strip(gateway_id, uid)
            if self._client_id_matches(stripped, unique_id, prefix=True):
                to_remove.add(uid)

        ns_prefix = self._ns_uid(gateway_id, unique_id)
        for uid in list(self._created):
            if uid == ns_prefix or uid.startswith(f"{ns_prefix}_"):
                to_remove.add(uid)

        for uid in to_remove:
            await self._remove_entity_ns(uid)

    async def async_remove_device(
        self, gateway_id: str, device_id: str, mode: str = "exact"
    ) -> None:
        use_prefix = mode == REMOVE_MODE_PREFIX
        dev_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        devices_to_remove: list[str] = []

        for device in dr.async_entries_for_config_entry(dev_reg, self.entry_id):
            for identifier in device.identifiers:
                if identifier[0] != DOMAIN:
                    continue
                client_id = self._client_device_id_from_ns(gateway_id, identifier[1])
                if client_id is None:
                    continue
                if self._client_id_matches(client_id, device_id, prefix=use_prefix):
                    devices_to_remove.append(device.id)
                    break

        for device_registry_id in devices_to_remove:
            for entity_entry in list(er.async_entries_for_device(entity_reg, device_registry_id)):
                if entity_entry.config_entry_id == self.entry_id and entity_entry.unique_id:
                    await self._remove_entity_ns(entity_entry.unique_id)
            dev_reg.async_remove_device(device_registry_id)

        if client := self._clients.get(gateway_id):
            to_discard = {
                ns
                for ns in client.device_ids
                if (cid := self._client_device_id_from_ns(gateway_id, ns)) is not None
                and self._client_id_matches(cid, device_id, prefix=use_prefix)
            }
            client.device_ids -= to_discard

    async def async_remove_gateway(self, gateway_id: str) -> None:
        """게이트웨이·하위 장치·엔티티를 HA 레지스트리와 내부 상태에서 제거."""
        prefix = f"{gateway_id}__"
        entity_reg = er.async_get(self.hass)

        for entity_entry in list(er.async_entries_for_config_entry(entity_reg, self.entry_id)):
            uid = entity_entry.unique_id
            if not uid or uid.endswith(f"_{CONNECTED_CLIENTS_UNIQUE_ID}"):
                continue
            if uid.startswith(prefix):
                await self._remove_entity_ns(uid, persist=False)

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
        await self.async_save()

        config_entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if config_entry:
            for subentry in list(config_entry.subentries.values()):
                if subentry.data.get("gateway_id") == gateway_id:
                    self.hass.config_entries.async_remove_subentry(
                        config_entry, subentry.subentry_id
                    )
                    break

        _LOGGER.info("Removed gateway and associated devices/entities: %s", gateway_id)

    async def _remove_entity_ns(self, ns_uid: str, *, persist: bool = True) -> None:
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
        self._defns.pop(ns_uid, None)
        self._entity_client.pop(ns_uid, None)
        if persist:
            await self.async_save()

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
        for uid in list(self._defns):
            if uid.startswith(prefix):
                self._defns.pop(uid, None)
        self._keep_last.pop(gateway_id, None)
        for platform, pending in self._pending.items():
            self._pending[platform] = [
                d for d in pending if not d.get("unique_id", "").startswith(prefix)
            ]

    @callback
    def handle_state(self, gateway_id: str, unique_id: str, value: Any) -> None:
        ns_uid = self._ns_uid(gateway_id, unique_id)
        self._states[ns_uid] = value
        self._schedule_save()
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
    def _client_id_matches(candidate: str, target: str, *, prefix: bool) -> bool:
        if prefix:
            return candidate == target or candidate.startswith(f"{target}_")
        return candidate == target

    @staticmethod
    def _client_device_id_from_ns(gateway_id: str, ns_dev: str) -> str | None:
        if ns_dev == gateway_id:
            return gateway_id
        gw_prefix = f"{gateway_id}:"
        if not ns_dev.startswith(gw_prefix):
            return None
        return ns_dev[len(gw_prefix) :]

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
