"""Repository-wide fixtures backed by the real Home Assistant test plugin."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the real HA loader find custom_components/ws_bridge in every test."""
