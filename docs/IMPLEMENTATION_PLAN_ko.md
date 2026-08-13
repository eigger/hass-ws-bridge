# ws_bridge 미구현 엔티티 구현 계획 / 작업 지시서

> **대상**: 이 저장소에서 작업할 다른 AI 에이전트 또는 개발자
> **기준 커밋**: `a305bf4` (v1.0.0)
> **작성일**: 2026-08-13

---

## 0. 이 문서를 읽는 법

1. **§1~2**로 현황과 우선순위를 파악한다.
2. **Phase 0 (§3)은 반드시 먼저 끝낸다.** 이후 모든 플랫폼이 여기서 추가되는 코어 기능(복합 상태, `params` 커맨드, `features` 플래그)에 의존한다.
3. 각 Phase는 **독립 PR 1개**로 만든다. Phase 내 플랫폼은 파일이 서로 겹치지 않으므로 병렬 작업이 가능하다(단 `const.py` / `__init__.py` / 문서는 충돌 지점이므로 주의).
4. 플랫폼 하나를 추가할 때 해야 할 일은 **§5의 체크리스트**에 전부 있다. 매번 그대로 따른다.
5. 코딩 규약은 **§6**, 테스트는 **§7**, 문서 갱신은 **§8**, 완료 조건(DoD)은 **§10**.
6. **§8.5(하위 호환 보증)는 코드를 쓰기 전에 반드시 읽는다.** 이미 배포된 클라이언트(v1.0.0)를 끊지 않는 것이 이 작업의 최우선 제약이다.

---

## 1. 현황

### 1.1 구현 완료 (9종)

| 프로토콜 `platform` | HA 도메인 | 방향 | 파일 |
|:---|:---|:---:|:---|
| `sensor` | sensor | 읽기 | `custom_components/ws_bridge/sensor.py` |
| `binary_sensor` | binary_sensor | 읽기 | `custom_components/ws_bridge/binary_sensor.py` |
| `text_sensor` | sensor (문자열) | 읽기 | `custom_components/ws_bridge/sensor.py` |
| `device_tracker` | device_tracker | 읽기 | `custom_components/ws_bridge/device_tracker.py` |
| `switch` | switch | 제어 | `custom_components/ws_bridge/switch.py` |
| `number` | number | 제어 | `custom_components/ws_bridge/number.py` |
| `select` | select | 제어 | `custom_components/ws_bridge/select.py` |
| `button` | button | 제어 | `custom_components/ws_bridge/button.py` |
| `update` | update | 제어 | `custom_components/ws_bridge/update.py` |

> `device_tracker` / `update` 및 `ws_bridge/sync`는 Phase 0 착수 전에 `main`에 이미 머지되어 있다. 객체 `value` 스키마도 그에 맞춰 열려 있으나, **얕은 병합·`params`·`features`·공용 헬퍼·`WsBridgeCompositeEntity`는 Phase 0에서 추가한다.**

### 1.2 미구현 (이번 작업 대상)

`light`, `cover`, `fan`, `text`, `lock`, `date`, `time`, `datetime`, `event`, `valve`,
`climate`, `humidifier`, `water_heater`, `siren`, `alarm_control_panel`,
`media_player`, `image`, `camera`, `vacuum`, `lawn_mower`, `remote`, `todo`

### 1.3 현재 아키텍처가 못 하는 것 (Phase 0에서 해결)

| 한계 | 위치 | 영향 |
|:---|:---|:---|
| 상태 값이 스칼라만 허용 (`int/float/str/bool/None`) | `websocket_api.py` `ws_state` 스키마 | light/climate/cover처럼 여러 속성을 한 엔티티가 갖는 플랫폼 구현 불가 |
| 커맨드가 단일 `value`만 전달 | `bridge.py` `send_command()` | `turn_on(brightness=128, rgb=[…])` 같은 복합 인자 전달 불가 |
| 엔티티 선언에 기능(feature) 표현 수단 없음 | `websocket_api.py` `ws_entity` 스키마 | `CoverEntityFeature`, `ClimateEntityFeature` 등 매핑 불가 |
| `_truthy()`가 `binary_sensor.py` / `switch.py`에 중복 | 두 파일 | 신규 플랫폼마다 3번째, 4번째 복사가 생김 |

---

## 2. 우선순위 및 단계

| Phase | 범위 | 근거 | 규모 |
|:---|:---|:---|:---|
| **0** | 코어 확장 (복합 상태 / `params` / `features` / 공용 헬퍼) | 이후 전 단계의 전제 | 필수 |
| **1** | `light`, `cover`, `fan` | ESPHome 대비 가장 많이 요구되는 3종 | 大 |
| **2** | `text`, `lock`, `date`, `time`, `datetime`, `event`, `valve` | 단순 스칼라 제어 — 코스트 대비 효과 최고 | 中 |
| **3** | `climate`, `humidifier`, `water_heater`, `siren`, `alarm_control_panel` | 복합 상태 + 다중 액션 | 大 |
| **4** | `media_player`, `image`, `camera` | 수요 제한적, 바이너리/URL 전송 설계 필요 (`update`는 main에 이미 있음) | 中 |
| **5** (보류) | `vacuum`, `lawn_mower`, `remote`, `todo` | 실사용 사례 확인 후 착수 | — |

> Phase 5는 **착수하지 말 것.** 요구가 확인되기 전에는 프로토콜 표면적만 넓힌다.

---

## 3. Phase 0 — 코어 확장 (필수 선행)

### 3.1 복합(dict) 상태 값 지원

