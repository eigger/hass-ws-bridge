"""media_player platform."""

from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_media_player_features(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("plain", "media_player", "Plain")
    await client.entity(
        "src", "media_player", "Src", features=["play"], source_list=["A"]
    )
    plain = hass.states.get(entity_id_for(hass, "media_player", "plain"))
    flags = plain.attributes["supported_features"]
    assert flags & MediaPlayerEntityFeature.PLAY
    assert not flags & MediaPlayerEntityFeature.SELECT_SOURCE
    src = hass.states.get(entity_id_for(hass, "media_player", "src"))
    assert src.attributes["supported_features"] & MediaPlayerEntityFeature.SELECT_SOURCE


async def test_media_player_state_position_and_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "speaker", "media_player", "Speaker", source_list=["HDMI", "Bluetooth"]
    )
    entity_id = entity_id_for(hass, "media_player", "speaker")
    payload = {
        "state": "playing",
        "volume_level": 0.4,
        "media_title": "Song",
        "source": "HDMI",
        "media_position": 42,
    }
    await client.state("speaker", payload)
    state = hass.states.get(entity_id)
    assert state.state == MediaPlayerState.PLAYING
    assert state.attributes["volume_level"] == 0.4
    assert state.attributes["source"] == "HDMI"
    assert state.attributes["media_title"] == "Song"
    assert state.attributes["media_position"] == 42
    stamped = state.attributes["media_position_updated_at"]
    assert stamped is not None

    # Same position → timestamp unchanged; a new position → re-stamped.
    await client.state("speaker", {"volume_level": 2})
    state = hass.states.get(entity_id)
    assert state.attributes["volume_level"] == 1.0  # clamped
    assert state.attributes["media_position_updated_at"] == stamped
    await client.state("speaker", {"media_position": 50})
    state = hass.states.get(entity_id)
    assert state.attributes["media_position"] == 50
    assert state.attributes["media_position_updated_at"] != stamped

    await call_service(hass, "media_player", "media_pause", entity_id)
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "speaker",
        "action": "media_pause",
    }
    assert hass.states.get(entity_id).state == MediaPlayerState.PAUSED

    await call_service(hass, "media_player", "volume_set", entity_id, volume_level=0.25)
    assert (await client.next_command())["params"] == {"volume_level": 0.25}
    assert hass.states.get(entity_id).attributes["volume_level"] == 0.25

    await call_service(
        hass, "media_player", "select_source", entity_id, source="Bluetooth"
    )
    assert (await client.next_command())["params"] == {"source": "Bluetooth"}
    assert hass.states.get(entity_id).attributes["source"] == "Bluetooth"
