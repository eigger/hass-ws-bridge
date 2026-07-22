# WebSocket Bridge 프로토콜 규격 (PROTOCOL)

`ws_bridge` 컴포넌트와 **클라이언트**(게이트웨이 앱, 스크립트, ESP32 펌웨어 등) 사이의 통신 규약입니다.

본 통합은 Home Assistant의 표준 WebSocket API(`/api/websocket`)를 그대로 활용하며, 일반적인 인증 단계를 거친 후 아래의 전용 커스텀 명령 타입을 사용해 엔티티를 동적으로 생성하고 제어할 수 있습니다. 추가 포트나 브로커(MQTT 등)가 필요 없이 기존 HA URL과 장기 액세스 토큰만 사용합니다.

---

## 1. 역할 정의

- **클라이언트**: 엔티티를 **선언**하고 **상태**를 push합니다. 또한 Home Assistant로부터 전달되는 제어 명령을 수신하여 장치를 제어합니다.
- **통합구성요소(Integration)**: 클라이언트의 선언을 바탕으로 엔티티를 **생성**하고 상태에 맞춰 **갱신**합니다. 제어형 플랫폼(`switch`, `number`, `select`, `button`)에 대해서는 제어 명령을 **해당 클라이언트에만 중계**합니다. 컴포넌트 내부에는 하드웨어 디코딩/설정 정보가 존재하지 않습니다.

---

## 2. 연결 및 인증

1. 클라이언트가 `wss://<HA>/api/websocket` 주소로 접속합니다.
2. 표준 auth 핸드셰이크를 수행합니다:
   - HA 수신: `{"type": "auth_required", "ha_version": "..."}`
   - 클라이언트 전송: `{"type": "auth", "access_token": "<장기_액세스_토큰>"}`
   - HA 수신: `{"type": "auth_ok", "ha_version": "..."}`
3. **`auth_ok`를 받은 뒤에만** 아래 `ws_bridge/*` 명령을 전송합니다.
4. 구독 세션을 등록합니다:
   - 전송: `{"id": <n>, "type": "ws_bridge/connect", "gateway_id": "<고유_ID>", "name": "<표시_이름>"}`
   - `gateway_id`: 클라이언트를 고유하게 식별할 ID입니다. HA에 **게이트웨이 디바이스**로 등록되고, 생성되는 장치/엔티티의 네임스페이스 접두어로 사용됩니다.
   - `name`: 게이트웨이 기기의 표시 이름입니다. 통합 설정 화면의 게이트웨이 Subentry 제목으로도 사용됩니다.
   - `keep_last_state_on_disconnect` (Boolean, 선택, 기본값 `false`): `true`로 설정하면 이 게이트웨이의 엔티티는 웹소켓 연결이 끊겨도(전원/와이파이 단절 등 비정상 종료 포함) `unavailable`로 표시되지 않고 마지막 상태를 그대로 유지합니다(Last Will/Testament 없는 MQTT retain과 유사). 통합은 다음 `ws_bridge/connect`가 값을 바꿀 때까지 게이트웨이별로 이 값을 기억합니다. 기본값(`false`)은 기존 동작(연결 끊김 시 unavailable)과 동일합니다.
   - `ws_bridge/connect` 시 `gateway_id`에 맞는 Subentry가 없으면 **자동 생성**됩니다. (수동 등록 불필요)
   - 컴포넌트가 웹소켓 커넥션과 `gateway_id`를 바인딩하여 제어 명령(`command`)을 이 클라이언트에만 라우팅합니다.

> **재연결**: 클라이언트 재연결 시 엔티티 선언(idempotent) 및 상태 데이터를 다시 한번 일괄 전송해야 하며, HA는 이를 기반으로 엔티티를 복원 및 갱신합니다. HA 재시작 후에도 통합이 마지막 state를 디스크에 저장하므로, 클라이언트가 state를 재전송하기 전에도 이전 값이 표시될 수 있습니다. 최신 값 동기화를 위해 재연결 시 state 재전송은 여전히 권장됩니다.

### 메시지 전송 순서 (필수)

```
연결 → auth_required 수신 → auth 전송 → auth_ok 수신 → ws_bridge/connect → ws_bridge/entity → ws_bridge/state
```

`auth_ok` 이전에 `ws_bridge/entity` 등을 내면 Home Assistant가 인증 메시지로 잘못 해석하여 거부합니다. (`Auth message incorrectly formatted`)

### 옵션 필드 작성 시 주의

- 사용하지 않는 옵션 필드는 JSON에서 **키 자체를 생략**하세요.
- `null`을 명시적으로 넣지 않는 것을 권장합니다. (0.1.2 이상에서 `null`도 허용되지만, 생략이 더 안전합니다.)

