# WebSocket Bridge 프로토콜 규격 (PROTOCOL)

`ws_bridge` 컴포넌트와 **클라이언트**(게이트웨이 앱, 스크립트, ESP32 펌웨어 등) 사이의 통신 규약입니다.

본 통합은 Home Assistant의 표준 WebSocket API(`/api/websocket`)를 그대로 활용하며, 일반적인 인증 단계를 거친 후 아래의 전용 커스텀 명령 타입을 사용해 엔티티를 동적으로 생성하고 제어할 수 있습니다. 추가 포트나 브로커(MQTT 등)가 필요 없이 기존 HA URL과 장기 액세스 토큰만 사용합니다.

---

## 1. 역할 정의

- **클라이언트**: 엔티티를 **선언**하고 **상태**를 push합니다. 또한 Home Assistant로부터 전달되는 제어 명령을 수신하여 장치를 제어합니다.
- **통합구성요소(Integration)**: 클라이언트의 선언을 바탕으로 엔티티를 **생성**하고 상태에 맞춰 **갱신**합니다. 제어형 플랫폼(`switch`, `number`, `select`, `button`, `update`)에 대해서는 제어 명령을 **해당 클라이언트에만 중계**합니다. 컴포넌트 내부에는 하드웨어 디코딩/설정 정보가 존재하지 않습니다.

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
   - `gateway_id` (String, 필수): 클라이언트를 고유하게 식별할 ID입니다. HA에 **게이트웨이 디바이스**로 등록되고, 생성되는 장치/엔티티의 네임스페이스 접두어로 사용됩니다.
   - `name` (String, 선택): 게이트웨이 기기의 표시 이름입니다. 통합 설정 화면의 게이트웨이 Subentry 제목으로도 사용됩니다.
   - `app_version` (String, 선택): 클라이언트의 펌웨어 또는 앱 버전입니다. 등록된 게이트웨이 기기의 `sw_version` 속성에 반영됩니다.
   - `keep_last_state_on_disconnect` (Boolean, 선택, 기본값 `false`): `true`로 설정하면 이 게이트웨이의 엔티티는 웹소켓 연결이 끊겨도(전원/와이파이 단절 등 비정상 종료 포함) `unavailable`로 표시되지 않고 마지막 상태를 그대로 유지합니다(Last Will/Testament 없는 MQTT retain과 유사). 통합은 다음 `ws_bridge/connect`가 값을 바꿀 때까지 게이트웨이별로 이 값을 (디스크에 저장해서) 기억합니다. 기본값(`false`)은 기존 동작(연결 끊김 시 unavailable)과 동일합니다. 이 옵션은 **HA 재시작**에도 적용됩니다 — `keep_last_state_on_disconnect` 게이트웨이의 엔티티는 클라이언트 재연결을 기다리지 않고, HA가 뜨는 즉시 저장된 정의·마지막 상태값으로 (available 상태로) 바로 복원됩니다.
   - `ws_bridge/connect` 시 `gateway_id`에 맞는 Subentry가 없으면 **자동 생성**됩니다. (수동 등록 불필요)
   - 컴포넌트가 웹소켓 커넥션과 `gateway_id`를 바인딩하여 제어 명령(`command`)을 이 클라이언트에만 라우팅합니다.

