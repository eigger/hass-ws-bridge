# 개발·테스트 안내

ws_bridge는 HACS 커스텀 통합이며 Home Assistant Core에 포함된 공식 통합이 아닙니다. 구조는 Core 컴포넌트 규칙을 따릅니다. 공통 규칙은 [hass-repo-standards](https://github.com/eigger/hass-repo-standards/tree/ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4) 참조 커밋 기준이며 적용 현황은 [STANDARDS.md](../STANDARDS.md), [ADOPTION_CHECKLIST.md](../ADOPTION_CHECKLIST.md)에 있습니다.

## 테스트 구조

실제 Home Assistant와 [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)를 사용합니다. HA 모듈을 가짜로 대체하지 않으며, `hass`·`MockConfigEntry`·`hass_ws_client` fixture로 config entry 등록·setup·unload와 WebSocket 프로토콜을 실제 경로로 실행하고 `hass.states`와 entity/device registry로 검증합니다. 외부 통신 mock은 camera 정지 이미지 HTTP 요청뿐입니다.

```text
tests/components/ws_bridge/
├── conftest.py            # init_integration, BridgeClient(hass_ws_client), registry helper
├── test_config_flow.py    # flow manager: 성공·중복
├── test_init.py           # setup / unload / reload / 저장
├── test_websocket_api.py  # connect·entity·state·availability·remove·sync
└── test_<platform>.py     # 플랫폼별 상태·command
```

## 실행

Python 3.14가 필요합니다(HA 2026.9.0 / 2026.10.2 모두 Python ≥ 3.14.2).

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt -r requirements_lint.txt PyTurboJPEG==1.8.3   # camera 플랫폼 의존성(CI는 ha-components로 설치)
.venv/bin/python -m pytest tests/components/ws_bridge/ -v
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
```

최소 지원 HA 검증은 별도 환경에서 `requirements_test_min.txt`로 같은 명령을 실행합니다.

## 검증 환경

| 환경 | Python | Home Assistant | 플러그인 | 결과 (2026-10-18) |
|---|---|---|---|---|
| current | 3.14.5 | 2026.10.2 | pytest-homeassistant-custom-component 0.13.373 | 179 passed, 5 xfailed |
| 최소 (hacs.json) | 3.14.5 | 2026.9.0 | pytest-homeassistant-custom-component 0.13.363 | 179 passed, 5 xfailed |

CI(`tests.yml`)는 위 두 환경을 `current`, `minimum-ha` job으로 실행합니다. 최소 지원 버전은 테스트 도구 최신화만으로 올리지 않으며, 올릴 때는 비호환 근거와 명시적 승인을 기록합니다. 5개 xfail(strict)은 알려진 실제 버그를 표시합니다(`tests/components/ws_bridge/` 내 xfail 사유 참조).

## 의존성

런타임 requirements는 `manifest.json`(현재 없음), HA 도메인 의존성은 `dependencies`(`websocket_api`)에 둡니다. 테스트·린트 requirements는 `requirements_test.txt`, `requirements_test_min.txt`, `requirements_lint.txt`로 분리하며 Dependabot은 최소 환경 파일을 제외합니다.
