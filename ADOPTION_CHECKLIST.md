# 공통 규칙 적용 체크리스트

이 파일은 ws_bridge의 **부분 이관** 점검표입니다. 대부분 항목은 TODO이며 실제 HA 테스트 전환은 완료되지 않았습니다. 예외는 [STANDARDS.md](STANDARDS.md#예외)에 기록했습니다. [사용법과 판정 기준](https://github.com/eigger/hass-repo-standards/blob/ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4/docs/checklist.md)을 읽고, 아래 규칙은 `STANDARDS.md`에 기록한 표준 커밋에서 확인합니다. 태그·릴리스 대신 `main`의 검토 커밋을 기준으로 하며, 위 사용법 링크의 `main`은 채택 시 검토한 커밋 SHA로 바꿉니다.

## 검토 대상

| 항목 | 값 |
|---|---|
| 통합 리포 / 실제 기본 브랜치 | eigger/hass-ws-bridge / main |
| domain / 구현 경로 | ws_bridge / custom_components/ws_bridge |
| 검토 대상 통합 커밋 / 채택 PR | origin/main d22912f 위의 chore/adopt-hass-repo-standards / 이 PR |
| 검토한 표준 전체 커밋 SHA | ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4 |
| 검토일 / 조율 담당 | 2026-10-18 / 메인 에이전트 |
| 구현 서브 에이전트 / 독립 리뷰·검증 서브 에이전트 | 없음(GOV-05 예외) / Opus 서브 에이전트(agent a5591016d6844dc22) |
| 중앙 현황표 반영일 / 기록 | 미반영 — 중앙 리포 PR 필요(GOV-04 TODO) |
| 변경 전 지원 최소 HA / 근거 파일 | 2026.9.0 / hacs.json |
| 유지·변경할 지원 최소 / 변경 시 실제 비호환 근거·명시적 승인 | 2026.9.0 유지, 변경 없음 |
| current 테스트 HA / 호환 Python·플러그인 | HA 미설치 unit 환경 / Python 3.14, pytest 8.4.2, voluptuous 0.15.2 (로컬+CI 설정, 원격 CI 미확인) |
| 최소 테스트 HA / 호환 Python·플러그인 | 미검증(예외) — 실제 HA 테스트 도입 후 2026.9.0 별도 job |
| profile / 테스트 경로 | integration / unit (mock 기반), tests/ — 실제 HA 전환은 예외 |
| 이전 검토 기록 | 최초 검토 |
| 채택 판정 | 부분 이관 — CI/린트/배지/표준 기록만 적용. 실제 HA 테스트 이관 TODO |

상태: `TODO` = 미확인·미충족, `PASS` = 근거로 확인, `EXCEPTION` = 적용 대상의 기록된 예외, `N/A` = 적용 조건에 해당 없음. `TODO`를 해당 없음으로 처리하지 않습니다. 묶은 규칙의 결과가 다르면 행을 나눕니다. 권장 항목은 별도로 표시했으며 미채택 이유를 기록합니다.

## 채택·구조·사용자 데이터

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| GOV-01, GOV-02 | `STANDARDS.md`에 표준 SHA·profile·실제 기본 브랜치·예외 기록, workflow/action은 검토 SHA로 고정 | PASS | STANDARDS.md(SHA·profile·브랜치·예외), tests.yml/validate.yml이 `@ba9f3fa…` 전체 SHA로 고정 |
| GOV-03 | 새 표준 채택 변경의 영향·이관 방법과 명시적 채택 PR 확인. 규칙 자체를 변경하면 공통 CHANGELOG 기록 | PASS | 이 PR이 명시적 채택 PR. 규칙 리포가 아니므로 공통 CHANGELOG 변경 없음 |
| GOV-04 | 중앙 표에 작업 시작·단계 변경·종료 상태, 담당·적용 내용·검증/리뷰 근거·남은 작업 갱신, 타 리포 기록 보존 | TODO | 중앙 adoption-status.md는 별도 리포 PR 필요, 이번 PR에서 미반영 |
| GOV-05 | 구현과 독립 리뷰·검증을 별도 서브 에이전트에게 위임, 지적 수정·재검증 및 결과 취합 | EXCEPTION | 구현을 메인 에이전트가 수행, 독립 리뷰만 Opus 서브 에이전트(리뷰 지적 수정·재검증 완료). [STANDARDS.md 예외](STANDARDS.md#예외) |
| HA-01, HA-13 | `custom_components/<domain>/`와 domain 일치, 필요한 모듈·공개 API·생명주기는 Core 대응 구조 | PASS | `custom_components/ws_bridge/`가 manifest domain `ws_bridge`와 일치. 라이프사이클 상세 검토는 HA-05 행 |
| HA-02 | manifest 필드·정렬·동작 선언 확인, 공식 품질 등급 자가 표기 없음 | TODO | manifest 필드 정렬·선언 상세 미검토 |
| HA-03 (권장) | 공통 상수·설정·갱신·플랫폼 역할 및 프로토콜 경계에 맞게 모듈 구성 | TODO | 구조 변경 없음, 미검토(권장) |
| HA-04, HA-08 | UI 설정·중복·안정적 식별 및 기능별 options/reauth/reconfigure, entity 의미·registry 영향 확인 | TODO | config_flow의 options/reauth/reconfigure 지원 여부 미검토(config_flow는 단일 인스턴스 unique_id=DOMAIN의 user step + subentry 사용, options/reauth/reconfigure 없음(저장 자격증명 없음 추정이나 미확정)) |
| HA-01, HA-04, HA-08, REL-01, REL-03 | domain·unique ID·entry schema·상태/통계 계약 변경 시 migration 테스트와 사용자 조치 안내 | N/A | 이번 PR은 domain·unique ID·entry schema를 변경하지 않음(포맷·린트·CI·문서만) |
| HA-05, HA-06 | setup 실패 구분, unload/reload·부분 실패의 task/listener/연결 정리, async·timeout·취소 처리 | TODO | `__init__.py` 확인: unload에서 플랫폼 unload→snapshot 정리→flush_save→bridge.unload(). 부분 setup 실패·ConfigEntryNotReady 처리와 취소는 미검토 |
| HA-07 | 중복 polling·property I/O 방지, push 보존, unavailable/unknown·실패 후 복구 | TODO | `entity.py:27` `_attr_should_poll=False`(push 구조). 복구 동작은 미검토 |
| HA-11, HA-12 | 번역·action/schema 일치, 로그/diagnostics/fixture 비식별화와 제공 시 redaction 테스트 | TODO | strings/translations(en, ko) 존재. action 일치·diagnostics redaction 미검토 |

## 실제 HA 테스트·호환성·의존성

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| TEST-08 | `tests/components/<domain>/`에 구현과 대응하는 테스트·domain fixture 배치, discovery·CI 경로 일치 | EXCEPTION | [STANDARDS.md 예외](STANDARDS.md#예외) — tests/ 평면 구조 유지 |
| TEST-02, TEST-03, DEP-07 | 실제 HA·호환 플러그인과 `hass`/`enable_custom_integrations` fixture 사용, HA core stub/복사본/`--no-deps`로 대체하지 않음 | EXCEPTION | [STANDARDS.md 예외](STANDARDS.md#예외) — conftest HA mock 사용 |
| TEST-09 | 실제 loader·config entry manager로 setup/플랫폼 로딩, HA 상태·registry·service/action으로 결과 검증 | EXCEPTION | [STANDARDS.md 예외](STANDARDS.md#예외) |
| TEST-01, TEST-06, TEST-07 | 구현 기능별 성공·실패·중복·migration·unload·복구 회귀 검증, 외부 통신 경계만 mock, skip 사유 | TODO | 기존 69개 회귀 테스트 보존·통과(로컬, CI는 원격 확인 전). 기능별 커버리지 평가는 미수행 |
| TEST-04, HACS-01 | 변경 전 지원 최소·current·각 Python/플러그인 분리, 선언한 정확한 최소 검증, 상향 시 비호환 근거·명시적 승인 확인 | EXCEPTION | 지원 최소 2026.9.0 유지(hacs.json). 정확한 최소 HA 검증 env 없음 — [STANDARDS.md 예외](STANDARDS.md#예외) |
| TEST-05, HA-10, DEP-02, DEP-05 | imagespec·blesession 등 최소/현재 라이브러리 별도 환경, 실제 HA 테스트·정확한 설치값·API 경계 검증 | N/A | manifest requirements가 비어 있어 최소/현재 라이브러리 환경 대상 없음 |
| DEP-01, DEP-06 | Python runtime은 manifest requirements, HA domain은 dependencies/after_dependencies, 테스트·린트 requirements는 별도 | PASS | manifest `requirements: []`, `dependencies: [websocket_api]`; requirements_test.txt·requirements_lint.txt 분리 |
| DEP-07, CI-06 | 실제 사용하는 HA 구성요소의 requirements·필수 재귀 의존성·선택 로딩 경로 설치, resolver·`pip check` 통과 | EXCEPTION | 실제 HA 미설치 unit 프로필. [STANDARDS.md 예외](STANDARDS.md#예외) |
| DEP-02, DEP-03, DEP-08 | 의존성 추가/변경의 버전·extras·marker·선언 위치·지원 플랫폼·라이선스 검토, 실제 HA 테스트와 문서 갱신 | N/A | 이번 변경에 런타임 의존성 추가·변경 없음(테스트 requirements만 신규 고정) |

독립 리뷰는 변경 전후 지원 최소와 current를 비교하고, 봇 PR이 과거 최소 requirements·constraints까지 갱신하거나 expected-ha-version·Python을 누락하지 않았는지 확인합니다. 최신 테스트 실패는 호환 수정 대상으로 처리합니다.

환경마다 아래 행을 복사합니다. 최소 HA와 최소 라이브러리 검증을 혼동하지 않고, marker가 활성인 환경에서 대상 패키지 설치값을 확인합니다. 실행하지 않은 조합은 `TODO` 또는 근거가 있는 `EXCEPTION`으로 남깁니다.

| 검증 축 / 상태 | 통합 커밋 | Python / HA / 플러그인 실제 버전 | 대상 패키지 실제 버전·extras·marker | 명령·테스트 결과·pip check / CI run·job | skip·제외·미검증 범위 |
|---|---|---|---|---|---|
| 현재 환경(unit, HA 미설치) / PASS | 작업 트리(a7640f6+변경, origin/main d22912f 기준) | Python 3.14 venv / HA 없음 / 플러그인 없음 | pytest 8.4.2, voluptuous 0.15.2 | 리뷰어 venv: `pip check` 정상, `pytest tests` 69 passed. 원격 CI는 PR 후 확인 | 실제 HA 기반 검증 아님 |
| 정확한 최소 HA 2026.9.0 / EXCEPTION | — | — | — | 미실행 | 실제 HA 테스트 도입 전까지 예외 |
| 정확한 최소 라이브러리 / N/A | — | — | requirements 없음 | — | 대상 package 없음 |

## HACS·CI·의존성 업데이트

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| HACS-01, HACS-02 | 루트 README/LICENSE/hacs.json, 검증한 최소 HA, 실제 배포 구조와 필요한 옵션 일치 | PASS | 루트 README.md/LICENSE/hacs.json 존재, hacs.json `homeassistant: 2026.9.0` 변경 없음. HACS 실행은 HACS-03 행 |
| HACS-03, HACS-05 | Default 여부는 목록 근거로 확인, [로컬 brand/icon.png 또는 원격 brands 근거](https://github.com/eigger/hass-repo-standards/blob/main/docs/hacs.md)와 HACS/Hassfest 실제 실행, ignore는 이유·해제 조건 기록 | TODO | `custom_components/ws_bridge/brand/icon.png` 존재. HACS/Hassfest 실제 실행 결과는 PR CI 확인 후 기록 |
| HACS-06 (권장) | description·topics·issue 경로·brands 및 사용하는 HACS 필드 지원 확인 | PASS | GitHub 저장소 description·topics(hacs, homeassistant, …)·Issues/Discussions 활성(gh repo view) |
| CI-01, CI-02 | Validate/Python Tests 공통화, 확장 job 유지, PR·실제 기본 브랜치 push·dispatch 및 필요한 schedule | PASS | 공통 python-tests/validate-integration 호출, PR·main push·dispatch, validate는 주간 schedule |
| CI-03, CI-05, CI-08 | 최소 권한·checkout 자격증명 비보존·timeout·concurrency, full SHA·갱신 관리, 비신뢰 입력·secrets 경계 | PASS | permissions contents: read, concurrency 설정, 공통 workflow는 full SHA 고정, dependabot github-actions 활성 |
| CI-04, CI-07, CI-12 | 실패를 숨기지 않는 실제 `ha` 필수 테스트, 버전별 환경·cache·Ruff 설정과 required checks 이름 확인 | EXCEPTION | unit 프로필로 실행(실패 숨김 없음). 실제 `ha` 필수는 [STANDARDS.md 예외](STANDARDS.md#예외). required checks 이름은 원격 CI 통과 후 설정 필요(미반영) |
| DEP-03, DEP-04, CI-09 | updater의 선택 package·연산자/extras/marker 보존, 안정 버전·major 정책, 실제 기본 브랜치·단일 bot branch·PR만 제안 | EXCEPTION | update_dependencies 미도입 — [STANDARDS.md 예외](STANDARDS.md#예외) |
| CI-09, CI-10, DEP-08 | 변경 tree의 새 하한·실제 HA 검증 후 PR 동기화, 실패 시 중단·변경 없음 시 기존 PR 정리, 후속 required checks 충족 방식 확인 | EXCEPTION | 위와 동일 — [STANDARDS.md 예외](STANDARDS.md#예외) |

## README·Bluetooth·유지보수

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| DOC-01, DOC-02, DOC-06 | 영어 README.md·한국어 README.ko.md·상호 링크·기존 내용 보존, 간결한 제목/소개/핵심지원/최소요구/빠른설치·설정/짧은예제/중요제한/문서목록, 상세옵션·긴YAML·참조·개발/실HA테스트·의존성/검증범위를 docs·examples 등으로 보존·분리하고 유효한 링크 제공, 실제 활성 Issues·Discussions 또는 대체 지원 경로·실제 LICENSE 링크 | EXCEPTION | 한국어 README가 README_ko.md(DOC-02 예외), README 분량 정리·CONTRIBUTING·docs/development 미작성(DOC-01/06). Issues/LICENSE 링크는 유효. [STANDARDS.md 예외](STANDARDS.md#예외) |
| DOC-03, DOC-04, DOC-05 | 제목 아래 관리 블록, flat-square·순서·실제 조건별 배지, CI 실제 기본 브랜치, 필수 동적 Usage·Analytics 참여 설치 의미·미집계/조회 실패와 0 설치 구분·이전 안내 보존 | PASS | README.md/README_ko.md 관리 블록, `sync_badges.py --check` rc=0, Usage 동적 배지 포함 |
| HA-09, HA-10 | BLE 사용 시 HA Bluetooth API·라이브러리 공개 경계, 지원한 proxy 경로·재연결·취소·서비스 변경 검증 | N/A | 특정 하드웨어/BLE에 묶이지 않는 범용 WebSocket 브리지(HA Bluetooth API 미사용) |
| DOC-07 | blesession/proxy 통합 README의 핵심조건·상세문서 링크, 공통 Bluetooth 설정·추천기기·active 스캔/GATT 차이, 통합별 troubleshooting 또는 공통 링크+모델고유조건·실제진단·민감정보 제거 제보 안내 | N/A | blesession/Bluetooth proxy 통합이 아님(범용 WebSocket 브리지) |
| DOC-07, HA-12 | 기기별 깨우기·인증·타 앱 연결·전송 제약, 실제 검증 경로와 미검증 범위, 공개 문제 로그 비식별화 | N/A | BLE 기기 통합이 아님(README 소개 참조) |
| HACS-04, REL-01, REL-02, REL-03, CI-11 | 통합 릴리스 시 같은 검증 commit/tag·manifest 버전·산출물·권한, 사용자 영향·지원 변경·제한 안내 | N/A | 이번 PR은 릴리스·태그·버전 변경 없음 |
| REL-04 | 이전/중단 시 README 상단 경로·유지보수 상태·재등록 여부, 자동 이전으로 오인하지 않는 안내 | N/A | 이전·중단 대상 아님 |
| REL-05 (권장) | 의존성/HA API 변경과 기능 변경 분리, 표준 변경은 명시적 채택 PR로 반영 | PASS | 런타임 로직 변경 없음(AST 비교: 포맷 외 bridge/entity/sensor의 동작 보존 조건 결합 3곳만), 표준 채택을 별도 PR로 분리 |

## 예외와 남은 작업

예외 원본은 `STANDARDS.md`입니다. 아래에 해당 위치를 연결하고, 예외가 실제 없음을 확인한 뒤에만 `없음`으로 바꿉니다.

| 규칙 ID | 예외 위치 / 이유 | 담당자 | 재검토 조건 |
|---|---|---|---|
| TEST-08/02/03/09/04, DEP-07, CI-04/06/07/09/10/12, DOC-01/02/06, GOV-05 | [STANDARDS.md 예외](STANDARDS.md#예외) | @eigger | 실제 HA 테스트 이관 PR 시 |

| 규칙 ID / TODO | 남은 작업 / issue·PR | 담당자 | 완료 근거 |
|---|---|---|---|
| GOV-04 | 중앙 adoption-status.md 자기 리포 행 갱신(중앙 리포 PR) | @eigger | 중앙 PR 링크 |
| HACS-03/05, CI | 이 PR의 원격 CI(HACS·Hassfest·Tests) 결과 확인 후 기록, required checks 설정 | @eigger | CI run 링크 |
| HA-02/03/04/05/06/07/08/11/12, TEST-01/06/07 | 코드 수준 검토(manifest, options/reauth, unload·복구, diagnostics 등) | @eigger | 후속 PR |
| TEST-08/02/03/09/04 | 실제 HA 기반 테스트 이관 + 최소 HA 2026.9.0 job | @eigger | tests/components/ws_bridge/ |
| DOC-01/02/06 | README.ko.md 이름 변경, README 분량 정리, CONTRIBUTING/docs 작성 | @eigger | 문서 PR |

최종 검토 시 적용 대상 필수 `TODO`와 `EXCEPTION`, 이유가 있는 `N/A`, 권장 미채택을 구분해 적습니다. CI 성공만으로 실물 기기 검증을 주장하지 않습니다. 실물 검증을 수행했다면 모델·펌웨어·어댑터/proxy·연결 경로와 결과를 별도로 기록합니다.

중앙 보고는 [적용 현황표](https://github.com/eigger/hass-repo-standards/blob/main/docs/adoption-status.md)의 자기 리포 행에 반영합니다. 리뷰 지적·수정·재검증 결과와 중앙 갱신 실패 사유가 있으면 남은 작업에도 기록합니다.
