# 적용한 공통 규칙

- 표준: https://github.com/eigger/hass-repo-standards/tree/ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4
- 참조 커밋 SHA: ba9f3fad8b635c163fb44a4e91b1833cc4ab47b4
- 채택일: 2026-10-18 (부분 이관, 채택 PR 전)
- profile: integration / unit (부분 이관 — 실제 HA fixture 전환 전까지)
- 적용 점검표: [ADOPTION_CHECKLIST.md](ADOPTION_CHECKLIST.md)
- 중앙 현황표: https://github.com/eigger/hass-repo-standards/blob/main/docs/adoption-status.md
- 조율 / 구현 / 독립 리뷰·검증 담당: 메인 에이전트 / 메인 에이전트(GOV-05 예외 참조) / 별도 Opus 서브 에이전트
- 중앙 현황 갱신일: 미등록 (중앙 리포 접근·PR 별도, 남은 작업)
- 실제 기본 브랜치: main
- 테스트 경로: tests/ (목표: tests/components/ws_bridge/)
- 변경 전 지원 최소 HA / 선언 근거: 2026.9.0 / hacs.json
- 적용 후 지원 최소 HA: 2026.9.0 (변경 없음)
- current HA 테스트 환경: 미구성 — 현재 CI는 HA 미설치 mock 기반 unit (CI Python 3.14 단일로 축소 — 기존 3.12~3.14 매트릭스에서 변경; pytest 8.4.2, voluptuous 0.15.2)
- 최소 HA 검증 환경: 미검증 (실제 HA 테스트 도입 후 2026.9.0 별도 job 필요)
- 최소 package 검증: 해당 없음 (manifest requirements 비어 있음)

## 예외

| 규칙 ID | 이유 | 담당자 | 재검토 조건 |
|---|---|---|---|
| TEST-08, TEST-02, TEST-03, TEST-09, CI-07, CI-12 (실제 HA fixture·config entry 테스트, tests/components/ws_bridge/) | 기존 69개 테스트가 conftest의 HA mock에 의존. 대규모 재작성이라 별도 PR로 분리 | @eigger | 실제 HA 기반 테스트 이관 PR 착수 시 |
| TEST-04 (최소 HA 2026.9.0 별도 job) | 위 이관에 종속 | @eigger | 실제 HA 테스트 도입 시 |
| CI-09, DEP-03 (update_dependencies workflow) | manifest requirements가 비어 갱신 대상 package 없음. dependabot(actions/pip)만 사용 | @eigger | requirements 추가 시 |
| GOV-05 | 구현을 서브 에이전트에 위임하지 않고 메인 에이전트가 수행; 독립 리뷰만 별도 Opus 서브 에이전트 | @eigger | 후속 이관 PR부터 구현 위임 |
| DOC-02 | 한국어 README가 README_ko.md (표준은 README.ko.md). 이름 변경은 외부 링크 영향이 있어 보류 | @eigger | 다음 문서 정리 PR |
