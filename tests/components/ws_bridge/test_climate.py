"""climate platform."""

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


@pytest.mark.parametrize(
    ("extra", "modes", "has", "has_not"),
    [
        (
            {"hvac_modes": ["heat", "nope", "cool"]},
            [HVACMode.HEAT, HVACMode.COOL],
            [ClimateEntityFeature.TARGET_TEMPERATURE, ClimateEntityFeature.TURN_ON],
            [ClimateEntityFeature.TURN_OFF],  # no "off" mode → no TURN_OFF
        ),
        (
            {"hvac_modes": ["off", "heat"]},
            [HVACMode.OFF, HVACMode.HEAT],
            [ClimateEntityFeature.TURN_OFF, ClimateEntityFeature.TURN_ON],
            [],
        ),
        (
            {"hvac_modes": ["heat"], "features": ["turn_off", "target_temperature"]},
            [HVACMode.HEAT],
            [ClimateEntityFeature.TARGET_TEMPERATURE],
            [ClimateEntityFeature.TURN_OFF],
        ),
        (
            {"hvac_modes": ["nope"]},  # nothing valid → [off]
            [HVACMode.OFF],
            [ClimateEntityFeature.TURN_OFF],
            [],
        ),
    ],
)
async def test_climate_modes_and_features(
    hass: HomeAssistant, client: BridgeClient, extra, modes, has, has_not
) -> None:
    await client.entity("ac", "climate", "AC", **extra)
    state = hass.states.get(entity_id_for(hass, "climate", "ac"))
    assert state.attributes["hvac_modes"] == modes
    flags = state.attributes["supported_features"]
    for flag in has:
        assert flags & flag
    for flag in has_not:
        assert not flags & flag


async def test_climate_state_and_set_temperature(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "ac",
        "climate",
        "AC",
        hvac_modes=["off", "cool", "heat"],
        features=["target_temperature", "turn_on", "turn_off", "fan_mode"],
        fan_modes=["low", "high"],
        min_temp=16,
        max_temp=30,
        target_temp_step=0.5,
    )
    entity_id = entity_id_for(hass, "climate", "ac")
    await client.state(
        "ac",
        {
            "hvac_mode": "cool",
            "hvac_action": "cooling",
            "current_temperature": 28,
            "target_temperature": 24,
            "fan_mode": "low",
        },
    )
    state = hass.states.get(entity_id)
    assert state.state == HVACMode.COOL
    assert state.attributes["hvac_action"] == HVACAction.COOLING
    assert state.attributes["current_temperature"] == 28
    assert state.attributes[ATTR_TEMPERATURE] == 24
    assert state.attributes["fan_mode"] == "low"
    assert state.attributes["min_temp"] == 16
    assert state.attributes["max_temp"] == 30
    assert state.attributes["target_temp_step"] == 0.5

    await call_service(hass, "climate", "set_temperature", entity_id, temperature=22)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "ac",
        "action": "set_temperature",
        "params": {"temperature": 22},
    }
    assert hass.states.get(entity_id).attributes[ATTR_TEMPERATURE] == 22

    # A partial push (only current temperature) keeps the optimistic target.
    await client.state("ac", {"current_temperature": 27.5})
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.attributes["current_temperature"] == 27.5
    assert state.state == HVACMode.COOL

    await call_service(hass, "climate", "set_hvac_mode", entity_id, hvac_mode="heat")
    assert (await client.next_command())["params"] == {"hvac_mode": "heat"}
    assert hass.states.get(entity_id).state == HVACMode.HEAT

    await call_service(hass, "climate", "turn_off", entity_id)
    assert (await client.next_command())["action"] == "turn_off"
    assert hass.states.get(entity_id).state == HVACMode.OFF
    await call_service(hass, "climate", "turn_on", entity_id)
    assert (await client.next_command())["action"] == "turn_on"
    assert hass.states.get(entity_id).state == HVACMode.COOL  # first non-off mode


async def test_climate_fahrenheit_unit(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "ac", "climate", "AC", hvac_modes=["heat"], temperature_unit="F"
    )
    entity_id = entity_id_for(hass, "climate", "ac")
    await client.state("ac", {"hvac_mode": "heat", "target_temperature": 68})
    # Test hass uses metric → 68 °F shown as 20 °C.
    assert hass.states.get(entity_id).attributes[ATTR_TEMPERATURE] == 20