**프로토콜 변경**: `ws_bridge/state`의 `value`가 객체(dict)를 허용한다.

```json
{
  "type": "ws_bridge/state",
  "states": [
    { "unique_id": "living_led", "value": { "state": "on", "brightness": 180 } }
  ]
}
```

**병합(merge) 규칙 — 반드시 이 규칙으로 구현할 것:**

- 이전 상태와 새 값이 **둘 다 dict**면 **얕은 병합(shallow merge)** 한다. 클라이언트가 `{"brightness": 200}`만 보내도 `state`, `rgb_color` 등 나머지가 보존된다.
- **키를 지우려면 JSON `null`을 보낸다.** 키 생략 ≠ 삭제. (`device_tracker` GPS 유실: `{"latitude": null, "longitude": null}`)
- 그 외에는 **교체**한다 (스칼라 → dict, dict → 스칼라 포함).
- 병합 **결과 전체**를 dispatcher로 내보낸다. 엔티티는 항상 완전한 상태를 받는다.
- `device_tracker` / `update`도 동일 규칙(복합 상태 + `WsBridgeCompositeEntity`). 기존에 "부분 객체 = 전체 교체"로 동작하던 클라이언트는 **브레이킹** — `null`로 지우는 쪽으로 맞춰야 한다.

`custom_components/ws_bridge/bridge.py`:

```python
@callback
def handle_state(self, gateway_id: str, unique_id: str, value: Any) -> None:
    ns_uid = self._ns_uid(gateway_id, unique_id)
    if isinstance(value, dict):
        prev = self._states.get(ns_uid)
        value = {**prev, **value} if isinstance(prev, dict) else dict(value)
    self._states[ns_uid] = value
    self._schedule_save()
    async_dispatcher_send(self.hass, signal_value(self.entry_id, ns_uid), value)
```

`custom_components/ws_bridge/websocket_api.py`의 `ws_state` 스키마:

```python
vol.Required("value"): vol.Any(int, float, str, bool, None, dict),
```

> **주의**: `_states`는 `Store`로 디스크에 JSON 저장된다. dict 상태도 그대로 직렬화되므로 추가 작업은 없지만, **JSON으로 표현 불가능한 값(bytes, tuple 등)을 넣지 말 것.** 색상은 반드시 list로 저장한다.

### 3.2 커맨드 `params` 확장

**프로토콜 변경**: HA→클라이언트 command 이벤트에 선택 필드 `params`(객체)를 추가한다. 기존 `value`는 **그대로 유지**(하위 호환).

```json
{
  "kind": "command",
  "unique_id": "living_led",
  "action": "turn_on",
  "params": { "brightness": 128, "rgb_color": [255, 0, 0], "transition": 1.5 }
}
```

`bridge.py`:

```python
@callback
def send_command(
    self, unique_id: str, action: str,
    value: Any = None, params: dict[str, Any] | None = None,
) -> None:
    gateway_id = self._entity_client.get(unique_id)
    client = self._clients.get(gateway_id) if gateway_id else None
    if client is None:
        return
    event: dict[str, Any] = {
        "kind": "command",
        "unique_id": self._strip(gateway_id, unique_id),
        "action": action,
    }
    if value is not None:
        event["value"] = value
    if params:
        event["params"] = params
    client.send_event(event)
```

**규칙**: 인자가 1개인 액션(`set_value`, `select_option`)은 계속 `value`를 쓴다. 인자가 2개 이상이거나 이름이 필요한 액션(`turn_on` with brightness 등)은 `params`를 쓴다. **같은 액션에서 둘을 섞지 말 것.**

### 3.3 `features` 필드

**프로토콜 변경**: `ws_bridge/entity`에 선택 필드 `features`(문자열 리스트)를 추가한다. 각 플랫폼 모듈이 자기 도메인의 `*EntityFeature` 플래그로 매핑한다.

```python
vol.Optional("features"): vol.Any([str], None),
```

각 플랫폼 모듈에 **모듈 수준 순수 함수**로 구현한다(§7의 테스트 용이성 때문에 필수):

```python
_FEATURE_MAP = {
    "open": CoverEntityFeature.OPEN,
    "close": CoverEntityFeature.CLOSE,
    "stop": CoverEntityFeature.STOP,
    "set_position": CoverEntityFeature.SET_POSITION,
    ...
}

def _features(names: list[str] | None) -> CoverEntityFeature:
    flags = CoverEntityFeature(0)
    for name in names or ():
        if (flag := _FEATURE_MAP.get(name)) is not None:
            flags |= flag
    return flags
```

- 알 수 없는 feature 이름은 **조용히 무시**한다(클라이언트 버전이 앞서 나가도 깨지지 않게).
- `features`가 없으면 각 플랫폼의 **합리적 기본값**을 쓴다(예: cover는 `OPEN|CLOSE|STOP`).

### 3.4 공용 헬퍼 모듈 신설

`custom_components/ws_bridge/helpers.py`를 새로 만들고, `binary_sensor.py` / `switch.py`의 중복 `_truthy()`를 **동작을 1비트도 바꾸지 않은 채** 여기로 이관한 뒤 두 파일에서 import 하도록 리팩터링한다.