> **재연결**: 클라이언트 재연결 시 엔티티 선언(idempotent) 및 상태 데이터를 다시 한번 일괄 전송해야 하며, HA는 이를 기반으로 엔티티를 복원 및 갱신합니다. 하위 장치(sub-device)는 재연결 후 **다시 선언되거나 상태를 받은 시점에** 온라인으로 복귀합니다 — 이전 세션에서 알던 장치를 무조건 되살리지는 않습니다(클라이언트에서 이미 사라진 장치가 살아 있는 것처럼 보이는 것을 막기 위해서). 게이트웨이 디바이스 자체는 접속 즉시 온라인이 됩니다. HA 재시작 후에도 통합이 마지막 state를 디스크에 저장하므로, 클라이언트가 state를 재전송하기 전에도 이전 값이 표시될 수 있습니다(`keep_last_state_on_disconnect` 게이트웨이는 즉시 — 위 항목 참고). 최신 값 동기화를 위해 재연결 시 state 재전송은 여전히 권장됩니다.

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
  - `platform` (String, 필수): 엔티티 플랫폼 타입. 지원 목록: `sensor`, `binary_sensor`, `text_sensor`, `device_tracker`, `switch`, `number`, `select`, `button`, `update`
  - `name` (String, 필수): 엔티티 이름.
  - `device` (Object, 옵션): 엔티티가 속한 하위 장치 정보.
    - `id` (String, 필수): 하위 장치 고유 ID.
    - `name` (String, 옵션): 장치 표시 이름.
  - `device_class` (String, 옵션): Home Assistant 표준 장치 클래스. `sensor`/`binary_sensor`뿐 아니라 모든 플랫폼에 적용됩니다 (예: `switch`의 `outlet`/`switch`, `number`의 `humidity`/`temperature`, `button`의 `restart`/`identify`/`update`).
  - `unit_of_measurement` (String, 옵션): 측정 단위 (예: `°C`, `%`, `V`, `lx`).
  - `state_class` (String, 옵션): 통계 처리를 위한 상태 클래스 (예: `measurement`, `total_increasing`).
  - `suggested_display_precision` (Integer, 옵션, `sensor` 플랫폼): 표시할 소수점 자리수 (클라이언트 쪽 반올림 설정과 맞추는 용도, 예: ESPHome의 `accuracy_decimals`). 안 보내면 HA는 받은 float를 그대로 표시해서, 센서에 따라 `48.85864`처럼 지저분한 값이 뜰 수 있습니다.
  - `icon` (String, 옵션): 표시 아이콘 (예: `mdi:thermometer`).
  - `entity_category` (String, 옵션): 엔티티 카테고리. `"config"` 또는 `"diagnostic"`.
  - **플랫폼 전용 필드**:
    - **`select` 플랫폼**: `options` (List of String, 필수) - 선택 가능한 옵션 목록.
    - **`number` 플랫폼**: `min`, `max`, `step` (Float, 옵션) - 입력 범위 및 단계값.
    - **`device_tracker` 플랫폼**: 선언 전용 필드 없음 — 위치는 상태(`value`) 객체로 전달합니다 (§3.2 참고).
    - **`update` 플랫폼**: 선언 전용 필드 없음 — 버전 정보는 상태(`value`) 객체로 전달합니다 (§3.2 참고). `device_class`를 생략하면 HA 쪽에서 `firmware`로 기본 설정합니다.

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
| `device_tracker` | 읽기 | 객체 (`latitude`/`longitude`, §3.2 참고) | — |
| `switch` | 제어 | 불리언 | `turn_on` / `turn_off` |
| `number` | 제어 | 숫자 | `set_value` (값 포함) |
| `select` | 제어 | 문자열 (옵션값) | `select_option` (옵션값 포함) |
| `button` | 제어 | — | `press` |
| `update` | 제어 | 객체 (`installed_version`/`latest_version`, §3.2 참고) | `install` / `check` |

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
    - `value` (Any, 필수): 새로운 상태 값. 대부분의 플랫폼은 스칼라이고, 상태가 단일 값이 아닌 플랫폼(현재 `device_tracker`와 `update`)은 **객체**를 사용합니다.
      - 모든 플랫폼에 대해 문자열 `"unknown"`(대소문자 구분 없음)을 보내면 HA의 사용 불가(`None`) 상태로 매핑됩니다.
      - `binary_sensor` 플랫폼은 `"1"`, `"true"`, `"on"`, `"yes"` (대소문자 구분 없음) 또는 진위값 `true`를 On 상태로 매핑합니다.
      - `sensor` 플랫폼 중 `device_class`가 `"timestamp"`이거나 `"date"`인 경우, 문자열 값을 자동으로 날짜/시간 객체로 변환합니다.
      - `device_tracker` 플랫폼은 아래 객체 형식을 사용합니다.
      - `update` 플랫폼은 아래 객체 형식을 사용합니다.
  - `ts` (Number, 선택): 상태 업데이트 타임스탬프 (현재 스키마에서는 허용되나 백엔드 로직에서는 무시됩니다).

#### `device_tracker` 상태 (객체 `value`)

```json
{
  "id": 4,
  "type": "ws_bridge/state",
  "states": [
    {
      "unique_id": "car_location",
      "value": {"latitude": 37.5665, "longitude": 126.9780, "gps_accuracy": 8}
    }
  ]
}
```

