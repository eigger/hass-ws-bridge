"""Diagnostics download: structure and redaction."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.const import CONF_ALLOWED_USER_IDS
from custom_components.ws_bridge.diagnostics import async_get_config_entry_diagnostics

from .conftest import BridgeClient


async def test_diagnostics_describes_live_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    client: BridgeClient,
) -> None:
    """Counts and gateway metadata are reported without entity values."""
    await client.connect("gw1", "GW1", manufacturer="ACME", model="M1")
    await client.entity("temp", "sensor", "Temp")
    await client.state("temp", "secret-reading-42")

    result = await async_get_config_entry_diagnostics(hass, init_integration)

    bridge = result["bridge"]
    assert bridge["control_connection_count"] == 1
    assert bridge["entity_count"] == 1
    assert bridge["state_count"] == 1
    assert bridge["gateways"]["gw1"]["manufacturer"] == "ACME"
    assert bridge["gateways"]["gw1"]["control_connections"] == 1
    assert bridge["gateways"]["gw1"]["has_owner"] is True
    assert bridge["media_sessions"] == []
    assert "secret-reading-42" not in str(result)


async def test_diagnostics_redacts_allowed_users(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """User ids are redacted; only their count is reported."""
    hass.config_entries.async_update_entry(
        init_integration,
        options={CONF_ALLOWED_USER_IDS: ["user-id-aaa", "user-id-bbb"]},
    )
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, init_integration)

    assert result["options"][CONF_ALLOWED_USER_IDS] == "**REDACTED**"
    assert result["allowed_user_count"] == 2
    assert "user-id-aaa" not in str(result)
    assert "user-id-bbb" not in str(result)