```python
"""플랫폼 공용 값 변환 헬퍼."""
from __future__ import annotations

from typing import Any

# 기존 binary_sensor._truthy / switch._truthy 와 완전히 동일한 목록.
# 여기에 항목을 추가하면 이미 배포된 클라이언트의 상태 해석이 바뀐다 — 절대 확장 금지.
_TRUE_STRINGS = ("1", "true", "on", "yes")

# lock/cover 등 신규 플랫폼 전용 어휘는 별도 파서에 둔다.
_LOCK_TRUE_STRINGS = ("locked", "lock", "1", "true", "on", "yes")


def is_unknown(value: Any) -> bool:
    """클라이언트가 보낸 'unknown'(대소문자 무시) 또는 None 인지."""
    return value is None or (isinstance(value, str) and value.lower() == "unknown")


def parse_bool(value: Any) -> bool | None:
    """binary_sensor / switch 용. 기존 _truthy 와 동작 동일."""
    if is_unknown(value):
        return None
    if isinstance(value, str):
        return value.lower() in _TRUE_STRINGS
    return bool(value)


def parse_locked(value: Any) -> bool | None:
    """lock 전용. parse_bool 과 분리해 기존 플랫폼에 영향이 없게 한다."""
    if is_unknown(value):
        return None
    if isinstance(value, str):
        return value.lower() in _LOCK_TRUE_STRINGS
    return bool(value)


def as_dict(value: Any) -> dict[str, Any]:
    """복합 상태 정규화. 스칼라가 오면 {'state': value} 로 승격."""
    if isinstance(value, dict):
        return value
    return {} if is_unknown(value) else {"state": value}
```

> **`_TRUE_STRINGS`를 확장하지 말 것.** `open`/`locked` 같은 어휘를 공용 목록에 넣으면, 이미 배포된 클라이언트가 `binary_sensor`에 보내던 `"open"`이 지금은 OFF로 해석되는데 업데이트 후 ON으로 바뀐다 — 사용자 자동화가 조용히 반전되는 하위 호환 파괴다. 신규 플랫폼의 어휘는 항상 **전용 파서**로 분리한다.
>
> 리팩터링 검증: 이관 후 `parse_bool`에 대해 기존 `_truthy`와 동일한 입력·출력을 확인하는 테스트를 추가한다(`"1"`, `"TRUE"`, `"on"`, `"yes"`, `"open"`→**False**, `"unknown"`→`None`, `None`→`None`, `0`→`False`, `1`→`True`).

### 3.5 복합 상태 엔티티 베이스

`custom_components/ws_bridge/entity.py`에 믹스인을 추가한다. Phase 1~3의 복합 플랫폼은 전부 이걸 상속한다.

```python
class WsBridgeCompositeEntity(WsBridgeEntity):
    """상태가 여러 속성으로 구성되는 플랫폼(light/cover/climate 등)의 베이스.

    `__init__` 에서는 `_state` 만 준비한다. `_apply_state()` 는 서브클래스가
    자기 필드를 대입한 뒤 호출하거나, `async_added_to_hass` 에서 반영한다.
    """

    def __init__(self, bridge: WsBridge, defn: dict[str, Any]) -> None:
        super().__init__(bridge, defn)
        self._state: dict[str, Any] = as_dict(bridge.last_state(self._attr_unique_id))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._apply_state()
        self._subscribe_state(self._on_value)

    @callback
    def _on_value(self, value: Any) -> None:
        self._state = as_dict(value)
        self._apply_state()
        safe_write_ha_state(self)

    def _apply_state(self) -> None:
        """서브클래스에서 self._state → self._attr_* 로 반영."""
        raise NotImplementedError
```

> `bridge.handle_state`가 이미 병합된 전체 dict를 보내므로, `_on_value`에서 다시 병합하지 **않는다**. 병합 책임은 bridge 한 곳에만 둔다.

### 3.6 Phase 0 완료 조건

- [ ] `handle_state` 병합 구현 + 스키마에 `dict` 허용
- [ ] `send_command(params=...)` 구현
- [ ] `ws_entity` 스키마에 `features` 추가
- [ ] `helpers.py` 신설 + `binary_sensor.py`/`switch.py` 중복 제거
- [ ] `WsBridgeCompositeEntity` 추가
- [ ] 신규 순수 테스트 4개 이상 (§7.1)
- [ ] 기존 테스트 전부 통과 (`python3 -m pytest tests/`)
- [ ] **이 시점에 사용자 노출 동작 변화는 0이어야 한다.** 순수 확장 커밋.

---

## 4. 플랫폼별 상세 스펙

각 표의 의미:
- **선언 필드** = `ws_bridge/entity`에 추가되는 선택 필드
- **상태 값** = `ws_bridge/state`의 `value`
- **커맨드** = HA→클라이언트 command 이벤트의 `action` / `params`

모든 플랫폼은 기존 공통 필드(`unique_id`, `platform`, `name`, `device`, `device_class`, `icon`, `entity_category`)를 그대로 지원한다.

---

### Phase 1

#### 4.1 `light` → HA `light`

**선언 필드**
| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `supported_color_modes` | `[str]` | `onoff`, `brightness`, `color_temp`, `hs`, `rgb`, `rgbw`, `rgbww`, `white` 중. 없으면 `["onoff"]` |
| `effect_list` | `[str]` | 효과 목록. 있으면 `LightEntityFeature.EFFECT` 자동 설정 |
| `min_color_temp_kelvin` / `max_color_temp_kelvin` | `int` | 색온도 범위 |
| `features` | `[str]` | `transition`, `flash`, `effect` |

**상태 값** (dict, 병합)
`state`(`"on"`/`"off"`/bool), `brightness`(0–255), `color_mode`, `color_temp_kelvin`,
`hs_color`(`[h, s]`), `rgb_color`(`[r,g,b]`), `rgbw_color`(`[r,g,b,w]`), `rgbww_color`(`[r,g,b,cw,ww]`), `effect`

