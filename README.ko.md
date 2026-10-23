<!-- hass-standards:header:start -->
# WebSocket Bridge (`ws_bridge`) for Home Assistant

외부 WebSocket 클라이언트에서 기기와 엔티티를 동적으로 등록하는 Home Assistant 통합구성요소입니다.

[English](README.md) | **한국어**

<!-- hass-standards:badges:start -->
[![Release](https://img.shields.io/github/v/release/eigger/hass-ws-bridge?style=flat)](https://github.com/eigger/hass-ws-bridge/releases)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5?style=flat)](#설치)
[![Home Assistant minimum](https://img.shields.io/badge/HA-%E2%89%A5%202026.9.0-41BDF5?style=flat)](hacs.json)
[![Tests](https://img.shields.io/github/actions/workflow/status/eigger/hass-ws-bridge/tests.yml?branch=main&style=flat&label=Tests)](https://github.com/eigger/hass-ws-bridge/actions/workflows/tests.yml)
[![Validate](https://img.shields.io/github/actions/workflow/status/eigger/hass-ws-bridge/validate.yml?branch=main&style=flat&label=Validate)](https://github.com/eigger/hass-ws-bridge/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/eigger/hass-ws-bridge?style=flat)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/eigger/hass-ws-bridge/total?style=flat&color=41BDF5&label=Downloads)](https://github.com/eigger/hass-ws-bridge/releases)
<!-- hass-standards:badges:end -->
<!-- hass-standards:header:end -->

Downloads 배지는 모든 GitHub 릴리스의 첨부 asset 다운로드 합계이며 활성 설치 수가 아닙니다. HACS 소스 파일 설치는 집계되지 않으며 ZIP 릴리스 배포는 사용하지 않습니다.

인증된 **WebSocket 클라이언트**가 엔티티를 동적으로 생성·갱신할 수 있게 해 주는 범용 Home Assistant 통합구성요소입니다. BLE, Zigbee 등 특정 하드웨어나 프로토콜에 묶이지 않으며, 정의된 통신 규약만 따르면 바로 사용할 수 있습니다.

## 주요 기능

- **추가 브로커/포트 불필요**: Home Assistant 표준 WebSocket API(`/api/websocket`)와 장기 액세스 토큰만 사용합니다. MQTT 브로커를 따로 띄우거나 TCP 포트를 추가로 열 필요가 없습니다.
- **동적 엔티티 생성**: 클라이언트가 WebSocket으로 JSON 메시지로 엔티티를 선언하면 Home Assistant에 즉시 생성됩니다.
- **클라이언트 기반 장치 그룹화**: 각 클라이언트(`gateway_id`)는 HA에 게이트웨이(부모) 디바이스로 등록되고, 해당 클라이언트가 선언한 장치·엔티티는 `via_device`로 하위에 묶입니다.
- **양방향 제어 라우팅**: `switch`, `number`, `select`, `button`, `update`, `light`, `cover`, `fan`, `text`, `lock`, `date`, `time`, `datetime`, `valve`, `climate`, `humidifier`, `water_heater`, `siren`, `alarm_control_panel`, `media_player`, `camera` 제어 이벤트(`command`)를 HA UI·자동화에서 발생시키면, 해당 엔티티를 등록한 클라이언트에만 전달합니다.
- **연결 상태 추적(LWT)**: 클라이언트 WebSocket 연결이 끊기면, 그 클라이언트가 등록한 하위 장치·엔티티가 자동으로 `unavailable`이 됩니다.
- **연결 클라이언트 수 진단 센서**: 현재 WebSocket으로 연결된 클라이언트(`gateway_id`) 수를 실시간으로 표시하는 진단 센서를 제공합니다.

---

## 요구 사항

- Home Assistant 2026.9.0 이상 (`hacs.json` 기준). HACS 커스텀 통합이며 Home Assistant Core에 포함된 공식 통합이 아닙니다.
- 인증된 WebSocket 클라이언트와 장기 액세스 토큰.

---

## 설치

<!-- hass-standards:installation:start -->
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eigger&repository=hass-ws-bridge)
<!-- hass-standards:installation:end -->

### 방법 1: HACS (권장)
1. Home Assistant 사이드바에서 **HACS**로 이동합니다.
2. 기본 통합 스토어에서 **WebSocket Bridge** (`ws_bridge`)를 검색하거나 위의 My Home Assistant 바로가기 버튼을 누릅니다.
3. **다운로드**를 클릭한 후 **Home Assistant를 재시작**합니다.

### 방법 2: 수동 설치
1. 이 리포지토리에서 `custom_components/ws_bridge` 폴더를 받습니다.
2. Home Assistant 설정 디렉터리의 `custom_components/` 아래에 복사합니다.
   * 대상 경로: `config/custom_components/ws_bridge/`
3. **Home Assistant를 재시작**합니다.

---

## 설정

1. **HA에 통합구성요소 추가**
   * **설정** → **디바이스 및 서비스** → **통합구성요소 추가**
   * **WebSocket Bridge**를 검색해 추가합니다. (추가 UI 설정 없이 바로 초기화됩니다.)
2. **게이트웨이 사용자 허용**
   * 통합구성요소의 **구성**(옵션) 화면에서 게이트웨이가 토큰을 사용할 수 있는 사용자를 선택합니다.
   * 선택 사항입니다. 목록이 비어 있으면 **관리자** 사용자의 토큰만 허용됩니다. 사용자를 선택하면 선택한 사용자만 허용됩니다(관리자도 목록에 포함해야 함). 게이트웨이 전용 비관리자 계정을 쓸 때 사용하세요.
3. **장기 액세스 토큰 발급**
   * 허용된 사용자로 로그인한 뒤 사용자 프로필 페이지 하단의 **토큰 생성**을 눌러 토큰을 복사합니다.
4. **클라이언트 설정**
   * 클라이언트 앱/장치에 Home Assistant WebSocket URL(예: `ws://192.168.1.100:8123/api/websocket`)과 발급한 토큰을 입력합니다.

---

## 대표 예제

```json
// auth_ok 이후 ws_bridge/connect → 엔티티 선언 → 상태 전송 순서
{"id": 3, "type": "ws_bridge/state", "states": [{"unique_id": "temp_1", "value": 25.4}]}
```

엔티티 선언·명령 이벤트 등 전체 메시지는 아래 문서를 참고하세요.

---

## 중요 제한

- 아직 수신하지 않는 플랫폼: `vacuum` / `lawn_mower` / `remote` / `todo` (계획 중, [프로토콜 §6](docs/PROTOCOL_ko.md)).
- 클라이언트 연결이 끊기면 기본적으로 해당 클라이언트의 엔티티가 `unavailable`이 됩니다(게이트웨이별 `keep_last_state_on_disconnect` 사용 시 제외).
- `auth` → `ws_bridge/connect` → `ws_bridge/entity` 순서를 반드시 지키세요. `auth_ok` 전의 메시지는 거부됩니다.

---

## 문서

- [아키텍처·지원 플랫폼·프로토콜 요약](docs/reference_ko.md)
- [프로토콜 규격 (한국어)](docs/PROTOCOL_ko.md) / [English](docs/PROTOCOL.md)
- [개발·테스트 안내 (한국어)](docs/development.md)

---

<!-- hass-standards:support:start -->
## 지원

- [Issues](https://github.com/eigger/hass-ws-bridge/issues): 버그를 신고하거나 기능을 요청하세요.
- [Discussions](https://github.com/eigger/hass-ws-bridge/discussions): 질문하고 사용 경험을 공유하세요.
<!-- hass-standards:support:end -->

<!-- hass-standards:related-projects:start -->
<!-- hass-standards:related-projects:end -->

<!-- hass-standards:license:start -->
## 라이선스

[MIT License](LICENSE) 라이선스로 배포됩니다.
<!-- hass-standards:license:end -->
