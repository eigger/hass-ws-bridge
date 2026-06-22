"""Config flow: 범용 브릿지는 설정이 없다. 클라이언트가 HA URL+토큰으로 연결하므로
여기선 통합 인스턴스(단일)만 생성한다."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class WsBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="WebSocket Bridge", data={})
        return self.async_show_form(step_id="user")
