"""text platform (writable string; distinct from read-only text_sensor)."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_text_attributes_state_and_set_value(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "ssid", "text", "SSID", min=1, max=32, pattern="[a-z]+", mode="password"
    )
    entity_id = entity_id_for(hass, "text", "ssid")
    # Registered in the text domain, not as a sensor.
    assert entity_id.startswith("text.")
    assert entity_id_for(hass, "sensor", "ssid") is None
    state = hass.states.get(entity_id)
    assert state.attributes["min"] == 1
    assert state.attributes["max"] == 32
    assert state.attributes["pattern"] == "[a-z]+"
    assert state.attributes["mode"] == "password"
    assert state.state == STATE_UNKNOWN

    await client.state("ssid", "home")
    assert hass.states.get(entity_id).state == "home"

    await call_service(hass, "text", "set_value", entity_id, value="office")
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "ssid",
        "action": "set_value",
        "value": "office",
    }
    assert hass.states.get(entity_id).state == "office"


async def test_text_defaults(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("note", "text", "Note", max=None)
    state = hass.states.get(entity_id_for(hass, "text", "note"))
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == 255
    assert state.attributes["mode"] == "text"
    await client.state("note", 123)  # non-string values are stringified
    assert hass.states.get(entity_id_for(hass, "text", "note")).state == "123"
