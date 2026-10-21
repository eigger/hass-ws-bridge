"""water_heater platform tests."""

from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_water_heater_features_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("plain", "water_heater", "Plain")
    plain = hass.states.get(entity_id_for(hass, "water_heater", "plain"))
    assert not (
        plain.attributes["supported_features"] & WaterHeaterEntityFeature.OPERATION_MODE
    )

    await client.entity(
        "wh",
        "water_heater",
        "WH",
        operation_list=["eco", "performance", "off"],
        temperature_unit="F",
        features=["target_temperature", "away_mode"],
    )
    entity_id = entity_id_for(hass, "water_heater", "wh")
    flags = hass.states.get(entity_id).attributes["supported_features"]
    assert flags & WaterHeaterEntityFeature.OPERATION_MODE
    assert flags & WaterHeaterEntityFeature.AWAY_MODE

    await client.state(
        "wh", {"state": "eco", "target_temperature": 122, "away_mode": "off"}
    )
    state = hass.states.get(entity_id)
    assert state.state == "eco"
    assert state.attributes["operation_mode"] == "eco"
    assert state.attributes["away_mode"] == "off"
    # Declared °F, test hass is metric: 122 °F → 50 °C.
    assert state.attributes["temperature"] == 50

    await call_service(
        hass,
        "water_heater",
        "set_operation_mode",
        entity_id,
        operation_mode="performance",
    )
    assert (await client.next_command())["params"] == {"operation_mode": "performance"}
    assert hass.states.get(entity_id).state == "performance"

    await call_service(hass, "water_heater", "set_away_mode", entity_id, away_mode=True)
    assert (await client.next_command())["params"] == {"away_mode": True}
    assert hass.states.get(entity_id).attributes["away_mode"] == "on"