**커맨드**
| action | params |
|:---|:---|
| `turn_on` | `brightness`, `color_temp_kelvin`, `hs_color`, `rgb_color`, `rgbw_color`, `rgbww_color`, `white`, `effect`, `transition`, `flash` (HA가 준 것만 포함) |
| `turn_off` | `transition` |

**구현 노트**
- `_attr_color_mode`는 **클라이언트가 보고한 값을 우선**하고, 없으면 `supported_color_modes`가 1개일 때 그 값으로 추론한다.
- HA는 `supported_color_modes`에 `ColorMode` enum을 요구한다. 문자열→enum 매핑 실패 시 해당 항목만 버린다.
- `async_turn_on(**kwargs)`의 kwargs 키는 HA 상수(`ATTR_BRIGHTNESS` 등)다. **kwargs를 그대로 params로 흘려보내지 말고 화이트리스트로 필터링**한다. tuple 값(`hs_color` 등)은 **반드시 `list()`로 변환**해야 JSON 직렬화된다.
- 낙관적 갱신(optimistic): 기존 `switch`와 동일하게 전송 직후 로컬 상태를 갱신하고 `async_write_ha_state()`.

#### 4.2 `cover` → HA `cover`

**선언 필드**: `features` (`open`, `close`, `stop`, `set_position`, `open_tilt`, `close_tilt`, `stop_tilt`, `set_tilt_position`). 기본값 `OPEN|CLOSE|STOP`.

**상태 값** (dict, 병합): `state`(`"open"`/`"closed"`/`"opening"`/`"closing"`), `position`(0–100), `tilt_position`(0–100)

**커맨드**: `open_cover`, `close_cover`, `stop_cover`, `set_cover_position`(`params.position`), `open_cover_tilt`, `close_cover_tilt`, `stop_cover_tilt`, `set_cover_tilt_position`(`params.tilt_position`)

**구현 노트**
- `is_closed`는 `position`이 있으면 `position == 0`, 없으면 `state == "closed"`로 판단한다. **둘 다 없으면 `None`을 반환**해야 HA가 unknown으로 표시한다(`False`를 반환하면 안 열렸는데 열린 것처럼 보인다).
- HA cover의 position은 **0=완전 닫힘, 100=완전 열림**이다. 프로토콜 문서에 반드시 명시할 것.

#### 4.3 `fan` → HA `fan`

**선언 필드**: `speed_count`(int, 기본 100), `preset_modes`(`[str]`), `features` (`set_speed`, `oscillate`, `direction`, `preset_mode`, `turn_on`, `turn_off`)

**상태 값** (dict, 병합): `state`, `percentage`(0–100), `preset_mode`, `oscillating`(bool), `direction`(`"forward"`/`"reverse"`)

**커맨드**: `turn_on`(`params`: `percentage`, `preset_mode`), `turn_off`, `set_percentage`(`params.percentage`), `set_preset_mode`(`params.preset_mode`), `oscillate`(`params.oscillating`), `set_direction`(`params.direction`)

---

### Phase 2 (스칼라 제어 — 구현 난도 낮음)

#### 4.4 `text` → HA `text`

> ⚠️ **기존 `text_sensor`(읽기 전용, sensor 도메인)와 완전히 다른 플랫폼이다.** 이름이 비슷하므로 `const.py`에서 `PLATFORM_TEXT = "text"`와 `PLATFORM_TEXT_SENSOR = "text_sensor"`를 나란히 두고 주석으로 구분을 명시할 것.

- **선언**: `min`(최소 길이 int, 기본 0), `max`(최대 길이 int, 기본 255), `pattern`(정규식 str), `mode`(`"text"`/`"password"`)
- **상태**: 문자열
- **커맨드**: `set_value` + `value`

> `min`/`max`는 `number`에서는 **값의 범위**, `text`에서는 **길이**다. 같은 필드명을 재사용하되 문서에 반드시 구분해 적을 것.

#### 4.5 `lock` → HA `lock`

- **선언**: `features` (`open`), `code_format`(str|null — HA LockEntity 검증용 **정규식**, 예 `"^\d{4}$"`. `"number"`/`"text"`는 alarm_control_panel 어휘)
- **상태**: `"locked"`, `"unlocked"`, `"locking"`, `"unlocking"`, `"jammed"`, `"opening"`, `"open"` (bool도 허용 — `true`=locked)
- **커맨드**: `lock`, `unlock`, `open` (`params.code`가 있으면 포함)
- **주의**: `code`는 **절대 로그에 남기지 말 것.**

#### 4.6 `date` / `time` / `datetime` → HA `date` / `time` / `datetime`

- **선언**: 추가 필드 없음
- **상태**: ISO 8601 문자열 (`"2026-08-13"` / `"07:30:00"` / `"2026-08-13T07:30:00+09:00"`)
- **커맨드**: `set_value` + `value` (동일 ISO 형식 문자열)
- **구현 노트**: `homeassistant.util.dt`의 `parse_date` / `parse_datetime`을 쓴다(이미 `sensor.py`에서 사용 중인 패턴). `time`은 `datetime.time.fromisoformat`. **파싱 실패 시 예외를 던지지 말고 `None`을 반환**한다. `datetime`이 tz-naive면 **`dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)`** 로 로컬 tz를 붙인다 — `dt_util.as_local()`은 naive를 UTC로 간주하므로 **쓰지 말 것**(서울 게이트웨이가 `"2026-08-13T07:30:00"`을 보내면 16:30으로 밀린다). (`sensor.py` timestamp에도 같은 구식 패턴이 남아 있을 수 있으나 별도 이슈.)

