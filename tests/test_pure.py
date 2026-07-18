"""Unit tests for the framework-agnostic ws_bridge logic."""
import os
import sys
from unittest.mock import MagicMock

# Ensure custom_components is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.ws_bridge.bridge import (
    WsBridge,
    signal_value,
    signal_avail,
    signal_clients,
)
from custom_components.ws_bridge import _subentry_gateway_ids


def test_signals():
    entry_id = "test_entry"
    unique_id = "sensor_1"
    ns_device_id = "device_1"

    assert signal_value(entry_id, unique_id) == "ws_bridge_test_entry_state_sensor_1"
    assert signal_avail(entry_id, ns_device_id) == "ws_bridge_test_entry_avail_device_1"
    assert signal_clients(entry_id) == "ws_bridge_test_entry_clients"


def test_bridge_static_helpers():
    # _client_id_matches
    assert WsBridge._client_id_matches("device_1", "device_1", prefix=False) is True
    assert WsBridge._client_id_matches("device_1_sub", "device_1", prefix=False) is False
    assert WsBridge._client_id_matches("device_1", "device_1", prefix=True) is True
    assert WsBridge._client_id_matches("device_1_sub", "device_1", prefix=True) is True
    assert WsBridge._client_id_matches("device_2", "device_1", prefix=True) is False

    # _client_device_id_from_ns
    assert WsBridge._client_device_id_from_ns("gateway_1", "gateway_1") == "gateway_1"
    assert WsBridge._client_device_id_from_ns("gateway_1", "gateway_1:device_1") == "device_1"
    assert WsBridge._client_device_id_from_ns("gateway_1", "other_gateway:device_1") is None

    # _ns_uid
    assert WsBridge._ns_uid("gateway_1", "sensor_1") == "gateway_1__sensor_1"

    # _ns_dev
    assert WsBridge._ns_dev("gateway_1", "device_1") == "gateway_1:device_1"

    # _strip
    assert WsBridge._strip("gateway_1", "gateway_1__sensor_1") == "sensor_1"
    assert WsBridge._strip("gateway_1", "other_gateway__sensor_1") == "other_gateway__sensor_1"


def test_subentry_gateway_ids():
    # Create mock subentries
    sub_1 = MagicMock()
    sub_1.data = {"gateway_id": "gw1"}
    
    sub_2 = MagicMock()
    sub_2.data = {"gateway_id": "gw2", "name": "Gateway 2"}
    
    sub_3 = MagicMock()
    sub_3.data = {"name": "No gateway ID"}

    entry = MagicMock()
    entry.subentries = {
        "sub1": sub_1,
        "sub2": sub_2,
        "sub3": sub_3,
    }

    assert _subentry_gateway_ids(entry) == {"gw1", "gw2"}
