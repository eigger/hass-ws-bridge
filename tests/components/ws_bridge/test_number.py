"""number platform."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_number_attributes_state_and_set_value(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "target",
        "number",
        "Target",
        min=10,
        max=30,
        step=0.5,
        unit_of_measurement="°C",
    )
    entity_id = entity_id_for(hass, "number", "target")
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["min"] == 10
    assert state.attributes["max"] == 30
    assert state.attributes["step"] == 0.5
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["icon"] == "mdi:numeric"

    await client.state("target", 21)
    assert hass.states.get(entity_id).state == "21"
    await client.state("target", "Unknown")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await call_service(hass, "number", "set_value", entity_id, value=26.5)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "target",
        "action": "set_value",
        "value": 26.5,
    }
    assert hass.states.get(entity_id).state == "26.5"


async def test_number_redeclare_updates_range(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("lvl", "number", "Level", min=0, max=10)
    await client.entity("lvl", "number", "Level", min=0, max=100, step=5)
    state = hass.states.get(entity_id_for(hass, "number", "lvl"))
    assert state.attributes["max"] == 100
    assert state.attributes["step"] == 5
