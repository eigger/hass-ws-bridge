"""date / time / datetime platforms."""

from datetime import UTC, datetime

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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


async def test_datetime_naive_is_local_and_aware_kept(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("dt", "datetime", "When")
    entity_id = entity_id_for(hass, "datetime", "dt")

    await client.state("dt", "2026-08-13T07:30:00+09:00")
    assert (
        hass.states.get(entity_id).state
        == datetime(2026, 8, 12, 22, 30, tzinfo=UTC).isoformat()
    )

    # tz-naive strings are HA local wall-clock (not UTC).
    await client.state("dt", "2026-08-13T07:30:00")
    expected = datetime(2026, 8, 13, 7, 30, tzinfo=dt_util.get_default_time_zone())
    assert hass.states.get(entity_id).state == expected.astimezone(UTC).isoformat()

    await client.state("dt", "garbage")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_datetime_set_value_sends_local_naive(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("dt", "datetime", "When")
    entity_id = entity_id_for(hass, "datetime", "dt")
    local = dt_util.get_default_time_zone()
    target = datetime(2026, 8, 13, 7, 30, tzinfo=local)
    await call_service(
        hass, "datetime", "set_value", entity_id, datetime=target.isoformat()
    )
    assert (await client.next_command())["value"] == "2026-08-13T07:30:00"
    assert hass.states.get(entity_id).state == target.astimezone(UTC).isoformat()
