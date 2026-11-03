"""Closed-socket detection and closing across HA's ActiveConnection layouts.

Up to HA 2026.10 ``send_message`` is the socket handler's bound method; from
2026.11 it is an ActiveConnection method wrapping the private ``_send_message``
slot and the handler's cancel is kept as ``_cancel_ws``. Both are modelled here
so each layout stays covered whichever HA version CI runs.
"""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge.bridge import connection_closed
from custom_components.ws_bridge.const import DOMAIN


class _Handler:
    def __init__(self) -> None:
        self.cancelled = 0

    def _send_message(self, _msg) -> None:
        pass

    def _cancel(self) -> None:
        self.cancelled += 1


class _ConnectionBase:
    user = None

    def _connect_closed_error(self, _msg) -> None:
        pass


class _OldLayout(_ConnectionBase):
    """HA <= 2026.10: send_message is the handler's bound method."""

    def __init__(self, handler: _Handler) -> None:
        self.send_message = handler._send_message

    def close(self) -> None:
        self.send_message = self._connect_closed_error


class _NewLayout(_ConnectionBase):
    """HA >= 2026.11: send_message is our method; the transport is a slot."""

    def __init__(self, handler: _Handler, *, cancel_ws: bool = True) -> None:
        self._send_message = handler._send_message
        self._cancel_ws = handler._cancel if cancel_ws else None

    def send_message(self, msg) -> None:
        self._send_message(msg)

    def close(self) -> None:
        self._send_message = self._connect_closed_error


def _layouts():
    return [
        pytest.param(lambda h: _OldLayout(h), id="old"),
        pytest.param(lambda h: _NewLayout(h), id="new"),
        # Supervisor unix-socket connections have no cancel_ws; the handler's
        # _cancel is still reachable through the transport.
        pytest.param(lambda h: _NewLayout(h, cancel_ws=False), id="new-no-cancel-ws"),
    ]


@pytest.mark.parametrize("make", _layouts())
def test_live_connection_is_not_closed(make) -> None:
    assert connection_closed(make(_Handler())) is False


@pytest.mark.parametrize("make", _layouts())
def test_closed_connection_is_detected(make) -> None:
    connection = make(_Handler())
    connection.close()
    assert connection_closed(connection) is True


@pytest.mark.parametrize("make", _layouts())
async def test_close_cancels_live_connection_once(
    hass: HomeAssistant, init_integration: MockConfigEntry, make, caplog
) -> None:
    bridge = hass.data[DOMAIN][init_integration.entry_id]
    handler = _Handler()

    bridge._close_connection(make(handler), "test")

    assert handler.cancelled == 1
    assert "Error closing client connection" not in caplog.text


@pytest.mark.parametrize("make", _layouts())
async def test_close_of_closed_connection_does_not_cancel_or_warn(
    hass: HomeAssistant, init_integration: MockConfigEntry, make, caplog
) -> None:
    bridge = hass.data[DOMAIN][init_integration.entry_id]
    handler = _Handler()
    connection = make(handler)
    connection.close()
    caplog.set_level("DEBUG", logger="custom_components.ws_bridge.bridge")

    bridge._close_connection(connection, "test")

    assert handler.cancelled == 0
    assert "Connection already closed (test)" in caplog.text
    assert "Error closing client connection" not in caplog.text