#### 4.7 `event` → HA `event`

- **선언**: `event_types`(`[str]`, **필수·비어 있으면 거절**), `device_class`(`button`/`motion`/`doorbell`)
- **상태**: 문자열(event_type) 또는 dict `{"event_type": "...", "attributes": {...}}`
- **커맨드**: 없음(읽기 전용)
- **구현 노트 — 중요**
  - `event`는 **상태를 갖지 않는다.** `bridge.last_state()`로 복원하면 **안 된다.** HA 재시작 시 마지막 이벤트가 새 이벤트로 재발화되면 자동화가 오작동한다.
  - `_on_value`에서 `self._trigger_event(event_type, attributes)` 후 `async_write_ha_state()`를 호출한다.
  - `event_types`에 없는 값이 오면 **무시하고 경고 로그**만 남긴다(HA가 예외를 던진다).
  - `handle_state`가 `_states`에 저장해 디스크에 남는 것은 무해하나, 엔티티 생성 시 초기값으로 쓰지 않는다.
  - **`handle_state`의 dict 얕은 병합을 `event`만 건너뛴다.** 병합하면 이전 `attributes`가 다음 이벤트로 샌다.

#### 4.8 `valve` → HA `valve`

- **선언**: `features` (`open`, `close`, `stop`, `set_position`), `reports_position`(bool, 기본 `true`)
- **상태** (dict): `state`(`"open"`/`"closed"`/`"opening"`/`"closing"`), `position`(0–100)
- **커맨드**: `open_valve`, `close_valve`, `stop_valve`, `set_valve_position`(`params.position`)
- **구현 노트**: `ValveEntity`는 `reports_position`이 `False`면 `is_closed`를, `True`면 `current_valve_position`을 요구한다. **둘을 섞으면 HA가 에러를 낸다.** 선언값에 따라 분기할 것. `features` 생략 시 기본값은 `reports_position`이 `true`면 SET_POSITION 포함, `false`면 제외. `reports_position=false`인데 `set_position`이 features에 있으면 무시한다.

---

### Phase 3 (복합 상태 + 다중 액션)

#### 4.9 `climate` → HA `climate`

**선언 필드**: `hvac_modes`(`[str]`, 필수 — `off`,`heat`,`cool`,`heat_cool`,`auto`,`dry`,`fan_only`), `fan_modes`, `swing_modes`, `preset_modes`, `min_temp`, `max_temp`, `target_temp_step`, `min_humidity`, `max_humidity`, `temperature_unit`(`"C"`/`"F"`, 기본 HA 시스템 단위), `features`(`target_temperature`, `target_temperature_range`, `target_humidity`, `fan_mode`, `preset_mode`, `swing_mode`, `turn_on`, `turn_off`)

**상태 값** (dict, 병합): `hvac_mode`, `hvac_action`(`heating`/`cooling`/`idle`/`off`), `current_temperature`, `target_temperature`, `target_temp_low`, `target_temp_high`, `current_humidity`, `target_humidity`, `fan_mode`, `swing_mode`, `preset_mode`

**커맨드**: `set_hvac_mode`(`params.hvac_mode`), `set_temperature`(`params`: `temperature` 또는 `target_temp_low`+`target_temp_high`), `set_fan_mode`, `set_swing_mode`, `set_preset_mode`, `set_humidity`, `turn_on`, `turn_off`

**구현 노트**: `hvac_modes`의 문자열은 `HVACMode` enum으로 변환해야 한다. 매핑 실패 항목은 버리고, 결과가 비면 `[HVACMode.OFF]`로 대체(빈 리스트면 HA가 엔티티를 거부한다).

#### 4.10 `humidifier` → HA `humidifier`

- **선언**: `device_class`(`humidifier`/`dehumidifier`), `min_humidity`, `max_humidity`, `available_modes`(`[str]`), `features`(`modes`)
- **상태** (dict): `state`(bool), `current_humidity`, `target_humidity`, `mode`, `action`
- **커맨드**: `turn_on`, `turn_off`, `set_humidity`(`params.humidity`), `set_mode`(`params.mode`)

#### 4.11 `water_heater` → HA `water_heater`

- **선언**: `operation_list`(`[str]`), `min_temp`, `max_temp`, `features`(`target_temperature`, `operation_mode`, `away_mode`, `on_off`)
- **상태** (dict): `state`(현재 operation), `current_temperature`, `target_temperature`, `away_mode`(bool)
- **커맨드**: `set_temperature`(`params.temperature`), `set_operation_mode`(`params.operation_mode`), `set_away_mode`(`params.away_mode`), `turn_on`, `turn_off`

#### 4.12 `siren` → HA `siren`

- **선언**: `available_tones`(`[str]`), `features`(`turn_on`, `turn_off`, `tones`, `duration`, `volume_set`)
- **상태**: bool
- **커맨드**: `turn_on`(`params`: `tone`, `duration`, `volume_level`), `turn_off`

#### 4.13 `alarm_control_panel` → HA `alarm_control_panel`

- **선언**: `code_arm_required`(bool, 기본 `true`), `code_format`(`"number"`/`"text"`/null), `features`(`arm_home`, `arm_away`, `arm_night`, `arm_vacation`, `arm_custom_bypass`, `trigger`)
- **상태**: `"disarmed"`, `"armed_home"`, `"armed_away"`, `"armed_night"`, `"armed_vacation"`, `"armed_custom_bypass"`, `"arming"`, `"pending"`, `"triggered"`
- **커맨드**: `alarm_disarm`, `alarm_arm_home`, `alarm_arm_away`, `alarm_arm_night`, `alarm_arm_vacation`, `alarm_arm_custom_bypass`, `alarm_trigger` — 각각 `params.code`(있을 때만)
- **주의**: `code`는 **절대 로그에 남기지 말 것.** 상태 문자열은 HA의 `AlarmControlPanelState` enum으로 변환한다.

