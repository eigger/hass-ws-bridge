"""WebSocket Bridge 통합 진입점.

범용 브릿지 — 인증된 클라이언트가 선언한 엔티티를 만들고 갱신. 형식(BLE 등) 무관.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import websocket_api
from .bridge import WsBridge
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_KEY = "_subentry_gids"

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
]


def _subentry_gateway_ids(entry: ConfigEntry) -> set[str]:
    return {
        sub.data["gateway_id"]
        for sub in entry.subentries.values()
        if sub.data.get("gateway_id")
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge = WsBridge(hass, entry.entry_id)

    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data:
        websocket_api.async_register(hass)   # WS 커스텀 명령 1회 등록
    domain_data[entry.entry_id] = bridge
    domain_data.setdefault(SNAPSHOT_KEY, {})[entry.entry_id] = _subentry_gateway_ids(entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Subentry 추가/삭제 처리. 삭제 시 해당 게이트웨이의 기기·엔티티를 정리."""
    domain_data = hass.data.get(DOMAIN, {})
    snapshots = domain_data.get(SNAPSHOT_KEY, {})
    old_gids = snapshots.get(entry.entry_id, set())
    new_gids = _subentry_gateway_ids(entry)
    removed = old_gids - new_gids
    added = new_gids - old_gids
    snapshots[entry.entry_id] = new_gids

    bridge: WsBridge | None = domain_data.get(entry.entry_id)
    if bridge and removed:
        for gateway_id in removed:
            _LOGGER.info("Subentry removed — cleaning up gateway: %s", gateway_id)
            await bridge.async_remove_gateway(gateway_id)

    if added:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        domain_data = hass.data.get(DOMAIN, {})
        bridge = domain_data.pop(entry.entry_id, None)
        if snapshots := domain_data.get(SNAPSHOT_KEY):
            snapshots.pop(entry.entry_id, None)
        if bridge:
            bridge.unload()
    return unloaded
