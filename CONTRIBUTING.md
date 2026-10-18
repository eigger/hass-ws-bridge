# Contributing

- 버그는 [Issues](https://github.com/eigger/hass-ws-bridge/issues), 질문·제안은 [Discussions](https://github.com/eigger/hass-ws-bridge/discussions)로 알려 주세요.
- 개발 환경, 테스트 실행 방법, 검증 환경 표는 [docs/development.md](docs/development.md)를 참고하세요.
- PR 전에 `ruff check .`, `ruff format --check .`, `pytest tests/components/ws_bridge/`를 실행해 주세요(camera 의존성 PyTurboJPEG 설치 포함, 자세한 내용은 개발 안내 참고). 표준 변경은 기능 변경과 분리해 별도 PR로 보내 주세요.
