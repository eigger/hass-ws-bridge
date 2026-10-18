"""switch platform: state + command relay."""

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_switch_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("relay", "switch", "Relay", device_class="outlet")
    entity_id = entity_id_for(hass, "switch", "relay")
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["device_class"] == "outlet"

    await client.state("relay", "on")
    assert hass.states.get(entity_id).state == STATE_ON
    await client.state("relay", False)
    assert hass.states.get(entity_id).state == STATE_OFF

    await call_service(hass, "switch", "turn_on", entity_id)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "relay",
        "action": "turn_on",
    }
    assert hass.states.get(entity_id).state == STATE_ON  # optimistic

    await call_service(hass, "switch", "turn_off", entity_id)
    assert (await client.next_command())["action"] == "turn_off"
    assert hass.states.get(entity_id).state == STATE_OFF
