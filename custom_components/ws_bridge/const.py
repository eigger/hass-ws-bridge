"""ws_bridge 상수.

범용 WebSocket 엔티티 브릿지 — BLE 등 특정 형식과 무관하게, 인증된 어떤 클라이언트든
프로토콜대로 엔티티를 선언/갱신하면 HA 엔티티를 만들어 준다.
"""

DOMAIN = "ws_bridge"

SUBENTRY_TYPE_GATEWAY = "gateway"

# 통합 진단 센서 unique_id 접미사
CONNECTED_CLIENTS_UNIQUE_ID = "connected_clients"

# 아이콘 (MDI)
ICON_BRIDGE = "mdi:swap-horizontal"
ICON_CONNECTED_CLIENTS = "mdi:account-multiple"
ICON_GATEWAY = "mdi:router-wireless"

# WebSocket 명령 타입 (PROTOCOL.md). 도메인 접두어를 따른다.
WS_CONNECT = f"{DOMAIN}/connect"
WS_ENTITY = f"{DOMAIN}/entity"
WS_STATE = f"{DOMAIN}/state"
WS_AVAILABILITY = f"{DOMAIN}/availability"
WS_REMOVE = f"{DOMAIN}/remove"
WS_SYNC = f"{DOMAIN}/sync"

# ws_bridge/remove mode (PROTOCOL.md §3.4)
REMOVE_MODE_EXACT = "exact"
REMOVE_MODE_PREFIX = "prefix"
REMOVE_MODES = (REMOVE_MODE_EXACT, REMOVE_MODE_PREFIX)

# HA→클라이언트 이벤트 kind
EVT_COMMAND = "command"

# ws_bridge/connect 선택 필드 — 켜두면 이 게이트웨이는 연결이 끊겨도(비정상 종료 포함)
# 엔티티를 unavailable로 만들지 않고 마지막 상태를 유지한다(MQTT retain과 유사).
# 클라이언트가 접속 시 선언하며, 서버는 다음 접속까지 그 값을 기억한다.
CONF_KEEP_LAST_STATE_ON_DISCONNECT = "keep_last_state_on_disconnect"
DEFAULT_KEEP_LAST_STATE_ON_DISCONNECT = False

# 기본 지원 플랫폼 (읽기: sensor/binary_sensor/text_sensor, 제어: switch/number/select/button/update)
PLATFORM_SENSOR = "sensor"
PLATFORM_BINARY_SENSOR = "binary_sensor"
PLATFORM_TEXT_SENSOR = "text_sensor"
PLATFORM_DEVICE_TRACKER = "device_tracker"
PLATFORM_SWITCH = "switch"
PLATFORM_NUMBER = "number"
PLATFORM_SELECT = "select"
PLATFORM_BUTTON = "button"
PLATFORM_UPDATE = "update"
PLATFORM_LIGHT = "light"
PLATFORM_COVER = "cover"
PLATFORM_FAN = "fan"
# text = HA text 도메인(쓰기 가능). text_sensor = 읽기 전용 문자열(sensor 도메인).
PLATFORM_TEXT = "text"
PLATFORM_LOCK = "lock"
PLATFORM_DATE = "date"
PLATFORM_TIME = "time"
PLATFORM_DATETIME = "datetime"
PLATFORM_EVENT = "event"
PLATFORM_VALVE = "valve"
PLATFORM_CLIMATE = "climate"
PLATFORM_HUMIDIFIER = "humidifier"
PLATFORM_WATER_HEATER = "water_heater"
PLATFORM_SIREN = "siren"
PLATFORM_ALARM_CONTROL_PANEL = "alarm_control_panel"
PLATFORM_MEDIA_PLAYER = "media_player"
PLATFORM_IMAGE = "image"
PLATFORM_CAMERA = "camera"

# text_sensor는 HA에 별도 도메인이 없다 — sensor 도메인 엔티티로 등록되지만(문자열
# native_value), 클라이언트가 보내는 platform 값과 내부 등록 키는 구분해서 유지한다.
ALL_PLATFORMS = [
    PLATFORM_SENSOR,
    PLATFORM_BINARY_SENSOR,
    PLATFORM_TEXT_SENSOR,
    PLATFORM_DEVICE_TRACKER,
    PLATFORM_SWITCH,
    PLATFORM_NUMBER,
    PLATFORM_SELECT,
    PLATFORM_BUTTON,
    PLATFORM_UPDATE,
    PLATFORM_LIGHT,
    PLATFORM_COVER,
    PLATFORM_FAN,
    PLATFORM_TEXT,
    PLATFORM_LOCK,
    PLATFORM_DATE,
    PLATFORM_TIME,
    PLATFORM_DATETIME,
    PLATFORM_EVENT,
    PLATFORM_VALVE,
    PLATFORM_CLIMATE,
    PLATFORM_HUMIDIFIER,
    PLATFORM_WATER_HEATER,
    PLATFORM_SIREN,
    PLATFORM_ALARM_CONTROL_PANEL,
    PLATFORM_MEDIA_PLAYER,
    PLATFORM_IMAGE,
    PLATFORM_CAMERA,
]

# 클라이언트가 icon을 생략했을 때 플랫폼별 기본값 (device_class·switch는 HA 기본 아이콘 사용).
# device_tracker는 일부러 제외 — HA가 home/not_home 상태에 따라 아이콘을 바꿔주는데,
# 여기서 고정 아이콘을 넣으면 그 동작을 덮어써 버린다.
DEFAULT_PLATFORM_ICONS: dict[str, str] = {
    PLATFORM_SENSOR: "mdi:gauge",
    PLATFORM_BINARY_SENSOR: "mdi:checkbox-blank-circle-outline",
    PLATFORM_TEXT_SENSOR: "mdi:form-textbox",
    PLATFORM_NUMBER: "mdi:numeric",
    PLATFORM_SELECT: "mdi:format-list-bulleted",
    PLATFORM_BUTTON: "mdi:gesture-tap-button",
    PLATFORM_LIGHT: "mdi:lightbulb",
    PLATFORM_COVER: "mdi:window-shutter",
    PLATFORM_FAN: "mdi:fan",
    PLATFORM_TEXT: "mdi:form-textbox",
    PLATFORM_LOCK: "mdi:lock",
    PLATFORM_DATE: "mdi:calendar",
    PLATFORM_TIME: "mdi:clock-outline",
    PLATFORM_DATETIME: "mdi:calendar-clock",
    PLATFORM_EVENT: "mdi:calendar-alert",
    PLATFORM_VALVE: "mdi:valve",
    PLATFORM_CLIMATE: "mdi:thermostat",
    PLATFORM_HUMIDIFIER: "mdi:air-humidifier",
    PLATFORM_WATER_HEATER: "mdi:water-boiler",
    PLATFORM_SIREN: "mdi:bullhorn",
    PLATFORM_ALARM_CONTROL_PANEL: "mdi:shield-home",
    PLATFORM_MEDIA_PLAYER: "mdi:cast",
    PLATFORM_IMAGE: "mdi:image",
    PLATFORM_CAMERA: "mdi:camera",
}
