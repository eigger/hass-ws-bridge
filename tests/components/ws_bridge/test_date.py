"""date platform tests."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_date(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("d", "date", "Day")
    entity_id = entity_id_for(hass, "date", "d")
    await client.state("d", "2026-08-13")
    assert hass.states.get(entity_id).state == "2026-08-13"
    await client.state("d", "nope")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
    await client.state("d", 20260813)  # non-string → unknown
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await call_service(hass, "date", "set_value", entity_id, date="2026-09-01")
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "d",
        "action": "set_value",
        "value": "2026-09-01",
    }
    assert hass.states.get(entity_id).state == "2026-09-01"
