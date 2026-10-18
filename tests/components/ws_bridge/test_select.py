"""select platform."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_select_options_state_and_command(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("mode", "select", "Mode", options=["eco", "comfort"])
    entity_id = entity_id_for(hass, "select", "mode")
    state = hass.states.get(entity_id)
    assert state.attributes["options"] == ["eco", "comfort"]
    assert state.state == STATE_UNKNOWN

    await client.state("mode", "eco")
    assert hass.states.get(entity_id).state == "eco"
    await client.state("mode", "unknown")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await call_service(hass, "select", "select_option", entity_id, option="comfort")
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "mode",
        "action": "select_option",
        "value": "comfort",
    }
    assert hass.states.get(entity_id).state == "comfort"

    await client.entity("mode", "select", "Mode", options=["eco", "comfort", "boost"])
    assert hass.states.get(entity_id).attributes["options"] == [
        "eco",
        "comfort",
        "boost",
    ]
