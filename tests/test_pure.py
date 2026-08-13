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
from custom_components.ws_bridge.websocket_api import resolve_connect_sw_version
from custom_components.ws_bridge.device_tracker import _parse_location
from custom_components.ws_bridge.helpers import as_dict, is_unknown, parse_bool, parse_locked
from custom_components.ws_bridge.cover import _features as cover_features
from custom_components.ws_bridge.fan import _features as fan_features
from custom_components.ws_bridge.light import _color_modes, _features as light_features
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.fan import FanEntityFeature
from homeassistant.components.light import ColorMode, LightEntityFeature
from custom_components.ws_bridge.date import _parse_date
from custom_components.ws_bridge.time import _parse_time
from custom_components.ws_bridge.datetime import _parse_datetime
from custom_components.ws_bridge.lock import _features as lock_features
from custom_components.ws_bridge.valve import _features as valve_features
from homeassistant.components.lock import LockEntityFeature
from homeassistant.components.valve import ValveEntityFeature
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
        mock_dev_reg.async_get_or_create.return_value = MagicMock(
            via_device_id=None, sw_version=None, hw_version=None,
            manufacturer="ws_bridge", model="Gateway",
        )

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


def _connect(bridge, gateway_id="gw1", connection=None, **kwargs):
    """레지스트리를 모킹한 connect_client 호출."""
    with patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_dev_reg = MagicMock()
        mock_dr.async_get.return_value = mock_dev_reg
        mock_dr.async_entries_for_config_entry.return_value = []
        mock_dev_reg.async_get_or_create.return_value = MagicMock(
            via_device_id=None, sw_version=None, hw_version=None,
            manufacturer="ws_bridge", model="Gateway",
        )
        return bridge.connect_client(
            connection=connection or MagicMock(),
            gateway_id=gateway_id,
            name="GW1",
            send_event=MagicMock(),
            **kwargs,
        )


def test_connect_defaults_device_registry_when_fields_omitted():
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_dev_reg = MagicMock()
        mock_dr.async_get.return_value = mock_dev_reg
        mock_dr.async_entries_for_config_entry.return_value = []
        mock_dev_reg.async_get_or_create.return_value = MagicMock(
            via_device_id=None, sw_version=None, hw_version=None,
            manufacturer="ws_bridge", model="Gateway",
        )
        bridge.connect_client(
            connection=MagicMock(),
            gateway_id="gw1",
            name="GW1",
            send_event=MagicMock(),
        )
        kwargs = mock_dev_reg.async_get_or_create.call_args.kwargs
        assert kwargs["manufacturer"] == "ws_bridge"
        assert kwargs["model"] == "Gateway"
        assert kwargs["sw_version"] is None
        assert kwargs["hw_version"] is None
        mock_dev_reg.async_update_device.assert_not_called()


def test_connect_applies_optional_device_fields_independently():
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.dr") as mock_dr:
        mock_dev_reg = MagicMock()
        mock_dr.async_get.return_value = mock_dev_reg
        mock_dr.async_entries_for_config_entry.return_value = []
        mock_dev_reg.async_get_or_create.return_value = MagicMock(
            via_device_id=None, sw_version=None, hw_version=None,
            manufacturer="ws_bridge", model="Gateway",
        )
        bridge.connect_client(
            connection=MagicMock(),
            gateway_id="gw1",
            name="GW1",
            send_event=MagicMock(),
            manufacturer="Espressif",
            hw_version="1.0",
        )
        kwargs = mock_dev_reg.async_get_or_create.call_args.kwargs
        assert kwargs["manufacturer"] == "Espressif"
        assert kwargs["model"] == "Gateway"
        assert kwargs["hw_version"] == "1.0"
        assert kwargs["sw_version"] is None


def test_reconnect_keeps_previous_device_fields_when_omitted():
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    _connect(bridge, manufacturer="Espressif", model="ESP32-S3")
    _connect(bridge)
    client = bridge._clients["gw1"]
    assert client.manufacturer == "Espressif"
    assert client.model == "ESP32-S3"


def test_resolve_connect_sw_version_prefers_sw_version():
    assert resolve_connect_sw_version({"sw_version": "2.0", "app_version": "1.0"}) == "2.0"
    assert resolve_connect_sw_version({"app_version": "1.0"}) == "1.0"
    assert resolve_connect_sw_version({"sw_version": "  ", "app_version": "1.0"}) == "1.0"
    assert resolve_connect_sw_version({}) is None