---

### Phase 4

#### 4.14 `update` → HA `update`

- **선언**: `title`, `release_url`, `features`(`install`, `progress`, `backup`, `specific_version`, `release_notes`)
- **상태** (dict): `installed_version`, `latest_version`, `in_progress`(bool), `update_percentage`(0–100), `release_summary`
- **커맨드**: `install`(`params`: `version`, `backup`), `skip`

#### 4.15 `media_player` / `image` / `camera`

**이 3종은 착수 전에 설계 결정이 필요하다. 임의로 진행하지 말고 아래를 먼저 정리한 뒤 이슈로 제안할 것.**

- `media_player`: 상태 필드가 많고(`volume_level`, `media_title`, `media_position`, `source_list`, …) 커맨드도 20여 종이다. **1차는 재생 제어 + 볼륨 + 소스 선택으로 범위를 좁힐 것.**
- `image` / `camera`: 바이너리 전송이 필요하다. HA WebSocket은 JSON 텍스트 프레임이므로 선택지는 **(a) 클라이언트가 접근 가능한 URL만 전달**, **(b) base64 인코딩 전송** 두 가지다. **(a)를 기본으로 권장**한다 — WebSocket 메시지 크기 제한과 메모리 부담 때문. (b)가 필요하면 크기 상한(예: 512KB)을 프로토콜에 못박고 초과 시 `send_error`로 거절할 것.

---

## 5. 플랫폼 1종 추가 시 체크리스트

**모든 플랫폼에 매번 그대로 적용한다.**

1. **`custom_components/ws_bridge/const.py`**
   - `PLATFORM_XXX = "xxx"` 상수 추가
   - `ALL_PLATFORMS` 리스트에 추가 — **누락 시 `ws_entity` 스키마의 `vol.In(ALL_PLATFORMS)`에서 거절된다**
   - `DEFAULT_PLATFORM_ICONS`에 기본 아이콘 추가(`device_class`로 아이콘이 결정되는 플랫폼은 생략 가능)

2. **`custom_components/ws_bridge/__init__.py`**
   - `PLATFORMS` 리스트에 `Platform.XXX` 추가 — **누락 시 `register_platform()`이 호출되지 않아 엔티티가 `_pending` 큐에 영원히 쌓이고 아무 에러도 나지 않는다. 가장 흔한 실수.**

3. **`custom_components/ws_bridge/xxx.py` 신규 작성**
   - `async_setup_entry()`에서 `bridge.register_platform(PLATFORM_XXX, async_add_entities, WsBridgeXxx)`
   - 엔티티 클래스는 `WsBridgeEntity`(스칼라) 또는 `WsBridgeCompositeEntity`(복합) + HA 도메인 엔티티를 다중 상속
   - `__init__`에서 `defn`을 읽어 `_attr_*` 설정 + `bridge.last_state()`로 초기 상태 복원
   - **`_update_platform_defn(defn)` 반드시 구현** — 클라이언트 재연결 시 메타데이터 갱신 경로다 (`entity.py:async_update_defn`에서 호출)
   - 상태가 있으면 `async_added_to_hass()`에서 `self._subscribe_state(self._on_value)`
   - 상태 반영은 `safe_write_ha_state(self)` 사용 (dispatcher는 이벤트 루프 밖일 수 있음)
   - 제어 메서드에서 `self._bridge.send_command(self._attr_unique_id, "<action>", params={...})` 후 낙관적 로컬 갱신 + `self.async_write_ha_state()`

4. **`custom_components/ws_bridge/websocket_api.py`**
   - `ws_entity` 스키마에 신규 선택 필드 추가 (`vol.Optional("...") : vol.Any(..., None)`)
   - **주석으로 어느 플랫폼용인지 명시** (기존 `# select`, `# number` 주석 스타일 유지)

5. **`tests/conftest.py`**
   - `homeassistant.components.xxx`를 mock 모듈 목록에 추가 — **누락 시 테스트가 ImportError로 죽는다**
   - 신규 플랫폼 모듈을 테스트에서 import 한다면 필요한 enum/상수도 mock에 채워야 한다

6. **`tests/test_pure.py`** — §7 참조

7. **문서** — §8 참조

---

## 6. 코딩 규약 (기존 코드에 맞출 것)

- 모든 모듈 첫 줄은 **한국어 docstring**. 기존 파일들의 톤을 그대로 따른다.
- `from __future__ import annotations` 필수.
- 모든 엔티티는 `_attr_should_poll = False`, `_attr_has_entity_name = True` (베이스에서 상속됨).
- import 순서: 표준 라이브러리 → `homeassistant.*` → 상대 import(`.bridge`, `.const`, `.entity`).
- `@callback` 데코레이터는 이벤트 루프에서 동기 실행되는 함수에만.
- 타입 힌트를 쓴다. `dict[str, Any]`, `str | None` 등 PEP 604 문법.
- 인라인 주석은 **꼭 필요한 곳에만** — 기존 코드는 주석 밀도가 낮고 "왜"를 설명하는 주석만 있다. 자명한 코드에 주석을 붙이지 말 것.
- 커밋: `feat(ws_bridge): add light platform` / `refactor(ws_bridge): extract shared value helpers` 형식(Conventional Commits, 기존 이력과 동일).

---

