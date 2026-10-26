# 적용한 공통 규칙

- 표준: https://github.com/eigger/hass-repo-standards/tree/v1.1.2
- 참조 커밋 SHA: df9798509d9228247ec32efb313ec7b687b5b152
- Standards release: v1.1.2
- Resolved standards SHA: df9798509d9228247ec32efb313ec7b687b5b152
- 재검토일: 2026-10-22 (로컬 작업 트리)
- 이전 기준 SHA: `ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4`
- 채택일: 2026-10-18 (PR #52 표준/CI, 후속 PR #55 실제 HA 테스트 이관, PR #56 버그 수정)
- profile: integration / ha (실제 HA fixture·통합 로딩)
- 적용 점검표: [ADOPTION_CHECKLIST.md](ADOPTION_CHECKLIST.md)
- 중앙 현황표: https://github.com/eigger/hass-repo-standards/blob/main/docs/adoption-status.md
- 조율 / 구현 / 검증: Antigravity
- 중앙 현황 갱신일: 2026-10-22
- 실제 기본 브랜치: main
- 테스트 경로: tests/components/ws_bridge/
- 변경 전 지원 최소 HA / 선언 근거: 2026.9.0 / hacs.json
- 적용 후 지원 최소 HA: 2026.9.0 (변경 없음)
- current HA 테스트 환경: Python 3.14 / HA 2026.10.2 / pytest-homeassistant-custom-component 0.13.373 (207 passed)
- 최소 HA 검증 환경: Python 3.14 / HA 2026.9.0 / pytest-homeassistant-custom-component 0.13.363 (CI job `minimum-ha`)
- 최소 package 검증: 해당 없음 (manifest requirements 비어 있음)

## 2026-10-22 재검토

- README 공통 영역·HACS 설치 배지·Default 상태·HACS Downloads를 최신 중앙 렌더러로 갱신합니다. 등재 근거: [HACS 공식 integration 목록](https://github.com/hacs/default/blob/master/integration), 2026-10-21 `eigger/hass-ws-bridge` 포함 확인(PR #10042). Default는 Core 통합이라는 뜻이 아닙니다.
- HA-02 제품 분류는 `diy_makers.web_data_connectors`, `hubs_protocols`입니다. 외부 WebSocket 클라이언트에서 기기/엔티티를 동적으로 선언·제어하는 범용 브리지 용도에 따른 분류입니다. 공식 taxonomy는 Core snapshot `ec18d8b25d1ee39aa8b85a72a170e42bee33228c`를 검토했습니다.
- TEST-08 플랫폼 테스트를 Home Assistant Core 표준에 맞춰 단일 파일 단위(26개 플랫폼 1:1)로 정리했습니다 (`test_alarm_control_panel.py`, `test_camera.py`, `test_date.py`, `test_datetime.py`, `test_humidifier.py`, `test_image.py`, `test_siren.py`, `test_time.py`, `test_water_heater.py`).
- Tests 및 Validate 워크플로를 최신 검토 SHA `0ec31111a81b0ee5702f1d8a17f03616a10a5db6`로 갱신하고, 중앙 표준 적합성 검사 job(`standards`) 및 `hassfest-core-ref` 설정을 반영했습니다.
- 지원 최소 HA 2026.9.0은 변경 없이 유지됩니다.

## 예외

| 규칙 ID | 이유 | 담당자 | 재검토 조건 |
|---|---|---|---|
| CI-09, DEP-03 (update_dependencies workflow) | manifest requirements가 비어 갱신 대상 package 없음. dependabot(actions/pip)만 사용 | @eigger | requirements 추가 시 |

README.ko.md 이름 변경·README 분리·실제 HA 테스트·최소 HA job은 이관을 완료해 예외가 아닙니다.

## 2026-10-23 다운로드 배지 부분 갱신

- 배지·DOC-03/05와 Validate 형식 검사기만 중앙 [`b54ac48102d6e326c6929071fdc02ba8fade794e`](https://github.com/eigger/hass-repo-standards/tree/b54ac48102d6e326c6929071fdc02ba8fade794e)를 채택합니다. 이전 기준 SHA `0ec31111a81b0ee5702f1d8a17f03616a10a5db6`의 채택 이력·예외는 보존합니다. 모든 중앙 workflow/action pin과 standards-ref는 GOV-02의 단일 기준 SHA 계약에 맞춰 갱신합니다. 중앙 diff에서 공용 workflow/action 실행 파일은 이전 기준과 동일함을 확인했습니다.
- 대상 기본 브랜치 커밋: `1e2d1e967b32b651b98052693417bdbe39165e9b`. 주 에이전트 직접 구현·자체 리뷰(GOV-05의 배지/생성물 변경 범위), 검증은 [ADOPTION_CHECKLIST.md](ADOPTION_CHECKLIST.md#2026-10-23-downloads-배지-부분-검증)에 기록합니다.
- Downloads는 모든 릴리스 첨부 asset 다운로드 합계입니다. 사용자 지시에 따라 ZIP 배포를 도입하지 않으며 현재 HACS 소스 파일 설치는 이 수치에 집계되지 않습니다. 통합 코드·의존성·지원 최소·기존 설치 안내는 변경하지 않습니다.

## 2026-10-23 ZIP 릴리스 배포

- 기준 중앙 SHA: `0c1592977591ecba077a4666d699840062711201` ([중앙 PR15](https://github.com/eigger/hass-repo-standards/pull/15) 스쿼시 머지). 이전 `b54ac48102d6e326c6929071fdc02ba8fade794e` 채택 이력·예외를 보존하며 HACS-04·CI-11의 ZIP 배포 계약을 추가합니다.
- 대상 시작 SHA: `5d10a9a024d27e946632290010a0c23e0c06f36e`. hacs.json의 zip_release/filename과 중앙 release caller를 함께 적용합니다. archive 파일명은 `ws_bridge.zip`, ZIP 루트는 해당 통합 파일입니다.
- 중앙 workflow/action pin과 standards-ref는 단일 SHA로 정합화합니다. release:published에서 기존 해당 릴리스에 ZIP만 첨부하며 소스 버전·태그·릴리스 발행은 자동 변경하지 않습니다. 기존 asset 덮어쓰기를 거부합니다.
- 기존 지원 최소 HA `2026.9.0`와 통합 버전 `2.0.3` 및 의존성·구현은 보존합니다. 기존 태그의 hacs.json은 소급 수정하지 않으므로 다음 릴리스부터 ZIP 설치로 전환됩니다.
- immutable-releases 설정은 enabled=false/enforced_by_owner=false로 확인했습니다. 업로드 지연·실패 및 기존 asset 복구는 중앙 [릴리스 계약](https://github.com/eigger/hass-repo-standards/blob/0c1592977591ecba077a4666d699840062711201/docs/releases.md#zip-릴리스-첨부)을 따릅니다. 실제 새 릴리스 발행·설치·기기 검증은 이번 작업에 포함하지 않습니다.

## 2026-10-25 중앙 검사기 갱신

- 검토한 중앙 main: `1863343638014adb8a4001afc8fddc1a27dc500f` (git ls-remote 확인). 이전 기본 기준 `0c1592977591ecba077a4666d699840062711201`의 채택 이력은 위 기록을 보존합니다.
- 모든 중앙 workflow/action pin과 reusable workflow의 standards-ref를 같은 검토 SHA로 맞춥니다. HACS-04는 actions/*의 full SHA 고정을 유지하면서 SHA 값 차이를 허용합니다.
- 통합 코드·런타임 의존성·지원 최소·배포 버전은 이번 변경 대상이 아닙니다. 기존 채택 범위를 전체 완료로 바꾸지 않으며 실제 검증 결과와 남은 항목은 ADOPTION_CHECKLIST.md의 같은 날짜 기록을 참조합니다.


### 2026-10-25 Standards 파일·표시 이름 분리

- 기존 Validate의 중앙 검사 job을 `standards.yml`로 옮기고 workflow/job 표시 이름을 `Standards`로 줄였습니다. Validate의 HACS/Hassfest, 검사 항목·통과 기준·실행 단계·조건·권한은 유지합니다.
- 위치 인식과 중앙 명명 안내를 맞춘 검토 소스: `ca740d88b32fa5dcbc94c41fce2908450c76ed50` ([중앙 PR #24](https://github.com/eigger/hass-repo-standards/pull/24), 현재 이 PR의 의존 변경). 이전 기준 `1863343638014adb8a4001afc8fddc1a27dc500f`의 검증 이력은 앞 기록으로 보존합니다. 모든 중앙 pin·standards-ref는 같은 새 검토 소스로 맞춥니다.

## 2026-10-25 중앙 immutable release 참조 전환

- 사용자 요청에 따라 현재 중앙 참조를 immutable `v1.0.0` / resolved SHA `44349ee5621eea5d80e5c427f7a2435d2c2491bb`로 전환했습니다. 중앙 workflow/action caller는 exact release tag를, `standards-ref`는 resolved full SHA를 사용합니다.
- 범위는 중앙 참조·기록 정합화뿐입니다. 기존 지원 최소, 통합 버전, manifest, 런타임 요구사항, 구현, 테스트와 CI의 caller-owned 설정은 보존했습니다.
- 과거 SHA·검증·예외 기록은 역사적 증거로 보존합니다. 이번 변경은 generated reference-only 범위이므로 GOV-05 자체 검토이며 PR CI/병합은 대기 상태입니다.
