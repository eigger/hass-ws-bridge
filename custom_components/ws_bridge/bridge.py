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
    PLATFORM_EVENT,
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


def _nonempty(value: Any) -> str | None:
    """프로토콜 선택 문자열. 비어 있으면 미전송으로 본다."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


@dataclass
class _Client:
    gateway_id: str
    name: str
    send_event: Callable[[dict[str, Any]], None]
    sw_version: str | None = None
    keep_last_state_on_disconnect: bool = False  # 클라이언트가 connect 시 선언
    device_ids: set[str] = field(default_factory=set)   # 네임스페이스된 sub-device id
    manufacturer: str | None = None
    model: str | None = None
    hw_version: str | None = None


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
        self._entity_device: dict[str, str] = {}        # ns unique_id → ns device id
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
            if ns_dev := defn.get("_device", {}).get("ns_id"):
                self._entity_device[uid] = ns_dev
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
        manufacturer: str | None = None,
        model: str | None = None,
        hw_version: str | None = None,
    ) -> Callable[[], None]:
        manufacturer = _nonempty(manufacturer)
        model = _nonempty(model)
        hw_version = _nonempty(hw_version)
        sw_version = _nonempty(sw_version)
        client = self._clients.get(gateway_id)
        if client is None:
            client = self._clients[gateway_id] = _Client(
                gateway_id, name or gateway_id, send_event, sw_version,
                keep_last_state_on_disconnect,
                manufacturer=manufacturer,
                model=model,
                hw_version=hw_version,
            )
        else:
            client.name = name or client.name
            client.send_event = send_event
            if sw_version:
                client.sw_version = sw_version
            if manufacturer:
                client.manufacturer = manufacturer
            if model:
                client.model = model
            if hw_version:
                client.hw_version = hw_version
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
        # 같은 게이트웨이의 두 번째 커넥션은 첫 커넥션이 쌓아둔 추적 정보를
        # 리셋하면 안 된다 — 마지막 커넥션이 끊길 때의 offline 팬아웃이 빈다.
        is_first_connection = gateway_id not in self._conn_client.values()
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

        manufacturer = client.manufacturer or "ws_bridge"
        model = client.model or "Gateway"
        gw_entry = dev_reg.async_get_or_create(
            config_entry_id=self.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, gateway_id)},
            name=client.name,
            manufacturer=manufacturer,
            model=model,
            sw_version=client.sw_version,
            hw_version=client.hw_version,
        )
        # via_device가 남아 있으면 제거, 디바이스 정보도 갱신
        if (
            gw_entry.via_device_id is not None
            or gw_entry.manufacturer != manufacturer
            or gw_entry.model != model
            or gw_entry.sw_version != client.sw_version
            or gw_entry.hw_version != client.hw_version
        ):
            dev_reg.async_update_device(
                gw_entry.id,
                via_device_id=None,
                manufacturer=manufacturer,
                model=model,
                sw_version=client.sw_version,
                hw_version=client.hw_version,
            )
        if is_first_connection:
            # 재연결 → 게이트웨이 자신은 즉시 온라인. sub-device는 이번 세션에
            # 클라이언트가 다시 선언하거나 상태를 보낼 때 _touch_device()가
            # 되돌린다. 예전에 알던 걸 무조건 되살리면 클라이언트에서 이미
            # 사라진 sub-device의 엔티티까지 살아 있는 것처럼 보인다.
            client.device_ids = {gateway_id}
            async_dispatcher_send(
                self.hass, signal_avail(self.entry_id, gateway_id), True
            )

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
                "manufacturer": client.manufacturer,
                "model": client.model,
                "sw_version": client.sw_version,
                "hw_version": client.hw_version,
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
        self._touch_device(client, ns_device_id)
        self._entity_client[ns["unique_id"]] = gateway_id
        self._entity_device[ns["unique_id"]] = ns_device_id

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

    # ── 동기화 (ws_bridge/sync) ──────────────────────────────────────────────
    async def async_sync_entities(
        self, gateway_id: str, unique_ids: list[str]
    ) -> list[str]:
        """클라이언트가 선언한 '전체 목록'과 대조해, 목록에 없는 이 게이트웨이의
        엔티티를 제거하고 제거된 (원본) unique_id 목록을 돌려준다.

        살아남는 엔티티는 건드리지 않으므로 히스토리·통계·entity_id가 그대로
        보존된다 — 전체 삭제 후 재선언하는 방식과의 결정적인 차이.
        연결이 끊겨 unavailable인 엔티티, HA 재시작 때 저장된 정의로 복원된
        (keep_last_state_on_disconnect) 엔티티도 모두 대조 대상이다.
        """
        keep = {self._ns_uid(gateway_id, uid) for uid in unique_ids}
        prefix = f"{gateway_id}__"

        known: set[str] = set()
        entity_reg = er.async_get(self.hass)
        for entity_entry in er.async_entries_for_config_entry(entity_reg, self.entry_id):
            uid = entity_entry.unique_id
            if uid and uid.startswith(prefix):
                known.add(uid)
        # 아직 레지스트리에 안 올라온 것(플랫폼 준비 전 pending)과 저장된 정의도 포함
        known.update(uid for uid in self._created if uid.startswith(prefix))
        known.update(uid for uid in self._defns if uid.startswith(prefix))
        known.update(
            uid
            for pending in self._pending.values()
            for defn in pending
            if (uid := defn.get("unique_id", "")).startswith(prefix)
        )
        # 통합 진단 센서는 게이트웨이 소유가 아니므로 절대 대조 대상이 아니다
        known = {
            uid for uid in known
            if not uid.endswith(f"_{CONNECTED_CLIENTS_UNIQUE_ID}")
        }

        stale = sorted(known - keep)
        if not stale:
            return []

        for uid in stale:
            await self._remove_entity_ns(uid, persist=False)
        await self.async_save()
        self._prune_empty_devices(gateway_id)

        removed = [self._strip(gateway_id, uid) for uid in stale]
        _LOGGER.info(
            "Sync removed %d stale entity/entities for gateway %s: %s",
            len(removed), gateway_id, ", ".join(removed),
        )
        return removed

    @callback
    def _prune_empty_devices(self, gateway_id: str) -> None:
        """엔티티가 하나도 남지 않은 sub-device를 레지스트리와 클라이언트 상태에서
        정리한다. 게이트웨이 디바이스 자체는 엔티티가 없어도 유지한다."""
        dev_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        client = self._clients.get(gateway_id)
        gw_prefix = f"{gateway_id}:"

        for device in list(dr.async_entries_for_config_entry(dev_reg, self.entry_id)):
            ns_dev = next(
                (ident[1] for ident in device.identifiers if ident[0] == DOMAIN), None
            )
            if ns_dev is None or not ns_dev.startswith(gw_prefix):
                continue
            if er.async_entries_for_device(
                entity_reg, device.id, include_disabled_entities=True
            ):
                continue
            _LOGGER.info("Removing sub-device with no remaining entities: %s", ns_dev)
            dev_reg.async_remove_device(device.id)
            if client is not None:
                client.device_ids.discard(ns_dev)

    # ── 삭제 (subentry / ws_bridge/remove) ───────────────────────────────────
    async def async_remove_entity(
        self, gateway_id: str, unique_id: str, mode: str = "exact"
    ) -> None:
        use_prefix = mode == REMOVE_MODE_PREFIX
        if not use_prefix:
            await self._remove_entity_ns(self._ns_uid(gateway_id, unique_id))
            _LOGGER.info("Removed entity: %s (gateway %s)", unique_id, gateway_id)
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

        if to_remove:
            _LOGGER.info(
                "Removed %d entity/entities matching prefix %s (gateway %s): %s",
                len(to_remove), unique_id, gateway_id,
                ", ".join(sorted(self._strip(gateway_id, uid) for uid in to_remove)),
            )

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

        if devices_to_remove:
            _LOGGER.info(
                "Removed %d sub-device(s) and their entities for %s=%s (gateway %s)",
                len(devices_to_remove), mode, device_id, gateway_id,
            )

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
        self._entity_device.pop(ns_uid, None)
        # 플랫폼이 아직 준비되지 않아 큐에 남아 있으면 빼준다 — 안 그러면
        # register_platform()의 flush가 방금 지운 엔티티를 되살린다.
        for platform, pending in self._pending.items():
            if any(d.get("unique_id") == ns_uid for d in pending):
                self._pending[platform] = [
                    d for d in pending if d.get("unique_id") != ns_uid
                ]
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
        for uid in list(self._entity_device):
            if uid.startswith(prefix):
                self._entity_device.pop(uid, None)
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
    def _touch_device(self, client: _Client, ns_dev: str) -> None:
        """이번 커넥션에서 처음 보는 sub-device면 온라인으로 되돌린다.

        선언(handle_entity)뿐 아니라 상태 갱신(handle_state)에서도 불린다 —
        재연결 시 엔티티를 다시 선언하지 않고 state만 보내는 클라이언트도
        그대로 동작하게 하기 위해서다.
        """
        if ns_dev in client.device_ids:
            return
        client.device_ids.add(ns_dev)
        async_dispatcher_send(self.hass, signal_avail(self.entry_id, ns_dev), True)

    def _entity_platform(self, ns_uid: str) -> str | None:
        """선언된 엔티티의 platform. event 병합 스킵 등에 사용."""
        if (ent := self._entities.get(ns_uid)) is not None:
            return ent._defn.get("platform")
        if (defn := self._defns.get(ns_uid)) is not None:
            return defn.get("platform")
        for pending in self._pending.values():
            for defn in pending:
                if defn.get("unique_id") == ns_uid:
                    return defn.get("platform")
        return None

    @callback
    def handle_state(self, gateway_id: str, unique_id: str, value: Any) -> None:
        ns_uid = self._ns_uid(gateway_id, unique_id)
        if (client := self._clients.get(gateway_id)) is not None:
            if (ns_dev := self._entity_device.get(ns_uid)) is not None:
                self._touch_device(client, ns_dev)
        is_event = self._entity_platform(ns_uid) == PLATFORM_EVENT
        if isinstance(value, dict):
            # event 는 fire-and-forget — 얕은 병합하면 이전 attributes 가 다음 이벤트로 샌다.
            if is_event:
                value = dict(value)
            else:
                prev = self._states.get(ns_uid)
                value = {**prev, **value} if isinstance(prev, dict) else dict(value)
        if is_event:
            # 복원하지 않으므로 디스크·메모리 영속화 생략 (발화마다 Store 방지).
            async_dispatcher_send(self.hass, signal_value(self.entry_id, ns_uid), value)
            return
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

    @callback
    def set_local_state(self, unique_id: str, value: Any) -> None:
        """낙관적 UI 상태를 _states 에 반영한다 (dispatcher 없음).

        복합 엔티티가 _state 사본만 바꾸면, 이후 클라이언트의 부분 푸시가
        stale 값과 병합되어 설정값이 되돌아간다.
        """
        if isinstance(value, dict):
            value = dict(value)
        self._states[unique_id] = value
        self._schedule_save()

    # ── HA → 클라이언트 (해당 클라이언트로만 라우팅) ─────────────────────────
    @callback
    def send_command(
        self, unique_id: str, action: str,
        value: Any = None, params: dict[str, Any] | None = None,
    ) -> bool:
        gateway_id = self._entity_client.get(unique_id)
        client = self._clients.get(gateway_id) if gateway_id else None
        if client is None:
            return False
        event: dict[str, Any] = {
            "kind": "command",
            "unique_id": self._strip(gateway_id, unique_id),   # 원래 unique_id로 복원
            "action": action,
        }
        if value is not None:
            event["value"] = value
        if params:
            event["params"] = params
        client.send_event(event)
        return True

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
