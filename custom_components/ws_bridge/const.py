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

# HA→클라이언트 이벤트 kind
EVT_COMMAND = "command"

# 기본 지원 플랫폼 (읽기: sensor/binary_sensor, 제어: switch/number/select/button)
PLATFORM_SENSOR = "sensor"
PLATFORM_BINARY_SENSOR = "binary_sensor"
PLATFORM_SWITCH = "switch"
PLATFORM_NUMBER = "number"
PLATFORM_SELECT = "select"
PLATFORM_BUTTON = "button"

ALL_PLATFORMS = [
    PLATFORM_SENSOR,
    PLATFORM_BINARY_SENSOR,
    PLATFORM_SWITCH,
    PLATFORM_NUMBER,
    PLATFORM_SELECT,
    PLATFORM_BUTTON,
]

# 클라이언트가 icon을 생략했을 때 플랫폼별 기본값 (device_class·switch는 HA 기본 아이콘 사용)
DEFAULT_PLATFORM_ICONS: dict[str, str] = {
    PLATFORM_SENSOR: "mdi:gauge",
    PLATFORM_BINARY_SENSOR: "mdi:checkbox-blank-circle-outline",
    PLATFORM_NUMBER: "mdi:numeric",
    PLATFORM_SELECT: "mdi:format-list-bulleted",
    PLATFORM_BUTTON: "mdi:gesture-tap-button",
}
