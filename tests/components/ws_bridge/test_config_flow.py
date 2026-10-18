"""Config flow tests via the real HA flow manager."""

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.const import DOMAIN


async def test_user_flow_creates_single_entry_and_loads(hass: HomeAssistant) -> None:
    """The user step shows an empty form and creates a loaded single instance."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] is None

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "WebSocket Bridge"
    assert result["data"] == {}

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.unique_id == DOMAIN
    # The flow does not patch setup: the created entry really loads.
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_user_flow_aborts_when_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Only one instance is allowed (unique_id == domain)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_user_flow_aborts_duplicate_while_form_open(hass: HomeAssistant) -> None:
    """A second flow started before the first finishes cannot create a duplicate."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert first["type"] is FlowResultType.FORM
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    # HA aborts the second flow with the same unique_id in progress.
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"

    result = await hass.config_entries.flow.async_configure(first["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
