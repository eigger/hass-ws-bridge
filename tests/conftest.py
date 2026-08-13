"""pytest configuration — mock Home Assistant modules to allow testing without HA installed."""
import sys
from enum import IntFlag
from unittest.mock import MagicMock


class MockBase:
    """Mock base class to support generic subclassing."""
    def __init__(self, *args, **kwargs):
        pass

    def __class_getitem__(cls, item):
        return cls


def mock_callback(func):
    """Mock for homeassistant.core.callback decorator."""
    return func


class Platform:
    """HA Platform enum stand-in with real string values for pure tests."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    DEVICE_TRACKER = "device_tracker"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"
    BUTTON = "button"
    UPDATE = "update"
    LIGHT = "light"
    COVER = "cover"
    FAN = "fan"
    TEXT = "text"
    LOCK = "lock"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    EVENT = "event"
    VALVE = "valve"
    CLIMATE = "climate"
    HUMIDIFIER = "humidifier"
    WATER_HEATER = "water_heater"
    SIREN = "siren"
    ALARM_CONTROL_PANEL = "alarm_control_panel"
    MEDIA_PLAYER = "media_player"
    IMAGE = "image"
    CAMERA = "camera"
    VACUUM = "vacuum"
    LAWN_MOWER = "lawn_mower"
    REMOTE = "remote"
    TODO = "todo"


class EntityCategory(str):
    """HA EntityCategory stand-in — callable like the real enum (`EntityCategory(cat)`)."""

    def __new__(cls, value: str = ""):
        return str.__new__(cls, value)


EntityCategory.CONFIG = EntityCategory("config")
EntityCategory.DIAGNOSTIC = EntityCategory("diagnostic")


class ColorMode:
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"
    RGB = "rgb"
    RGBW = "rgbw"
    RGBWW = "rgbww"
    WHITE = "white"


class LightEntityFeature(IntFlag):
    EFFECT = 4
    FLASH = 8
    TRANSITION = 32


class CoverEntityFeature(IntFlag):
    OPEN = 1
    CLOSE = 2
    SET_POSITION = 4
    STOP = 8
    OPEN_TILT = 16
    CLOSE_TILT = 32
    STOP_TILT = 64
    SET_TILT_POSITION = 128


class FanEntityFeature(IntFlag):
    SET_SPEED = 1
    OSCILLATE = 2
    DIRECTION = 4
    PRESET_MODE = 8
    TURN_OFF = 16
    TURN_ON = 32


class LockEntityFeature(IntFlag):
    OPEN = 1


class ValveEntityFeature(IntFlag):
    OPEN = 1
    CLOSE = 2
    SET_POSITION = 4
    STOP = 8


class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    TARGET_TEMPERATURE_RANGE = 2
    TARGET_HUMIDITY = 4
    FAN_MODE = 8
    PRESET_MODE = 16
    SWING_MODE = 32
    TURN_OFF = 128
    TURN_ON = 256


class HVACMode:
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"


class HVACAction:
    OFF = "off"
    HEATING = "heating"
    COOLING = "cooling"
    DRYING = "drying"
    FAN = "fan"
    IDLE = "idle"
    PREHEATING = "preheating"
    DEFROSTING = "defrosting"


class HumidifierEntityFeature(IntFlag):
    MODES = 1


class HumidifierAction:
    HUMIDIFYING = "humidifying"
    DRYING = "drying"
    IDLE = "idle"
    OFF = "off"


class WaterHeaterEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    OPERATION_MODE = 2
    AWAY_MODE = 4
    ON_OFF = 8


class SirenEntityFeature(IntFlag):
    TURN_ON = 1
    TURN_OFF = 2
    TONES = 4
    DURATION = 8
    VOLUME_SET = 16


class AlarmControlPanelEntityFeature(IntFlag):
    ARM_HOME = 1
    ARM_AWAY = 2
    ARM_NIGHT = 4
    ARM_VACATION = 8
    ARM_CUSTOM_BYPASS = 16
    TRIGGER = 32


class CodeFormat:
    NUMBER = "number"
    TEXT = "text"


class AlarmControlPanelState:
    DISARMED = "disarmed"
    ARMED_HOME = "armed_home"
    ARMED_AWAY = "armed_away"
    ARMED_NIGHT = "armed_night"
    ARMED_VACATION = "armed_vacation"
    ARMED_CUSTOM_BYPASS = "armed_custom_bypass"
    ARMING = "arming"
    PENDING = "pending"
    TRIGGERED = "triggered"


class UnitOfTemperature:
    CELSIUS = "°C"
    FAHRENHEIT = "°F"


class TextMode:
    TEXT = "text"
    PASSWORD = "password"


class MockEventEntity(MockBase):
    def _trigger_event(self, event_type, event_attributes=None):
        self._last_triggered = (event_type, event_attributes or {})


# Set up core mocks
sys.modules["homeassistant"] = MagicMock()

mock_const = MagicMock()
mock_const.Platform = Platform
mock_const.EntityCategory = EntityCategory
sys.modules["homeassistant.const"] = mock_const

# Mock homeassistant.core
mock_core = MagicMock()
mock_core.callback = mock_callback
sys.modules["homeassistant.core"] = mock_core

# Mock homeassistant.config_entries
mock_config_entries = MagicMock()
sys.modules["homeassistant.config_entries"] = mock_config_entries

# Mock homeassistant.helpers.entity
mock_entity = MagicMock()
mock_entity.Entity = MockBase
sys.modules["homeassistant.helpers.entity"] = mock_entity

# Mock homeassistant.helpers.storage
mock_storage = MagicMock()
mock_storage.Store = MockBase
sys.modules["homeassistant.helpers.storage"] = mock_storage

# Mock other helper modules
for mod in [
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.event",
    "homeassistant.helpers.entity_platform",
    "homeassistant.components",
    "homeassistant.components.websocket_api",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.device_tracker",
    "homeassistant.components.switch",
    "homeassistant.components.number",
    "homeassistant.components.select",
    "homeassistant.components.button",
    "homeassistant.components.update",
    "homeassistant.components.light",
    "homeassistant.components.cover",
    "homeassistant.components.fan",
    "homeassistant.components.text",
    "homeassistant.components.lock",
    "homeassistant.components.date",
    "homeassistant.components.time",
    "homeassistant.components.datetime",
    "homeassistant.components.event",
    "homeassistant.components.valve",
    "homeassistant.components.climate",
    "homeassistant.components.humidifier",
    "homeassistant.components.water_heater",
    "homeassistant.components.siren",
    "homeassistant.components.alarm_control_panel",
    "homeassistant.exceptions",
    "homeassistant.util.enum",
]:
    sys.modules[mod] = MagicMock()

# device_tracker.TrackerEntity is subclassed, so it must be a real class
# rather than a MagicMock attribute. (Imported from the top-level
# device_tracker module, not .config_entry — that alias is deprecated.)
mock_device_tracker = sys.modules["homeassistant.components.device_tracker"]
mock_device_tracker.TrackerEntity = MockBase

mock_update = sys.modules["homeassistant.components.update"]
mock_update.UpdateEntity = MockBase
mock_update.UpdateEntityFeature = MagicMock()
mock_update.UpdateDeviceClass = MagicMock()

mock_light = sys.modules["homeassistant.components.light"]
mock_light.LightEntity = MockBase
mock_light.ColorMode = ColorMode
mock_light.LightEntityFeature = LightEntityFeature

mock_cover = sys.modules["homeassistant.components.cover"]
mock_cover.CoverEntity = MockBase
mock_cover.CoverEntityFeature = CoverEntityFeature

mock_fan = sys.modules["homeassistant.components.fan"]
mock_fan.FanEntity = MockBase
mock_fan.FanEntityFeature = FanEntityFeature

mock_text = sys.modules["homeassistant.components.text"]
mock_text.TextEntity = MockBase
mock_text.TextMode = TextMode

mock_lock = sys.modules["homeassistant.components.lock"]
mock_lock.LockEntity = MockBase
mock_lock.LockEntityFeature = LockEntityFeature

sys.modules["homeassistant.components.date"].DateEntity = MockBase
sys.modules["homeassistant.components.time"].TimeEntity = MockBase
sys.modules["homeassistant.components.datetime"].DateTimeEntity = MockBase

mock_event = sys.modules["homeassistant.components.event"]
mock_event.EventEntity = MockEventEntity

mock_valve = sys.modules["homeassistant.components.valve"]
mock_valve.ValveEntity = MockBase
mock_valve.ValveEntityFeature = ValveEntityFeature

mock_climate = sys.modules["homeassistant.components.climate"]
mock_climate.ClimateEntity = MockBase
mock_climate.ClimateEntityFeature = ClimateEntityFeature
mock_climate.HVACMode = HVACMode
mock_climate.HVACAction = HVACAction

mock_humidifier = sys.modules["homeassistant.components.humidifier"]
mock_humidifier.HumidifierEntity = MockBase
mock_humidifier.HumidifierEntityFeature = HumidifierEntityFeature
mock_humidifier.HumidifierAction = HumidifierAction

mock_water = sys.modules["homeassistant.components.water_heater"]
mock_water.WaterHeaterEntity = MockBase
mock_water.WaterHeaterEntityFeature = WaterHeaterEntityFeature

mock_siren = sys.modules["homeassistant.components.siren"]
mock_siren.SirenEntity = MockBase
mock_siren.SirenEntityFeature = SirenEntityFeature

mock_alarm = sys.modules["homeassistant.components.alarm_control_panel"]
mock_alarm.AlarmControlPanelEntity = MockBase
mock_alarm.AlarmControlPanelEntityFeature = AlarmControlPanelEntityFeature
mock_alarm.AlarmControlPanelState = AlarmControlPanelState
mock_alarm.CodeFormat = CodeFormat

mock_const.UnitOfTemperature = UnitOfTemperature

# homeassistant.util 을 MagicMock 으로 두면 `from homeassistant.util import dt` 가
# sys.modules['homeassistant.util.dt'] 가 아니라 MagicMock 자식을 돌려준다.
import types

_util_mod = types.ModuleType("homeassistant.util")
_dt_mod = types.ModuleType("homeassistant.util.dt")
_dt_mod.as_local = lambda dt: dt
_dt_mod.DEFAULT_TIME_ZONE = __import__("datetime").timezone(
    __import__("datetime").timedelta(hours=9)
)
_dt_mod.parse_date = lambda value: __import__("datetime").date.fromisoformat(value) if isinstance(value, str) else None
_dt_mod.parse_datetime = lambda value: __import__("datetime").datetime.fromisoformat(value) if isinstance(value, str) else None
_util_mod.dt = _dt_mod
sys.modules["homeassistant.util"] = _util_mod
sys.modules["homeassistant.util.dt"] = _dt_mod
# MagicMock 패키지는 속성 접근 시 sys.modules 를 보지 않으므로 명시적으로 연결
sys.modules["homeassistant"].util = _util_mod

sys.modules["homeassistant.exceptions"].HomeAssistantError = Exception
