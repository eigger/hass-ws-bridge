# 공통 규칙 적용 체크리스트

이 파일은 ws_bridge의 적용 점검표입니다. 예외는 [STANDARDS.md](STANDARDS.md#예외)에 기록했습니다. [사용법과 판정 기준](https://github.com/eigger/hass-repo-standards/blob/ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4/docs/checklist.md)을 읽고, 아래 규칙은 `STANDARDS.md`에 기록한 표준 커밋에서 확인합니다. 태그·릴리스 대신 `main`의 검토 커밋을 기준으로 하며, 위 사용법 링크의 `main`은 채택 시 검토한 커밋 SHA로 바꿉니다.

## 검토 대상

| 항목 | 값 |
|---|---|
| 통합 리포 / 실제 기본 브랜치 | eigger/hass-ws-bridge / main |
| domain / 구현 경로 | ws_bridge / custom_components/ws_bridge |
| 검토 대상 통합 커밋 / 채택 PR | main 1b7826c 위의 feat/real-ha-tests / 후속 PR(번호는 생성 후 기록) |
| 검토한 표준 전체 커밋 SHA | ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4 |
| 검토일 / 조율 담당 | 2026-10-18 / 메인 에이전트 |
| 구현 서브 에이전트 / 독립 리뷰·검증 서브 에이전트 | Opus 구현 에이전트 / 별도 Opus 리뷰 에이전트 |
| 원격 CI(PR #52) | Tests(lint, Python 3.14 unit)·Validate(hacs, hassfest) 4개 SUCCESS |
| 중앙 현황표 반영일 / 기록 | 2026-10-18 / [커밋 645184b](https://github.com/eigger/hass-repo-standards/commit/645184b) |
| 변경 전 지원 최소 HA / 근거 파일 | 2026.9.0 / hacs.json |
| 유지·변경할 지원 최소 / 변경 시 실제 비호환 근거·명시적 승인 | 2026.9.0 유지, 변경 없음 |
| current 테스트 HA / 호환 Python·플러그인 | HA 2026.10.2 / Python 3.14.5 / plugin 0.13.373 |
| 최소 테스트 HA / 호환 Python·플러그인 | HA 2026.9.0 / Python 3.14.5 / plugin 0.13.363 |
| profile / 테스트 경로 | integration / ha, tests/components/ws_bridge/ |
| 이전 검토 기록 | 최초 검토 |
| 채택 판정 | PR #52(표준·CI) + 후속 PR(실제 HA 테스트·문서) 적용. 남은 작업은 아래 표 |

상태: `TODO` = 미확인·미충족, `PASS` = 근거로 확인, `EXCEPTION` = 적용 대상의 기록된 예외, `N/A` = 적용 조건에 해당 없음. `TODO`를 해당 없음으로 처리하지 않습니다. 묶은 규칙의 결과가 다르면 행을 나눕니다. 권장 항목은 별도로 표시했으며 미채택 이유를 기록합니다.

## 채택·구조·사용자 데이터

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| GOV-01, GOV-02 | `STANDARDS.md`에 표준 SHA·profile·실제 기본 브랜치·예외 기록, workflow/action은 검토 SHA로 고정 | PASS | STANDARDS.md(SHA·profile·브랜치·예외), tests.yml/validate.yml이 `@ba9f3fa…` 전체 SHA로 고정 |
| GOV-03 | 새 표준 채택 변경의 영향·이관 방법과 명시적 채택 PR 확인. 규칙 자체를 변경하면 공통 CHANGELOG 기록 | PASS | 이 PR이 명시적 채택 PR. 규칙 리포가 아니므로 공통 CHANGELOG 변경 없음 |
| GOV-04 | 중앙 표에 작업 시작·단계 변경·종료 상태, 담당·적용 내용·검증/리뷰 근거·남은 작업 갱신, 타 리포 기록 보존 | PASS | 중앙 표 자기 행 갱신: [커밋 645184b](https://github.com/eigger/hass-repo-standards/commit/645184b) (다른 행 변경 없음) |
| GOV-05 | 구현과 독립 리뷰·검증을 별도 서브 에이전트에게 위임, 지적 수정·재검증 및 결과 취합 | EXCEPTION | PR #52는 메인 에이전트가 구현(사후 Opus 리뷰), 이번 PR은 Opus 구현 서브 에이전트 + 별도 Opus 리뷰어가 수행하고 지적 수정·재검증함. PR #52분 예외는 [STANDARDS.md 예외](STANDARDS.md#예외) |
| HA-01, HA-13 | `custom_components/<domain>/`와 domain 일치, 필요한 모듈·공개 API·생명주기는 Core 대응 구조 | PASS | `custom_components/ws_bridge/`가 manifest domain `ws_bridge`와 일치. 라이프사이클 상세 검토는 HA-05 행 |
| HA-02 | manifest 필드·정렬·동작 선언 확인, 공식 품질 등급 자가 표기 없음 | PASS | manifest 필드 확인: domain·name·codeowners·config_flow·dependencies·documentation·iot_class·issue_tracker·requirements·version, 품질 등급 자가 표기 없음 |
| HA-03 (권장) | 공통 상수·설정·갱신·플랫폼 역할 및 프로토콜 경계에 맞게 모듈 구성 | PASS | const/entity/bridge/websocket_api/플랫폼 모듈 분리 구조 유지, 변경 없음 |
| HA-04, HA-08 | UI 설정·중복·안정적 식별 및 기능별 options/reauth/reconfigure, entity 의미·registry 영향 확인 | PASS | config_flow: 단일 인스턴스 unique_id=DOMAIN, 중복 abort 테스트(test_config_flow). 저장 자격증명이 없어 options/reauth/reconfigure는 해당 없음 |
| HA-01, HA-04, HA-08, REL-01, REL-03 | domain·unique ID·entry schema·상태/통계 계약 변경 시 migration 테스트와 사용자 조치 안내 | N/A | 이번 PR은 domain·unique ID·entry schema를 변경하지 않음(이 후속 PR은 테스트·문서·CI만 변경, custom_components 변경 없음) |
| HA-05, HA-06 | setup 실패 구분, unload/reload·부분 실패의 task/listener/연결 정리, async·timeout·취소 처리 | TODO | test_init: setup/unload/reload·플랫폼/저장 정리는 PASS. unload 시 클라이언트 소켓 종료는 `test_unload_closes_client_connections`로 검증(비공개 `WebSocketHandler._cancel` 사용, HA 2026.9.0/2026.10.2 모두 확인). 미충족: 부분 setup 실패 정리 미검증 |
| HA-07 | 중복 polling·property I/O 방지, push 보존, unavailable/unknown·실패 후 복구 | PASS | should_poll=False push 구조, unavailable/disconnect 복구·keep_last 테스트 |
| HA-11, HA-12 | 번역·action/schema 일치, 로그/diagnostics/fixture 비식별화와 제공 시 redaction 테스트 | PASS | strings/translations(en, ko) 존재. diagnostics는 제공하지 않아 redaction 해당 없음, 테스트 fixture에 실제 토큰 없음 |

## 실제 HA 테스트·호환성·의존성

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| TEST-08 | `tests/components/<domain>/`에 구현과 대응하는 테스트·domain fixture 배치, discovery·CI 경로 일치 | PASS | tests/components/ws_bridge/ 배치, pyproject testpaths·CI pytest-args 일치 |
| TEST-02, TEST-03, DEP-07 | 실제 HA·호환 플러그인과 `hass`/`enable_custom_integrations` fixture 사용, HA core stub/복사본/`--no-deps`로 대체하지 않음 | PASS | 실제 homeassistant 2026.10.2/2026.9.0 + pytest-homeassistant-custom-component, `enable_custom_integrations`, sys.modules mock 제거 |
| TEST-09 | 실제 loader·config entry manager로 setup/플랫폼 로딩, HA 상태·registry·service/action으로 결과 검증 | PASS | hass.config_entries.async_setup/flow, hass.states·registry·service로 검증 |
| TEST-01, TEST-06, TEST-07 | 구현 기능별 성공·실패·중복·migration·unload·복구 회귀 검증, 외부 통신 경계만 mock, skip 사유 | PASS | 기존 69개 동작을 실제 HA 테스트로 이식(총 179+5 xfail). mock은 camera HTTP 경계만. 이식하지 않은 항목은 내부 필드 단언뿐(가시 효과로 대체) |
| TEST-04, HACS-01 | 변경 전 지원 최소·current·각 Python/플러그인 분리, 선언한 정확한 최소 검증, 상향 시 비호환 근거·명시적 승인 확인 | PASS | 지원 최소 2026.9.0 유지, 별도 minimum-ha job(HA 2026.9.0 / plugin 0.13.363)과 current(2026.10.2) 분리 |
| TEST-05, HA-10, DEP-02, DEP-05 | imagespec·blesession 등 최소/현재 라이브러리 별도 환경, 실제 HA 테스트·정확한 설치값·API 경계 검증 | N/A | manifest requirements가 비어 있어 최소/현재 라이브러리 환경 대상 없음 |
| DEP-01, DEP-06 | Python runtime은 manifest requirements, HA domain은 dependencies/after_dependencies, 테스트·린트 requirements는 별도 | PASS | manifest `requirements: []`, `dependencies: [websocket_api]`; requirements_test.txt·requirements_lint.txt 분리 |
| DEP-07, CI-06 | 실제 사용하는 HA 구성요소의 requirements·필수 재귀 의존성·선택 로딩 경로 설치, resolver·`pip check` 통과 | PASS | ha-components로 전달 플랫폼 requirements(camera → PyTurboJPEG 1.8.3) 설치, `pip check` 양 환경 정상 |
| DEP-02, DEP-03, DEP-08 | 의존성 추가/변경의 버전·extras·marker·선언 위치·지원 플랫폼·라이선스 검토, 실제 HA 테스트와 문서 갱신 | N/A | 이번 변경에 런타임 의존성 추가·변경 없음(테스트 requirements만 신규 고정) |

독립 리뷰는 변경 전후 지원 최소와 current를 비교하고, 봇 PR이 과거 최소 requirements·constraints까지 갱신하거나 expected-ha-version·Python을 누락하지 않았는지 확인합니다. 최신 테스트 실패는 호환 수정 대상으로 처리합니다.

환경마다 아래 행을 복사합니다. 최소 HA와 최소 라이브러리 검증을 혼동하지 않고, marker가 활성인 환경에서 대상 패키지 설치값을 확인합니다. 실행하지 않은 조합은 `TODO` 또는 근거가 있는 `EXCEPTION`으로 남깁니다.

| 검증 축 / 상태 | 통합 커밋 | Python / HA / 플러그인 실제 버전 | 대상 패키지 실제 버전·extras·marker | 명령·테스트 결과·pip check / CI run·job | skip·제외·미검증 범위 |
|---|---|---|---|---|---|
| 현재 환경 / PASS | feat/real-ha-tests 작업 트리 | Python 3.14.5 / HA 2026.10.2 / pytest-homeassistant-custom-component 0.13.373 | PyTurboJPEG 1.8.3(camera) | `pytest tests/components/ws_bridge/`: 179 passed, 5 xfailed; `pip check` 정상 | 5 xfail(strict)=알려진 버그 |
| 정확한 최소 HA 2026.9.0 / PASS | feat/real-ha-tests 작업 트리 | Python 3.14.5 / HA 2026.9.0 / plugin 0.13.363 | PyTurboJPEG 1.8.3 | 179 passed, 5 xfailed; `pip check` 정상 | 5 xfail(strict) |
| 정확한 최소 라이브러리 / N/A | — | — | requirements 없음 | — | 대상 package 없음 |

## HACS·CI·의존성 업데이트

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| HACS-01, HACS-02 | 루트 README/LICENSE/hacs.json, 검증한 최소 HA, 실제 배포 구조와 필요한 옵션 일치 | PASS | 루트 README.md/LICENSE/hacs.json 존재, hacs.json `homeassistant: 2026.9.0` 변경 없음. HACS 실행은 HACS-03 행 |
| HACS-03, HACS-05 | Default 여부는 목록 근거로 확인, [로컬 brand/icon.png 또는 원격 brands 근거](https://github.com/eigger/hass-repo-standards/blob/main/docs/hacs.md)와 HACS/Hassfest 실제 실행, ignore는 이유·해제 조건 기록 | PASS | `custom_components/ws_bridge/brand/icon.png` 존재. HACS·Hassfest 실제 실행 SUCCESS: [hacs](https://github.com/eigger/hass-ws-bridge/actions/runs/39079552654/job/117533535663), [hassfest](https://github.com/eigger/hass-ws-bridge/actions/runs/39079552654/job/117533535682) |
| HACS-06 (권장) | description·topics·issue 경로·brands 및 사용하는 HACS 필드 지원 확인 | PASS | GitHub 저장소 description·topics(hacs, homeassistant, …)·Issues/Discussions 활성(gh repo view) |
| CI-01, CI-02 | Validate/Python Tests 공통화, 확장 job 유지, PR·실제 기본 브랜치 push·dispatch 및 필요한 schedule | PASS | 공통 python-tests/validate-integration 호출, PR·main push·dispatch, validate는 주간 schedule |
| CI-03, CI-05, CI-08 | 최소 권한·checkout 자격증명 비보존·timeout·concurrency, full SHA·갱신 관리, 비신뢰 입력·secrets 경계 | PASS | permissions contents: read, concurrency 설정, 공통 workflow는 full SHA 고정, dependabot github-actions 활성 |
| CI-04, CI-07, CI-12 | 실패를 숨기지 않는 실제 `ha` 필수 테스트, 버전별 환경·cache·Ruff 설정과 required checks 이름 확인 | PASS | ha 프로필 필수 테스트, current·minimum-ha, Ruff 고정. PR #55 원격 CI SUCCESS: [current ha](https://github.com/eigger/hass-ws-bridge/actions/runs/39098317420/job/117589245571), [minimum-ha ha](https://github.com/eigger/hass-ws-bridge/actions/runs/39098317420/job/117589245634), [lint](https://github.com/eigger/hass-ws-bridge/actions/runs/39098317420/job/117589245766), [hacs](https://github.com/eigger/hass-ws-bridge/actions/runs/39098317417/job/117589245430), [hassfest](https://github.com/eigger/hass-ws-bridge/actions/runs/39098317417/job/117589245612). required checks 설정은 별도 남은 작업 |
| DEP-03, DEP-04, CI-09 | updater의 선택 package·연산자/extras/marker 보존, 안정 버전·major 정책, 실제 기본 브랜치·단일 bot branch·PR만 제안 | EXCEPTION | update_dependencies 미도입 — [STANDARDS.md 예외](STANDARDS.md#예외) |
| CI-09, CI-10, DEP-08 | 변경 tree의 새 하한·실제 HA 검증 후 PR 동기화, 실패 시 중단·변경 없음 시 기존 PR 정리, 후속 required checks 충족 방식 확인 | EXCEPTION | 위와 동일 — [STANDARDS.md 예외](STANDARDS.md#예외) |

## README·Bluetooth·유지보수

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| DOC-01, DOC-02, DOC-06 | 영어 README.md·한국어 README.ko.md·상호 링크·기존 내용 보존, 간결한 제목/소개/핵심지원/최소요구/빠른설치·설정/짧은예제/중요제한/문서목록, 상세옵션·긴YAML·참조·개발/실HA테스트·의존성/검증범위를 docs·examples 등으로 보존·분리하고 유효한 링크 제공, 실제 활성 Issues·Discussions 또는 대체 지원 경로·실제 LICENSE 링크 | PASS | README.md/README.ko.md 표준 순서, 상세는 docs/reference*.md, 개발·테스트는 docs/development.md·CONTRIBUTING.md, Issues/Discussions/LICENSE 링크 |
| DOC-03, DOC-04, DOC-05 | 제목 아래 관리 블록, flat-square·순서·실제 조건별 배지, CI 실제 기본 브랜치, 필수 동적 Usage·Analytics 참여 설치 의미·미집계/조회 실패와 0 설치 구분·이전 안내 보존 | PASS | README.md/README.ko.md 관리 블록, `sync_badges.py --check` rc=0, Usage 동적 배지 포함 |
| HA-09, HA-10 | BLE 사용 시 HA Bluetooth API·라이브러리 공개 경계, 지원한 proxy 경로·재연결·취소·서비스 변경 검증 | N/A | 특정 하드웨어/BLE에 묶이지 않는 범용 WebSocket 브리지(HA Bluetooth API 미사용) |
| DOC-07 | blesession/proxy 통합 README의 핵심조건·상세문서 링크, 공통 Bluetooth 설정·추천기기·active 스캔/GATT 차이, 통합별 troubleshooting 또는 공통 링크+모델고유조건·실제진단·민감정보 제거 제보 안내 | N/A | blesession/Bluetooth proxy 통합이 아님(범용 WebSocket 브리지) |
| DOC-07, HA-12 | 기기별 깨우기·인증·타 앱 연결·전송 제약, 실제 검증 경로와 미검증 범위, 공개 문제 로그 비식별화 | N/A | BLE 기기 통합이 아님(README 소개 참조) |
| HACS-04, REL-01, REL-02, REL-03, CI-11 | 통합 릴리스 시 같은 검증 commit/tag·manifest 버전·산출물·권한, 사용자 영향·지원 변경·제한 안내 | N/A | 이번 PR은 릴리스·태그·버전 변경 없음 |
| REL-04 | 이전/중단 시 README 상단 경로·유지보수 상태·재등록 여부, 자동 이전으로 오인하지 않는 안내 | N/A | 이전·중단 대상 아님 |
| REL-05 (권장) | 의존성/HA API 변경과 기능 변경 분리, 표준 변경은 명시적 채택 PR로 반영 | PASS | 런타임 로직 변경 없음(AST 비교: 포맷 외 bridge/entity/sensor의 동작 보존 조건 결합 3곳만), 표준 채택을 별도 PR로 분리 |

## 예외와 남은 작업

예외 원본은 `STANDARDS.md`입니다.

| 규칙 ID | 예외 위치 / 이유 | 담당자 | 재검토 조건 |
|---|---|---|---|
| CI-09, DEP-03 | [STANDARDS.md 예외](STANDARDS.md#예외) — requirements 없음 | @eigger | requirements 추가 시 |

| 규칙 ID / TODO | 남은 작업 / issue·PR | 담당자 | 완료 근거 |
|---|---|---|---|
| CI-04/12 | required checks(`current / lint`, `current / Python 3.14 / ha / current`, `minimum-ha / lint`, `minimum-ha / Python 3.14 / ha / current`, `validate / hacs`, `validate / hassfest`) 저장소 설정 반영(옛 `unit` 체크 요구가 있으면 제거) | @eigger | branch protection 설정 |
| 제품 결함 | 수정 완료(xfail 5건 해제): ① `_remove_entity_ns`가 registry 항목까지 제거 ② lock 낙관 플래그 상호 배타 ③ unload가 클라이언트 소켓 종료. 남은 항목: update 낙관 in_progress는 HA install wrapper가 즉시 초기화해 보이지 않음(테스트로 문서화) | @eigger | 이 수정 PR |

최종 검토 시 적용 대상 필수 `TODO`는 HA-05/06(부분 setup 실패 정리 검증)이며 CI 성공만으로 실물 기기 검증을 주장하지 않습니다. 이 통합은 특정 기기에 묶이지 않아 실물 검증 해당 없음입니다.


## 2026-10-22 재검토

이번 검토 대상은 main에서 시작한 로컬 변경이며, 검토 표준은 `0ec31111a81b0ee5702f1d8a17f03616a10a5db6`입니다. 위 2026-10-18 채택 표는 이력으로 보존하며 이번 변경의 검증 결과와 구분합니다.

| 항목 | 상태 | 이번 검토 근거 |
|---|---|---|
| GOV-01, GOV-02 | PASS | 최신 원격 main full SHA 확인 (`0ec31111a81b0ee5702f1d8a17f03616a10a5db6`), STANDARDS.md 기준 SHA 및 workflows의 `standards-ref` 일치 |
| HACS-01, HACS-02 | PASS | 루트 README/LICENSE/hacs.json 존재, 최소 지원 HA 2026.9.0 유지 |
| HACS-03 | PASS | [공식 기본 목록](https://github.com/hacs/default/blob/master/integration)에 `eigger/hass-ws-bridge` 포함 확인 (2026-10-21 [PR #10042](https://github.com/hacs/default/pull/10042) 머지). Default 배지 및 My Home Assistant 바로가기 연결 |
| HA-02 | PASS | 실제 WebSocket 브리지 용도에 맞게 `diy_makers.web_data_connectors`, `hubs_protocols` 카테고리 선정. 공식 Core taxonomy 확인, manifest.json 및 `.hass-standards.json.categories_review`에 기록 |
| DOC-01…DOC-06 | PASS | 중앙 README 템플릿 영역(`header`, `badges`, `installation`, `support`, `related-projects`, `license`) 경계 주석 반영, HACS Default 및 Downloads 배지 적용, `check_integration.py` 검사 통과 |
| TEST-08, TEST-03 | PASS | 26개 플랫폼 1:1 테스트 파일 구성 (`test_alarm_control_panel.py`, `test_camera.py`, `test_date.py`, `test_datetime.py`, `test_humidifier.py`, `test_image.py`, `test_siren.py`, `test_time.py`, `test_water_heater.py` 분리 이관), 루트 conftest 중앙 템플릿 일치, 도메인 conftest 마커 추가, 207개 테스트 전량 통과 |
| CI-01, CI-02, CI-03 | PASS | Tests/Validate 워크플로 최신 SHA `0ec31111a81b0ee5702f1d8a17f03616a10a5db6` 고정, `standards` job(중앙 템플릿 적합성 검사) 및 `hassfest-core-ref` 설정 |
| REL-01…REL-03 | N/A | 이번 작업에서 버전·태그·릴리스를 생성하지 않음 |

### 이번 검증 결과

- 로컬 Python 3.14 WSL 테스트: `python3 -m pytest tests/components/ws_bridge/ -q` → 207 passed in 123.07s
- 정적 분석: `python -m ruff check .` → All checks passed!, `python -m ruff format --check .` → 79 files already formatted
- 중앙 통합 검사: `python ..\hass-repo-standards\scripts\check_integration.py . --check` → Exit code 0 (오류 없음)

## 2026-10-23 Downloads 배지 부분 검증

- 기준: 중앙 `b54ac48102d6e326c6929071fdc02ba8fade794e`의 DOC-03/05·배지 생성기와 Validate 형식 검사기만 부분 채택. 대상 시작 SHA `1e2d1e967b32b651b98052693417bdbe39165e9b`. 기존 전체 채택 결과·예외는 유지하며 이번 변경으로 전체 재채택 완료를 주장하지 않습니다.
- 계획/자체 리뷰: 양언어 관리 블록을 같은 중앙 렌더러로 생성, 잘못된 HACS 데이터 조회 배지를 Downloads로 교체, 집계 의미와 소스 파일 설치 제외를 양언어로 명시. GOV-02에 따라 중앙 호출 pin과 standards-ref를 같은 SHA로 맞춥니다. 이전 기준과 새 기준의 공용 workflow/action 파일은 동일하며 실행 설정·지원 최소·ZIP 배포 설정을 보존합니다.
- 검증 명령·결과와 최종 head SHA·원격 CI 링크는 이 PR 본문에 기록합니다. 문서·배지·형식 검사기 pin만 변경하므로 로컬 HA 환경을 재구축하지 않으며 실제 기기·HA UI·사용자 다운로드 집계는 미검증입니다.
- 실행 결과: WSL Ubuntu Python 3.14.4/PyYAML 6.0.3/packaging 26.0에서 중앙 `scripts/sync_badges.py <repo> --check`, `scripts/check_integration.py <repo>` 및 actionlint 1.7.12의 전체 caller workflow 검사 PASS. Windows Git의 `git diff --check` PASS. 양언어 배지 외 기존 본문은 집계 설명의 정정·추가만 허용하고 보존했습니다.
- 초기 검사 실패 기록: 단일 기준 SHA 계약에 맞지 않는 검사기 pin만의 갱신은 GOV-02에서 거부되어 모든 중앙 pin을 동일 SHA로 정합화했습니다. Windows 중앙 템플릿 CRLF 비교는 실패하여 LF 중앙 snapshot의 Linux 검사로 재검증했습니다. WSL Git은 Windows worktree gitdir 경로를 해석하지 못해 diff 검사를 실패했고 동일 변경의 Windows Git 검사로 대체했습니다. 실패를 PASS로 소급하지 않습니다.

## 2026-10-23 ZIP 릴리스 적용 검증

- 기준 `0c1592977591ecba077a4666d699840062711201` / 대상 시작 `5d10a9a024d27e946632290010a0c23e0c06f36e`. HACS-04/CI-11 부분 갱신이며 기존 전체 채택 이력·예외는 유지합니다.
- 계획: hacs.json에 zip_release:true, filename:ws_bridge.zip을 추가하고 중앙 release.yml을 같은 SHA로 생성합니다. 기존 caller는 중앙 pin/standards-ref만 변경합니다. 지원 최소·통합 버전·의존성·구현·README 본문을 보존합니다.
- 검증: 중앙 생성기/정적 검사·actionlint·실제 packager로 추적된 통합 파일의 ZIP 루트·manifest/번역/brand 등 런타임 자료 포함과 저장소 메타데이터 제외를 확인합니다. CLI 검증 명령·실제 버전·최종 head SHA·ZIP 결과·독립 리뷰·원격 CI 링크는 이 PR 본문에서 한 번 기록합니다.
- 중앙 실행 로직은 독립 zip_release_review 리뷰에서 지적 수정 후 추가 지적 없음. 대상 caller/메타데이터/ZIP도 별도 독립 리뷰합니다. 로컬 HA 환경 재구축·새 릴리스 발행·asset 업로드·기기 설치는 수행하지 않으며 미실행을 PASS로 기록하지 않습니다. immutable-releases는 enabled:false로 확인했습니다.


## 2026-10-25 중앙 검사기 부분 갱신 검증

- 검토한 중앙 SHA: `1863343638014adb8a4001afc8fddc1a27dc500f`; 적용 시작 커밋: `fd39ea8f8d04cd436453eee3281d205667102386`.
- 범위: 중앙 pin·standards-ref·검토 기준 기록 정합화. HA 구현·요구 버전은 유지합니다.
- 로컬: Python 3.14.5 / PyYAML 6.0.3, `python scripts/check_integration.py <target>` (검토한 중앙 source에서 실행): PASS.
- actionlint: PASS. PR CI·독립 리뷰 결과는 PR 링크와 check 결과를 확인합니다. 이 로컬 결과만으로 전체 채택 완료를 주장하지 않습니다.
- 독립 리뷰: 별도 review_checker_rollout 담당자가 19개 리포의 workflow 69개·기존 job 100개를 구조 비교했습니다. 새 CI 회귀 지적 없음. 기존 job ID·입력·권한·지원 최소와 통합 코드 보존 및 새 standards job의 중앙 템플릿 일치 확인. 실행 변경 없는 이 기록 추가 전 작업 트리를 검토했습니다.


### 2026-10-25 Standards workflow 분리 검증

- 분리 시작 커밋: `8e3854c56e8f86d9f6a2e8b2ea8fe7737cc275b6`; 검토 중앙 소스 `ca740d88b32fa5dcbc94c41fce2908450c76ed50` (중앙 PR #24). Validate는 HACS/Hassfest job을 그대로 유지하며 중앙 job만 standards.yml로 이동하고 표시 이름을 Standards로 변경합니다.
- 독립 리뷰: root 구현의 19개 리포에 대해 별도 fix_scale_atflee_ci 담당자가 Validate job 19개와 이동 job 19개의 YAML 정의를 비교했습니다. 파일 이동·표시 이름 외 실제 검사 단계·이벤트·권한·timeout·입력 변경 없음. 중앙 위치 인식 변경은 root가 별도 독립 리뷰했습니다.
- 로컬: 새 중앙 검사기·actionlint·diff 검사 PASS. 중앙 전체232개·관련38개 회귀 테스트와 양 배치19개 동등성 검사 PASS. 모든 대상 기본 브랜치의 branch protection·rulesets 조회에서 필수 검사 이름 설정이 없어 이름 변경으로 인한 대기 충돌 없음. 원격 CI는 이 PR의 최신 head에서 확인합니다.
- 검사 기준을 추가하거나 완화하지 않았으며 기존 inline 배치도 같은 기준으로 지원합니다. 실제 runtime·지원 최소·의존성은 이 파일 분리에서 변경하지 않습니다.
