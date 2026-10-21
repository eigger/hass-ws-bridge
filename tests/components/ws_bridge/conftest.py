"""Fixtures for ws_bridge tests.

The integration has no external device/cloud boundary: its clients talk to HA over
HA's own WebSocket API. Tests therefore drive it through the real `hass_ws_client`
(real aiohttp WebSocket + real HA auth) and verify results via hass.states and the
entity/device registries.
"""

# <!-- hass-standards:domain-fixtures:start -->
# Use pytest_homeassistant_custom_component.common.MockConfigEntry for
# mock_config_entry when the integration uses config entries.
# Define mock_client only when an external communication client is present.
# Mock external communication boundaries, never Home Assistant core modules.
# Keep integration-specific fixtures below this managed block.
# <!-- hass-standards:domain-fixtures:end -->

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import (
    MockHAClientWebSocket,
    WebSocketGenerator,
)

from custom_components.ws_bridge.bridge import WsBridge
from custom_components.ws_bridge.const import DOMAIN

RECEIVE_TIMEOUT = 5


def get_bridge(hass: HomeAssistant, entry: MockConfigEntry) -> WsBridge:
    """Bridge instance the integration stored for this entry."""
    return hass.data[DOMAIN][entry.entry_id]


def entity_id_for(
    hass: HomeAssistant, domain: str, unique_id: str, gateway_id: str = "gw1"
) -> str | None:
    """entity_id registered for a client-declared unique_id (namespaced by gateway)."""
    return er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{gateway_id}__{unique_id}"
    )


def get_device(hass: HomeAssistant, identifier: str) -> dr.DeviceEntry | None:
    """ws_bridge device by its (namespaced) identifier, or None."""
    devices = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, identifier)})
    assert len(devices) <= 1
    return devices[0] if devices else None


def entity_is_live(
    hass: HomeAssistant, domain: str, unique_id: str, gateway_id: str = "gw1"
) -> bool:
    """True when the entity is registered and currently provided (not unavailable)."""
    entity_id = entity_id_for(hass, domain, unique_id, gateway_id)
    if entity_id is None:
        return False
    state = hass.states.get(entity_id)
    return state is not None and state.state != STATE_UNAVAILABLE


class BridgeClient:
    """A ws_bridge protocol client on top of a real HA WebSocket connection."""

    def __init__(
        self, hass: HomeAssistant, entry: MockConfigEntry, ws: MockHAClientWebSocket
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.ws = ws
        self._next_id = 0
        self.events: list[dict[str, Any]] = []
        self.connect_id: int | None = None

    async def send(self, type_: str, **payload: Any) -> dict[str, Any]:
        """Send a ws_bridge/<type_> command and return its result message."""
        self._next_id += 1
        msg_id = self._next_id
        await self.ws.send_json({"id": msg_id, "type": f"{DOMAIN}/{type_}", **payload})
        while True:
            msg = await self.ws.receive_json(timeout=RECEIVE_TIMEOUT)
            if msg.get("type") == "event":
                self.events.append(msg["event"])
                continue
            if msg.get("id") == msg_id:
                await self.hass.async_block_till_done()
                return msg

    async def ok(self, type_: str, **payload: Any) -> Any:
        msg = await self.send(type_, **payload)
        assert msg["success"], msg
        return msg.get("result")

    async def connect(
        self, gateway_id: str = "gw1", name: str | None = "GW1", **extra: Any
    ) -> None:
        payload: dict[str, Any] = {"gateway_id": gateway_id, **extra}
        if name is not None:
            payload["name"] = name
        await self.ok("connect", **payload)
        self.connect_id = self._next_id

    async def entity(
        self, unique_id: str, platform: str, name: str = "X", **extra: Any
    ) -> None:
        await self.ok(
            "entity", unique_id=unique_id, platform=platform, name=name, **extra
        )

    async def state(self, unique_id: str, value: Any) -> None:
        await self.ok("state", states=[{"unique_id": unique_id, "value": value}])

    async def availability(self, device_id: str, online: bool) -> None:
        await self.ok("availability", device_id=device_id, online=online)

    async def next_command(self) -> dict[str, Any]:
        """Next HA→client command event pushed on the connect subscription."""
        if not self.events:
            while True:
                msg = await self.ws.receive_json(timeout=RECEIVE_TIMEOUT)
                if msg.get("type") == "event":
                    assert msg["id"] == self.connect_id
                    self.events.append(msg["event"])
                    break
        return self.events.pop(0)

    async def close(self) -> None:
        """Close the socket and wait until HA has processed the disconnect."""
        bridge = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        before = len(bridge._conn_client) if bridge else 0
        await self.ws.close()
        for _ in range(200):
            await asyncio.sleep(0.01)
            await self.hass.async_block_till_done()
            if bridge is None or len(bridge._conn_client) < before:
                return
        raise AssertionError("HA did not process the WebSocket disconnect")


async def call_service(
    hass: HomeAssistant, domain: str, service: str, entity_id: str, **data: Any
) -> None:
    """Call an entity service through HA's service registry."""
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def restart_without_client(
    hass: HomeAssistant, entry: MockConfigEntry, client: BridgeClient
) -> None:
    """Drop the client, then reload the entry (HA restart equivalent).

    keep_last gateways are recreated from storage but have no live client.
    """
    await client.close()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """The single ws_bridge config entry, as the config flow creates it."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="WebSocket Bridge", unique_id=DOMAIN, data={}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the entry through the real config entry manager."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture
def bridge_client_factory(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
) -> Callable[[], Awaitable[BridgeClient]]:
    """Open additional authenticated WebSocket clients."""

    async def _make() -> BridgeClient:
        return BridgeClient(hass, init_integration, await hass_ws_client(hass))

    return _make


@pytest.fixture
async def client(
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> BridgeClient:
    """A client already registered as gateway `gw1` (name `GW1`)."""
    bridge_client = await bridge_client_factory()
    await bridge_client.connect()
    return bridge_client