def test_reconnect_does_not_resurrect_undeclared_sub_devices():
    """재연결 시 이전 세션의 sub-device를 무조건 online으로 되돌리면, 클라이언트에서
    이미 사라진 sub-device의 엔티티까지 살아 있는 것처럼 보인다. 이번 세션에 다시
    선언된 것만 복귀해야 한다."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge.register_platform("sensor", MagicMock(), MagicMock())

    conn = MagicMock()
    disconnect = _connect(bridge, connection=conn)
    for dev in ("keeps", "goes_away"):
        bridge.handle_entity("gw1", {
            "unique_id": f"{dev}_x", "platform": "sensor", "name": "X",
            "device": {"id": dev},
        })
    assert bridge._clients["gw1"].device_ids == {"gw1", "gw1:keeps", "gw1:goes_away"}
    disconnect()

    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        _connect(bridge)
        bridge.handle_entity("gw1", {
            "unique_id": "keeps_x", "platform": "sensor", "name": "X",
            "device": {"id": "keeps"},
        })

    online = {
        c.args[1] for c in send.call_args_list
        if c.args[1].startswith("ws_bridge_entry1_avail_") and c.args[2] is True
    }
    assert "ws_bridge_entry1_avail_gw1:keeps" in online
    assert "ws_bridge_entry1_avail_gw1:goes_away" not in online
    assert bridge._clients["gw1"].device_ids == {"gw1", "gw1:keeps"}


def test_reconnect_state_only_client_still_restores_availability():
    """엔티티를 다시 선언하지 않고 state만 보내는 클라이언트도 그대로 동작해야 한다."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge.register_platform("sensor", MagicMock(), MagicMock())

    disconnect = _connect(bridge)
    bridge.handle_entity("gw1", {
        "unique_id": "sub_x", "platform": "sensor", "name": "X",
        "device": {"id": "sub"},
    })
    disconnect()

    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        _connect(bridge)
        bridge.handle_state("gw1", "sub_x", 42)

    online = {
        c.args[1] for c in send.call_args_list
        if c.args[1].startswith("ws_bridge_entry1_avail_") and c.args[2] is True
    }
    assert "ws_bridge_entry1_avail_gw1:sub" in online


def test_second_connection_does_not_reset_device_tracking():
    """같은 게이트웨이의 두 번째 커넥션이 첫 커넥션의 추적 정보를 지우면,
    마지막 커넥션이 끊길 때 offline 팬아웃이 빈다."""
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    bridge = WsBridge(hass, "entry1")
    bridge.register_platform("sensor", MagicMock(), MagicMock())

    _connect(bridge, connection=MagicMock())
    bridge.handle_entity("gw1", {
        "unique_id": "sub_x", "platform": "sensor", "name": "X",
        "device": {"id": "sub"},
    })
    _connect(bridge, connection=MagicMock())   # 두 번째 커넥션

    assert bridge._clients["gw1"].device_ids == {"gw1", "gw1:sub"}


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


def test_parse_location_null_clears_coordinates():
    """JSON null 은 좌표 없음(unknown)으로 취급 — 얕은 병합 후 GPS 유실 경로."""
    assert _parse_location(
        {"latitude": None, "longitude": None, "gps_accuracy": 9999}
    ) == (None, None, 9999)
    assert _parse_location(
        {"latitude": 37.5, "longitude": None}
    ) == (None, None, 0)


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

# ── Phase 0: 복합 상태 / params / helpers ────────────────────────────────────

def test_handle_state_shallow_merges_dicts():
    """dict + dict 는 얕은 병합. 이전 키가 보존된다."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        bridge.handle_state("gw1", "led", {"state": "on", "brightness": 100})
        bridge.handle_state("gw1", "led", {"brightness": 200})

    assert bridge._states["gw1__led"] == {"state": "on", "brightness": 200}
    assert send.call_args_list[-1].args[2] == {"state": "on", "brightness": 200}


def test_handle_state_event_does_not_merge_attributes():
    """event 플랫폼은 얕은 병합을 건너뛴다 — 이전 attributes 가 다음 이벤트로 새면 안 된다."""
    from custom_components.ws_bridge.event import WsBridgeEvent

    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    entity = WsBridgeEvent(
        bridge,
        {
            "unique_id": "gw1__bell",
            "platform": "event",
            "name": "Bell",
            "event_types": ["doorbell", "motion"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    bridge._entities["gw1__bell"] = entity
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        bridge.handle_state(
            "gw1", "bell",
            {"event_type": "doorbell", "attributes": {"zone": "front"}},
        )
        bridge.handle_state("gw1", "bell", {"event_type": "motion"})

    # event 는 복원하지 않으므로 _states / Store 에 넣지 않는다.
    assert "gw1__bell" not in bridge._states
    assert bridge._save_unsub is None
    assert send.call_args_list[-1].args[2] == {"event_type": "motion"}
    assert send.call_args_list[0].args[2] == {
        "event_type": "doorbell",
        "attributes": {"zone": "front"},
    }


def test_set_local_state_keeps_optimistic_keys_on_partial_push():
    """낙관적 설정이 bridge._states 에 있으면 부분 푸시로 되돌아가지 않는다."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send"):
        bridge.handle_state(
            "gw1", "ac",
            {"hvac_mode": "heat", "target_temperature": 26, "current_temperature": 22},
        )
    bridge.set_local_state(
        "gw1__ac",
        {"hvac_mode": "heat", "target_temperature": 24, "current_temperature": 22},
    )
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        bridge.handle_state("gw1", "ac", {"current_temperature": 27.5})

    assert bridge._states["gw1__ac"] == {
        "hvac_mode": "heat",
        "target_temperature": 24,
        "current_temperature": 27.5,
    }
    assert send.call_args.args[2]["target_temperature"] == 24


