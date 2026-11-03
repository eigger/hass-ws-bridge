"""Diagnostics download through HA's real diagnostics view: structure and redaction."""

from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.ws_bridge.const import CONF_ALLOWED_USER_IDS

from .conftest import BridgeClient


async def test_diagnostics_describes_live_state(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    client: BridgeClient,
) -> None:
    """Counts and gateway metadata are reported without entity values."""
    await client.connect("gw1", "GW1", manufacturer="ACME", model="M1")
    await client.entity("temp", "sensor", "Temp")
    await client.state("temp", "secret-reading-42")

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    bridge = result["bridge"]
    assert bridge["control_connection_count"] == 1
    assert bridge["entity_count"] == 1
    assert bridge["state_count"] == 1
    assert bridge["gateways"]["gw1"]["manufacturer"] == "ACME"
    assert bridge["gateways"]["gw1"]["control_connections"] == 1
    assert bridge["gateways"]["gw1"]["has_owner"] is True
    assert bridge["media_sessions"] == []
    assert "secret-reading-42" not in str(result)


async def test_diagnostics_media_session_omits_ids(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
    hass_admin_user: MockUser,
    hass_access_token: str,
) -> None:
    """Media sessions list gateway/entity only: no session id, user or token id."""
    await client.entity("cam", "camera", "Cam")
    session = await client.ok("media_open", unique_id="cam")
    refresh_token = hass.auth.async_validate_access_token(hass_access_token)
    assert refresh_token is not None

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    sessions = result["bridge"]["media_sessions"]
    assert len(sessions) == 1
    assert sessions[0]["unique_id"] == "gw1__cam"
    assert sessions[0]["expires_in"] >= 0
    assert session["session_id"] not in str(result)
    assert hass_admin_user.id not in str(result)
    assert refresh_token.id not in str(result)

    media = await bridge_client_factory()
    await media.ok("media_connect", session_id=session["session_id"])

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert result["bridge"]["media_connections"] == [
        {"gateway_id": "gw1", "unique_id": "gw1__cam"}
    ]
    assert session["session_id"] not in str(result)
    assert hass_admin_user.id not in str(result)
    assert refresh_token.id not in str(result)


async def test_diagnostics_redacts_allowed_users(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """User ids are redacted; only their count is reported."""
    hass.config_entries.async_update_entry(
        init_integration,
        options={CONF_ALLOWED_USER_IDS: ["user-id-aaa", "user-id-bbb"]},
    )
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert result["options"][CONF_ALLOWED_USER_IDS] == "**REDACTED**"
    assert result["allowed_user_count"] == 2
    assert "user-id-aaa" not in str(result)
    assert "user-id-bbb" not in str(result)


async def test_diagnostics_after_unload(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """An unloaded entry has no bridge, but the download must still work."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert result["bridge"] is None
