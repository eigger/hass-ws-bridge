"""Per-gateway diagnostic entities: connectivity and control connection count."""

from collections.abc import Awaitable, Callable

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.const import (
    CONTROL_CONNECTIONS_KEY,
    DOMAIN,
    GATEWAY_CONNECTED_KEY,
)

from .conftest import BridgeClient, entity_id_for, get_device, restart_without_client

Factory = Callable[[], Awaitable[BridgeClient]]


def _diag_id(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    domain: str,
    key: str,
    gateway_id: str = "gw1",
) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_gateway_{gateway_id}_{key}"
    )


def _state(
    hass: HomeAssistant, entry: MockConfigEntry, gateway_id: str = "gw1"
) -> tuple[str | None, str | None]:
    connected = _diag_id(
        hass, entry, "binary_sensor", GATEWAY_CONNECTED_KEY, gateway_id
    )
    count = _diag_id(hass, entry, "sensor", CONTROL_CONNECTIONS_KEY, gateway_id)
    return (
        hass.states.get(connected).state if connected else None,
        hass.states.get(count).state if count else None,
    )


async def test_connect_creates_diagnostic_entities_on_gateway_device(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    assert _state(hass, init_integration) == (STATE_ON, "1")

    registry = er.async_get(hass)
    device = get_device(hass, "gw1")
    assert device is not None
    assert device.serial_number == "gw1"
    for domain, key in (
        ("binary_sensor", GATEWAY_CONNECTED_KEY),
        ("sensor", CONTROL_CONNECTIONS_KEY),
    ):
        entry = registry.async_get(_diag_id(hass, init_integration, domain, key))
        assert entry.device_id == device.id
        assert entry.entity_category == er.EntityCategory.DIAGNOSTIC
    connected = hass.states.get(
        _diag_id(hass, init_integration, "binary_sensor", GATEWAY_CONNECTED_KEY)
    )
    assert connected.attributes["device_class"] == BinarySensorDeviceClass.CONNECTIVITY


async def test_disconnect_turns_off_but_stays_available(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    await client.entity("temp", "sensor", "Temp")
    await client.close()

    assert _state(hass, init_integration) == (STATE_OFF, "0")
    # Client entities go unavailable; the diagnostics must keep reporting.
    assert hass.states.get(entity_id_for(hass, "sensor", "temp")).state == "unavailable"


async def test_diagnostics_survive_restart_without_client(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    await restart_without_client(hass, init_integration, client)

    assert _state(hass, init_integration) == (STATE_OFF, "0")


async def test_second_control_connection_is_counted(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    bridge_client_factory: Factory,
) -> None:
    second = await bridge_client_factory()
    await second.connect("gw1", "GW1")
    assert _state(hass, init_integration) == (STATE_ON, "2")

    await second.close()
    assert _state(hass, init_integration) == (STATE_ON, "1")


async def test_socket_switching_gateway_updates_previous_gateway(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    await client.connect("gw2", "GW2")

    assert _state(hass, init_integration, "gw1") == (STATE_OFF, "0")
    assert _state(hass, init_integration, "gw2") == (STATE_ON, "1")


async def test_removing_gateway_removes_diagnostics_and_reconnect_recreates(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    bridge_client_factory: Factory,
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1")
    sub = next(s for s in init_integration.subentries.values() if s.unique_id == "gw1")
    assert hass.config_entries.async_remove_subentry(init_integration, sub.subentry_id)
    await hass.async_block_till_done()

    assert _state(hass, init_integration) == (None, None)

    await gw.close()
    again = await bridge_client_factory()
    await again.connect("gw1", "GW1")
    assert _state(hass, init_integration) == (STATE_ON, "1")


async def test_client_prefix_remove_never_touches_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    await client.entity("temp", "sensor", "Temp")
    # A prefix equal to the entry id would match the bridge-owned unique ids
    # ("<entry_id>_gateway_...") if they were considered at all.
    await client.ok("remove", unique_id=init_integration.entry_id, mode="prefix")

    assert _state(hass, init_integration) == (STATE_ON, "1")
    assert entity_id_for(hass, "sensor", "temp") is not None


async def test_prefix_remove_is_limited_to_the_calling_gateway(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    bridge_client_factory: Factory,
) -> None:
    other = await bridge_client_factory()
    await other.connect("gw2", "GW2")
    await other.entity("temp", "sensor", "Temp")

    # gw1 asks to remove a prefix that is gw2's gateway id.
    await client.ok("remove", unique_id="gw2", mode="prefix")

    assert entity_id_for(hass, "sensor", "temp", "gw2") is not None
    assert _state(hass, init_integration, "gw2") == (STATE_ON, "1")


async def test_diagnostics_are_recreated_when_removed_from_registry(
    hass: HomeAssistant, init_integration: MockConfigEntry, client: BridgeClient
) -> None:
    """Liveness is judged from the registry, not only from remove_gateway."""
    registry = er.async_get(hass)
    for domain, key in (
        ("binary_sensor", GATEWAY_CONNECTED_KEY),
        ("sensor", CONTROL_CONNECTIONS_KEY),
    ):
        registry.async_remove(_diag_id(hass, init_integration, domain, key))
    await hass.async_block_till_done()
    assert _state(hass, init_integration) == (None, None)

    await client.connect("gw1", "GW1")

    assert _state(hass, init_integration) == (STATE_ON, "1")
