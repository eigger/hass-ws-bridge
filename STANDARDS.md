# 적용한 공통 규칙

- 표준: https://github.com/eigger/hass-repo-standards/tree/ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4
- 참조 커밋 SHA: ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4
- 채택일: 2026-10-18 (PR #52 표준/CI, 후속 PR 실제 HA 테스트 이관)
- profile: integration / ha (실제 HA fixture·통합 로딩)
- 적용 점검표: [ADOPTION_CHECKLIST.md](ADOPTION_CHECKLIST.md)
- 중앙 현황표: https://github.com/eigger/hass-repo-standards/blob/main/docs/adoption-status.md
- 조율 / 구현 / 독립 리뷰·검증 담당: 메인 에이전트 / 구현 서브 에이전트(Opus) / 별도 리뷰 서브 에이전트(Opus)
- 중앙 현황 갱신일: 미등록 (중앙 리포 PR 별도, 남은 작업)
- 실제 기본 브랜치: main
- 테스트 경로: tests/components/ws_bridge/
- 변경 전 지원 최소 HA / 선언 근거: 2026.9.0 / hacs.json
- 적용 후 지원 최소 HA: 2026.9.0 (변경 없음)
- current HA 테스트 환경: Python 3.14.5 / HA 2026.10.2 / pytest-homeassistant-custom-component 0.13.373 (179 passed, 5 xfailed)
- 최소 HA 검증 환경: Python 3.14.5 / HA 2026.9.0 / pytest-homeassistant-custom-component 0.13.363 (179 passed, 5 xfailed)
- 최소 package 검증: 해당 없음 (manifest requirements 비어 있음)

## 예외

| 규칙 ID | 이유 | 담당자 | 재검토 조건 |
|---|---|---|---|
| CI-09, DEP-03 (update_dependencies workflow) | manifest requirements가 비어 갱신 대상 package 없음. dependabot(actions/pip)만 사용 | @eigger | requirements 추가 시 |

README.ko.md 이름 변경·README 분리·실제 HA 테스트·최소 HA job은 이관을 완료해 예외가 아닙니다.
