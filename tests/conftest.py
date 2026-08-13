"""pytest configuration — mock Home Assistant modules to allow testing without HA installed."""
import sys
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
    UPDATE = "update"
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
    "homeassistant.exceptions",
    "homeassistant.util",
    "homeassistant.util.dt",
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

sys.modules["homeassistant.exceptions"].HomeAssistantError = Exception
