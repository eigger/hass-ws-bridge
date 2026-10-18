"""light platform: color modes, composite state merge, optimistic commands."""

import pytest
from homeassistant.components.light import ColorMode, LightEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        (None, [ColorMode.ONOFF]),
        (["rgb", "nope"], [ColorMode.RGB]),
        # ONOFF/BRIGHTNESS are exclusive with real color modes (HA rule).
        (["brightness", "rgb"], [ColorMode.RGB]),
        (["onoff", "brightness"], [ColorMode.BRIGHTNESS]),
    ],
)
async def test_light_supported_color_modes(
    hass: HomeAssistant, client: BridgeClient, declared, expected
) -> None:
    await client.entity("led", "light", "LED", supported_color_modes=declared)
    state = hass.states.get(entity_id_for(hass, "light", "led"))
    assert state.attributes["supported_color_modes"] == expected


async def test_light_features_and_effects(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "led",
        "light",
        "LED",
        features=["transition", "unknown"],
        effect_list=["rainbow"],
        supported_color_modes=["color_temp"],
        min_color_temp_kelvin=2000,
        max_color_temp_kelvin=6500,
    )
    state = hass.states.get(entity_id_for(hass, "light", "led"))
    flags = state.attributes["supported_features"]
    assert flags & LightEntityFeature.TRANSITION
    assert flags & LightEntityFeature.EFFECT
    assert state.attributes["effect_list"] == ["rainbow"]
    assert state.attributes["min_color_temp_kelvin"] == 2000
    assert state.attributes["max_color_temp_kelvin"] == 6500


async def test_light_infers_color_mode_and_merges_partial_state(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "led", "light", "LED", supported_color_modes=["rgb", "color_temp"]
    )
    entity_id = entity_id_for(hass, "light", "led")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await client.state("led", {"state": "on", "rgb_color": [255, 64, 0]})
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["color_mode"] == ColorMode.RGB
    assert state.attributes["rgb_color"] == (255, 64, 0)

    # dict + dict is a shallow merge: previous keys survive.
    await client.state("led", {"brightness": 50})
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 50
    assert state.attributes["rgb_color"] == (255, 64, 0)

    # Explicit color_mode wins when supported.
    await client.state("led", {"color_mode": "color_temp", "color_temp_kelvin": 3000})
    state = hass.states.get(entity_id)
    assert state.attributes["color_mode"] == ColorMode.COLOR_TEMP
    assert state.attributes["color_temp_kelvin"] == 3000

    # scalar replaces dict; dict then replaces scalar (no merge across types).
    await client.state("led", "off")
    assert hass.states.get(entity_id).state == STATE_OFF
    await client.state("led", {"brightness": 10})
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN  # no "state" key after replace
    assert state.attributes.get("rgb_color") is None


async def test_light_tolerates_bad_numbers(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """Parse failures must not raise, or every later update would be lost."""
    await client.entity(
        "led", "light", "LED", supported_color_modes=["rgb", "color_temp"]
    )
    entity_id = entity_id_for(hass, "light", "led")
    await client.state(
        "led",
        {
            "state": "on",
            "brightness": "abc",
            "color_temp_kelvin": "warm",
            "rgb_color": [1, "x", 3],
        },
    )
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] is None
    assert state.attributes["color_temp_kelvin"] is None
    assert state.attributes["rgb_color"] is None

    await client.state("led", {"brightness": 300})
    assert hass.states.get(entity_id).attributes["brightness"] == 255


async def test_light_commands_with_params_and_optimistic_state(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "led", "light", "LED", supported_color_modes=["rgb"], features=["transition"]
    )
    entity_id = entity_id_for(hass, "light", "led")
    await client.state("led", {"state": "off", "rgb_color": [1, 2, 3]})

    await call_service(
        hass, "light", "turn_on", entity_id, brightness=128, rgb_color=[10, 20, 30]
    )
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "led",
        "action": "turn_on",
        "params": {"brightness": 128, "rgb_color": [10, 20, 30]},
    }
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 128
    assert state.attributes["rgb_color"] == (10, 20, 30)

    # A partial push from the client must not revert the optimistic values.
    await client.state("led", {"effect": None})
    state = hass.states.get(entity_id)
    assert state.attributes["brightness"] == 128
    assert state.attributes["rgb_color"] == (10, 20, 30)

    await call_service(hass, "light", "turn_off", entity_id, transition=2)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "led",
        "action": "turn_off",
        "params": {"transition": 2},
    }
    assert hass.states.get(entity_id).state == STATE_OFF

    await call_service(hass, "light", "turn_on", entity_id)
    cmd = await client.next_command()
    assert "params" not in cmd  # empty params are omitted
