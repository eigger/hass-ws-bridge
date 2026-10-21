"""time platform tests."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, call_service, entity_id_for


async def test_time(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("t", "time", "Alarm")
    entity_id = entity_id_for(hass, "time", "t")
    await client.state("t", "07:30:00")
    assert hass.states.get(entity_id).state == "07:30:00"
    await client.state("t", "bad")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await call_service(hass, "time", "set_value", entity_id, time="06:15:00")
    assert (await client.next_command())["value"] == "06:15:00"
    assert hass.states.get(entity_id).state == "06:15:00"
