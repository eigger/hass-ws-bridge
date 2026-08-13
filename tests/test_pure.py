"""Unit tests for the framework-agnostic ws_bridge logic."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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
from custom_components.ws_bridge.const import ALL_PLATFORMS, PLATFORM_UPDATE
from custom_components.ws_bridge.device_tracker import _parse_location
from custom_components.ws_bridge.update import _parse_update_state, _strip_build_suffix


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


def _sync_bridge():
    """레지스트리를 모킹한 브릿지 — async_sync_entities 테스트용."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge._store = MagicMock()
    bridge._store.async_save = AsyncMock()
    return bridge


def _reg_entry(unique_id):
    entry = MagicMock()
    entry.unique_id = unique_id
    return entry


def test_sync_removes_only_undeclared_entities():
    """선언 목록에 없는 것만 지우고, 살아남는 엔티티는 건드리지 않아야 한다
    (히스토리·통계·entity_id 보존)."""
    bridge = _sync_bridge()
    bridge._created = {"gw1__a", "gw1__b", "gw1__c"}
    bridge._states = {"gw1__a": 1, "gw1__b": 2, "gw1__c": 3}
    bridge._entity_client = {u: "gw1" for u in bridge._created}
    live = {u: MagicMock(async_remove=AsyncMock()) for u in bridge._created}
    bridge._entities = dict(live)

    with patch("custom_components.ws_bridge.bridge.er") as mock_er, \
         patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_er.async_entries_for_config_entry.return_value = [
            _reg_entry("gw1__a"), _reg_entry("gw1__b"), _reg_entry("gw1__c")
        ]
        mock_dr.async_entries_for_config_entry.return_value = []
        removed = asyncio.run(bridge.async_sync_entities("gw1", ["a", "c"]))

    assert removed == ["b"]
    live["gw1__b"].async_remove.assert_awaited_once()
    live["gw1__a"].async_remove.assert_not_called()
    live["gw1__c"].async_remove.assert_not_called()
    assert bridge._created == {"gw1__a", "gw1__c"}
    assert bridge._states == {"gw1__a": 1, "gw1__c": 3}


def test_sync_ignores_other_gateways_and_diagnostic_sensor():
    """다른 게이트웨이의 엔티티와 통합 진단 센서는 절대 건드리면 안 된다."""
    bridge = _sync_bridge()
    bridge._created = {"gw1__a", "gw2__a"}
    bridge._entities = {
        u: MagicMock(async_remove=AsyncMock()) for u in bridge._created
    }

    with patch("custom_components.ws_bridge.bridge.er") as mock_er, \
         patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_er.async_entries_for_config_entry.return_value = [
            _reg_entry("gw1__a"),
            _reg_entry("gw2__a"),
            _reg_entry("entry1_connected_clients"),
        ]
        mock_dr.async_entries_for_config_entry.return_value = []
        removed = asyncio.run(bridge.async_sync_entities("gw1", ["a"]))

    assert removed == []
    assert bridge._created == {"gw1__a", "gw2__a"}


def test_sync_reconciles_restored_keep_last_definitions():
    """keep_last_state_on_disconnect로 HA 재시작 때 부활한 정의도 대조 대상이다 —
    클라이언트가 더는 선언하지 않는 엔티티가 영원히 살아남던 문제의 핵심."""
    bridge = _sync_bridge()
    bridge._keep_last = {"gw1": True}
    bridge._defns = {
        "gw1__a": {"unique_id": "gw1__a", "platform": "sensor",
                   "_device": {"gateway_id": "gw1"}},
        "gw1__gone": {"unique_id": "gw1__gone", "platform": "sensor",
                      "_device": {"gateway_id": "gw1"}},
    }
    bridge._seed_restorable_entities()
    assert len(bridge._pending["sensor"]) == 2

    with patch("custom_components.ws_bridge.bridge.er") as mock_er, \
         patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_er.async_entries_for_config_entry.return_value = []
        mock_dr.async_entries_for_config_entry.return_value = []
        removed = asyncio.run(bridge.async_sync_entities("gw1", ["a"]))

    assert removed == ["gone"]
    assert "gw1__gone" not in bridge._defns
    # pending에 남아 있으면 플랫폼 준비 시점에 되살아난다
    assert [d["unique_id"] for d in bridge._pending["sensor"]] == ["gw1__a"]


