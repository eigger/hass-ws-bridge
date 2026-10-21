"""humidifier platform tests."""

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierEntityFeature,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_humidifier_features(hass: HomeAssistant, client: BridgeClient) -> None:
    # "modes" feature needs available_modes; available_modes implies it.
    await client.entity("a", "humidifier", "A", features=["modes"])
    await client.entity("b", "humidifier", "B", available_modes=["auto"])
    a = hass.states.get(entity_id_for(hass, "humidifier", "a"))
    b = hass.states.get(entity_id_for(hass, "humidifier", "b"))
    assert not a.attributes["supported_features"] & HumidifierEntityFeature.MODES
    assert b.attributes["supported_features"] & HumidifierEntityFeature.MODES


async def test_humidifier_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "hum",
        "humidifier",
        "Hum",
        available_modes=["auto", "sleep"],
        features=["modes"],
        min_humidity=30,
        max_humidity=80,
    )
    entity_id = entity_id_for(hass, "humidifier", "hum")
    await client.state(
        "hum",
        {"state": "on", "target_humidity": 45, "mode": "auto", "action": "humidifying"},
    )
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["humidity"] == 45
    assert state.attributes["mode"] == "auto"
    assert state.attributes["action"] == HumidifierAction.HUMIDIFYING
    assert state.attributes["min_humidity"] == 30
    assert state.attributes["max_humidity"] == 80

    await call_service(hass, "humidifier", "set_humidity", entity_id, humidity=55)
    assert (await client.next_command())["params"] == {"humidity": 55}
    assert hass.states.get(entity_id).attributes["humidity"] == 55
    await call_service(hass, "humidifier", "set_mode", entity_id, mode="sleep")
    assert (await client.next_command())["params"] == {"mode": "sleep"}
    assert hass.states.get(entity_id).attributes["mode"] == "sleep"
    await call_service(hass, "humidifier", "turn_off", entity_id)
    assert (await client.next_command())["action"] == "turn_off"
    assert hass.states.get(entity_id).state == "off"
