"""update platform."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BridgeClient, call_service, entity_id_for, restart_without_client


async def test_update_full_payload(hass: HomeAssistant, client: BridgeClient) -> None:
    await client.entity("fw", "update", "Firmware")
    entity_id = entity_id_for(hass, "update", "fw")
    # UpdateEntity's class default CONFIG category is not kept.
    assert er.async_get(hass).async_get(entity_id).entity_category is None
    state = hass.states.get(entity_id)
    assert state.attributes["device_class"] == "firmware"
    assert state.state == STATE_UNKNOWN

    await client.state(
        "fw",
        {
            "installed_version": "1.0.0",
            "latest_version": "1.0.1",
            "in_progress": True,
            "progress": 45,
            "title": "Living Room",
            "summary": "Bug fixes",
            "release_url": "https://example.com",
        },
    )
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "1.0.0"
    assert state.attributes["latest_version"] == "1.0.1"
    assert state.attributes["in_progress"] is True
    assert state.attributes["update_percentage"] == 45
    assert state.attributes["title"] == "Living Room"
    assert state.attributes["release_summary"] == "Bug fixes"
    assert state.attributes["release_url"] == "https://example.com"


@pytest.mark.parametrize(
    ("payload", "in_progress", "percentage"),
    [
        ({"in_progress": False, "progress": 80}, False, None),  # idle → hidden
        ({"in_progress": True, "progress": 150}, True, 100),  # clamped
        ({"in_progress": "yes", "progress": -5}, True, 0),
        ({"in_progress": 1, "progress": "bad"}, True, None),
    ],
)
async def test_update_progress_parsing(
    hass: HomeAssistant, client: BridgeClient, payload, in_progress, percentage
) -> None:
    await client.entity("fw", "update", "Firmware")
    entity_id = entity_id_for(hass, "update", "fw")
    await client.state(
        "fw", {"installed_version": "1.0.0", "latest_version": "1.0.1", **payload}
    )
    state = hass.states.get(entity_id)
    assert state.attributes["in_progress"] is in_progress
    assert state.attributes["update_percentage"] == percentage


async def test_update_non_dict_clears_versions(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("fw", "update", "Firmware")
    entity_id = entity_id_for(hass, "update", "fw")
    await client.state("fw", {"installed_version": "1.0.0", "latest_version": "1.0.0"})
    assert hass.states.get(entity_id).state == STATE_OFF
    await client.state("fw", "unknown")
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["installed_version"] is None
    assert state.attributes["in_progress"] is False


@pytest.mark.parametrize(
    ("installed", "latest", "expected"),
    [
        ("2025.11.5_c51f7548", "2025.11.5", STATE_OFF),  # only build suffix differs
        ("2025.11.5_c51f7548", "2025.11.6_aa", STATE_ON),
        ("1.0.0_foo_bar", "1.0.0", STATE_OFF),
    ],
)
async def test_update_ignores_esphome_build_suffix(
    hass: HomeAssistant, client: BridgeClient, installed, latest, expected
) -> None:
    await client.entity("fw", "update", "Firmware")
    await client.state("fw", {"installed_version": installed, "latest_version": latest})
    assert hass.states.get(entity_id_for(hass, "update", "fw")).state == expected


async def test_update_install_is_optimistic_but_not_persisted(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    bridge_client_factory,
) -> None:
    """in_progress is transient: shown immediately, never stored, so a device
    that vanishes mid-flash does not stay "Installing…" after a restart. A
    stale progress (often 100 from the last run) is cleared on install."""
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("fw", "update", "Firmware")
    await gw.state(
        "fw",
        {
            "installed_version": "1.0.0",
            "latest_version": "1.0.1",
            "in_progress": False,
            "progress": 100,
        },
    )
    entity_id = entity_id_for(hass, "update", "fw")
    assert hass.states.get(entity_id).attributes["update_percentage"] is None

    await call_service(hass, "update", "install", entity_id)
    assert await gw.next_command() == {
        "kind": "command",
        "unique_id": "fw",
        "action": "install",
    }
    state = hass.states.get(entity_id)
    # HA core's async_install_with_progress resets _attr_in_progress once
    # async_install returns, so the optimistic flag is not visible here.
    assert state.attributes["in_progress"] is False
    assert state.attributes["update_percentage"] is None

    await restart_without_client(hass, init_integration, gw)
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["in_progress"] is False
    assert state.attributes["installed_version"] == "1.0.0"
    assert state.attributes["update_percentage"] is None


async def test_update_install_clears_stale_progress(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    """The client confirming install without a progress value must not bring
    back the stale 100 % via the shallow merge."""
    await client.entity("fw", "update", "Firmware")
    entity_id = entity_id_for(hass, "update", "fw")
    await client.state(
        "fw",
        {
            "installed_version": "1.0.0",
            "latest_version": "1.0.1",
            "in_progress": False,
            "progress": 100,
        },
    )
    await call_service(hass, "update", "install", entity_id)
    await client.state("fw", {"in_progress": True})
    state = hass.states.get(entity_id)
    assert state.attributes["in_progress"] is True
    assert state.attributes["update_percentage"] is None
    await client.state("fw", {"progress": 30})
    assert hass.states.get(entity_id).attributes["update_percentage"] == 30


async def test_update_refresh_is_silent_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    """homeassistant.update_entity → async_update is a refresh hook, not a user
    command: it sends `check` when connected and never raises when not."""
    assert await async_setup_component(hass, "homeassistant", {})
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("fw", "update", "Firmware")
    await gw.state("fw", {"installed_version": "1.0.0"})
    entity_id = entity_id_for(hass, "update", "fw")

    await call_service(hass, "homeassistant", "update_entity", entity_id)
    assert (await gw.next_command())["action"] == "check"

    await restart_without_client(hass, init_integration, gw)
    await call_service(hass, "homeassistant", "update_entity", entity_id)
    assert hass.states.get(entity_id).attributes["installed_version"] == "1.0.0"