## 7. 테스트 요구사항

`tests/`는 **HA 없이 도는 순수 테스트**다(`conftest.py`가 HA 모듈을 전부 mock). 이 제약을 깨지 말 것 — CI(`.github/workflows/tests.yml`)가 `pytest`와 `voluptuous`만 설치한다.

실행:

```bash
python3 -m pytest tests/ -q   # CI는 python -m pytest tests/
```

### 7.1 Phase 0 필수 테스트

- `handle_state`: dict + dict → 얕은 병합, 이전 키 보존
- `handle_state`: dict → 스칼라, 스칼라 → dict는 교체
- `handle_state`: 병합 **결과 전체**가 dispatcher로 전달되는지
- `send_command`: `params` 전달 / `params=None`이거나 빈 dict면 키 자체가 없어야 함
- `helpers.parse_bool`, `helpers.is_unknown`, `helpers.as_dict` 경계값

### 7.2 플랫폼별 필수 테스트

- `_features()` 매핑 함수: 알려진 이름 → 올바른 플래그 합, **미지의 이름은 무시**, `None`/빈 리스트 → 기본값
- 상태 파서: `"unknown"`, `None`, 타입 불일치 입력에서 예외를 던지지 않고 `None`을 반환하는지
- `cover.is_closed`: position 없음 + state 없음 → `None` (`False` 아님)

### 7.3 정합성 테스트 (Phase 0에서 1회 추가, 이후 자동 방어)

`const.ALL_PLATFORMS`와 `__init__.PLATFORMS`가 어긋나지 않는지 검사하는 테스트를 반드시 추가한다. §5의 1·2번 누락 실수를 CI에서 잡아준다.

```python
def test_all_platforms_are_forwarded():
    """ALL_PLATFORMS의 모든 항목이 HA 플랫폼으로 forward 되는지.
    text_sensor는 sensor 플랫폼에 얹혀 가므로 예외."""
    from custom_components.ws_bridge.const import ALL_PLATFORMS
    from custom_components.ws_bridge import PLATFORMS

    forwarded = {str(p) for p in PLATFORMS}
    expected = set(ALL_PLATFORMS) - {"text_sensor"}
    assert expected <= forwarded
```

> `PLATFORMS`가 mock된 `Platform` enum을 담으므로 `str(p)` 비교가 mock 환경에서 그대로 동작하지 않을 수 있다. 그럴 경우 `conftest.py`에서 `Platform`을 **실제 문자열 값을 갖는 가짜 enum**으로 mock 하도록 고칠 것 — 이 테스트는 포기하지 말고 conftest 쪽을 맞춘다.

---

## 8. 문서 갱신 (각 Phase PR에 포함, 별도 PR 금지)

`docs/PROTOCOL.md`와 `docs/PROTOCOL_ko.md`는 **항상 같은 PR에서 동시에** 수정한다. 내용이 어긋나면 안 된다.

| 위치 | 갱신 내용 |
|:---|:---|
| `PROTOCOL.md` / `PROTOCOL_ko.md` §3.1 `platform` 설명 | 신규 플랫폼 이름 추가 |
| 〃 §3.1 플랫폼 전용 필드 | 신규 선언 필드 + `features` 설명 |
| 〃 §3.1 **Platform Reference 표** | 행 추가 (플랫폼 / 방향 / 상태 값 타입 / 커맨드 action) |
| 〃 §3.2 `value` 설명 | **dict 허용 + 얕은 병합 규칙**을 Phase 0에서 명시 |
| 〃 §4 커맨드 이벤트 | **`params` 필드**를 Phase 0에서 명시 |
| `README.md` / `README_ko.md` 기능 목록 | 제어 가능 컴포넌트 나열 부분(`switch`, `number`, `select`, `button`)에 신규 항목 추가 |
| `custom_components/ws_bridge/manifest.json` | Phase 완료마다 `version` 상향 (Phase 0 → `1.4.0` — main이 이미 `1.3.x`이므로, 이후 마이너 증가) |

`strings.json` / `translations/*.json`은 **신규 진단 엔티티를 추가하지 않는 한 수정 불필요**하다.

---

## 8.5 하위 호환 보증 (필독)

**이 계획 전체에 기존 클라이언트를 끊는 변경은 없다.** 아래 표가 근거이며, 각 Phase PR에서 이 표를 다시 검증한다.

| 변경 | 하위 호환 여부 | 근거 |
|:---|:---:|:---|
| `ws_state`의 `value`에 `dict` 허용 | ✅ | `vol.Any(...)`에 타입을 **추가**만 함. 기존 스칼라는 그대로 통과 |
| `handle_state` 얕은 병합 | ⚠️ | dict 플랫폼 **전부**에 적용. `device_tracker`/`update`는 의도적 브레이킹(부분 객체=교체 → 병합+`null` 삭제). 스칼라 7종은 불변 |
| command 이벤트의 `params` 필드 | ✅ | 기존 7종 플랫폼은 계속 `value`만 쓴다. `params`는 신규 플랫폼 엔티티에만 실린다 — 기존 클라이언트는 자기가 선언한 적 없는 엔티티의 커맨드를 받지 않는다 |
| `ws_entity`의 `features` 필드 | ✅ | `vol.Optional`. 안 보내면 각 플랫폼 기본값 |
| `ALL_PLATFORMS` / `PLATFORMS` 항목 추가 | ✅ | 순수 추가. 기존 7종의 등록 경로 불변 |
| `helpers.py`로 `_truthy` 이관 | ✅ | **§3.4의 "목록 확장 금지" 조건 하에서만.** 문자열 목록을 건드리면 즉시 파괴적 변경이 된다 |
| `WsBridgeCompositeEntity` 추가 | ✅ | 신규 클래스. 기존 `WsBridgeEntity` 상속 계층 불변 |
| `manifest.json` 버전 상향 | ✅ | HA 통합 버전은 클라이언트 프로토콜과 무관 |
| `STORAGE_VERSION` | ✅ | **1로 유지한다. 올리지 말 것** — 마이그레이션 함수가 없어서 올리면 기존 상태 저장소를 읽지 못한다 |

