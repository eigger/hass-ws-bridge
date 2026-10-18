"""event platform."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BridgeClient, entity_id_for, restart_without_client


async def test_event_fires_declared_types_only(
    hass: HomeAssistant, client: BridgeClient, caplog
) -> None:
    await client.entity(
        "bell",
        "event",
        "Bell",
        event_types=["doorbell", "motion"],
        device_class="doorbell",
    )
    entity_id = entity_id_for(hass, "event", "bell")
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["event_types"] == ["doorbell", "motion"]
    assert state.attributes["device_class"] == "doorbell"

    await client.state("bell", "doorbell")
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "doorbell"
    first_fired = state.state

    await client.state("bell", "ghost")
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "doorbell"  # unchanged
    assert state.state == first_fired
    assert "Ignoring undeclared event_type 'ghost'" in caplog.text

    await client.state(
        "bell", {"event_type": "motion", "attributes": {"zone": "front"}}
    )
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "motion"
    assert state.attributes["zone"] == "front"


async def test_event_attributes_do_not_leak_between_events(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """event payloads are not shallow-merged like other dict states."""
    await client.entity("bell", "event", "Bell", event_types=["doorbell", "motion"])
    entity_id = entity_id_for(hass, "event", "bell")
    await client.state(
        "bell", {"event_type": "doorbell", "attributes": {"zone": "front"}}
    )
    await client.state("bell", {"event_type": "motion"})
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "motion"
    assert "zone" not in state.attributes


async def test_event_is_not_persisted_or_replayed(
    hass: HomeAssistant,
    hass_storage: dict,
    init_integration: MockConfigEntry,
    bridge_client_factory,
) -> None:
    """No ghost event after restart; firing never writes the Store."""
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("btn", "event", "Button", event_types=["pressed", "held"])
    entity_id = entity_id_for(hass, "event", "btn")
    await gw.state("btn", "pressed")
    fired = hass.states.get(entity_id)
    assert fired.attributes["event_type"] == "pressed"

    await restart_without_client(hass, init_integration, gw)
    key = f"ws_bridge.{init_integration.entry_id}.states"
    assert "gw1__btn" not in hass_storage[key]["data"]["states"]
    # Recreated from its keep_last declaration but without replaying the event
    # (HA's own RestoreEntity shows the previous last-fired timestamp).
    state = hass.states.get(entity_id)
    assert state.attributes["event_types"] == ["pressed", "held"]
    assert state.state == fired.state  # no new firing timestamp
