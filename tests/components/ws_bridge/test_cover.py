"""cover platform."""

import pytest
from homeassistant.components.cover import CoverEntityFeature, CoverState
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BridgeClient, call_service, entity_id_for, restart_without_client


async def test_cover_features(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("default", "cover", "Default")
    await client.entity(
        "custom", "cover", "Custom", features=["open", "set_position", "nope"]
    )
    await client.entity("bogus", "cover", "Bogus", features=["nope"])
    default = hass.states.get(entity_id_for(hass, "cover", "default"))
    flags = default.attributes["supported_features"]
    assert flags & CoverEntityFeature.OPEN
    assert flags & CoverEntityFeature.CLOSE
    assert flags & CoverEntityFeature.STOP
    custom = hass.states.get(entity_id_for(hass, "cover", "custom"))
    flags = custom.attributes["supported_features"]
    assert flags & CoverEntityFeature.OPEN
    assert flags & CoverEntityFeature.SET_POSITION
    assert not flags & CoverEntityFeature.CLOSE
    bogus = hass.states.get(entity_id_for(hass, "cover", "bogus"))
    assert (
        bogus.attributes["supported_features"]
        == (default.attributes["supported_features"])
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, STATE_UNKNOWN),  # nothing known → unknown, not "open"
        ({"position": 0}, CoverState.CLOSED),
        ({"position": 50}, CoverState.OPEN),
        ({"state": "closed"}, CoverState.CLOSED),
        ({"state": "open"}, CoverState.OPEN),
        # opening/closing win over position.
        ({"state": "opening", "position": 0}, CoverState.OPENING),
        ({"state": "closing", "position": 100}, CoverState.CLOSING),
        ({"position": "bad"}, STATE_UNKNOWN),
    ],
)
async def test_cover_state(
    hass: HomeAssistant, client: BridgeClient, value, expected
) -> None:
    await client.entity(
        "blind", "cover", "Blind", features=["open", "close", "set_position"]
    )
    await client.state("blind", value)
    assert hass.states.get(entity_id_for(hass, "cover", "blind")).state == expected


async def test_cover_position_attributes_clamped(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "blind", "cover", "Blind", features=["set_position", "set_tilt_position"]
    )
    await client.state("blind", {"position": 150, "tilt_position": -3})
    state = hass.states.get(entity_id_for(hass, "cover", "blind"))
    assert state.attributes["current_position"] == 100
    assert state.attributes["current_tilt_position"] == 0


async def test_cover_commands(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity(
        "blind", "cover", "Blind", features=["open", "close", "stop", "set_position"]
    )
    entity_id = entity_id_for(hass, "cover", "blind")
    await client.state("blind", {"state": "closed", "position": 0})

    await call_service(hass, "cover", "open_cover", entity_id)
    assert (await client.next_command())["action"] == "open_cover"
    assert hass.states.get(entity_id).state == CoverState.OPENING

    await call_service(hass, "cover", "stop_cover", entity_id)
    assert (await client.next_command())["action"] == "stop_cover"

    await call_service(hass, "cover", "set_cover_position", entity_id, position=40)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "blind",
        "action": "set_cover_position",
        "params": {"position": 40},
    }
    assert hass.states.get(entity_id).attributes["current_position"] == 40


async def test_cover_opening_is_not_persisted(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    """opening is optimistic only — persisting it would stick after restart."""
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("blind", "cover", "Blind", features=["open", "close"])
    await gw.state("blind", {"state": "closed"})
    entity_id = entity_id_for(hass, "cover", "blind")

    await call_service(hass, "cover", "open_cover", entity_id)
    assert hass.states.get(entity_id).state == CoverState.OPENING

    await restart_without_client(hass, init_integration, gw)
    assert hass.states.get(entity_id).state == CoverState.CLOSED
