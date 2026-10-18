"""device_tracker platform (GPS source, object state value)."""

import pytest
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, entity_id_for

FAR = {"latitude": 37.5665, "longitude": 126.9780}


async def test_tracker_location_and_home_zone(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("car", "device_tracker", "Car")
    entity_id = entity_id_for(hass, "device_tracker", "car")
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["source_type"] == "gps"
    # HA picks the zone-based icon itself; no fixed default icon is forced.
    assert "icon" not in state.attributes

    await client.state("car", {**FAR, "gps_accuracy": 8})
    state = hass.states.get(entity_id)
    assert state.state == STATE_NOT_HOME
    assert state.attributes["latitude"] == 37.5665
    assert state.attributes["longitude"] == 126.9780
    assert state.attributes["gps_accuracy"] == 8

    await client.state(
        "car",
        {"latitude": hass.config.latitude, "longitude": hass.config.longitude},
    )
    assert hass.states.get(entity_id).state == STATE_HOME


async def test_tracker_accepts_numeric_strings(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("car", "device_tracker", "Car")
    await client.state("car", {"latitude": "37.5", "longitude": "127.0"})
    state = hass.states.get(entity_id_for(hass, "device_tracker", "car"))
    assert state.attributes["latitude"] == 37.5
    assert state.attributes["longitude"] == 127.0
    assert state.attributes["gps_accuracy"] == 0


@pytest.mark.parametrize(
    "value",
    [
        {"latitude": 37.5},  # half a coordinate is "unknown", not a wrong spot
        {"latitude": "N/A", "longitude": 127.0},
        {"latitude": True, "longitude": 127.0},
        "unknown",
        37.5,
    ],
)
async def test_tracker_rejects_partial_or_invalid(
    hass: HomeAssistant, client: BridgeClient, value
) -> None:
    await client.entity("car", "device_tracker", "Car")
    await client.state("car", value)
    state = hass.states.get(entity_id_for(hass, "device_tracker", "car"))
    assert state.state == STATE_UNKNOWN
    assert "latitude" not in state.attributes


async def test_tracker_null_after_merge_clears_location(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """Shallow merge + JSON null lets a client report GPS loss."""
    await client.entity("car", "device_tracker", "Car")
    entity_id = entity_id_for(hass, "device_tracker", "car")
    await client.state("car", {**FAR, "gps_accuracy": 8})
    assert hass.states.get(entity_id).state == STATE_NOT_HOME

    await client.state("car", {"gps_accuracy": 20})  # merge keeps coordinates
    state = hass.states.get(entity_id)
    assert state.attributes["latitude"] == 37.5665
    assert state.attributes["gps_accuracy"] == 20

    await client.state(
        "car", {"latitude": None, "longitude": None, "gps_accuracy": 9999}
    )
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert "latitude" not in state.attributes
