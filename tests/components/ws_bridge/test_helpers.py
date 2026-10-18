"""Auxiliary pure parsing/calculation tests, run under the real HA package.

These complement (never replace) the real-HA integration tests in this folder;
they pin edge cases of the value parsers and feature mappers with HA's real enums.
"""

from datetime import date, datetime, time, timedelta, timezone

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature
from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.fan import FanEntityFeature
from homeassistant.components.humidifier import HumidifierEntityFeature
from homeassistant.components.light import ColorMode, LightEntityFeature
from homeassistant.components.lock import LockEntityFeature
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.siren import SirenEntityFeature
from homeassistant.components.valve import ValveEntityFeature
from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ws_bridge import _subentry_gateway_ids
from custom_components.ws_bridge.alarm_control_panel import _features as alarm_features
from custom_components.ws_bridge.bridge import (
    WsBridge,
    signal_avail,
    signal_clients,
    signal_value,
)
from custom_components.ws_bridge.camera import _features as camera_features
from custom_components.ws_bridge.climate import _features as climate_features
from custom_components.ws_bridge.climate import _hvac_modes
from custom_components.ws_bridge.const import (
    ALL_PLATFORMS,
    DOMAIN,
    PLATFORM_TEXT,
    PLATFORM_TEXT_SENSOR,
    PLATFORM_UPDATE,
)
from custom_components.ws_bridge.cover import _features as cover_features
from custom_components.ws_bridge.date import _parse_date
from custom_components.ws_bridge.datetime import _parse_datetime
from custom_components.ws_bridge.device_tracker import _parse_location
from custom_components.ws_bridge.fan import _features as fan_features
from custom_components.ws_bridge.helpers import (
    as_dict,
    is_unknown,
    parse_bool,
    parse_locked,
    sanitize_remote_url,
)
from custom_components.ws_bridge.humidifier import _features as hum_features
from custom_components.ws_bridge.light import _color_modes
from custom_components.ws_bridge.light import _features as light_features
from custom_components.ws_bridge.lock import _features as lock_features
from custom_components.ws_bridge.media_player import _features as media_features
from custom_components.ws_bridge.siren import _features as siren_features
from custom_components.ws_bridge.time import _parse_time
from custom_components.ws_bridge.update import _parse_update_state, _strip_build_suffix
from custom_components.ws_bridge.valve import _features as valve_features
from custom_components.ws_bridge.water_heater import _features as wh_features
from custom_components.ws_bridge.websocket_api import resolve_connect_sw_version


def test_signals() -> None:
    assert signal_value("e", "s1") == "ws_bridge_e_state_s1"
    assert signal_avail("e", "d1") == "ws_bridge_e_avail_d1"
    assert signal_clients("e") == "ws_bridge_e_clients"


def test_bridge_namespacing_helpers() -> None:
    assert WsBridge._client_id_matches("d1", "d1", prefix=False)
    assert not WsBridge._client_id_matches("d1_sub", "d1", prefix=False)
    assert WsBridge._client_id_matches("d1_sub", "d1", prefix=True)
    assert not WsBridge._client_id_matches("d2", "d1", prefix=True)
    assert not WsBridge._client_id_matches("d10", "d1", prefix=True)
    assert WsBridge._client_device_id_from_ns("gw", "gw") == "gw"
    assert WsBridge._client_device_id_from_ns("gw", "gw:d1") == "d1"
    assert WsBridge._client_device_id_from_ns("gw", "other:d1") is None
    assert WsBridge._ns_uid("gw", "s") == "gw__s"
    assert WsBridge._ns_dev("gw", "d") == "gw:d"
    assert WsBridge._strip("gw", "gw__s") == "s"
    assert WsBridge._strip("gw", "other__s") == "other__s"


def test_subentry_gateway_ids(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        subentries_data=[
            ConfigSubentryData(
                data={"gateway_id": "gw1"},
                subentry_type="gateway",
                title="1",
                unique_id="gw1",
            ),
            ConfigSubentryData(
                data={"gateway_id": "gw2", "name": "G2"},
                subentry_type="gateway",
                title="2",
                unique_id="gw2",
            ),
            ConfigSubentryData(
                data={"name": "no id"},
                subentry_type="gateway",
                title="3",
                unique_id=None,
            ),
        ],
    )
    assert _subentry_gateway_ids(entry) == {"gw1", "gw2"}


