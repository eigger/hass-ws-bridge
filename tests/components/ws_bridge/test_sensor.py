"""sensor / text_sensor platform and the integration's connected-clients sensor."""

from datetime import UTC, datetime

from homeassistant.const import STATE_UNKNOWN, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.const import DOMAIN
from custom_components.ws_bridge.sensor import _parse_sensor_value

from .conftest import BridgeClient, entity_id_for, get_bridge


async def test_sensor_declared_and_updated(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "temp",
        "sensor",
        "Temperature",
        device_class="temperature",
        unit_of_measurement="°C",
        state_class="measurement",
        suggested_display_precision=1,
    )
    entity_id = entity_id_for(hass, "sensor", "temp")
    assert entity_id == "sensor.gw1_temperature"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await client.state("temp", 21.5)
    state = hass.states.get(entity_id)
    assert state.state == "21.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    # device_class given → no default platform icon
    assert "icon" not in state.attributes

    await client.state("temp", "unknown")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
    await client.state("temp", None)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_sensor_default_icon_and_redeclare_updates_metadata(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("rpm", "sensor", "RPM")
    entity_id = entity_id_for(hass, "sensor", "rpm")
    assert hass.states.get(entity_id).attributes["icon"] == "mdi:gauge"

    await client.entity(
        "rpm",
        "sensor",
        "Speed",
        icon="mdi:speedometer",
        unit_of_measurement="rpm",
    )
    # Idempotent declaration: same entity, updated metadata.
    assert entity_id_for(hass, "sensor", "rpm") == entity_id
    state = hass.states.get(entity_id)
    assert state.attributes["icon"] == "mdi:speedometer"
    assert state.attributes["unit_of_measurement"] == "rpm"
    assert state.attributes["friendly_name"] == "GW1 Speed"

    await client.entity("rpm", "sensor", "Speed", device_class="speed")
    assert "icon" not in hass.states.get(entity_id).attributes


async def test_entity_category_registered_from_declaration(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("diag", "sensor", "Diag", entity_category="diagnostic")
    await client.entity("cfg", "number", "Cfg", entity_category="config")
    await client.entity("plain", "sensor", "Plain", entity_category=None)
    ent_reg = er.async_get(hass)
    assert (
        ent_reg.async_get(entity_id_for(hass, "sensor", "diag")).entity_category
        is EntityCategory.DIAGNOSTIC
    )
    assert (
        ent_reg.async_get(entity_id_for(hass, "number", "cfg")).entity_category
        is EntityCategory.CONFIG
    )
    assert (
        ent_reg.async_get(entity_id_for(hass, "sensor", "plain")).entity_category
        is None
    )


async def test_sensor_timestamp_and_date_parsing(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("boot", "sensor", "Boot", device_class="timestamp")
    await client.entity("day", "sensor", "Day", device_class="date")
    boot = entity_id_for(hass, "sensor", "boot")
    day = entity_id_for(hass, "sensor", "day")

    await client.state("boot", "2026-08-13T07:30:00+00:00")
    assert hass.states.get(boot).state == datetime(
        2026, 8, 13, 7, 30, tzinfo=UTC
    ).isoformat(timespec="seconds")
    await client.state("day", "2026-08-13")
    assert hass.states.get(day).state == "2026-08-13"


async def test_timestamp_sensor_accepts_epoch_and_survives_bad_value(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """A float epoch (ESPHome uptime-style) must not break adding the entity."""
    await client.entity("boot", "sensor", "Boot", device_class="timestamp")
    boot = entity_id_for(hass, "sensor", "boot")
    await client.state("boot", 1793242000.0)
    assert hass.states.get(boot).state == datetime.fromtimestamp(
        1793242000, tz=UTC
    ).isoformat(timespec="seconds")
    # Epoch milliseconds are accepted too; garbage becomes unknown, not an error.
    await client.state("boot", 1793242000000)
    assert hass.states.get(boot).state == datetime.fromtimestamp(
        1793242000, tz=UTC
    ).isoformat(timespec="seconds")
    await client.state("boot", "not-a-time")
    assert hass.states.get(boot).state == STATE_UNKNOWN


async def test_uptime_and_text_sensor_timestamp_and_stored_epoch(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """uptime/text_sensor classes parse epochs; a redeclared class re-parses."""
    expected = datetime.fromtimestamp(1793242000, tz=UTC).isoformat(timespec="seconds")
    await client.entity("up", "sensor", "Up", device_class="uptime")
    await client.entity("ts", "text_sensor", "Ts", device_class="timestamp")
    await client.state("up", "1793242000")
    await client.state("ts", 1793242000.0)
    assert hass.states.get(entity_id_for(hass, "sensor", "up")).state == expected
    assert hass.states.get(entity_id_for(hass, "sensor", "ts")).state == expected

    # Plain sensor holding an epoch, later redeclared as a timestamp.
    await client.entity("plain", "sensor", "Plain")
    await client.state("plain", 1793242000.0)
    await client.entity("plain", "sensor", "Plain", device_class="timestamp")
    plain = hass.states.get(entity_id_for(hass, "sensor", "plain"))
    assert plain.state == expected
    # An absurd integer must not raise out of the parser (not sendable over
    # HA's JSON websocket, so exercised directly).
    assert _parse_sensor_value("timestamp", 10**400) is None
    assert _parse_sensor_value("uptime", True) is None


async def test_redeclare_before_entity_is_added_does_not_raise(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """Re-announcing a defn for an entity without hass must be a no-op write."""
    await client.entity("plain", "sensor", "Plain")
    bridge = get_bridge(hass, client.entry)
    entity = bridge._entities["gw1__plain"]
    original_hass = entity.hass
    entity.hass = None
    try:
        entity.async_update_defn({**entity._defn, "name": "Renamed"})
    finally:
        entity.hass = original_hass
    assert entity._attr_name == "Renamed"


async def test_text_sensor_is_a_sensor_entity(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """text_sensor has no HA domain of its own — it is a string sensor."""
    await client.entity("fw", "text_sensor", "Firmware")
    entity_id = entity_id_for(hass, "sensor", "fw")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.attributes["icon"] == "mdi:form-textbox"
    await client.state("fw", "v1.2.3")
    assert hass.states.get(entity_id).state == "v1.2.3"
    await client.state("fw", "UNKNOWN")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_connected_clients_sensor_counts_gateways(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{init_integration.entry_id}_connected_clients"
    )
    assert entity_id is not None
    reg_entry = ent_reg.async_get(entity_id)
    assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC
    device = dr.async_get(hass).async_get(reg_entry.device_id)
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.name == "WebSocket Bridge"
    assert hass.states.get(entity_id).state == "0"

    first = await bridge_client_factory()
    await first.connect("gw1", "GW1")
    assert hass.states.get(entity_id).state == "1"
    # Second connection of the same gateway does not double count.
    first_again = await bridge_client_factory()
    await first_again.connect("gw1", "GW1")
    assert hass.states.get(entity_id).state == "1"
    second = await bridge_client_factory()
    await second.connect("gw2", "GW2")
    assert hass.states.get(entity_id).state == "2"

    await second.close()
    assert hass.states.get(entity_id).state == "1"
    await first.close()
    assert hass.states.get(entity_id).state == "1"
    await first_again.close()
    assert hass.states.get(entity_id).state == "0"