**프로토콜 계약 — 아래는 어떤 Phase에서도 변경 금지:**

- `ws_bridge/connect` / `entity` / `state` / `availability` / `remove`의 **기존 필드 이름·타입·필수 여부**
- 기존 7종 플랫폼의 **상태 값 해석 규칙** (`"unknown"` → None, `"1"/"true"/"on"/"yes"` → ON, timestamp/date 파싱)
- 기존 커맨드 **action 이름과 `value` 전달 방식** (`turn_on`, `turn_off`, `set_value`, `select_option`, `press`)
- `unique_id` 네임스페이스 규칙 (`{gateway_id}__{unique_id}`, `{gateway_id}:{device_id}`) — 바꾸면 **모든 사용자의 기존 엔티티가 새 엔티티로 재생성되어 자동화·이력이 전부 끊긴다**

**단, 다운그레이드(롤백)는 안전하지 않다.** 신규 복합 플랫폼을 쓰다가 통합을 v1.0.0으로 되돌리면, 디스크에 남은 dict 상태를 구버전 `sensor._parse_value`가 그대로 HA 상태로 넘겨 오류가 난다. 릴리스 노트에 **"신규 플랫폼 사용 후 롤백 시 해당 엔티티를 삭제할 것"**을 명시한다. (업그레이드 방향은 문제없다.)

---

## 9. 함정 목록 (실제로 밟기 쉬운 것들)

1. **`__init__.py`의 `PLATFORMS` 누락** → 엔티티가 `_pending`에 무한 적재. 로그도 에러도 없음. 가장 흔함.
2. **`ALL_PLATFORMS` 누락** → `ws_entity`가 `vol.In` 검증에서 거절. 클라이언트는 `invalid_format` 에러만 받는다.
3. **`_update_platform_defn` 미구현** → 클라이언트 재연결 시 메타데이터(옵션 목록, 범위 등)가 갱신되지 않음. `entity.py:async_update_defn`은 `hasattr` 체크로 조용히 건너뛴다.
4. **JSON 직렬화 불가 값**을 `_states`에 저장 → `Store.async_save()`가 실패. 색상 tuple은 반드시 `list()`.
5. **`event` 플랫폼에서 `last_state()` 복원** → HA 재시작 시 유령 이벤트 발화, 자동화 오작동.
6. **`cover.is_closed`가 `False`를 기본 반환** → 상태 미확인인데 "열림"으로 표시.
7. **`tests/conftest.py`에 신규 HA 컴포넌트 mock 누락** → CI ImportError.
8. **`params`와 `value` 혼용** → 클라이언트 파서가 복잡해진다. 액션별로 하나만 쓴다.
9. **`text` vs `text_sensor` 혼동** → 서로 다른 플랫폼. `min`/`max`의 의미도 다르다(길이 vs 값 범위).
10. **`hvac_modes` / `supported_color_modes`가 빈 리스트** → HA가 엔티티 등록을 거부. 매핑 실패 시 안전한 기본값으로 대체할 것.
11. **`send_command`의 `if value is not None`** → `value=False`(예: `oscillate` 끄기)를 보내면 `False is not None`이라 통과한다. 문제없지만, `params` 쪽은 `if params:`라서 **빈 dict가 누락된다.** 의도된 동작이니 빈 params를 보내야 하는 액션을 만들지 말 것.
12. **하위 호환** — 기존 7종 플랫폼의 프로토콜/동작은 **절대 변경 금지**. 이미 배포된 클라이언트(v1.0.0)가 그대로 동작해야 한다. 모든 변경은 선택 필드 추가로만.

---

## 10. Phase 완료 조건 (DoD)

각 Phase PR은 아래를 전부 만족해야 머지한다.

- [ ] `python -m pytest tests/ -q` 전체 통과
- [ ] §5 체크리스트 7항목 모두 수행
- [ ] `PROTOCOL.md` + `PROTOCOL_ko.md` 동시 갱신, 두 문서 내용 일치
- [ ] `README.md` + `README_ko.md` 기능 목록 갱신
- [ ] `manifest.json` 버전 상향
- [ ] **§8.5 하위 호환 보증 표를 항목별로 재검증** — 기존 7종 플랫폼의 필드·상태 해석·action 이름·unique_id 규칙 무변경
- [ ] 신규 플랫폼별 예제 JSON(선언 1개 + 상태 1개 + 커맨드 1개)이 PROTOCOL 문서에 포함
- [ ] PR 설명에 "이 Phase에서 추가된 프로토콜 표면" 요약 명시

---

## 11. 권장 착수 순서 요약

```
Phase 0  코어 확장          ← 여기서 시작. 단독 PR.
   ↓
Phase 1  light / cover / fan
   ↓
Phase 2  text / lock / date / time / datetime / event / valve
   ↓
Phase 3  climate / humidifier / water_heater / siren / alarm_control_panel
   ↓
Phase 4  update / media_player / image / camera   ← §4.15 설계 결정 먼저
   ↓
Phase 5  보류 (수요 확인 후)
```