- `latitude`, `longitude` (Float, 둘 다 필수): 좌표입니다. **둘 다 있고 숫자로 해석돼야** 하며, 하나라도 없거나 파싱되지 않으면 반쪽만 반영하지 않고 '위치 모름'으로 처리합니다. 좌표 한쪽만으로는 엉뚱한 위치에 찍히기 때문입니다.
- `gps_accuracy` (Integer, 옵션, 기본값 `0`): 정확도 반경(미터). HA가 존(zone) 진입 여부를 판단할 때 사용합니다.
엔티티 상태(`home` / `not_home` / 존 이름)는 HA가 좌표로부터 계산하므로 별도의 상태 문자열을 보낼 필요가 없습니다. (이걸 직접 지정하는 필드는 일부러 안 뒀습니다 — `TrackerEntity.location_name`이 HA에서 deprecated고 2027.7에 제거될 예정입니다.)

> **배터리**: 여기에 `battery_level`을 넣지 마세요. HA가 `device_tracker`의 `battery_level`을 폐기(deprecate)하고 별도 배터리 엔티티를 권장합니다 — 일반 `sensor`를 `"device_class": "battery"`로 선언하세요.

#### `update` 상태 (객체 `value`)

```json
{
  "id": 5,
  "type": "ws_bridge/state",
  "states": [
    {
      "unique_id": "firmware",
      "value": {
        "installed_version": "1.0.0",
        "latest_version": "1.0.1",
        "in_progress": false,
        "title": "Living Room",
        "summary": "Bug fixes"
      }
    }
  ]
}
```

- `installed_version` (String, 옵션): 현재 실행 중인 펌웨어/앱 버전.
- `latest_version` (String, 옵션): 매니페스트가 제공하는 버전. `installed_version`과 다르면 HA가 업데이트를 표시합니다.
- `in_progress` (Boolean, 옵션, 기본값 `false`): 플래시가 진행 중이면 `true`.
- `progress` (Number, 옵션, 0–100): 진행률. `in_progress`가 `true`일 때만 의미가 있습니다.
- `title`, `summary`, `release_url` (String, 옵션): 업데이트 카드 / 릴리스 노트 대화상자에 표시됩니다.

빈 옵션 키는 `""`로 보내지 말고 생략하세요. 문자열 `"unknown"`(또는 객체가 아닌 값)을 보내면 버전 필드를 비웁니다.

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

### 3.5 엔티티 목록 동기화 (`ws_bridge/sync`)

클라이언트가 **자신의 전체 엔티티 목록**을 알려주면, 통합은 그 목록에 **없는** 이 게이트웨이의 엔티티를 제거합니다. 클라이언트 쪽에서 없어진 센서를 HA에서도 정리하는 용도입니다.

한 번 선언된 엔티티는 명시적으로 삭제하기 전까지 계속 유지되므로(§5 참고), 클라이언트 설정에서 센서를 빼도 HA에는 그대로 남습니다. `keep_last_state_on_disconnect`를 쓰는 게이트웨이는 저장된 정의로 HA 재시작 때마다 복원되기 때문에 더 두드러집니다. 이 명령이 그 정리 경로입니다.

* **요청**
  ```json
  {
    "id": 7,
    "type": "ws_bridge/sync",
    "unique_ids": ["multisensor_lux", "temp_sensor_01", "switch_01"]
  }
  ```
  - `unique_ids` (List of String, 필수, **1개 이상**): 이 게이트웨이가 현재 제공하는 **모든** 엔티티의 원본 `unique_id` 목록입니다. 여기 없는 엔티티는 삭제됩니다.

* **응답** — 실제로 삭제된 원본 `unique_id` 목록을 돌려줍니다.
  ```json
  {
    "id": 7,
    "type": "result",
    "success": true,
    "result": { "removed": ["old_sensor"] }
  }
  ```

#### 동작 규칙

