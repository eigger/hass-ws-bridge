"""Config entry setup / unload / reload / persistence through the real entry manager."""

from datetime import timedelta

from aiohttp import WSMsgType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ws_bridge import PLATFORMS, SUBENTRY_SNAPSHOTS
from custom_components.ws_bridge.bridge import SAVE_DELAY
from custom_components.ws_bridge.const import (
    ALL_PLATFORMS,
    DOMAIN,
    PLATFORM_TEXT_SENSOR,
    SUBENTRY_TYPE_GATEWAY,
)

from .conftest import BridgeClient, entity_id_for, get_device


def _store_key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}.{entry.entry_id}.states"


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_forwards_every_declared_platform(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Every protocol platform is loaded (text_sensor rides on sensor)."""
    forwarded = {str(p) for p in PLATFORMS}
    assert set(ALL_PLATFORMS) - {PLATFORM_TEXT_SENSOR} <= forwarded
    for platform in PLATFORMS:
        assert platform in hass.config.components
    assert Platform.SENSOR in PLATFORMS
    assert init_integration.entry_id in hass.data[DOMAIN]


async def test_unload_cleans_up_and_marks_entities_unavailable(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    client: BridgeClient,
) -> None:
    await client.entity("temp", "sensor", "Temp")
    await client.state("temp", 3)
    entity_id = entity_id_for(hass, "sensor", "temp")
    assert hass.states.get(entity_id).state == "3"

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.data[DOMAIN] == {}
    assert SUBENTRY_SNAPSHOTS not in hass.data
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    # Pending debounced save was flushed synchronously on unload.
    stored = hass_storage[_store_key(init_integration)]["data"]
    assert stored["states"] == {"gw1__temp": 3}


async def test_debounced_save_writes_after_delay(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    client: BridgeClient,
) -> None:
    await client.entity("temp", "sensor", "Temp")
    await client.state("temp", 1)
    assert _store_key(init_integration) not in hass_storage

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()
    assert hass_storage[_store_key(init_integration)]["data"]["states"] == {
        "gw1__temp": 1
    }


async def test_reload_restores_last_state_when_client_redeclares(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    bridge_client_factory,
) -> None:
    """After a restart the persisted value is shown as soon as the entity is
    redeclared, before the client pushes a fresh state."""
    await client.entity("temp", "sensor", "Temp")
    await client.state("temp", 42)
    entity_id = entity_id_for(hass, "sensor", "temp")

    await _reload(hass, init_integration)
    # Default gateways (no keep_last) are not recreated without the client.
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    assert hass_storage[_store_key(init_integration)]["data"]["entities"] == {}

    # Unloading closed the old socket; the client reconnects on a new one.
    client = await bridge_client_factory()
    await client.connect()
    await client.entity("temp", "sensor", "Temp")
    assert entity_id_for(hass, "sensor", "temp") == entity_id
    assert hass.states.get(entity_id).state == "42"


async def test_reload_recreates_keep_last_entities_without_client(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    bridge_client_factory,
) -> None:
    keep = await bridge_client_factory()
    await keep.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await keep.entity("temp", "sensor", "Temp", device={"id": "room", "name": "Room"})
    await keep.state("temp", 7)
    plain = await bridge_client_factory()
    await plain.connect("gw2", "GW2")
    await plain.entity("temp", "sensor", "Temp")
    await plain.state("temp", 8)
    keep_id = entity_id_for(hass, "sensor", "temp", "gw1")
    plain_id = entity_id_for(hass, "sensor", "temp", "gw2")

    await keep.close()
    await plain.close()
    assert hass.states.get(keep_id).state == "7"  # kept on disconnect
    assert hass.states.get(plain_id).state == STATE_UNAVAILABLE

    await _reload(hass, init_integration)
    stored = hass_storage[_store_key(init_integration)]["data"]
    # Only keep_last gateways persist declarations, without registry ids.
    assert set(stored["entities"]) == {"gw1__temp"}
    assert "via_device_id" not in stored["entities"]["gw1__temp"]["_device"]
    assert "via_device" not in stored["entities"]["gw1__temp"]["_device"]
    assert stored["keep_last"] == {"gw1": True, "gw2": False}

    # Recreated at startup with last value and available, client still offline.
    assert hass.states.get(keep_id).state == "7"
    assert hass.states.get(plain_id).state == STATE_UNAVAILABLE


async def test_turning_keep_last_off_purges_stored_declarations(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    bridge_client_factory,
) -> None:
    """Reconnecting with keep_last off drops that gateway's stored declarations
    (states are kept), so storage does not keep growing; others are untouched."""
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw1.entity("a", "sensor", "A")
    await gw1.state("a", 1)
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2", keep_last_state_on_disconnect=True)
    await gw2.entity("b", "sensor", "B")

    await gw1.connect("gw1", "GW1", keep_last_state_on_disconnect=False)
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    data = hass_storage[_store_key(init_integration)]["data"]
    assert set(data["entities"]) == {"gw2__b"}
    assert data["states"]["gw1__a"] == 1
    assert data["keep_last"] == {"gw1": False, "gw2": True}

    # And gw1's entity is no longer recreated at startup without its client.
    assert await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id_for(hass, "sensor", "a")).state == (
        STATE_UNAVAILABLE
    )
    assert hass.states.get(entity_id_for(hass, "sensor", "b", "gw2")).state != (
        STATE_UNAVAILABLE
    )


async def test_setup_prunes_orphaned_store_entries(
    hass: HomeAssistant, hass_storage: dict, config_entry: MockConfigEntry
) -> None:
    """Store rows without an entity registry entry are dropped at load time
    (states and declarations), so deleted entities never come back."""
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, "gw1__kept", config_entry=config_entry
    )
    device = {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True, "name": "GW1"}
    hass_storage[_store_key(config_entry)] = {
        "version": 1,
        "minor_version": 1,
        "key": _store_key(config_entry),
        "data": {
            "states": {"gw1__kept": 5, "gw1__gone": 6},
            "entities": {
                uid: {
                    "unique_id": uid,
                    "platform": "sensor",
                    "name": uid,
                    "_device": device,
                }
                for uid in ("gw1__kept", "gw1__gone")
            },
            "keep_last": {"gw1": True},
        },
    }

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    data = hass_storage[_store_key(config_entry)]["data"]
    assert data["states"] == {"gw1__kept": 5}
    assert set(data["entities"]) == {"gw1__kept"}
    entity_id = entity_id_for(hass, "sensor", "kept")
    assert hass.states.get(entity_id).state == "5"
    assert entity_id_for(hass, "sensor", "gone") is None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_connect_creates_gateway_subentry(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    named = await bridge_client_factory()
    await named.connect("gw1", "Living Room")
    unnamed = await bridge_client_factory()
    await unnamed.connect("gw2", None)

    subentries = {
        sub.data["gateway_id"]: sub for sub in init_integration.subentries.values()
    }
    assert set(subentries) == {"gw1", "gw2"}
    assert subentries["gw1"].subentry_type == SUBENTRY_TYPE_GATEWAY
    assert subentries["gw1"].unique_id == "gw1"
    assert subentries["gw1"].title == "Living Room"
    assert subentries["gw2"].title == "gw2"

    # Rename → the existing subentry is updated, no duplicate.
    await named.connect("gw1", "Kitchen")
    subs = [s for s in init_integration.subentries.values() if s.unique_id == "gw1"]
    assert len(subs) == 1
    assert subs[0].title == "Kitchen"
    assert subs[0].data == {"gateway_id": "gw1", "name": "Kitchen"}

    device = get_device(hass, "gw1")
    assert device.config_entry_id == init_integration.entry_id
    assert device.config_subentry_id == subs[0].subentry_id


async def test_subentry_removal_cleans_gateway(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    bridge_client_factory,
) -> None:
    gw1 = await bridge_client_factory()
    await gw1.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw1.entity("temp", "sensor", "Temp", device={"id": "room"})
    await gw1.entity("relay", "switch", "Relay")
    await gw1.state("temp", 1)
    gw2 = await bridge_client_factory()
    await gw2.connect("gw2", "GW2")
    await gw2.entity("temp", "sensor", "Temp")

    temp_id = entity_id_for(hass, "sensor", "temp")
    relay_id = entity_id_for(hass, "switch", "relay")
    sub = next(s for s in init_integration.subentries.values() if s.unique_id == "gw1")
    assert hass.config_entries.async_remove_subentry(init_integration, sub.subentry_id)
    await hass.async_block_till_done()

    assert get_device(hass, "gw1") is None
    assert get_device(hass, "gw1:room") is None
    assert entity_id_for(hass, "sensor", "temp") is None
    assert entity_id_for(hass, "switch", "relay") is None
    assert hass.states.get(temp_id) is None
    assert hass.states.get(relay_id) is None
    # Other gateway untouched.
    assert entity_id_for(hass, "sensor", "temp", "gw2") is not None
    assert get_device(hass, "gw2") is not None

    data = hass_storage[_store_key(init_integration)]["data"]
    assert not any(uid.startswith("gw1__") for uid in data["states"])
    assert not any(uid.startswith("gw1__") for uid in data["entities"])
    assert "gw1" not in data["keep_last"]
    assert hass.data[SUBENTRY_SNAPSHOTS][init_integration.entry_id] == {"gw2"}


async def test_commands_before_connect(
    hass: HomeAssistant, bridge_client_factory
) -> None:
    """Without ws_bridge/connect a connection owns no gateway."""
    anon = await bridge_client_factory()
    # entity/state/availability are accepted but ignored.
    await anon.entity("temp", "sensor", "Temp")
    await anon.state("temp", 1)
    await anon.availability("dev", False)
    assert entity_id_for(hass, "sensor", "temp") is None

    for type_, payload in (("remove", {}), ("sync", {"unique_ids": ["a"]})):
        msg = await anon.send(type_, **payload)
        assert not msg["success"]
        assert msg["error"]["code"] == "not_connected"


async def test_unload_closes_client_connections(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    caplog,
) -> None:
    """Desired behavior: unloading the entry drops client sockets quietly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert "Error closing client connection" not in caplog.text
    assert (await client.ws.receive(timeout=5)).type is WSMsgType.CLOSE
    assert client.ws.closed
