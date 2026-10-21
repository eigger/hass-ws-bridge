"""datetime platform tests."""

from datetime import UTC, datetime

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .conftest import BridgeClient, call_service, entity_id_for


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
