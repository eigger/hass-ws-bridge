"""siren platform tests."""

from homeassistant.components.siren import SirenEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_siren_features_state_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("notone", "siren", "NoTone", features=["tones"])
    flags = hass.states.get(entity_id_for(hass, "siren", "notone")).attributes[
        "supported_features"
    ]
    assert not flags & SirenEntityFeature.TONES

    await client.entity(
        "siren",
        "siren",
        "Siren",
        available_tones=["alarm", "chime"],
        features=["turn_on", "turn_off", "tones", "volume_set", "duration"],
    )
    entity_id = entity_id_for(hass, "siren", "siren")
    state = hass.states.get(entity_id)
    assert state.attributes["supported_features"] & SirenEntityFeature.TONES
    assert state.attributes["available_tones"] == ["alarm", "chime"]

    await client.state("siren", True)
    assert hass.states.get(entity_id).state == STATE_ON
    await client.state("siren", {"state": "off"})
    assert hass.states.get(entity_id).state == STATE_OFF
    await client.state("siren", "unknown")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await call_service(hass, "siren", "turn_on", entity_id, tone="chime", duration=5)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "siren",
        "action": "turn_on",
        "params": {"tone": "chime", "duration": 5},
    }
    assert hass.states.get(entity_id).state == STATE_ON
    await call_service(hass, "siren", "turn_off", entity_id)
    assert (await client.next_command())["action"] == "turn_off"
    assert hass.states.get(entity_id).state == STATE_OFF
