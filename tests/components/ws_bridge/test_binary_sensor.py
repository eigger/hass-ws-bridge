"""binary_sensor platform."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, entity_id_for


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", STATE_ON),
        ("TRUE", STATE_ON),
        ("on", STATE_ON),
        ("yes", STATE_ON),
        # The truthy vocabulary is frozen: "open" is not on (no list expansion).
        ("open", STATE_OFF),
        ("locked", STATE_OFF),
        ("0", STATE_OFF),
        (1, STATE_ON),
        (0, STATE_OFF),
        (True, STATE_ON),
        (False, STATE_OFF),
        ("unknown", STATE_UNKNOWN),
        (None, STATE_UNKNOWN),
    ],
)
async def test_binary_sensor_value_parsing(
    hass: HomeAssistant, client: BridgeClient, value, expected
) -> None:
    await client.entity("door", "binary_sensor", "Door", device_class="door")
    entity_id = entity_id_for(hass, "binary_sensor", "door")
    await client.state("door", value)
    state = hass.states.get(entity_id)
    assert state.state == expected
    assert state.attributes["device_class"] == "door"


async def test_binary_sensor_default_icon(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("flag", "binary_sensor", "Flag")
    state = hass.states.get(entity_id_for(hass, "binary_sensor", "flag"))
    assert state.attributes["icon"] == "mdi:checkbox-blank-circle-outline"
    assert state.state == STATE_UNKNOWN
