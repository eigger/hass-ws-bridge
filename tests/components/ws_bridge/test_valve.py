"""valve platform."""

import pytest
from homeassistant.components.valve import ValveEntityFeature, ValveState
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BridgeClient, call_service, entity_id_for, restart_without_client


@pytest.mark.parametrize(
    ("extra", "has", "has_not"),
    [
        ({}, [ValveEntityFeature.OPEN, ValveEntityFeature.SET_POSITION], []),
        (
            {"reports_position": False},
            [ValveEntityFeature.OPEN],
            [ValveEntityFeature.SET_POSITION],
        ),
        (
            {"features": ["open", "set_position"], "reports_position": False},
            [ValveEntityFeature.OPEN],
            [ValveEntityFeature.SET_POSITION],
        ),
        (
            {"features": ["open", "nope"]},
            [ValveEntityFeature.OPEN],
            [ValveEntityFeature.CLOSE],
        ),
    ],
)
async def test_valve_features(
    hass: HomeAssistant, client: BridgeClient, extra, has, has_not
) -> None:
    await client.entity("v", "valve", "Valve", **extra)
    flags = hass.states.get(entity_id_for(hass, "valve", "v")).attributes[
        "supported_features"
    ]
    for flag in has:
        assert flags & flag
    for flag in has_not:
        assert not flags & flag


async def test_valve_position_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("v", "valve", "Valve")
    entity_id = entity_id_for(hass, "valve", "v")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
    await client.state("v", {"position": 0})
    assert hass.states.get(entity_id).state == ValveState.CLOSED
    await client.state("v", {"position": 70})
    state = hass.states.get(entity_id)
    assert state.state == ValveState.OPEN
    assert state.attributes["current_position"] == 70

    await call_service(hass, "valve", "set_valve_position", entity_id, position=20)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "v",
        "action": "set_valve_position",
        "params": {"position": 20},
    }
    assert hass.states.get(entity_id).attributes["current_position"] == 20


async def test_valve_without_position_uses_state(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("v", "valve", "Valve", reports_position=False)
    entity_id = entity_id_for(hass, "valve", "v")
    await client.state("v", {"state": "closed", "position": 50})
    assert hass.states.get(entity_id).state == ValveState.CLOSED
    await client.state("v", {"state": "open"})
    assert hass.states.get(entity_id).state == ValveState.OPEN


async def test_valve_opening_is_not_persisted(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("v", "valve", "Valve", reports_position=False)
    await gw.state("v", {"state": "closed"})
    entity_id = entity_id_for(hass, "valve", "v")

    await call_service(hass, "valve", "open_valve", entity_id)
    assert (await gw.next_command())["action"] == "open_valve"
    assert hass.states.get(entity_id).state == ValveState.OPENING

    await restart_without_client(hass, init_integration, gw)
    assert hass.states.get(entity_id).state == ValveState.CLOSED