def test_platform_constants() -> None:
    assert PLATFORM_UPDATE in ALL_PLATFORMS
    assert PLATFORM_TEXT == "text"
    assert PLATFORM_TEXT_SENSOR == "text_sensor"
    assert {PLATFORM_TEXT, PLATFORM_TEXT_SENSOR} <= set(ALL_PLATFORMS)


def test_resolve_connect_sw_version() -> None:
    assert (
        resolve_connect_sw_version({"sw_version": "2.0", "app_version": "1"}) == "2.0"
    )
    assert resolve_connect_sw_version({"app_version": " 1.0 "}) == "1.0"
    assert resolve_connect_sw_version({"sw_version": "  ", "app_version": "1"}) == "1"
    assert resolve_connect_sw_version({"sw_version": None}) is None
    assert resolve_connect_sw_version({}) is None


def test_parse_bool_and_locked() -> None:
    for truthy in ("1", "TRUE", "on", "yes", 1, True):
        assert parse_bool(truthy) is True
    for falsy in ("open", "locked", "0", 0, False):
        assert parse_bool(falsy) is False
    assert parse_bool("unknown") is None
    assert parse_bool(None) is None
    assert parse_locked("locked") is True
    assert parse_locked("lock") is True
    assert parse_locked("open") is False
    assert parse_locked("unknown") is None


def test_is_unknown_and_as_dict_copies() -> None:
    assert is_unknown(None)
    assert is_unknown("UNKNOWN")
    assert not is_unknown("on")
    assert not is_unknown(0)
    src = {"a": 1}
    out = as_dict(src)
    assert out == src
    assert out is not src
    out["a"] = 2
    assert src["a"] == 1
    assert as_dict("on") == {"state": "on"}
    assert as_dict(None) == {}
    assert as_dict("unknown") == {}


def test_sanitize_remote_url() -> None:
    assert sanitize_remote_url("http://cam.local/still.jpg")
    assert sanitize_remote_url("https://192.168.1.10/x")  # LAN allowed
    assert sanitize_remote_url("http://127.0.0.1/x") is None
    assert sanitize_remote_url("http://[::1]/x") is None
    assert sanitize_remote_url("http://localhost./x") is None
    assert sanitize_remote_url("http://metadata.google.internal/") is None
    assert sanitize_remote_url("http://169.254.169.254/") is None
    assert sanitize_remote_url("http://0.0.0.0/") is None
    assert sanitize_remote_url("http://224.0.0.1/") is None
    assert sanitize_remote_url("file:///etc/passwd") is None
    assert sanitize_remote_url("   ") is None
    assert sanitize_remote_url(None) is None
    assert sanitize_remote_url("http:///nohost") is None
    assert sanitize_remote_url("rtsp://cam.local/s") is None
    assert sanitize_remote_url(
        "rtsp://cam.local/s", schemes=("http", "https", "rtsp", "rtsps")
    )


def test_parse_location() -> None:
    assert _parse_location(
        {"latitude": 37.5, "longitude": 127.0, "gps_accuracy": 8}
    ) == (
        37.5,
        127.0,
        8,
    )
    assert _parse_location({"latitude": "37.5", "longitude": "127"}) == (37.5, 127.0, 0)
    assert _parse_location({"latitude": 37.5}) == (None, None, 0)
    assert _parse_location({"latitude": True, "longitude": 1}) == (None, None, 0)
    assert _parse_location(
        {"latitude": None, "longitude": None, "gps_accuracy": 9999}
    ) == (
        None,
        None,
        9999,
    )
    for bad in ("unknown", None, 37.5):
        assert _parse_location(bad) == (None, None, 0)


def test_parse_update_state() -> None:
    full = _parse_update_state(
        {
            "installed_version": "1.0.0",
            "latest_version": " 1.0.1 ",
            "in_progress": True,
            "progress": 45,
            "title": "",
        }
    )
    assert full["latest_version"] == "1.0.1"
    assert full["progress"] == 45
    assert full["title"] is None
    assert (
        _parse_update_state({"in_progress": False, "progress": 80})["progress"] is None
    )
    assert (
        _parse_update_state({"in_progress": True, "progress": 150})["progress"] == 100
    )
    empty = _parse_update_state("unknown")
    assert empty["installed_version"] is None
    assert empty["in_progress"] is False
    assert _strip_build_suffix("1.0.0") == "1.0.0"
    assert _strip_build_suffix("2025.11.5_c51f7548") == "2025.11.5"
    assert _strip_build_suffix("1.0.0_foo_bar") == "1.0.0"
    assert _strip_build_suffix("_only") == ""


