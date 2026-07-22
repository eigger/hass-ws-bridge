"""Unit tests for the framework-agnostic ws_bridge logic."""
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure custom_components is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from custom_components.ws_bridge.bridge import (
    WsBridge,
    _Client,
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


def test_seed_restorable_entities_only_for_keep_last_gateways():
    """HA 재시작 직후 pending 큐 예약은 keep_last_state_on_disconnect였던
    게이트웨이의 엔티티에만 적용돼야 한다."""
    bridge = WsBridge(MagicMock(), "entry1")
    defn_gw1 = {
        "unique_id": "gw1__sensor_a",
        "platform": "sensor",
        "_device": {"gateway_id": "gw1"},
    }
    defn_gw2 = {
        "unique_id": "gw2__sensor_b",
        "platform": "sensor",
        "_device": {"gateway_id": "gw2"},
    }
    bridge._defns = {"gw1__sensor_a": defn_gw1, "gw2__sensor_b": defn_gw2}
    bridge._keep_last = {"gw1": True, "gw2": False}

    bridge._seed_restorable_entities()

    assert bridge._pending == {"sensor": [defn_gw1]}
    assert bridge._entity_client == {"gw1__sensor_a": "gw1"}


def test_prune_orphan_states_also_prunes_defns():
    """entity registry에 없는 unique_id는 states뿐 아니라 저장된 정의(defns)도 같이 정리돼야
    재부팅 때 이미 삭제된 엔티티가 되살아나지 않는다."""
    bridge = WsBridge(MagicMock(), "entry1")
    bridge._states = {"gw1__a": 1, "gw1__b": 2}
    bridge._defns = {
        "gw1__a": {"unique_id": "gw1__a"},
        "gw1__b": {"unique_id": "gw1__b"},
    }

    known_entry = MagicMock()
    known_entry.unique_id = "gw1__a"

    with patch("custom_components.ws_bridge.bridge.er") as mock_er:
        mock_er.async_get.return_value = MagicMock()
        mock_er.async_entries_for_config_entry.return_value = [known_entry]
        changed = bridge._prune_orphan_states()

    assert changed is True
    assert bridge._states == {"gw1__a": 1}
    assert bridge._defns == {"gw1__a": {"unique_id": "gw1__a"}}


def test_handle_entity_persists_defn_only_for_keep_last_gateways():
    """저장 용량 절약: keep_last_state_on_disconnect가 아닌(기본값) 게이트웨이의 엔티티는
    정의를 저장하지 않는다 — 대다수 사용자의 스토리지 크기가 이전(state만 저장)과
    동일하게 유지돼야 한다."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge.register_platform("sensor", MagicMock(), MagicMock())

    bridge._clients["gw1"] = _Client("gw1", "GW1", MagicMock())
    bridge._keep_last["gw1"] = False
    bridge.handle_entity("gw1", {"unique_id": "a", "platform": "sensor", "name": "A"})
    assert bridge._defns == {}

    bridge._clients["gw2"] = _Client("gw2", "GW2", MagicMock())
    bridge._keep_last["gw2"] = True
    bridge.handle_entity("gw2", {"unique_id": "b", "platform": "sensor", "name": "B"})
    assert "gw2__b" in bridge._defns


def test_connect_client_purges_stale_defns_when_flag_turns_off():
    """keep_last_state_on_disconnect를 껐다가 재연결하면, 더는 필요 없어진 저장된
    엔티티 정의를 즉시 정리해서 스토리지가 계속 불어나지 않게 한다."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge._keep_last["gw1"] = True
    bridge._defns = {
        "gw1__a": {"unique_id": "gw1__a", "platform": "sensor", "_device": {"gateway_id": "gw1"}},
        "gw2__b": {"unique_id": "gw2__b", "platform": "sensor", "_device": {"gateway_id": "gw2"}},
    }

    with patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_dev_reg = MagicMock()
        mock_dr.async_get.return_value = mock_dev_reg
        mock_dr.async_entries_for_config_entry.return_value = []
        mock_dev_reg.async_get_or_create.return_value = MagicMock(via_device_id=None, sw_version=None)

        bridge.connect_client(
            connection=MagicMock(),
            gateway_id="gw1",
            name="GW1",
            send_event=MagicMock(),
            keep_last_state_on_disconnect=False,
        )

    assert "gw1__a" not in bridge._defns
    assert "gw2__b" in bridge._defns