- **살아남는 엔티티는 건드리지 않습니다.** 전체 삭제 후 재선언하는 방식과 달리 entity_id·히스토리·long-term statistics가 그대로 보존됩니다. 재접속마다 호출해도 안전합니다.
- 대조 범위는 **해당 게이트웨이**로 한정됩니다. 다른 게이트웨이의 엔티티와 통합 진단 센서(`connected_clients`)는 영향받지 않습니다.
- 연결이 끊겨 `unavailable`인 엔티티, 아직 플랫폼 준비 전이라 대기 중인 엔티티, `keep_last_state_on_disconnect`로 복원된 엔티티까지 모두 대조 대상입니다.
- 엔티티가 하나도 남지 않은 하위 장치(sub-device)는 기기 목록에서도 함께 제거됩니다. 게이트웨이 디바이스 자체는 유지됩니다.
- 빈 배열(`[]`)은 **스키마에서 거부**됩니다. 설정을 못 읽었거나 부분 부팅한 클라이언트가 실수로 전체를 날리는 사고를 막기 위해서입니다. 전체 삭제는 대상을 생략한 `ws_bridge/remove`를 쓰세요.

#### 호출 시점

엔티티 선언을 **전부 끝낸 직후**에 한 번 보내세요.

```
ws_bridge/connect → ws_bridge/entity × N → ws_bridge/sync → ws_bridge/state
```

> **주의**: 장치를 시간이 지나면서 발견하는 클라이언트(예: BLE advertisement를 수신해야 sub-device를 만드는 경우)는 접속 직후에 호출하면 **아직 못 본 장치가 전부 삭제됩니다**. 이런 클라이언트는 이 명령을 아예 쓰지 않거나, 전체 목록을 확실히 아는 시점(예: 스캔 주기 완료 후)에만 호출하세요. 통합은 "선언이 끝났는지" 스스로 판단하지 않습니다 — 판단은 전적으로 클라이언트 몫입니다.

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
    - `action`: 수행할 제어 동작 (`turn_on`, `turn_off`, `press`, `set_value`, `select_option`, `install`, `check`).
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

### `update` 명령

- `install` — 현재 제공된 펌웨어 설치를 시작합니다 (`value` 없음). 클라이언트는 플래시가 끝날 때까지 `in_progress: true`(알고 있으면 `progress`도)를 push해야 합니다. 성공하면 보통 기기가 재부팅됩니다.
- `check` — 업데이트 매니페스트를 다시 가져옵니다. HA가 이 엔티티에 `homeassistant.update_entity`를 호출할 때 전달됩니다.

---

## 5. 비고
- 엔티티 unique_id 구성 권장 형식: `<device_id>_<key>`.
- 클라이언트가 선언하지 않은 엔티티는 HA에 생성되지 않습니다.
- **유지 정책**: 한 번 선언된 엔티티는 `ws_bridge/remove`·`ws_bridge/sync`·Subentry 삭제로 **명시적으로 제거하기 전까지** HA에 남습니다. 재접속 시 선언되지 않았다는 이유만으로 자동 삭제되지는 않습니다 — 연결이 끊긴 것과 장치가 없어진 것을 통합이 구분할 수 없기 때문입니다. 클라이언트에서 없어진 엔티티를 정리하려면 §3.5를 사용하세요.

---

## 6. 예정 플랫폼

아래 `platform` 값은 **지금 받지 않습니다**. `ws_bridge/entity`는 §3.1 목록 밖이면 거절합니다. **도메인은 한 번에 하나만** 넣습니다. 클라이언트(ESPHome 래핑 포함)보다 **PROTOCOL + HA 플랫폼**(`ALL_PLATFORMS`, `Platform.*`)을 먼저 올립니다. 기존 플랫폼 래핑은 HA를 건드리지 않아도 되지만, 새 도메인은 그렇지 않습니다.

| 순서 | 플랫폼 | 메모 |
|:---:|:---|:---|
| 1 | `text` | 다음. 쓰기 가능 문자열 + `set_value` (`min`/`max`/`pattern`/`mode`). `text_sensor`(읽기 전용, HA `sensor`로 생성)와 다름. |
| 2 | `lock` | `lock` / `unlock`. `open`과 PIN `code`는 해당 PR에서 범위를 정함. |
| 3 | `cover`, `fan` | 도메인별 PR. position / %, feature 비트, 객체에 가까운 state. |
| 4 | `light`, `climate` | 각자 단독, 마지막. `update`보다 큰 객체 state. |

`date` / `time`은 `text`와 난이도가 비슷하지만 이 대기열에는 넣지 않습니다.
