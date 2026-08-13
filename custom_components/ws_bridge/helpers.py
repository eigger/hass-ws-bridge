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