def test_date_time_parsers() -> None:
    assert _parse_date("2026-08-13") == date(2026, 8, 13)
    assert _parse_date("nope") is None
    assert _parse_date(None) is None
    assert _parse_time("07:30:00") == time(7, 30)
    assert _parse_time("bad") is None
    aware = _parse_datetime("2026-08-13T07:30:00+09:00")
    assert aware == datetime(2026, 8, 13, 7, 30, tzinfo=timezone(timedelta(hours=9)))
    naive = _parse_datetime("2026-08-13T07:30:00")
    assert naive == datetime(2026, 8, 13, 7, 30, tzinfo=dt_util.get_default_time_zone())
    assert _parse_datetime("garbage") is None


def test_light_mappers() -> None:
    assert _color_modes(None) == {ColorMode.ONOFF}
    assert _color_modes(["rgb", "nope"]) == {ColorMode.RGB}
    assert _color_modes(["brightness", "rgb"]) == {ColorMode.RGB}
    assert _color_modes(["onoff", "brightness"]) == {ColorMode.BRIGHTNESS}
    flags = light_features(["transition", "unknown"], has_effects=True)
    assert flags & LightEntityFeature.TRANSITION
    assert flags & LightEntityFeature.EFFECT
    assert light_features(None, has_effects=False) == LightEntityFeature(0)


def test_cover_fan_lock_valve_features() -> None:
    default = cover_features(None)
    assert default & CoverEntityFeature.OPEN
    assert default & CoverEntityFeature.STOP
    flags = cover_features(["open", "set_position", "nope"])
    assert flags & CoverEntityFeature.SET_POSITION
    assert not flags & CoverEntityFeature.CLOSE
    assert fan_features(None) & FanEntityFeature.SET_SPEED
    flags = fan_features(["oscillate", "ghost"])
    assert flags & FanEntityFeature.OSCILLATE
    assert not flags & FanEntityFeature.SET_SPEED
    assert lock_features(["open"]) & LockEntityFeature.OPEN
    assert lock_features(None) == LockEntityFeature(0)
    assert valve_features(None) & ValveEntityFeature.SET_POSITION
    assert not valve_features(None, reports_position=False) & (
        ValveEntityFeature.SET_POSITION
    )
    assert not valve_features(["open", "set_position"], reports_position=False) & (
        ValveEntityFeature.SET_POSITION
    )
    assert not valve_features(["open", "nope"]) & ValveEntityFeature.CLOSE


def test_climate_and_comfort_features() -> None:
    assert _hvac_modes(None) == [HVACMode.OFF]
    assert _hvac_modes(["HEAT", "nope", "cool"]) == [HVACMode.HEAT, HVACMode.COOL]
    flags = climate_features(None, has_off=True)
    assert flags & ClimateEntityFeature.TARGET_TEMPERATURE
    assert flags & ClimateEntityFeature.TURN_OFF
    assert not climate_features(None, has_off=False) & ClimateEntityFeature.TURN_OFF
    assert not climate_features(["turn_off"], has_off=False) & (
        ClimateEntityFeature.TURN_OFF
    )
    assert not hum_features(["modes"], has_modes=False) & HumidifierEntityFeature.MODES
    assert hum_features(None, has_modes=True) & HumidifierEntityFeature.MODES
    assert not wh_features(None, has_operation_list=False) & (
        WaterHeaterEntityFeature.OPERATION_MODE
    )
    assert wh_features(None, has_operation_list=True) & (
        WaterHeaterEntityFeature.OPERATION_MODE
    )


def test_siren_alarm_media_camera_features() -> None:
    assert not siren_features(["tones"], has_tones=False) & SirenEntityFeature.TONES
    assert siren_features(None, has_tones=True) & SirenEntityFeature.TONES
    assert alarm_features(None)
    assert alarm_features(["arm_away"]) & AlarmControlPanelEntityFeature.ARM_AWAY
    assert not alarm_features(["arm_away"]) & AlarmControlPanelEntityFeature.ARM_HOME
    flags = media_features(None, has_sources=False)
    assert flags & MediaPlayerEntityFeature.PLAY
    assert not flags & MediaPlayerEntityFeature.SELECT_SOURCE
    assert media_features(["play"], has_sources=True) & (
        MediaPlayerEntityFeature.SELECT_SOURCE
    )
    assert (
        not camera_features(["stream"], has_stream=False) & CameraEntityFeature.STREAM
    )
    assert camera_features(None, has_stream=True) & CameraEntityFeature.STREAM
