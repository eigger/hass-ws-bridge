"""button platform."""

from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_button_press_relays_command(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("reboot", "button", "Reboot", device_class="restart")
    entity_id = entity_id_for(hass, "button", "reboot")
    assert hass.states.get(entity_id).attributes["device_class"] == "restart"

    await call_service(hass, "button", "press", entity_id)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "reboot",
        "action": "press",
    }
    # HA records the press time as the button state.
    assert hass.states.get(entity_id).state not in ("unknown", "unavailable")
