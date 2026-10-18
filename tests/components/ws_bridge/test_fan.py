"""fan platform."""

from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_fan_features(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("default", "fan", "Default")
    await client.entity("osc", "fan", "Osc", features=["oscillate", "ghost"])
    flags = hass.states.get(entity_id_for(hass, "fan", "default")).attributes[
        "supported_features"
    ]
    assert flags & FanEntityFeature.TURN_ON
    assert flags & FanEntityFeature.SET_SPEED
    flags = hass.states.get(entity_id_for(hass, "fan", "osc")).attributes[
        "supported_features"
    ]
    assert flags & FanEntityFeature.OSCILLATE
    assert not flags & FanEntityFeature.SET_SPEED


async def test_fan_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "fan",
        "fan",
        "Fan",
        features=["set_speed", "oscillate", "preset_mode", "turn_on", "turn_off"],
        preset_modes=["auto", "sleep"],
        speed_count=4,
    )
    entity_id = entity_id_for(hass, "fan", "fan")
    await client.state("fan", {"state": "on", "percentage": 40, "oscillating": "yes"})
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["percentage"] == 40
    assert state.attributes["oscillating"] is True
    assert state.attributes["preset_modes"] == ["auto", "sleep"]
    assert state.attributes["percentage_step"] == 25

    await call_service(hass, "fan", "set_percentage", entity_id, percentage=0)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "fan",
        "action": "set_percentage",
        "params": {"percentage": 0},
    }
    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF  # 0 % turns off
    assert state.attributes["percentage"] == 0

    await call_service(hass, "fan", "turn_on", entity_id, percentage=75)
    assert (await client.next_command())["params"] == {"percentage": 75}
    assert hass.states.get(entity_id).state == STATE_ON

    await call_service(hass, "fan", "oscillate", entity_id, oscillating=False)
    assert (await client.next_command())["params"] == {"oscillating": False}
    assert hass.states.get(entity_id).attributes["oscillating"] is False

    await call_service(hass, "fan", "set_preset_mode", entity_id, preset_mode="sleep")
    assert (await client.next_command())["params"] == {"preset_mode": "sleep"}
    assert hass.states.get(entity_id).attributes["preset_mode"] == "sleep"
