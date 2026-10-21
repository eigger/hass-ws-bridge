"""alarm_control_panel platform tests."""

import pytest
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BridgeClient, call_service, entity_id_for, restart_without_client


async def test_alarm_state_and_disarm_with_code(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity(
        "alarm",
        "alarm_control_panel",
        "Alarm",
        code_format="number",
        features=["arm_home", "arm_away", "trigger"],
    )
    entity_id = entity_id_for(hass, "alarm_control_panel", "alarm")
    state = hass.states.get(entity_id)
    assert state.attributes["code_format"] == CodeFormat.NUMBER
    assert state.attributes["code_arm_required"] is True
    flags = state.attributes["supported_features"]
    assert flags & AlarmControlPanelEntityFeature.ARM_AWAY
    assert not flags & AlarmControlPanelEntityFeature.ARM_NIGHT

    await client.state("alarm", "armed_away")
    assert hass.states.get(entity_id).state == AlarmControlPanelState.ARMED_AWAY
    await client.state("alarm", {"state": "triggered"})
    assert hass.states.get(entity_id).state == AlarmControlPanelState.TRIGGERED

    await call_service(
        hass, "alarm_control_panel", "alarm_disarm", entity_id, code="1234"
    )
    assert await client.next_command() == {
        "kind": "command",
        "unique_id": "alarm",
        "action": "alarm_disarm",
        "params": {"code": "1234"},
    }
    assert hass.states.get(entity_id).state == AlarmControlPanelState.DISARMED

    await call_service(
        hass, "alarm_control_panel", "alarm_arm_home", entity_id, code="1234"
    )
    assert (await client.next_command())["action"] == "alarm_arm_home"
    assert hass.states.get(entity_id).state == AlarmControlPanelState.ARMED_HOME


async def test_alarm_command_failure_keeps_state(
    hass: HomeAssistant, init_integration: MockConfigEntry, bridge_client_factory
) -> None:
    gw = await bridge_client_factory()
    await gw.connect("gw1", "GW1", keep_last_state_on_disconnect=True)
    await gw.entity("alarm", "alarm_control_panel", "Alarm", code_format="number")
    await gw.state("alarm", "armed_away")
    entity_id = entity_id_for(hass, "alarm_control_panel", "alarm")
    await restart_without_client(hass, init_integration, gw)
    assert hass.states.get(entity_id).state == AlarmControlPanelState.ARMED_AWAY

    with pytest.raises(HomeAssistantError, match="not connected"):
        await call_service(
            hass, "alarm_control_panel", "alarm_disarm", entity_id, code="1234"
        )
    assert hass.states.get(entity_id).state == AlarmControlPanelState.ARMED_AWAY
