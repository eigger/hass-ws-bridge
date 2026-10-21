# 적용한 공통 규칙

- 표준: https://github.com/eigger/hass-repo-standards/tree/0ec31111a81b0ee5702f1d8a17f03616a10a5db6
- 참조 커밋 SHA: 0ec31111a81b0ee5702f1d8a17f03616a10a5db6
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
