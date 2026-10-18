"""lock platform."""

import pytest
from homeassistant.components.lock import LockEntityFeature, LockState
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_lock_features(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("door", "lock", "Door", features=["open"])
    await client.entity("plain", "lock", "Plain")
    door = hass.states.get(entity_id_for(hass, "lock", "door"))
    assert door.attributes["supported_features"] & LockEntityFeature.OPEN
    plain = hass.states.get(entity_id_for(hass, "lock", "plain"))
    assert plain.attributes["supported_features"] == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("locked", LockState.LOCKED),
        ("lock", LockState.LOCKED),
        ("unlocked", LockState.UNLOCKED),
        ("locking", LockState.LOCKING),
        ("unlocking", LockState.UNLOCKING),
        ("jammed", LockState.JAMMED),
        ("opening", LockState.OPENING),
        ("open", LockState.OPEN),
        (True, LockState.LOCKED),
        (False, LockState.UNLOCKED),
        ("on", LockState.LOCKED),  # lock-only vocabulary also accepts truthy
        ("unknown", STATE_UNKNOWN),
    ],
)
async def test_lock_states(
    hass: HomeAssistant, client: BridgeClient, value, expected
) -> None:
    await client.entity("door", "lock", "Door")
    await client.state("door", value)
    assert hass.states.get(entity_id_for(hass, "lock", "door")).state == expected


async def test_lock_commands_with_code(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("door", "lock", "Door", features=["open"])
    entity_id = entity_id_for(hass, "lock", "door")
    await client.state("door", "unlocked")

    await call_service(hass, "lock", "lock", entity_id, code="1234")
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "door",
        "action": "lock",
        "params": {"code": "1234"},
    }
    assert hass.states.get(entity_id).state == LockState.LOCKING

    await client.state("door", "locked")  # client confirms
    assert hass.states.get(entity_id).state == LockState.LOCKED

    await call_service(hass, "lock", "unlock", entity_id)
    cmd = await client.next_command()
    assert cmd["action"] == "unlock"
    assert "params" not in cmd
    assert hass.states.get(entity_id).state == LockState.UNLOCKING

    await client.state("door", "unlocked")
    await call_service(hass, "lock", "open", entity_id)
    assert (await client.next_command())["action"] == "open"
    assert hass.states.get(entity_id).state == LockState.OPENING


async def test_lock_back_to_back_optimistic_commands(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("door", "lock", "Door")
    entity_id = entity_id_for(hass, "lock", "door")
    await client.state("door", "unlocked")
    await call_service(hass, "lock", "lock", entity_id)
    await call_service(hass, "lock", "unlock", entity_id)
    assert hass.states.get(entity_id).state == LockState.UNLOCKING