def test_entity_send_command_raises_when_disconnected():
    from homeassistant.exceptions import HomeAssistantError
    from custom_components.ws_bridge.entity import WsBridgeEntity

    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    entity = WsBridgeEntity(
        bridge,
        {
            "unique_id": "gw1__sw",
            "platform": "switch",
            "name": "SW",
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    try:
        entity._send_command("turn_on")
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError as err:
        assert "not connected" in str(err).lower()


def test_handle_state_null_clears_merged_key():
    """병합 후 JSON null 로 키를 지울 수 있다 (device_tracker GPS 유실 등)."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send"):
        bridge.handle_state(
            "gw1", "car",
            {"latitude": 37.5, "longitude": 127.0, "gps_accuracy": 8},
        )
        bridge.handle_state(
            "gw1", "car",
            {"latitude": None, "longitude": None, "gps_accuracy": 9999},
        )

    assert bridge._states["gw1__car"] == {
        "latitude": None,
        "longitude": None,
        "gps_accuracy": 9999,
    }
    assert _parse_location(bridge._states["gw1__car"]) == (None, None, 9999)


def test_handle_state_replaces_on_type_change():
    """dict → 스칼라, 스칼라 → dict 는 교체한다."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send"):
        bridge.handle_state("gw1", "a", {"state": "on"})
        bridge.handle_state("gw1", "a", 42)
        assert bridge._states["gw1__a"] == 42

        bridge.handle_state("gw1", "a", {"brightness": 10})
        assert bridge._states["gw1__a"] == {"brightness": 10}


def test_handle_state_dispatches_full_merged_value():
    """병합 결과 전체가 dispatcher로 전달된다."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send") as send:
        bridge.handle_state("gw1", "led", {"state": "on", "rgb_color": [1, 2, 3]})
        bridge.handle_state("gw1", "led", {"brightness": 50})

    dispatched = send.call_args_list[-1].args[2]
    assert dispatched == {"state": "on", "rgb_color": [1, 2, 3], "brightness": 50}


def test_send_command_params():
    """params 가 전달되고, None/빈 dict 이면 키 자체가 없다."""
    hass = MagicMock()
    bridge = WsBridge(hass, "entry1")
    send_event = MagicMock()
    bridge._clients["gw1"] = _Client("gw1", "GW1", send_event)
    bridge._entity_client["gw1__led"] = "gw1"

    assert bridge.send_command("gw1__led", "turn_on", params={"brightness": 128}) is True
    assert send_event.call_args.args[0] == {
        "kind": "command",
        "unique_id": "led",
        "action": "turn_on",
        "params": {"brightness": 128},
    }

    send_event.reset_mock()
    bridge.send_command("gw1__led", "turn_off", params=None)
    assert "params" not in send_event.call_args.args[0]

    send_event.reset_mock()
    bridge.send_command("gw1__led", "turn_off", params={})
    assert "params" not in send_event.call_args.args[0]

    send_event.reset_mock()
    bridge.send_command("gw1__led", "set_value", value=26.5)
    assert send_event.call_args.args[0] == {
        "kind": "command",
        "unique_id": "led",
        "action": "set_value",
        "value": 26.5,
    }


def test_parse_bool_matches_legacy_truthy():
    """기존 _truthy 와 동일. 'open' 은 False (목록 확장 금지)."""
    assert parse_bool("1") is True
    assert parse_bool("TRUE") is True
    assert parse_bool("on") is True
    assert parse_bool("yes") is True
    assert parse_bool("open") is False
    assert parse_bool("unknown") is None
    assert parse_bool(None) is None
    assert parse_bool(0) is False
    assert parse_bool(1) is True
    assert parse_bool(True) is True
    assert parse_bool(False) is False


def test_helpers_is_unknown_and_as_dict():
    assert is_unknown(None) is True
    assert is_unknown("unknown") is True
    assert is_unknown("UNKNOWN") is True
    assert is_unknown("on") is False
    assert is_unknown(0) is False

    src = {"a": 1}
    out = as_dict(src)
    assert out == {"a": 1}
    assert out is not src
    out["a"] = 2
    assert src["a"] == 1

    assert as_dict("on") == {"state": "on"}
    assert as_dict(None) == {}
    assert as_dict("unknown") == {}


def test_entity_category_standin_is_callable():
    """entity.py 가 EntityCategory(cat) 생성자를 호출한다 — conftest 스탠드인이 맞아야 함."""
    from homeassistant.const import EntityCategory

    assert EntityCategory.CONFIG == "config"
    assert EntityCategory("diagnostic") == EntityCategory.DIAGNOSTIC
    assert "config" in (EntityCategory.CONFIG, EntityCategory.DIAGNOSTIC)


def test_parse_locked_accepts_lock_vocabulary():
    """lock 전용 어휘. parse_bool 과 분리되어 기존 플랫폼에 영향 없음."""
    assert parse_locked("locked") is True
    assert parse_locked("lock") is True
    assert parse_locked("open") is False
    assert parse_bool("locked") is False


def test_all_platforms_are_forwarded():
    """ALL_PLATFORMS의 모든 항목이 HA 플랫폼으로 forward 되는지.
    text_sensor는 sensor 플랫폼에 얹혀 가므로 예외."""
    from custom_components.ws_bridge import PLATFORMS

    forwarded = {str(p) for p in PLATFORMS}
    expected = set(ALL_PLATFORMS) - {"text_sensor"}
    assert expected <= forwarded

# ── Phase 1: light / cover / fan ─────────────────────────────────────────────

def test_light_color_modes_and_features():
    assert _color_modes(None) == {ColorMode.ONOFF}
    assert _color_modes(["rgb", "nope"]) == {ColorMode.RGB}
    # HA: ONOFF/BRIGHTNESS 는 다른 색 모드와 배타
    assert _color_modes(["brightness", "rgb"]) == {ColorMode.RGB}
    assert _color_modes(["onoff", "brightness"]) == {ColorMode.BRIGHTNESS}
    flags = light_features(["transition", "unknown"], has_effects=True)
    assert flags & LightEntityFeature.TRANSITION
    assert flags & LightEntityFeature.EFFECT


def test_light_apply_state_tolerates_bad_numbers():
    """brightness/color_temp 파싱 실패가 예외로 전파되면 이후 갱신이 전부 죽는다."""
    from custom_components.ws_bridge.light import WsBridgeLight

    bridge = WsBridge(MagicMock(), "entry1")
    entity = WsBridgeLight(
        bridge,
        {
            "unique_id": "gw1__led",
            "platform": "light",
            "name": "LED",
            "supported_color_modes": ["rgb", "color_temp"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity._state = {"state": "on", "brightness": "abc", "color_temp_kelvin": "warm"}
    entity._apply_state()
    assert entity._attr_is_on is True
    assert entity._attr_brightness is None
    assert entity._attr_color_temp_kelvin is None


def test_light_infers_color_mode_from_payload():
    from custom_components.ws_bridge.light import WsBridgeLight

    bridge = WsBridge(MagicMock(), "entry1")
    entity = WsBridgeLight(
        bridge,
        {
            "unique_id": "gw1__led",
            "platform": "light",
            "name": "LED",
            "supported_color_modes": ["rgb", "color_temp"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity._state = {"state": "on", "rgb_color": [255, 64, 0]}
    entity._apply_state()
    assert entity._attr_color_mode == ColorMode.RGB
    assert entity._attr_rgb_color == (255, 64, 0)


def test_cover_features_default_and_unknown_ignored():
    default = cover_features(None)
    assert default & CoverEntityFeature.OPEN
    assert default & CoverEntityFeature.CLOSE
    assert default & CoverEntityFeature.STOP
    flags = cover_features(["open", "set_position", "nope"])
    assert flags & CoverEntityFeature.OPEN
    assert flags & CoverEntityFeature.SET_POSITION
    assert not (flags & CoverEntityFeature.CLOSE)


def test_cover_is_closed_none_when_unknown():
    """position/state 둘 다 없으면 None — False 면 열린 것처럼 오표시."""
    from custom_components.ws_bridge.cover import WsBridgeCover

    bridge = WsBridge(MagicMock(), "entry1")
    entity = WsBridgeCover(
        bridge,
        {
            "unique_id": "gw1__blind",
            "platform": "cover",
            "name": "Blind",
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    assert entity.is_closed is None
    entity._state = {"position": 0}
    entity._apply_state()
    assert entity.is_closed is True
    entity._state = {"position": 50}
    entity._apply_state()
    assert entity.is_closed is False
    entity._state = {"state": "closed"}
    entity._attr_current_cover_position = None
    assert entity.is_closed is True


def test_cover_opening_closing_override_position():
    """position=0 이어도 state=opening 이면 HA 가 OPENING 으로 표시해야 한다."""
    from custom_components.ws_bridge.cover import WsBridgeCover

    bridge = WsBridge(MagicMock(), "entry1")
    entity = WsBridgeCover(
        bridge,
        {
            "unique_id": "gw1__blind",
            "platform": "cover",
            "name": "Blind",
            "features": ["open", "close", "set_position"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity._state = {"state": "opening", "position": 0}
    entity._apply_state()
    assert entity.is_opening is True
    assert entity.is_closing is False
    assert entity.is_closed is True  # position 기준 — HA state 는 is_opening 우선
    entity._state = {"state": "closing", "position": 100}
    entity._apply_state()
    assert entity.is_closing is True


def test_fan_features_default_and_unknown_ignored():
    default = fan_features(None)
    assert default & FanEntityFeature.TURN_ON
    assert default & FanEntityFeature.SET_SPEED
    flags = fan_features(["oscillate", "ghost"])
    assert flags & FanEntityFeature.OSCILLATE
    assert not (flags & FanEntityFeature.SET_SPEED)


def test_fan_set_percentage_zero_turns_off():
    from custom_components.ws_bridge.fan import WsBridgeFan

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.send_command = MagicMock(return_value=True)
    entity = WsBridgeFan(
        bridge,
        {
            "unique_id": "gw1__fan",
            "platform": "fan",
            "name": "Fan",
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity._state = {"state": "on", "percentage": 40}
    entity._apply_state()
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    import asyncio

    asyncio.run(entity.async_set_percentage(0))
    assert entity._state["state"] == "off"
    assert entity._attr_is_on is False
    assert entity._attr_percentage == 0

# ── Phase 2: text / lock / date / time / datetime / event / valve ────────────

def test_text_and_text_sensor_are_distinct_platforms():
    from custom_components.ws_bridge.const import PLATFORM_TEXT, PLATFORM_TEXT_SENSOR, ALL_PLATFORMS
    assert PLATFORM_TEXT == "text"
    assert PLATFORM_TEXT_SENSOR == "text_sensor"
    assert PLATFORM_TEXT in ALL_PLATFORMS
    assert PLATFORM_TEXT_SENSOR in ALL_PLATFORMS
    assert PLATFORM_TEXT != PLATFORM_TEXT_SENSOR


def test_lock_features_and_state_parser():
    from custom_components.ws_bridge.lock import WsBridgeLock

    assert lock_features(["open"]) & LockEntityFeature.OPEN
    assert lock_features(None) == LockEntityFeature(0)

    bridge = WsBridge(MagicMock(), "entry1")
    entity = WsBridgeLock(
        bridge,
        {
            "unique_id": "gw1__door",
            "platform": "lock",
            "name": "Door",
            "features": ["open"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity._apply("locking")
    assert entity._attr_is_locking is True
    assert entity._attr_is_locked is False
    entity._apply("jammed")
    assert entity._attr_is_jammed is True
    entity._apply(True)
    assert entity._attr_is_locked is True
    entity._apply("unknown")
    assert entity._attr_is_locked is None


def test_date_time_datetime_parsers():
    from datetime import date, time, datetime, timezone, timedelta
    from homeassistant.util import dt as dt_util

    assert _parse_date("2026-08-13") == date(2026, 8, 13)
    assert _parse_date("nope") is None
    assert _parse_date(None) is None
    assert _parse_time("07:30:00") == time(7, 30, 0)
    assert _parse_time("bad") is None
    aware = _parse_datetime("2026-08-13T07:30:00+09:00")
    assert aware == datetime(2026, 8, 13, 7, 30, tzinfo=timezone(timedelta(hours=9)))
    naive = _parse_datetime("2026-08-13T07:30:00")
    assert naive == datetime(2026, 8, 13, 7, 30, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    assert naive.tzinfo is not None
    assert _parse_datetime("garbage") is None


def test_event_ignores_undeclared_and_skips_last_state_restore():
    from custom_components.ws_bridge.event import WsBridgeEvent

    bridge = WsBridge(MagicMock(), "entry1")
    bridge._states["gw1__btn"] = "pressed"
    entity = WsBridgeEvent(
        bridge,
        {
            "unique_id": "gw1__btn",
            "platform": "event",
            "name": "Button",
            "event_types": ["pressed", "held"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    assert not hasattr(entity, "_last_triggered")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._on_value("pressed")
    assert entity._last_triggered[0] == "pressed"
    entity._on_value("ghost")
    assert entity._last_triggered[0] == "pressed"  # unchanged
    entity._on_value({"event_type": "held", "attributes": {"x": 1}})
    assert entity._last_triggered == ("held", {"x": 1})


def test_valve_features_default():
    flags = valve_features(None)
    assert flags & ValveEntityFeature.OPEN
    assert flags & ValveEntityFeature.SET_POSITION
    flags = valve_features(None, reports_position=False)
    assert flags & ValveEntityFeature.OPEN
    assert not (flags & ValveEntityFeature.SET_POSITION)
    flags = valve_features(["open", "set_position"], reports_position=False)
    assert flags & ValveEntityFeature.OPEN
    assert not (flags & ValveEntityFeature.SET_POSITION)
    flags = valve_features(["open", "nope"])
    assert flags & ValveEntityFeature.OPEN
    assert not (flags & ValveEntityFeature.CLOSE)


# ── Phase 3: climate / humidifier / water_heater / siren / alarm ─────────────

def test_climate_hvac_modes_and_features():
    from custom_components.ws_bridge.climate import _hvac_modes, _features
    from homeassistant.components.climate import ClimateEntityFeature, HVACMode

    assert _hvac_modes(None) == [HVACMode.OFF]
    assert _hvac_modes(["heat", "nope", "cool"]) == [HVACMode.HEAT, HVACMode.COOL]
    flags = _features(None, has_off=True)
    assert flags & ClimateEntityFeature.TARGET_TEMPERATURE
    assert flags & ClimateEntityFeature.TURN_ON
    assert flags & ClimateEntityFeature.TURN_OFF
    flags = _features(None, has_off=False)
    assert not (flags & ClimateEntityFeature.TURN_OFF)
    flags = _features(["turn_off", "target_temperature"], has_off=False)
    assert not (flags & ClimateEntityFeature.TURN_OFF)


def test_climate_apply_and_set_temperature():
    from custom_components.ws_bridge.climate import WsBridgeClimate
    from homeassistant.components.climate import HVACMode

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.send_command = MagicMock(return_value=True)
    entity = WsBridgeClimate(
        bridge,
        {
            "unique_id": "gw1__ac",
            "platform": "climate",
            "name": "AC",
            "hvac_modes": ["off", "cool", "heat"],
            "features": ["target_temperature", "turn_on", "turn_off"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._on_value(
        {
            "hvac_mode": "cool",
            "hvac_action": "cooling",
            "current_temperature": 28,
            "target_temperature": 24,
        }
    )
    assert entity._attr_hvac_mode == HVACMode.COOL
    assert entity._attr_target_temperature == 24.0

    asyncio.run(entity.async_set_temperature(temperature=22))
    bridge.send_command.assert_called_with(
        "gw1__ac", "set_temperature", params={"temperature": 22}
    )
    assert entity._attr_target_temperature == 22


def test_humidifier_and_water_heater_basics():
    from custom_components.ws_bridge.humidifier import WsBridgeHumidifier, _features as hum_features
    from custom_components.ws_bridge.water_heater import (
        WsBridgeWaterHeater,
        _features as wh_features,
    )
    from homeassistant.components.humidifier import HumidifierAction, HumidifierEntityFeature
    from homeassistant.components.water_heater import WaterHeaterEntityFeature
    from homeassistant.const import UnitOfTemperature

    assert not (hum_features(["modes"], has_modes=False) & HumidifierEntityFeature.MODES)
    assert hum_features(None, has_modes=True) & HumidifierEntityFeature.MODES
    assert not (
        wh_features(None, has_operation_list=False) & WaterHeaterEntityFeature.OPERATION_MODE
    )
    assert (
        wh_features(None, has_operation_list=True) & WaterHeaterEntityFeature.OPERATION_MODE
    )

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.send_command = MagicMock(return_value=True)
    hum = WsBridgeHumidifier(
        bridge,
        {
            "unique_id": "gw1__hum",
            "platform": "humidifier",
            "name": "Hum",
            "available_modes": ["auto", "sleep"],
            "features": ["modes"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    hum.hass = MagicMock()
    hum.async_write_ha_state = MagicMock()
    hum._on_value(
        {"state": "on", "target_humidity": 45, "mode": "auto", "action": "humidifying"}
    )
    assert hum._attr_is_on is True
    assert hum._attr_target_humidity == 45.0
    assert hum._attr_action == HumidifierAction.HUMIDIFYING

    wh = WsBridgeWaterHeater(
        bridge,
        {
            "unique_id": "gw1__wh",
            "platform": "water_heater",
            "name": "WH",
            "operation_list": ["eco", "performance", "off"],
            "temperature_unit": "F",
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    wh.hass = MagicMock()
    wh.async_write_ha_state = MagicMock()
    assert wh._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT
    wh._on_value({"state": "eco", "target_temperature": 50, "away_mode": False})
    assert wh._attr_current_operation == "eco"
    assert wh._attr_is_away_mode_on is False


def test_siren_and_alarm_control_panel():
    from custom_components.ws_bridge.siren import WsBridgeSiren, _features as siren_features
    from custom_components.ws_bridge.alarm_control_panel import WsBridgeAlarmControlPanel
    from homeassistant.components.alarm_control_panel import (
        AlarmControlPanelState,
        CodeFormat,
    )
    from homeassistant.components.siren import SirenEntityFeature
    from homeassistant.exceptions import HomeAssistantError

    assert not (siren_features(["tones"], has_tones=False) & SirenEntityFeature.TONES)
    assert siren_features(None, has_tones=True) & SirenEntityFeature.TONES

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.send_command = MagicMock(return_value=True)

    siren = WsBridgeSiren(
        bridge,
        {
            "unique_id": "gw1__siren",
            "platform": "siren",
            "name": "Siren",
            "available_tones": ["alarm", "chime"],
            "features": ["turn_on", "turn_off", "tones", "volume_set"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    siren.async_write_ha_state = MagicMock()
    siren._apply(True)
    assert siren._attr_is_on is True

    alarm = WsBridgeAlarmControlPanel(
        bridge,
        {
            "unique_id": "gw1__alarm",
            "platform": "alarm_control_panel",
            "name": "Alarm",
            "code_format": "number",
            "features": ["arm_home", "arm_away", "trigger"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    alarm.async_write_ha_state = MagicMock()
    assert alarm._attr_code_format == CodeFormat.NUMBER
    alarm._apply("armed_away")
    assert alarm._attr_alarm_state == AlarmControlPanelState.ARMED_AWAY
    asyncio.run(alarm.async_alarm_disarm(code="1234"))
    bridge.send_command.assert_called_with(
        "gw1__alarm", "alarm_disarm", params={"code": "1234"}
    )
    assert alarm._attr_alarm_state == AlarmControlPanelState.DISARMED

    bridge.send_command = MagicMock(return_value=False)
    alarm._apply("armed_away")
    try:
        asyncio.run(alarm.async_alarm_disarm(code="1234"))
        raise AssertionError("expected HomeAssistantError")
    except HomeAssistantError:
        pass
    assert alarm._attr_alarm_state == AlarmControlPanelState.ARMED_AWAY


def test_phase3_platforms_registered():
    from custom_components.ws_bridge.const import (
        PLATFORM_CLIMATE,
        PLATFORM_HUMIDIFIER,
        PLATFORM_WATER_HEATER,
        PLATFORM_SIREN,
        PLATFORM_ALARM_CONTROL_PANEL,
        ALL_PLATFORMS,
    )

    for p in (
        PLATFORM_CLIMATE,
        PLATFORM_HUMIDIFIER,
        PLATFORM_WATER_HEATER,
        PLATFORM_SIREN,
        PLATFORM_ALARM_CONTROL_PANEL,
    ):
        assert p in ALL_PLATFORMS


# ── Phase 4: media_player / image / camera + version pin ─────────────────────

def test_media_player_features_and_state():
    from custom_components.ws_bridge.media_player import (
        WsBridgeMediaPlayer,
        _features,
    )
    from homeassistant.components.media_player import (
        MediaPlayerEntityFeature,
        MediaPlayerState,
    )

    flags = _features(None, has_sources=False)
    assert flags & MediaPlayerEntityFeature.PLAY
    assert not (flags & MediaPlayerEntityFeature.SELECT_SOURCE)
    assert _features(["play"], has_sources=True) & MediaPlayerEntityFeature.SELECT_SOURCE

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.send_command = MagicMock(return_value=True)
    entity = WsBridgeMediaPlayer(
        bridge,
        {
            "unique_id": "gw1__speaker",
            "platform": "media_player",
            "name": "Speaker",
            "source_list": ["HDMI", "Bluetooth"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._on_value(
        {
            "state": "playing",
            "volume_level": 0.4,
            "media_title": "Song",
            "source": "HDMI",
            "media_position": 42,
        }
    )
    assert entity._attr_state == MediaPlayerState.PLAYING
    assert entity._attr_volume_level == 0.4
    assert entity._attr_source == "HDMI"
    assert entity._attr_media_position == 42
    assert entity._attr_media_position_updated_at is not None
    stamped = entity._attr_media_position_updated_at
    entity._on_value(
        {
            "state": "playing",
            "volume_level": 0.5,
            "media_title": "Song",
            "source": "HDMI",
            "media_position": 42,
        }
    )
    assert entity._attr_media_position_updated_at is stamped
    entity._on_value(
        {
            "state": "playing",
            "volume_level": 0.5,
            "media_title": "Song",
            "source": "HDMI",
            "media_position": 50,
        }
    )
    assert entity._attr_media_position == 50
    assert entity._attr_media_position_updated_at is not stamped
    asyncio.run(entity.async_media_pause())
    bridge.send_command.assert_called_with("gw1__speaker", "media_pause")
    assert entity._attr_state == MediaPlayerState.PAUSED


def test_image_and_camera_url_state():
    from custom_components.ws_bridge.image import WsBridgeImage
    from custom_components.ws_bridge.camera import WsBridgeCamera, _features
    from custom_components.ws_bridge.helpers import sanitize_remote_url
    from homeassistant.components.camera import CameraEntityFeature

    assert sanitize_remote_url("http://cam.local/still.jpg")
    assert sanitize_remote_url("http://127.0.0.1/x") is None
    assert sanitize_remote_url("file:///etc/passwd") is None
    assert sanitize_remote_url(
        "rtsp://cam.local/stream", schemes=("http", "https", "rtsp", "rtsps")
    )

    assert not (_features(["stream"], has_stream=False) & CameraEntityFeature.STREAM)
    assert _features(None, has_stream=True) & CameraEntityFeature.STREAM

    bridge = WsBridge(MagicMock(), "entry1")
    bridge.hass = MagicMock()
    img = WsBridgeImage(
        bridge,
        {
            "unique_id": "gw1__snap",
            "platform": "image",
            "name": "Snap",
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    img.hass = MagicMock()
    img.async_write_ha_state = MagicMock()
    img._on_value({"image_url": "http://cam.local/still.jpg"})
    assert img._attr_image_url == "http://cam.local/still.jpg"
    assert img._attr_image_last_updated is not None
    first_updated = img._attr_image_last_updated
    img._on_value({"image_url": "http://cam.local/still.jpg", "extra": 1})
    assert img._attr_image_last_updated is first_updated
    img._on_value({"image_url": "http://cam.local/still2.jpg"})
    assert img._attr_image_last_updated is not first_updated

    cam = WsBridgeCamera(
        bridge,
        {
            "unique_id": "gw1__cam",
            "platform": "camera",
            "name": "Cam",
            "features": ["on_off", "stream"],
            "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
        },
    )
    cam.hass = MagicMock()
    cam.async_write_ha_state = MagicMock()
    cam._on_value(
        {
            "still_image_url": "http://cam.local/still.jpg",
            "stream_source": "rtsp://cam.local/stream",
            "is_on": True,
        }
    )
    assert cam._still_url.endswith("still.jpg")
    assert asyncio.run(cam.stream_source()) == "rtsp://cam.local/stream"
    assert cam._attr_supported_features & CameraEntityFeature.STREAM
    cam._on_value({"still_image_url": "http://127.0.0.1/admin", "is_on": True})
    assert cam._still_url is None




def _mk_entity(cls, platform, uid, seed, extra_defn=None):
    """seed 상태를 미리 넣은 bridge + 연결된 클라이언트로 엔티티를 만든다."""
    bridge = WsBridge(MagicMock(), "entry1")
    bridge._clients["gw1"] = _Client("gw1", "GW", MagicMock())
    bridge._entity_client[f"gw1__{uid}"] = "gw1"
    defn = {
        "unique_id": f"gw1__{uid}",
        "platform": platform,
        "name": "X",
        "_device": {"ns_id": "gw1", "gateway_id": "gw1", "is_gateway": True},
    }
    defn.update(extra_defn or {})
    with patch("custom_components.ws_bridge.bridge.async_dispatcher_send"):
        bridge.handle_state("gw1", uid, seed)
    entity = cls(bridge, defn)
    entity.hass = MagicMock()
    entity.async_write_ha_state = lambda: None
    return bridge, entity, defn


def test_publish_state_does_not_persist_transient_cover_state():
    """opening 은 낙관적 표시일 뿐 — 저장하면 재시작 후 'Opening' 으로 고착된다."""
    from custom_components.ws_bridge.cover import WsBridgeCover

    bridge, entity, defn = _mk_entity(
        WsBridgeCover, "cover", "bl", {"state": "closed", "position": 0}
    )
    asyncio.run(entity.async_open_cover())

    assert entity.is_opening is True                      # UI 는 즉시 반응
    assert bridge._states["gw1__bl"]["state"] == "closed"  # 저장본은 그대로

    restored = WsBridgeCover(bridge, defn)
    restored.hass = MagicMock()
    restored._apply_state()
    assert restored.is_opening is False


def test_publish_state_does_not_persist_update_in_progress():
    """플래시 중 기기가 사라져도 재시작 후 'Installing…' 이 남으면 안 된다."""
    from custom_components.ws_bridge.update import WsBridgeUpdate

    bridge, entity, defn = _mk_entity(
        WsBridgeUpdate, "update", "fw",
        {"installed_version": "1.0.0", "latest_version": "1.0.1", "in_progress": False},
    )
    asyncio.run(entity.async_install(None, False))

    assert entity._attr_in_progress is True
    assert bridge._states["gw1__fw"]["in_progress"] is False

    restored = WsBridgeUpdate(bridge, defn)
    restored.hass = MagicMock()
    restored._apply_state()
    assert restored._attr_in_progress is False


def test_install_clears_stale_progress_percentage():
    """이전 설치의 progress:100 이 낙관적 UI에 100%로 깜빡이면 안 된다."""
    from custom_components.ws_bridge.update import WsBridgeUpdate

    bridge, entity, _ = _mk_entity(
        WsBridgeUpdate,
        "update",
        "fw",
        {
            "installed_version": "1.0.0",
            "latest_version": "1.0.1",
            "in_progress": False,
            "progress": 100,
        },
    )
    assert entity._attr_update_percentage is None  # not in_progress → hidden

    asyncio.run(entity.async_install(None, False))

    assert entity._attr_in_progress is True
    assert entity._attr_update_percentage is None
    assert entity._state.get("progress") is None


def test_update_refresh_hook_is_silent_when_disconnected():
    """async_update 는 사용자 명령이 아니라 새로고침 훅 — 예외를 던지면 안 된다."""
    from custom_components.ws_bridge.update import WsBridgeUpdate

    bridge, entity, _ = _mk_entity(
        WsBridgeUpdate, "update", "fw", {"installed_version": "1.0.0"}
    )
    bridge._clients.clear()   # 게이트웨이 끊김

    asyncio.run(entity.async_update())   # 예외 없이 통과해야 한다