def test_sync_prunes_sub_devices_left_empty():
    """엔티티가 하나도 안 남은 sub-device는 기기 목록에서도 사라져야 한다.
    게이트웨이 디바이스 자체는 유지한다."""
    bridge = _sync_bridge()
    bridge._created = {"gw1__a"}
    bridge._entities = {"gw1__a": MagicMock(async_remove=AsyncMock())}
    bridge._clients["gw1"] = _Client("gw1", "GW1", MagicMock())
    bridge._clients["gw1"].device_ids = {"gw1", "gw1:sub1"}

    gw_device = MagicMock(id="dev_gw", identifiers={("ws_bridge", "gw1")})
    sub_device = MagicMock(id="dev_sub", identifiers={("ws_bridge", "gw1:sub1")})

    with patch("custom_components.ws_bridge.bridge.er") as mock_er, \
         patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_er.async_entries_for_config_entry.return_value = [_reg_entry("gw1__a")]
        mock_er.async_entries_for_device.return_value = []   # 남은 엔티티 없음
        mock_dev_reg = MagicMock()
        mock_dr.async_get.return_value = mock_dev_reg
        mock_dr.async_entries_for_config_entry.return_value = [gw_device, sub_device]
        asyncio.run(bridge.async_sync_entities("gw1", ["nothing_matches"]))

    mock_dev_reg.async_remove_device.assert_called_once_with("dev_sub")
    assert bridge._clients["gw1"].device_ids == {"gw1"}


def test_sync_is_noop_when_everything_still_declared():
    bridge = _sync_bridge()
    bridge._created = {"gw1__a", "gw1__b"}

    with patch("custom_components.ws_bridge.bridge.er") as mock_er, \
         patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_er.async_entries_for_config_entry.return_value = [
            _reg_entry("gw1__a"), _reg_entry("gw1__b")
        ]
        mock_dr.async_entries_for_config_entry.return_value = []
        removed = asyncio.run(
            bridge.async_sync_entities("gw1", ["a", "b", "not_yet_created"])
        )

    assert removed == []
    bridge._store.async_save.assert_not_called()


def test_parse_location_full_payload():
    assert _parse_location(
        {"latitude": 37.5665, "longitude": 126.9780, "gps_accuracy": 8}
    ) == (37.5665, 126.9780, 8)


def test_parse_location_accepts_numeric_strings():
    """클라이언트가 숫자를 문자열로 보내도 좌표로 받아들인다."""
    assert _parse_location(
        {"latitude": "37.5", "longitude": "127.0"}
    ) == (37.5, 127.0, 0)


def test_parse_location_rejects_partial_or_non_dict():
    """반쪽짜리 좌표는 엉뚱한 위치로 잡히므로 '위치 모름'으로 떨어뜨려야 한다."""
    # 경도 누락 → 위도도 버림
    assert _parse_location({"latitude": 37.5}) == (None, None, 0)
    # 숫자가 아닌 좌표
    assert _parse_location({"latitude": "N/A", "longitude": 127.0}) == (None, None, 0)
    # bool은 float()이 되지만 좌표로는 무의미
    assert _parse_location({"latitude": True, "longitude": 127.0}) == (None, None, 0)
    # dict가 아닌 값 (스칼라 오발신 / "unknown" / None)
    assert _parse_location("unknown") == (None, None, 0)
    assert _parse_location(None) == (None, None, 0)
    assert _parse_location(37.5) == (None, None, 0)


def test_all_platforms_includes_update():
    assert PLATFORM_UPDATE in ALL_PLATFORMS
    assert PLATFORM_UPDATE == "update"


def test_parse_update_state_full_payload():
    parsed = _parse_update_state(
        {
            "installed_version": "1.0.0",
            "latest_version": "1.0.1",
            "in_progress": True,
            "progress": 45,
            "title": "Living Room",
            "summary": "Bug fixes",
            "release_url": "https://example.com",
        }
    )
    assert parsed["installed_version"] == "1.0.0"
    assert parsed["latest_version"] == "1.0.1"
    assert parsed["in_progress"] is True
    assert parsed["progress"] == 45
    assert parsed["title"] == "Living Room"
    assert parsed["summary"] == "Bug fixes"
    assert parsed["release_url"] == "https://example.com"


def test_parse_update_state_clamps_progress_and_ignores_when_idle():
    idle = _parse_update_state({"in_progress": False, "progress": 80})
    assert idle["in_progress"] is False
    assert idle["progress"] is None

    installing = _parse_update_state({"in_progress": True, "progress": 150})
    assert installing["progress"] == 100


def test_parse_update_state_rejects_non_dict():
    empty = _parse_update_state("unknown")
    assert empty["installed_version"] is None
    assert empty["latest_version"] is None
    assert empty["in_progress"] is False
    assert _parse_update_state(None)["installed_version"] is None


def test_strip_build_suffix():
    """HA only calls version_is_newer when the raw strings differ — the
    interesting case is a build suffix on an otherwise equal version."""
    assert _strip_build_suffix("1.0.0") == "1.0.0"
    assert _strip_build_suffix("2025.11.5_c51f7548") == "2025.11.5"
    assert _strip_build_suffix("1.0.0_foo_bar") == "1.0.0"
    assert _strip_build_suffix("_only") == ""


def test_send_command_returns_false_when_disconnected():
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    assert bridge.send_command("gw1__firmware", "install") is False

    send_event = MagicMock()
    bridge._clients["gw1"] = _Client("gw1", "GW1", send_event)
    bridge._entity_client["gw1__firmware"] = "gw1"
    assert bridge.send_command("gw1__firmware", "install") is True
    send_event.assert_called_once_with(
        {"kind": "command", "unique_id": "firmware", "action": "install"}
    )

