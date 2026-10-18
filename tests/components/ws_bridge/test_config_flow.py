"""Config flow tests via the real HA flow manager."""

from homeassistant.auth.models import User
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.const import CONF_ALLOWED_USER_IDS, DOMAIN


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


async def test_options_flow_lists_active_human_users_and_saves_allowlist(
    hass: HomeAssistant, config_entry: MockConfigEntry, hass_admin_user: User
) -> None:
    """Only active, non-system users are offered; the selection is stored."""
    inactive = await hass.auth.async_create_user("Inactive")
    await hass.auth.async_deactivate_user(inactive)
    system = await hass.auth.async_create_system_user("System")
    other = await hass.auth.async_create_user("Other")

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    selector = result["data_schema"].schema[CONF_ALLOWED_USER_IDS]
    offered = {option["value"] for option in selector.config["options"]}
    assert hass_admin_user.id in offered
    assert other.id in offered
    assert inactive.id not in offered
    assert system.id not in offered

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOWED_USER_IDS: [other.id]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_ALLOWED_USER_IDS: [other.id]}


async def test_options_flow_drops_stale_user_ids_and_allows_empty(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Removed users do not block saving; an empty selection (admins only) is valid."""
    other = await hass.auth.async_create_user("Other")
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_ALLOWED_USER_IDS: ["gone-user"]}
    )
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOWED_USER_IDS: [other.id]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_ALLOWED_USER_IDS: [other.id]}

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOWED_USER_IDS: []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_ALLOWED_USER_IDS: []}