### 디바이스 계층 (그룹화)
엔티티는 게이트웨이 및 하위 장치(sub-device) 아래에 계층적으로 정렬됩니다.
```
게이트웨이 디바이스 (예: "거실 게이트웨이" via gateway_id)
   └─ via_device ─ sub-device (예: "다기능 센서 1" via device_id)
                      └─ 엔티티 (RPM, 온도, 스위치 등)
```
컴포넌트는 내부적으로 고유 ID 충돌을 방지하기 위해 다음과 같이 네임스페이스를 자동 추가합니다:
- 엔티티 unique_id: `{gateway_id}__{unique_id}`
- 장치 식별자(identifier): `{gateway_id}:{device_id}`

---

## 3. 메시지 규격 (클라이언트 → HA)

### 3.1 엔티티 선언 (`ws_bridge/entity`)
HA에 동적으로 엔티티를 등록하거나 메타데이터를 업데이트합니다. 이 명령은 멱등(idempotent)하며, 여러 번 선언해도 중복 생성되지 않고 기존 정의를 유지/갱신합니다.

* **요청**
  ```json
  {
    "id": 2,
    "type": "ws_bridge/entity",
    "unique_id": "multisensor_lux",
    "platform": "sensor",
    "name": "조도 센서",
    "device": {
      "id": "multisensor_01",
      "name": "다기능 센서"
    },
    "device_class": "illuminance",
    "unit_of_measurement": "lx",
    "state_class": "measurement",
    "icon": "mdi:weather-sunny",
    "entity_category": "diagnostic"
  }
  ```
  - `unique_id` (String, 필수): 게이트웨이 내에서 고유한 엔티티 식별자입니다. (HA 내부적으로는 `{gateway_id}__{unique_id}` 형태로 자동 변환됩니다.)
  - `platform` (String, 필수): 엔티티 플랫폼 타입. 지원 목록: `sensor`, `binary_sensor`, `text_sensor`, `switch`, `number`, `select`, `button`
  - `name` (String, 필수): 엔티티 이름.
  - `device` (Object, 옵션): 엔티티가 속한 하위 장치 정보.
    - `id` (String, 필수): 하위 장치 고유 ID.
    - `name` (String, 옵션): 장치 표시 이름.
  - `device_class` (String, 옵션): Home Assistant 표준 장치 클래스.
  - `unit_of_measurement` (String, 옵션): 측정 단위 (예: `°C`, `%`, `V`, `lx`).
  - `state_class` (String, 옵션): 통계 처리를 위한 상태 클래스 (예: `measurement`, `total_increasing`).
  - `icon` (String, 옵션): 표시 아이콘 (예: `mdi:thermometer`).
  - `entity_category` (String, 옵션): 엔티티 카테고리. `"config"` 또는 `"diagnostic"`.
  - **플랫폼 전용 필드**:
    - **`select` 플랫폼**: `options` (List of String, 필수) - 선택 가능한 옵션 목록.
    - **`number` 플랫폼**: `min`, `max`, `step` (Float, 옵션) - 입력 범위 및 단계값.

