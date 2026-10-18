"""ws_bridge/* protocol over the real HA WebSocket API (PROTOCOL.md §2-§3)."""

import asyncio
from datetime import timedelta

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ws_bridge.const import CONF_ALLOWED_USER_IDS, DOMAIN

from .conftest import BridgeClient, entity_id_for, entity_is_live, get_device


# ── connect / gateway device ────────────────────────────────────────────────
async def test_connect_registers_gateway_device_with_defaults(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    device = get_device(hass, "gw1")
    assert device is not None
    assert device.name == "GW1"
    assert device.manufacturer == "ws_bridge"
    assert device.model == "Gateway"
    assert device.sw_version is None
    assert device.hw_version is None
    assert device.via_device_id is None


async def test_connect_optional_device_fields_are_independent(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", manufacturer="Espressif", hw_version="1.0")
    device = get_device(hass, "gw1")
    assert device.manufacturer == "Espressif"
    assert device.model == "Gateway"
    assert device.hw_version == "1.0"
    assert device.sw_version is None

    # Reconnect without the fields keeps previously reported values.
    await gw.connect("gw1", "GW1", model="ESP32-S3", manufacturer="  ")
    device = get_device(hass, "gw1")
    assert device.manufacturer == "Espressif"
    assert device.model == "ESP32-S3"
    assert device.hw_version == "1.0"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"sw_version": "2.0", "app_version": "1.0"}, "2.0"),
        ({"app_version": "1.0"}, "1.0"),
        ({"sw_version": "  ", "app_version": "1.0"}, "1.0"),
        ({}, None),
    ],
)
async def test_connect_sw_version_prefers_sw_over_deprecated_app_version(
    hass: HomeAssistant, bridge_client_factory, payload, expected
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", **payload)
    assert get_device(hass, "gw1").sw_version == expected


async def test_connect_removes_offline_duplicate_by_name(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    """A gateway that came back under a new gateway_id with the same name
    replaces the old offline device (and its sub-devices)."""
    old = await bridge_client_factory()
    await old.connect("old_gw", "Kitchen")
    await old.entity("t", "sensor", "T", device={"id": "probe"})
    assert get_device(hass, "old_gw:probe") is not None
    await old.close()

    new = await bridge_client_factory()
    await new.connect("new_gw", "Kitchen")
    assert get_device(hass, "old_gw") is None
    assert get_device(hass, "old_gw:probe") is None
    assert get_device(hass, "new_gw") is not None


async def test_connect_keeps_online_device_with_same_name(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    first = await bridge_client_factory()
    await first.connect("gw_a", "Kitchen")
    second = await bridge_client_factory()
    await second.connect("gw_b", "Kitchen")
    assert get_device(hass, "gw_a") is not None
    assert get_device(hass, "gw_b") is not None


# ── entity declaration / device hierarchy ────────────────────────────────────
async def test_sub_device_hierarchy_and_naming(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("lux", "sensor", "Lux", device={"id": "ms1", "name": "Multi"})
    await client.entity("a", "sensor", "A", device={"id": "hall", "name": "gw1 Hall"})
    await client.entity("b", "sensor", "B", device={"id": "den", "name": "GW1 Den"})
    await client.entity("c", "sensor", "C", device={"id": "noname"})
    await client.entity("own", "sensor", "Own", device={"id": "gw1"})

    gateway = get_device(hass, "gw1")
    sub = get_device(hass, "gw1:ms1")
    assert sub.name == "GW1 Multi"
    assert sub.via_device_id == gateway.id
    # No double prefix when the name already starts with gateway name / id.
    assert get_device(hass, "gw1:hall").name == "gw1 Hall"
    assert get_device(hass, "gw1:den").name == "GW1 Den"
    assert get_device(hass, "gw1:noname").name == "GW1 noname"
    # device.id == gateway_id → entity belongs to the gateway device.
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get(entity_id_for(hass, "sensor", "own")).device_id == (
        gateway.id
    )
    assert ent_reg.async_get(entity_id_for(hass, "sensor", "lux")).device_id == (sub.id)


async def test_same_unique_id_on_two_gateways_does_not_collide(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1")
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2")
    await gw1.entity("temp", "sensor", "Temp")
    await gw2.entity("temp", "sensor", "Temp")
    await gw1.state("temp", 1)
    await gw2.state("temp", 2)
    assert hass.states.get(entity_id_for(hass, "sensor", "temp", "gw1")).state == "1"
    assert hass.states.get(entity_id_for(hass, "sensor", "temp", "gw2")).state == "2"


@pytest.mark.parametrize(
    ("platform", "extra", "message"),
    [
        ("event", {}, "event_types is required"),
        ("event", {"event_types": []}, "event_types is required"),
        ("climate", {}, "hvac_modes is required"),
        ("climate", {"hvac_modes": []}, "hvac_modes is required"),
    ],
)
async def test_entity_required_lists_validated(
    hass: HomeAssistant, client: BridgeClient, platform, extra, message
) -> None:
    msg = await client.send(
        "entity", unique_id="x", platform=platform, name="X", **extra
    )
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"
    assert message in msg["error"]["message"]
    assert entity_id_for(hass, platform, "x") is None


async def test_entity_schema_rejects_unknown_platform(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    msg = await client.send("entity", unique_id="x", platform="toaster", name="X")
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"


# ── availability / disconnect / reconnect ───────────────────────────────────
async def test_sub_device_availability(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("t", "sensor", "T", device={"id": "probe"})
    await client.entity("g", "sensor", "G")
    sub_entity = entity_id_for(hass, "sensor", "t")
    gw_entity = entity_id_for(hass, "sensor", "g")

    await client.availability("probe", False)
    assert hass.states.get(sub_entity).state == STATE_UNAVAILABLE
    assert hass.states.get(gw_entity).state != STATE_UNAVAILABLE
    await client.availability("probe", True)
    assert hass.states.get(sub_entity).state != STATE_UNAVAILABLE

    # device_id == gateway_id addresses the gateway device itself.
    await client.availability("gw1", False)
    assert hass.states.get(gw_entity).state == STATE_UNAVAILABLE
    assert hass.states.get(sub_entity).state != STATE_UNAVAILABLE


async def test_disconnect_marks_only_that_gateway_unavailable(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1")
    await gw1.entity("t", "sensor", "T", device={"id": "probe"})
    await gw1.entity("g", "sensor", "G")
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2")
    await gw2.entity("g", "sensor", "G")
    await gw1.state("g", 1)

    await gw1.close()
    assert hass.states.get(entity_id_for(hass, "sensor", "t")).state == (
        STATE_UNAVAILABLE
    )
    assert hass.states.get(entity_id_for(hass, "sensor", "g")).state == (
        STATE_UNAVAILABLE
    )
    assert hass.states.get(entity_id_for(hass, "sensor", "g", "gw2")).state != (
        STATE_UNAVAILABLE
    )


async def test_keep_last_state_on_disconnect(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("t", "sensor", "T", device={"id": "probe"})
    await gw.state("t", 12)
    await gw.close()
    assert hass.states.get(entity_id_for(hass, "sensor", "t")).state == "12"


async def test_reconnect_does_not_resurrect_undeclared_sub_devices(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    first = await bridge_client_factory()
    await first.connect()
    for dev in ("keeps", "goes_away"):
        await first.entity(f"{dev}_x", "sensor", "X", device={"id": dev})
    await first.entity("own", "sensor", "Own")
    await first.close()
    keeps = entity_id_for(hass, "sensor", "keeps_x")
    gone = entity_id_for(hass, "sensor", "goes_away_x")
    own = entity_id_for(hass, "sensor", "own")
    assert hass.states.get(keeps).state == STATE_UNAVAILABLE

    second = await bridge_client_factory()
    await second.connect()
    # The gateway device itself is online right after connect.
    assert hass.states.get(own).state != STATE_UNAVAILABLE
    assert hass.states.get(keeps).state == STATE_UNAVAILABLE
    await second.entity("keeps_x", "sensor", "X", device={"id": "keeps"})
    assert hass.states.get(keeps).state != STATE_UNAVAILABLE
    assert hass.states.get(gone).state == STATE_UNAVAILABLE


async def test_reconnect_state_only_client_restores_availability(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    first = await bridge_client_factory()
    await first.connect()
    await first.entity("sub_x", "sensor", "X", device={"id": "sub"})
    await first.close()
    entity_id = entity_id_for(hass, "sensor", "sub_x")
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    second = await bridge_client_factory()
    await second.connect()
    await second.state("sub_x", 42)
    state = hass.states.get(entity_id)
    assert state.state == "42"


async def test_second_connection_does_not_reset_device_tracking(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    """Closing the last of two connections still fans out offline to the
    sub-devices the first connection declared."""
    conn1 = await bridge_client_factory()
    await conn1.connect()
    await conn1.entity("sub_x", "sensor", "X", device={"id": "sub"})
    conn2 = await bridge_client_factory()
    await conn2.connect()
    entity_id = entity_id_for(hass, "sensor", "sub_x")

    await conn1.close()
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    await conn2.close()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


# ── commands (HA → client) ───────────────────────────────────────────────────
async def test_commands_route_only_to_owning_gateway(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1")
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2")
    await gw1.entity("relay", "switch", "Relay")
    await gw2.entity("relay", "switch", "Relay")

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": entity_id_for(hass, "switch", "relay", "gw2")},
        blocking=True,
    )
    assert await gw2.next_command() == {
        "kind": "command",
        "unique_id": "relay",
        "action": "turn_on",
    }
    assert gw1.events == []
    assert hass.states.get(entity_id_for(hass, "switch", "relay", "gw2")).state == (
        STATE_ON
    )
    assert hass.states.get(entity_id_for(hass, "switch", "relay", "gw1")).state != (
        STATE_ON
    )


async def test_command_fails_when_gateway_not_connected(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    """A keep_last entity restored at startup has no live client yet: commands
    raise instead of setting an optimistic state."""
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("relay", "switch", "Relay")
    await gw.state("relay", False)
    await gw.close()
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    entity_id = entity_id_for(hass, "switch", "relay")
    assert hass.states.get(entity_id).state == STATE_OFF

    with pytest.raises(HomeAssistantError, match="not connected"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": entity_id}, blocking=True
        )
    assert hass.states.get(entity_id).state == STATE_OFF

    # Once the client reconnects the same entity is controllable again.
    again = await bridge_client_factory()
    await again.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert (await again.next_command())["action"] == "turn_on"
    assert hass.states.get(entity_id).state == STATE_ON


# ── remove (§3.4) ────────────────────────────────────────────────────────────
async def test_remove_entity_exact_and_prefix(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    for uid in ("sensor_1", "sensor_1_temp", "sensor_1_hum", "sensor_10", "other"):
        await client.entity(uid, "sensor", uid)

    await client.ok("remove", unique_id="sensor_1")
    assert not entity_is_live(hass, "sensor", "sensor_1")
    assert entity_is_live(hass, "sensor", "sensor_1_temp")

    await client.ok("remove", unique_id="sensor_1", mode="prefix")
    assert not entity_is_live(hass, "sensor", "sensor_1_temp")
    assert not entity_is_live(hass, "sensor", "sensor_1_hum")
    # Prefix matches whole `_`-separated segments only.
    assert entity_is_live(hass, "sensor", "sensor_10")
    assert entity_is_live(hass, "sensor", "other")

    # A removed entity can be declared again and is live.
    await client.entity("sensor_1", "sensor", "sensor_1")
    await client.state("sensor_1", 5)
    assert entity_is_live(hass, "sensor", "sensor_1")
    assert hass.states.get(entity_id_for(hass, "sensor", "sensor_1")).state == "5"


async def test_remove_entity_deletes_registry_entry(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """PROTOCOL §3.4: removal is permanent — no registry entry is left behind."""
    await client.entity("t", "sensor", "T")
    entity_id = entity_id_for(hass, "sensor", "t")
    await client.ok("remove", unique_id="t")
    assert entity_id_for(hass, "sensor", "t") is None
    assert hass.states.get(entity_id) is None


async def test_remove_entity_not_live_deletes_registry_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    bridge_client_factory,
) -> None:
    """An entity that is only in the registry (not created this run) is removed
    from the registry."""
    await client.entity("t", "sensor", "T")
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    client = await bridge_client_factory()  # reload closed the old socket
    await client.connect()
    await client.ok("remove", unique_id="t")
    assert entity_id_for(hass, "sensor", "t") is None


async def test_remove_device_exact_and_prefix(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    for dev in ("node", "node_a", "node_b", "nodex"):
        await client.entity(f"{dev}_t", "sensor", "T", device={"id": dev})

    await client.ok("remove", device_id="node")
    assert get_device(hass, "gw1:node") is None
    assert entity_id_for(hass, "sensor", "node_t") is None
    assert get_device(hass, "gw1:node_a") is not None

    await client.ok("remove", device_id="node", mode="prefix")
    assert get_device(hass, "gw1:node_a") is None
    assert get_device(hass, "gw1:node_b") is None
    assert entity_id_for(hass, "sensor", "node_a_t") is None
    assert get_device(hass, "gw1:nodex") is not None
    assert get_device(hass, "gw1") is not None

    # A removed sub-device redeclared later comes back online.
    await client.entity("node_a_t", "sensor", "T", device={"id": "node_a"})
    assert hass.states.get(entity_id_for(hass, "sensor", "node_a_t")).state != (
        STATE_UNAVAILABLE
    )


async def test_remove_whole_gateway(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    await client.entity("t", "sensor", "T", device={"id": "probe"})
    await client.entity("g", "switch", "G")
    await client.ok("remove")

    assert get_device(hass, "gw1") is None
    assert get_device(hass, "gw1:probe") is None
    assert entity_id_for(hass, "sensor", "t") is None
    assert entity_id_for(hass, "switch", "g") is None
    assert not any(
        s.data.get("gateway_id") == "gw1" for s in init_integration.subentries.values()
    )
    # The integration's own diagnostic sensor survives.
    assert er.async_get(hass).async_get_entity_id(
        "sensor", "ws_bridge", f"{init_integration.entry_id}_connected_clients"
    )


# ── sync (§3.5) ──────────────────────────────────────────────────────────────
async def test_sync_removes_only_undeclared(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1")
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2")
    for uid in ("a", "b", "c"):
        await gw1.entity(uid, "sensor", uid)
    await gw2.entity("b", "sensor", "b")
    await gw1.state("a", 1)
    a_id = entity_id_for(hass, "sensor", "a")
    a_entry_id = er.async_get(hass).async_get(a_id).id

    assert await gw1.ok("sync", unique_ids=["a", "c", "not_yet_created"]) == {
        "removed": ["b"]
    }
    assert not entity_is_live(hass, "sensor", "b")
    # Survivors untouched (same registry entry, same state).
    assert er.async_get(hass).async_get(a_id).id == a_entry_id
    assert hass.states.get(a_id).state == "1"
    assert entity_is_live(hass, "sensor", "c")
    # Other gateways are never reconciled.
    assert entity_is_live(hass, "sensor", "b", "gw2")
    # The integration's diagnostic sensor is never part of a gateway's list.
    assert er.async_get(hass).async_get_entity_id(
        "sensor", "ws_bridge", f"{gw1.entry.entry_id}_connected_clients"
    )


async def test_sync_deletes_registry_entry_and_is_idempotent(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("a", "sensor", "A")
    await client.entity("b", "sensor", "B")
    assert await client.ok("sync", unique_ids=["a"]) == {"removed": ["b"]}
    assert entity_id_for(hass, "sensor", "b") is None
    # Second symptom of the same bug: the entity is reported removed again.
    assert await client.ok("sync", unique_ids=["a"]) == {"removed": []}


async def test_sync_noop_and_keeps_gateway_device(
    hass: HomeAssistant, hass_storage: dict, client: BridgeClient
) -> None:
    await client.entity("t", "sensor", "T", device={"id": "probe"})
    await client.entity("keep", "sensor", "K", device={"id": "other"})
    assert await client.ok("sync", unique_ids=["t", "keep"]) == {"removed": []}
    # A no-op sync does not write the Store.
    assert f"ws_bridge.{client.entry.entry_id}.states" not in hass_storage
    assert await client.ok("sync", unique_ids=["keep"]) == {"removed": ["t"]}
    assert not entity_is_live(hass, "sensor", "t")
    assert entity_is_live(hass, "sensor", "keep")
    assert get_device(hass, "gw1:other") is not None
    assert get_device(hass, "gw1") is not None


async def test_sync_prunes_sub_devices_left_empty(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """PROTOCOL §3.5: sub-devices left with no entities are removed."""
    await client.entity("t", "sensor", "T", device={"id": "probe"})
    await client.entity("keep", "sensor", "K", device={"id": "other"})
    assert await client.ok("sync", unique_ids=["keep"]) == {"removed": ["t"]}
    assert get_device(hass, "gw1:probe") is None
    assert get_device(hass, "gw1:other") is not None


async def test_sync_reconciles_restored_keep_last_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    """Entities recreated at startup from stored keep_last declarations are also
    reconciled, so stale ones do not live forever."""
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("a", "sensor", "A")
    await gw.entity("gone", "sensor", "Gone")
    await gw.close()
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert entity_is_live(hass, "sensor", "gone")

    again = await bridge_client_factory()
    await again.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    assert await again.ok("sync", unique_ids=["a"]) == {"removed": ["gone"]}
    assert not entity_is_live(hass, "sensor", "gone")

    # Not resurrected by a later restart either.
    await again.close()
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert not entity_is_live(hass, "sensor", "gone")
    assert entity_is_live(hass, "sensor", "a")


async def test_sync_rejects_empty_list(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("a", "sensor", "A")
    msg = await client.send("sync", unique_ids=[])
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"
    assert entity_id_for(hass, "sensor", "a") is not None


# ── device registry: via_device_id ─────────────────────────────────────────
async def test_sub_device_created_when_gateway_device_missing(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """If the gateway device was deleted, sub-devices are still created (no via)."""
    gateway = get_device(hass, "gw1")
    dr.async_get(hass).async_remove_device(gateway.id)
    await hass.async_block_till_done()
    await client.entity("t", "sensor", "T", device={"id": "probe"})
    sub = get_device(hass, "gw1:probe")
    assert sub is not None
    assert sub.via_device_id is None


# ── token owner allowlist ───────────────────────────────────────────────────
GUARDED_COMMANDS = [
    ("connect", {"gateway_id": "gw2"}),
    ("entity", {"unique_id": "s1", "platform": "sensor", "name": "S"}),
    ("state", {"states": [{"unique_id": "s1", "value": 1}]}),
    ("availability", {"device_id": "d1", "online": True}),
    ("remove", {"unique_id": "s1"}),
    ("sync", {"unique_ids": ["s1"]}),
]


@pytest.mark.parametrize(("command", "payload"), GUARDED_COMMANDS)
async def test_commands_rejected_when_admin_not_listed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    bridge_client_factory,
    command: str,
    payload: dict,
) -> None:
    """A non-empty allowlist is exclusive: even an admin must be listed."""
    hass.config_entries.async_update_entry(
        init_integration, options={CONF_ALLOWED_USER_IDS: ["someone-else"]}
    )
    ws = await bridge_client_factory()
    msg = await ws.send(command, **payload)
    assert not msg["success"]
    assert msg["error"]["code"] == "not_allowed"


@pytest.mark.parametrize(("command", "payload"), GUARDED_COMMANDS)
async def test_empty_allowlist_rejects_non_admin(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client,
    hass_read_only_access_token: str,
    command: str,
    payload: dict,
) -> None:
    ws = BridgeClient(
        hass, init_integration, await hass_ws_client(hass, hass_read_only_access_token)
    )
    msg = await ws.send(command, **payload)
    assert not msg["success"]
    assert msg["error"]["code"] == "not_allowed"


async def test_rejected_connect_creates_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client,
    hass_read_only_access_token: str,
) -> None:
    ws = BridgeClient(
        hass, init_integration, await hass_ws_client(hass, hass_read_only_access_token)
    )
    msg = await ws.send("connect", gateway_id="gw1", name="GW1")
    assert msg["error"]["code"] == "not_allowed"
    assert get_device(hass, "gw1") is None
    assert not init_integration.subentries


async def test_empty_allowlist_allows_admin(client: BridgeClient) -> None:
    await client.entity("s1", "sensor")


async def test_listed_non_admin_can_connect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_ws_client,
    hass_read_only_user,
    hass_read_only_access_token: str,
) -> None:
    hass.config_entries.async_update_entry(
        init_integration, options={CONF_ALLOWED_USER_IDS: [hass_read_only_user.id]}
    )
    ws = BridgeClient(
        hass, init_integration, await hass_ws_client(hass, hass_read_only_access_token)
    )
    await ws.connect()
    await ws.entity("s1", "sensor")
    assert get_device(hass, "gw1") is not None


async def test_rejected_commands_do_not_change_state(
    hass: HomeAssistant, client: BridgeClient, bridge_client_factory
) -> None:
    await client.entity("s1", "sensor")
    await client.state("s1", 1)
    hass.config_entries.async_update_entry(
        client.entry, options={CONF_ALLOWED_USER_IDS: ["someone-else"]}
    )
    await hass.async_block_till_done()
    ws = await bridge_client_factory()
    for command, payload in GUARDED_COMMANDS[2:]:
        msg = await ws.send(command, **payload)
        assert msg["error"]["code"] == "not_allowed"
    assert entity_id_for(hass, "sensor", "s1") is not None


async def test_connection_closed_when_owner_removed_from_allowlist(
    hass: HomeAssistant, client: BridgeClient, hass_admin_user
) -> None:
    hass.config_entries.async_update_entry(
        client.entry, options={CONF_ALLOWED_USER_IDS: ["someone-else"]}
    )
    await hass.async_block_till_done()
    bridge = hass.data[DOMAIN][client.entry.entry_id]
    for _ in range(200):
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
        if not bridge._conn_client:
            break
    assert not bridge._conn_client


async def test_connection_closed_after_command_rejected_for_lost_admin(
    hass: HomeAssistant, client: BridgeClient, hass_admin_user
) -> None:
    """Losing admin rights (no options change) closes the gateway on its next command."""
    await hass.auth.async_update_user(hass_admin_user, group_ids=["system-read-only"])
    msg = await client.send("state", states=[{"unique_id": "s1", "value": 1}])
    assert msg["error"]["code"] == "not_allowed"
    bridge = hass.data[DOMAIN][client.entry.entry_id]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    for _ in range(200):
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
        if not bridge._conn_client:
            break
    assert not bridge._conn_client