* **응답**
  ```json
  {
    "id": 2,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

#### 플랫폼 참조 표:
| 플랫폼 | 방향 | 상태 값 타입 | 제어 명령 action |
|:---|:---:|:---|:---|
| `sensor` | 읽기 | 숫자/문자열 | — |
| `binary_sensor` | 읽기 | 불리언 | — |
| `text_sensor` | 읽기 | 문자열 | — (HA `sensor` 엔티티로 생성됨 — HA에는 별도의 text-sensor 도메인이 없음) |
| `switch` | 제어 | 불리언 | `turn_on` / `turn_off` |
| `number` | 제어 | 숫자 | `set_value` (값 포함) |
| `select` | 제어 | 문자열 (옵션값) | `select_option` (옵션값 포함) |
| `button` | 제어 | — | `press` |

---

### 3.2 상태 데이터 업데이트 (`ws_bridge/state`)
하나 이상의 엔티티 상태를 일괄 업데이트(배치)합니다. 엔티티 등록(`ws_bridge/entity`) 이전에 상태 메시지가 먼저 도착하더라도 버퍼링되어, 추후 엔티티가 선언될 때 최종 상태가 즉시 반영됩니다.

* **요청**
  ```json
  {
    "id": 3,
    "type": "ws_bridge/state",
    "states": [
      {
        "unique_id": "multisensor_lux",
        "value": 350
      },
      {
        "unique_id": "temp_sensor_01",
        "value": 24.5
      }
    ]
  }
  ```
  - `states` (List, 필수): 업데이트할 엔티티 정보 목록.
    - `unique_id` (String, 필수): 등록 시 사용했던 원본 `unique_id` (게이트웨이 네임스페이스 제외).
    - `value` (Any, 필수): 새로운 상태 값.
      - `binary_sensor` 플랫폼은 `"1"`, `"true"`, `"on"`, `"yes"` (대소문자 구분 없음) 또는 진위값 `true`를 On 상태로 매핑합니다.

* **응답**
  ```json
  {
    "id": 3,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

### 3.3 하위 장치 가용성 상태 (`ws_bridge/availability`)
특정 하위 장치(sub-device)의 연결 상태를 일괄 제어(Online/Offline)합니다. 이 요청을 통해 해당 장치에 소속된 모든 엔티티의 사용 가능 상태(`available`)가 함께 토글됩니다.

* **요청**
  ```json
  {
    "id": 4,
    "type": "ws_bridge/availability",
    "device_id": "multisensor_01",
    "online": false
  }
  ```
  - `device_id` (String, 필수): 장치 등록 시 사용했던 원본 `device_id` (게이트웨이 네임스페이스 제외).
  - `online` (Boolean, 필수): `true` 이면 사용 가능(Online), `false` 이면 사용 불가(Offline) 상태가 됩니다.

* **응답**
  ```json
  {
    "id": 4,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

### 3.4 삭제 (`ws_bridge/remove`)
HA에 등록된 엔티티·하위 장치·게이트웨이를 **완전히 삭제**합니다. 연결이 끊겨 `unavailable` 상태인 항목도 레지스트리에서 제거됩니다.

또한 **설정 → WebSocket Bridge → 게이트웨이 Subentry 삭제** 또는 **`ws_bridge/remove`(게이트웨이 전체)** 시, 해당 `gateway_id`의 Subentry·기기·엔티티가 자동으로 정리됩니다.

* **요청 (엔티티 1개)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove",
    "unique_id": "multisensor_lux"
  }
  ```

* **요청 (하위 장치 + 소속 엔티티 — 정확 일치, 기본값)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove",
    "device_id": "multisensor_01"
  }
  ```

* **요청 (하위 장치 트리 — prefix 일치, 예: BLE MAC 인스턴스)**
  ```json
  {
    "id": 6,
    "type": "ws_bridge/remove",
    "device_id": "jaalee_jht",
    "mode": "prefix"
  }
  ```
  클라이언트 `device.id`가 `jaalee_jht`이거나 `jaalee_jht_`로 시작하는 하위 장치(예: `jaalee_jht_AABBCCDDEEFF`)와 그 엔티티를 모두 제거합니다.

* **요청 (게이트웨이 전체 — `unique_id`·`device_id` 생략)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove"
  }
  ```

  - `unique_id` (String, 옵션): 삭제할 엔티티의 원본 `unique_id`. `device_id`보다 우선합니다.
  - `device_id` (String, 옵션): 삭제할 하위 장치 ID. 해당 장치와 소속 엔티티를 제거합니다.
  - `mode` (String, 옵션): `unique_id` 또는 `device_id` 지정 시 삭제 범위. 기본값 `"exact"`.
    - `"exact"`: 클라이언트 id가 **완전 일치**하는 대상만 삭제 (기존 동작).
    - `"prefix"`: 대상 id와 **일치하거나** `대상id_`로 시작하는 모든 하위 id 삭제 (예: 프로필 `jaalee_jht` + MAC 인스턴스 `jaalee_jht_AABBCCDDEEFF`). MAC별 `device.id`를 쓰는 advertisement 센서에 사용.
  - 둘 다 생략: 현재 연결된 게이트웨이의 **모든** 엔티티·하위 장치·게이트웨이 디바이스를 삭제합니다.

* **응답**
  ```json
  {
    "id": 5,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

## 4. 제어 명령 수신 (HA → 클라이언트)

제어형 엔티티가 HA 상에서 조작되면, 해당 엔티티를 등록한 클라이언트 세션 채널을 통해 명령 이벤트가 실시간으로 전달됩니다.

클라이언트는 이 이벤트를 구독하여 실제 장치를 동작시키고, 성공 후 `ws_bridge/state` 메시지를 보내 새로운 상태를 반영해야 합니다.

* **이벤트 메시지**
  ```json
  {
    "id": 1,
    "type": "event",
    "event": {
      "kind": "command",
      "unique_id": "switch_01",
      "action": "turn_on"
    }
  }
  ```
  - `id`: 클라이언트가 세션을 연결할 때 사용한 `ws_bridge/connect` 메시지의 ID입니다.
  - `event` (Object): 제어 세부 정보.
    - `kind`: 항상 `"command"` 입니다.
    - `unique_id`: 제어 대상 엔티티의 원본 `unique_id` (게이트웨이 네임스페이스 제거됨).
    - `action`: 수행할 제어 동작 (`turn_on`, `turn_off`, `press`, `set_value`, `select_option`).
    - `value` (Any, 옵션): 설정할 값 (예: `set_value` 시 대상 숫자, `select_option` 시 대상 문자열).

### 값 설정 예시
```json
{
  "id": 1,
  "type": "event",
  "event": {
    "kind": "command",
    "unique_id": "target_temp",
    "action": "set_value",
    "value": 26.5
  }
}
```

---

## 5. 비고
- 엔티티 unique_id 구성 권장 형식: `<device_id>_<key>`.
- 클라이언트가 선언하지 않은 엔티티는 HA에 생성되지 않습니다.
